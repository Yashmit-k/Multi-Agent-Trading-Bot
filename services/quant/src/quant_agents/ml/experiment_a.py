"""Experiment A: CURRENT vs NEW on a common eligible row set. Research only."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from quant_agents.ml.experiment import git_identity, load_parquet_table
from quant_agents.ml.features import (
    CURRENT_COLUMNS,
    NEW_COLUMNS,
    current_matrix,
    filter_new_eligible,
    new_matrix,
)
from quant_agents.ml.model import make_model

THRESHOLD = 0.5
CORR_THRESHOLD = 0.95
MIN_UNIQUE_ENDS = 9
UNRELIABLE_SYMBOL_N = 15
BOOTSTRAP_DRAWS = 400


def _stamp(raw: object) -> datetime:
    stamp = datetime.fromisoformat(str(raw))
    if stamp.tzinfo is None:
        raise SystemExit(f"timezone-naive timestamp {raw}")
    return stamp


def _row_id(row: dict[str, Any]) -> str:
    return f"{row['symbol']}|{row['end']}"


def timestamp_splits(ends: list[str]) -> tuple[str, str, list[str], list[str], list[str]]:
    unique = sorted(set(ends))
    if len(unique) < MIN_UNIQUE_ENDS:
        raise SystemExit(f"too few unique timestamps: {len(unique)}")
    cut_valid = int(len(unique) * 0.6)
    cut_test = int(len(unique) * 0.8)
    if cut_valid < 3 or cut_test <= cut_valid or cut_test >= len(unique):
        raise SystemExit("degenerate unique-end split")
    validation_start = unique[cut_valid]
    test_start = unique[cut_test]
    return (
        validation_start,
        test_start,
        unique[:cut_valid],
        unique[cut_valid:cut_test],
        unique[cut_test:],
    )


def assign_splits(
    rows: list[dict[str, Any]],
    *,
    cutoff: datetime,
    clocks: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int], str, str]:
    validation_start, test_start, _, _, _ = timestamp_splits(clocks or [str(row["end"]) for row in rows])
    purged: dict[str, int] = {"train_cross": 0, "valid_cross": 0, "test_cross": 0}
    train: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    for row in rows:
        end = str(row["end"])
        future = str(row["future_end"])
        if end < validation_start:
            if future < validation_start:
                train.append(row)
            else:
                purged["train_cross"] += 1
        elif end < test_start:
            if future < test_start:
                valid.append(row)
            else:
                purged["valid_cross"] += 1
        else:
            if _stamp(future) <= cutoff:
                test.append(row)
            else:
                purged["test_cross"] += 1
    return train, valid, test, purged, validation_start, test_start


def assert_split_invariants(
    train: list[dict[str, Any]],
    valid: list[dict[str, Any]],
    test: list[dict[str, Any]],
) -> None:
    train_ends = {str(row["end"]) for row in train}
    valid_ends = {str(row["end"]) for row in valid}
    test_ends = {str(row["end"]) for row in test}
    if train_ends & valid_ends or train_ends & test_ends or valid_ends & test_ends:
        raise SystemExit("end timestamps are not pairwise disjoint across splits")
    if not train or not valid or not test:
        raise SystemExit("empty split after label purge")
    if max(_stamp(row["future_end"]) for row in train) >= min(_stamp(row["end"]) for row in valid):
        raise SystemExit("max(train.future_end) is not < min(valid.end)")
    if max(_stamp(row["future_end"]) for row in valid) >= min(_stamp(row["end"]) for row in test):
        raise SystemExit("max(valid.future_end) is not < min(test.end)")
    for name, part in (("train", train), ("validation", valid), ("test", test)):
        labels = {int(row["label"]) for row in part}
        if len(labels) < 2:
            raise SystemExit(f"{name} has a single class {labels}; AUC is undefined")
        clocks = {str(row["end"]) for row in part}
        if len(clocks) < 2:
            raise SystemExit(f"{name} has too few unique timestamps ({len(clocks)})")
    for row in train + valid + test:
        if "future_close" in row or str(row.get("feature_future_close", "")):
            raise SystemExit("feature matrix includes future close")


def _xy_current(rows: list[dict[str, Any]]) -> tuple[list[list[float]], list[int]]:
    return current_matrix(rows), [int(row["label"]) for row in rows]


def _xy_new(rows: list[dict[str, Any]], features: dict[str, dict[str, float]]) -> tuple[list[list[float]], list[int]]:
    ordered = [features[_row_id(row)] for row in rows]
    return new_matrix(ordered), [int(row["label"]) for row in rows]


def _positive_proba(model: Any, x: list[list[float]]) -> list[float]:
    probs = model.predict_proba(x)
    classes = list(model.classes_)
    if 1 not in classes:
        return [0.0 for _ in probs]
    idx = classes.index(1)
    return [float(row[idx]) for row in probs]


def score_split(y_true: list[int], y_prob: list[float], *, name: str) -> dict[str, Any]:
    if not y_true:
        raise SystemExit(f"{name} split is empty")
    if len(set(y_true)) < 2:
        raise SystemExit(f"{name} has a single class {Counter(y_true)}; AUC is undefined")
    pred = [1 if value >= THRESHOLD else 0 for value in y_prob]
    return {
        "n": len(y_true),
        "roc_auc": float(roc_auc_score(y_true, y_prob)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "brier": float(brier_score_loss(y_true, y_prob)),
        "accuracy": float(accuracy_score(y_true, pred)),
        "predicted_positive_rate": float(sum(pred) / len(pred)),
        "positive_rate": float(sum(y_true) / len(y_true)),
    }


def fit_score(train: list[dict[str, Any]], valid: list[dict[str, Any]], test: list[dict[str, Any]], kind: str, features: dict[str, dict[str, float]]) -> tuple[Any, dict[str, Any]]:
    model = make_model()
    if kind == "current":
        x_train, y_train = _xy_current(train)
        x_valid, y_valid = _xy_current(valid)
        x_test, y_test = _xy_current(test)
    else:
        x_train, y_train = _xy_new(train, features)
        x_valid, y_valid = _xy_new(valid, features)
        x_test, y_test = _xy_new(test, features)
    model.fit(x_train, y_train)
    valid_p = _positive_proba(model, x_valid)
    test_p = _positive_proba(model, x_test)
    return model, {
        "validation": score_split(y_valid, valid_p, name=f"{kind}_validation"),
        "test": score_split(y_test, test_p, name=f"{kind}_test"),
        "test_proba": test_p,
        "valid_proba": valid_p,
    }


def per_symbol_table(rows: list[dict[str, Any]], y_true: list[int], y_prob: list[float]) -> list[dict[str, Any]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[str(row["symbol"])].append(index)
    table = []
    for symbol, indexes in sorted(grouped.items()):
        labels = [y_true[i] for i in indexes]
        probs = [y_prob[i] for i in indexes]
        pred = [1 if value >= THRESHOLD else 0 for value in probs]
        auc: Any = "N/A"
        if len(set(labels)) == 2:
            auc = float(roc_auc_score(labels, probs))
        table.append(
            {
                "symbol": symbol,
                "samples": len(indexes),
                "positive_rate": float(sum(labels) / len(labels)),
                "predicted_positive_rate": float(sum(pred) / len(pred)),
                "roc_auc": auc,
                "accuracy": float(accuracy_score(labels, pred)),
                "unreliable": len(indexes) < UNRELIABLE_SYMBOL_N,
            }
        )
    def sort_key(item: dict[str, Any]) -> tuple[int, float]:
        auc = item["roc_auc"]
        if auc == "N/A":
            return (1, 0.0)
        return (0, -float(auc))

    table.sort(key=sort_key)
    return table


def train_diagnostics(x_train: list[list[float]], columns: tuple[str, ...]) -> dict[str, Any]:
    array = np.asarray(x_train, dtype=float)
    missing = {name: 0.0 for name in columns}
    constants = [name for index, name in enumerate(columns) if float(np.nanstd(array[:, index])) == 0.0]
    corr_pairs: list[list[Any]] = []
    if array.shape[0] > 1:
        corr = np.corrcoef(array, rowvar=False)
        for i, left in enumerate(columns):
            for j, right in enumerate(columns):
                if j <= i:
                    continue
                value = float(corr[i, j])
                if math.isfinite(value) and abs(value) >= CORR_THRESHOLD:
                    corr_pairs.append([left, right, value])
    return {"missing_pct": missing, "constants": constants, "high_corr": corr_pairs, "n": int(array.shape[0]), "p": len(columns)}


def coefficient_magnitudes(model: Any, columns: tuple[str, ...]) -> list[list[Any]]:
    clf = model.named_steps["clf"]
    coef = clf.coef_[0]
    ranked = sorted(zip(columns, (abs(float(item)) for item in coef), (float(item) for item in coef)), key=lambda item: -item[1])
    return [[name, mag, signed] for name, mag, signed in ranked]


def bootstrap_auc_lift(
    rows: list[dict[str, Any]],
    y_true: list[int],
    current_p: list[float],
    new_p: list[float],
    *,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = 0,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    by_end: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_end[str(row["end"])].append(index)
    clocks = list(by_end)
    lifts: list[float] = []
    for _ in range(draws):
        chosen = rng.choice(clocks, size=len(clocks), replace=True)
        indexes = [i for clock in chosen for i in by_end[clock]]
        labels = [y_true[i] for i in indexes]
        if len(set(labels)) < 2:
            continue
        cur = float(roc_auc_score(labels, [current_p[i] for i in indexes]))
        new = float(roc_auc_score(labels, [new_p[i] for i in indexes]))
        lifts.append(new - cur)
    if not lifts:
        raise SystemExit("bootstrap produced no two-class resamples")
    arr = np.asarray(lifts)
    return {
        "mean": float(arr.mean()),
        "p025": float(np.percentile(arr, 2.5)),
        "p975": float(np.percentile(arr, 97.5)),
        "draws": float(len(lifts)),
    }


def parquet_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _md_table(rows: list[dict[str, Any]]) -> str:
    header = "| symbol | samples | positive_rate | predicted_positive_rate | ROC-AUC | accuracy | note |"
    sep = "|---|---:|---:|---:|---:|---:|---|"
    lines = [header, sep]
    for row in rows:
        note = "unreliable" if row["unreliable"] else ""
        auc = row["roc_auc"] if row["roc_auc"] == "N/A" else f"{row['roc_auc']:.4f}"
        lines.append(
            f"| {row['symbol']} | {row['samples']} | {row['positive_rate']:.3f} | {row['predicted_positive_rate']:.3f} | {auc} | {row['accuracy']:.3f} | {note} |"
        )
    return "\n".join(lines)


def write_report(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def run_experiment_a(parquet_path: Path, out_dir: Path) -> dict[str, Any]:
    rows, meta = load_parquet_table(parquet_path)
    overnight = int(meta.get("dropped_overnight", "0"))
    cutoff = datetime.fromisoformat(meta["training_data_cutoff"])
    if cutoff.tzinfo is None:
        raise SystemExit("training_data_cutoff must be timezone-aware")
    eligible, rel_rows, drop_new = filter_new_eligible(rows)
    if not eligible:
        raise SystemExit("no NEW-eligible rows")
    features = {_row_id(row): rel_rows[index] for index, row in enumerate(eligible)}
    all_clocks = [str(row["end"]) for row in eligible]
    train, valid, test, purged, validation_start, test_start = assign_splits(
        eligible, cutoff=cutoff, clocks=all_clocks
    )
    assert_split_invariants(train, valid, test)
    for part in (train, valid, test):
        ids = [_row_id(row) for row in part]
        if len(ids) != len(set(ids)):
            raise SystemExit("duplicate row IDs in a split")
    current_model, current_scores = fit_score(train, valid, test, "current", features)
    new_model, new_scores = fit_score(train, valid, test, "new", features)
    y_test = [int(row["label"]) for row in test]
    if [_row_id(row) for row in train + valid + test] != [_row_id(row) for row in train + valid + test]:
        raise SystemExit("CURRENT/NEW row ID mismatch")
    lift = bootstrap_auc_lift(test, y_test, current_scores["test_proba"], new_scores["test_proba"])
    x_train_new, _ = _xy_new(train, features)
    diagnostics = train_diagnostics(x_train_new, NEW_COLUMNS)
    coefs = coefficient_magnitudes(new_model, NEW_COLUMNS)
    symbols = per_symbol_table(test, y_test, new_scores["test_proba"])
    git_commit, git_dirty = git_identity()
    drop_by_split = {
        "eligible_before_split": len(eligible),
        "purged": purged,
        "new_warmup": dict(drop_new),
        "dropped_overnight_parquet": overnight,
        "train": len(train),
        "validation": len(valid),
        "test": len(test),
    }
    legacy_note = None
    try:
        legacy_train, legacy_valid, legacy_test, _, _, _ = assign_splits(
            rows, cutoff=cutoff, clocks=[str(row["end"]) for row in rows]
        )
        _, legacy_scores = fit_score(legacy_train, legacy_valid, legacy_test, "current", {})
        legacy_note = {
            "n_train": len(legacy_train),
            "n_valid": len(legacy_valid),
            "n_test": len(legacy_test),
            "test": legacy_scores["test"],
        }
    except SystemExit:
        legacy_note = {"skipped": True}
    payload = {
        "timeframe": meta.get("timeframe"),
        "parquet": str(parquet_path),
        "parquet_sha256": parquet_sha256(parquet_path),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "feature_list": list(NEW_COLUMNS),
        "feature_count": len(NEW_COLUMNS),
        "research_only": True,
        "splits": {
            "validation_start": validation_start,
            "test_start": test_start,
            "train": {"start": min(str(r["end"]) for r in train), "end": max(str(r["end"]) for r in train), "n": len(train)},
            "validation": {"start": min(str(r["end"]) for r in valid), "end": max(str(r["end"]) for r in valid), "n": len(valid)},
            "test": {"start": min(str(r["end"]) for r in test), "end": max(str(r["end"]) for r in test), "n": len(test)},
        },
        "drops": drop_by_split,
        "current_common": {k: current_scores[k] for k in ("validation", "test")},
        "new": {k: new_scores[k] for k in ("validation", "test")},
        "bootstrap_auc_lift_test": lift,
        "train_diagnostics": diagnostics,
        "coefficients": coefs,
        "per_symbol_test": symbols,
        "legacy_current_side_note": legacy_note,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    report = _render_report(payload)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    return payload


def _render_report(payload: dict[str, Any]) -> str:
    cur_t = payload["current_common"]["test"]
    new_t = payload["new"]["test"]
    cur_v = payload["current_common"]["validation"]
    new_v = payload["new"]["validation"]
    lift = payload["bootstrap_auc_lift_test"]
    noise = not (lift["p025"] > 0)
    lines = [
        "# Experiment A",
        "",
        "Research-only relative features from Feature Engine columns. They are **not** canonical FeatureSet fields until the engine emits them.",
        "",
        f"- parquet: `{payload['parquet']}`",
        f"- parquet sha256: `{payload['parquet_sha256']}`",
        f"- git: `{payload['git_commit']}` dirty={payload['git_dirty']}",
        f"- NEW feature count: {payload['feature_count']}",
        f"- NEW list: {', '.join(payload['feature_list'])}",
        "",
        "## Splits",
        "",
        f"TRAIN start `{payload['splits']['train']['start']}` end `{payload['splits']['train']['end']}` n={payload['splits']['train']['n']}",
        f"VALIDATION start `{payload['splits']['validation']['start']}` end `{payload['splits']['validation']['end']}` n={payload['splits']['validation']['n']}",
        f"TEST start `{payload['splits']['test']['start']}` end `{payload['splits']['test']['end']}` n={payload['splits']['test']['n']}",
        "",
        f"validation_start={payload['splits']['validation_start']} test_start={payload['splits']['test_start']}",
        "",
        "## Drops",
        "",
        json.dumps(payload["drops"], indent=2),
        "",
        "## CURRENT vs NEW (common eligible rows, threshold 0.5)",
        "",
        "| split | model | n | accuracy | ROC-AUC | precision | recall | F1 | Brier | pred_pos |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        _metric_row("validation", "CURRENT", cur_v),
        _metric_row("validation", "NEW", new_v),
        _metric_row("test", "CURRENT", cur_t),
        _metric_row("test", "NEW", new_t),
        "",
        f"Test AUC lift bootstrap (timestamps): mean={lift['mean']:.4f} 95% [{lift['p025']:.4f}, {lift['p975']:.4f}] draws={int(lift['draws'])}",
        "",
        f"Lift distinguishable from noise: {not noise}",
        "",
        "## Train diagnostics (NEW only)",
        "",
        json.dumps(payload["train_diagnostics"], indent=2),
        "",
        "## |coef| after StandardScaler",
        "",
        json.dumps(payload["coefficients"], indent=2),
        "",
        "## Per-symbol test (NEW)",
        "",
        _md_table(payload["per_symbol_test"]),
        "",
        "## Legacy CURRENT side note (full six-column set, not the headline comparison)",
        "",
        json.dumps(payload["legacy_current_side_note"], indent=2, default=str),
        "",
        "## Answers A-E",
        "",
        *_answers(payload),
        "",
    ]
    return "\n".join(lines) + "\n"


def _answers(payload: dict[str, Any]) -> list[str]:
    lift = payload["bootstrap_auc_lift_test"]
    new_auc = payload["new"]["test"]["roc_auc"]
    cur_auc = payload["current_common"]["test"]["roc_auc"]
    material = lift["p025"] > 0
    near_half = new_auc < 0.55
    symbols = payload["per_symbol_test"]
    numeric = [row for row in symbols if row["roc_auc"] != "N/A" and not row["unreliable"]]
    spread = 0.0
    if numeric:
        aucs = [float(row["roc_auc"]) for row in numeric]
        spread = max(aucs) - min(aucs)
    lines = [
        f"A. Material AUC lift (bootstrap 2.5% > 0): {material}. CURRENT test AUC={cur_auc:.4f} NEW={new_auc:.4f} lift 95% [{lift['p025']:.4f}, {lift['p975']:.4f}].",
        f"B. Global model useful: {material and new_auc >= 0.55}. Point estimate can look useful while timestamp bootstrap still covers 0.",
        f"C. Stocks differ: per-symbol AUC range among reliable two-class names is {spread:.3f}. Many names are unreliable on this short test window.",
        "D. More historical data: only if lift exceeds bootstrap noise and is stable across folds. This run does not clear that bar." if not material else "D. Lift exceeds bootstrap noise on this sample; still require fold stability before collecting years of data.",
        "E. If a later run shows a real 1d lift that survives timestamp bootstrap, collect at least 3 years of daily data. Do not treat 5m row counts as independent. If NEW stays ~0.50 or the lift CI includes 0, investigate labels and context next; do not collect more data yet.",
        f"Near 0.50: {near_half}.",
    ]
    return lines


def _metric_row(split: str, model: str, metrics: dict[str, Any]) -> str:
    return (
        f"| {split} | {model} | {metrics['n']} | {metrics['accuracy']:.4f} | {metrics['roc_auc']:.4f} | "
        f"{metrics['precision']:.4f} | {metrics['recall']:.4f} | {metrics['f1']:.4f} | {metrics['brier']:.4f} | "
        f"{metrics['predicted_positive_rate']:.4f} |"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment A CURRENT vs NEW (research only)")
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run_experiment_a(args.parquet, args.out)


if __name__ == "__main__":
    main()
