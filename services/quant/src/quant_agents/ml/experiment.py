"""Train a logistic baseline from a Phase 6 parquet. Does not load production MlAgent."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from quant_agents.labelers import LABEL_VERSION, parse_label_horizon
from quant_agents.ml.artifact import write_artifact
from quant_agents.ml.model import make_model
from quant_agents.ml.splits import WalkForwardSplitter, chronological_split

REQUIRED_LOG_KEYS = (
    "experiment_id",
    "snapshot_id",
    "snapshot_sha256",
    "dataset_schema_version",
    "feature_version",
    "model_version",
    "label_version",
    "label_horizon",
    "training_data_cutoff",
    "timeframe",
    "git_commit",
    "git_dirty",
    "model",
    "hyperparameters",
    "training_period",
    "validation_period",
    "test_period",
    "split",
    "metrics",
    "limitations",
    "created_at",
)

MODEL_VERSION = "1.0.0-baseline"
FINITE_METRIC_KEYS = (
    "directional_accuracy",
    "precision",
    "recall",
    "f1",
    "roc_auc",
    "pr_auc",
    "brier",
)


def _decode_meta(raw: dict[bytes, bytes] | None) -> dict[str, str]:
    if not raw:
        return {}
    return {key.decode(): value.decode() for key, value in raw.items()}


def load_parquet_table(path: Path) -> tuple[list[dict[str, object]], dict[str, str]]:
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    rows = table.to_pylist()
    rows.sort(key=lambda item: str(item.get("end", "")))
    return rows, _decode_meta(table.schema.metadata)


def feature_columns(row: dict[str, object]) -> list[str]:
    return sorted(key for key in row if str(key).startswith("feature_"))


def _period(rows: list[dict[str, object]]) -> dict[str, str | None]:
    if not rows:
        return {"start": None, "end": None}
    stamps = [str(item["end"]) for item in rows]
    return {"start": min(stamps), "end": max(stamps)}


def git_identity() -> tuple[str, bool]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        porcelain = subprocess.check_output(["git", "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return "", False
    return commit, bool(porcelain.strip())


def train_majority(labels: list[int]) -> int:
    if not labels:
        raise SystemExit("train split is empty; cannot choose majority class")
    counts = Counter(labels)
    return counts.most_common(1)[0][0]


def previous_bar_predictions(rows: list[dict[str, object]], fallback: int) -> list[int]:
    last_label: dict[str, int] = {}
    ordered = [fallback] * len(rows)
    by_symbol = sorted(enumerate(rows), key=lambda item: (str(item[1]["symbol"]), str(item[1]["end"])))
    for index, row in by_symbol:
        symbol = str(row["symbol"])
        ordered[index] = last_label[symbol] if symbol in last_label else fallback
        last_label[symbol] = int(row["label"])
    return ordered


def _proba(model: Any, x: list[list[float]]) -> list[float]:
    if not x:
        return []
    probs = model.predict_proba(x)
    classes = list(model.classes_)
    if 1 in classes:
        idx = classes.index(1)
        return [float(row[idx]) for row in probs]
    return [0.0 for _ in probs]


def score_split(y_true: list[int], y_pred: list[int], y_prob: list[float] | None, *, name: str) -> dict[str, float]:
    if not y_true:
        raise SystemExit(f"{name} split is empty; cannot score")
    counts = Counter(y_true)
    if len(counts) < 2:
        raise SystemExit(f"{name} has a single class {dict(counts)}; AUC is undefined")
    if y_prob is None:
        y_prob = [float(item) for item in y_pred]
    roc = float(roc_auc_score(y_true, y_prob))
    pr = float(average_precision_score(y_true, y_prob))
    brier = float(brier_score_loss(y_true, y_prob))
    payload = {
        "n": float(len(y_true)),
        "roc_auc": roc,
        "pr_auc": pr,
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "brier": brier,
        "directional_accuracy": float(accuracy_score(y_true, y_pred)),
        "up_rate": float(sum(y_true) / len(y_true)),
    }
    require_finite(payload, name)
    return payload


def require_finite(metrics: dict[str, float], name: str) -> None:
    for key in FINITE_METRIC_KEYS:
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise SystemExit(f"{name} metric {key} is not finite: {value}")


def _xy(rows: list[dict[str, object]], columns: list[str]) -> tuple[list[list[float]], list[int]]:
    x = [[float(row[col]) for col in columns] for row in rows]
    y = [int(row["label"]) for row in rows]
    return x, y


def _parse_stamp(raw: object) -> datetime:
    text = str(raw)
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        raise SystemExit(f"timezone-naive timestamp {text}")
    return stamp


def assert_rows_within_cutoff(rows: list[dict[str, object]], cutoff: datetime, *, name: str) -> None:
    if cutoff is None:
        raise SystemExit("training_data_cutoff is required; cutoff vs split check cannot be skipped")
    for row in rows:
        future = row.get("future_end")
        if not future:
            raise SystemExit(f"{name} row missing future_end; cutoff vs split check cannot be skipped")
        if _parse_stamp(future) > cutoff:
            raise SystemExit(f"{name} row future_end {future} is after cutoff {cutoff.isoformat()}")


def walk_forward_metrics(
    rows: list[dict[str, object]],
    columns: list[str],
    *,
    label_horizon: int,
    train_size: int,
    test_size: int,
    cutoff: datetime,
) -> list[dict[str, object]]:
    splitter = WalkForwardSplitter(train_size=train_size, test_size=test_size, label_horizon=label_horizon)
    folds: list[dict[str, object]] = []
    for index, (train_slice, test_slice) in enumerate(splitter.split(len(rows))):
        train_rows = rows[train_slice]
        test_rows = rows[test_slice]
        assert_rows_within_cutoff(train_rows, cutoff, name=f"walk_forward[{index}].train")
        assert_rows_within_cutoff(test_rows, cutoff, name=f"walk_forward[{index}].test")
        if train_rows and test_rows:
            last_train = str(train_rows[-1]["end"])
            first_test = str(test_rows[0]["end"])
            if first_test < last_train:
                raise AssertionError("walk-forward test window is not after train")
        model = make_model()
        x_train, y_train = _xy(train_rows, columns)
        x_test, y_test = _xy(test_rows, columns)
        model.fit(x_train, y_train)
        pred = [int(item) for item in model.predict(x_test)]
        folds.append(
            {
                "fold": index,
                "train_period": _period(train_rows),
                "validation_period": _period(test_rows),
                "metrics": score_split(y_test, pred, _proba(model, x_test), name=f"walk_forward[{index}]"),
            }
        )
    return folds


def append_experiment_log(path: Path, record: dict[str, object]) -> None:
    missing = [key for key in REQUIRED_LOG_KEYS if key not in record]
    if missing:
        raise ValueError(f"experiment log missing {missing}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def run_experiment(
    parquet_path: Path,
    output_dir: Path,
    log_path: Path,
    *,
    label_horizon: int | None = None,
    cutoff: datetime | None = None,
) -> dict[str, object]:
    horizon = parse_label_horizon(label_horizon)
    rows, meta = load_parquet_table(parquet_path)
    if not rows:
        raise SystemExit("parquet has no rows")
    timeframes = {str(row.get("timeframe") or meta.get("timeframe", "")) for row in rows}
    if len(timeframes) != 1:
        raise SystemExit("mix of timeframes is forbidden; pass one parquet per --timeframe")
    cutoff_raw = cutoff.isoformat() if cutoff is not None else meta.get("training_data_cutoff", "")
    if not cutoff_raw:
        raise SystemExit("training_data_cutoff is required; cutoff vs split check cannot be skipped")
    cutoff_stamp = cutoff or datetime.fromisoformat(cutoff_raw)
    if cutoff_stamp.tzinfo is None:
        raise SystemExit("training_data_cutoff must be timezone-aware")
    columns = feature_columns(rows[0])
    split = chronological_split(len(rows), label_horizon=horizon)
    embargo = split.embargo_bars
    train_rows = rows[: split.train_end]
    valid_rows = rows[split.train_end + embargo : split.valid_end]
    test_rows = rows[split.valid_end + embargo :]
    assert_rows_within_cutoff(train_rows, cutoff_stamp, name="train")
    assert_rows_within_cutoff(valid_rows, cutoff_stamp, name="validation")
    assert_rows_within_cutoff(test_rows, cutoff_stamp, name="test")
    model = make_model()
    x_train, y_train = _xy(train_rows, columns)
    model.fit(x_train, y_train)
    x_valid, y_valid = _xy(valid_rows, columns)
    x_test, y_test = _xy(test_rows, columns)
    valid_pred = [int(item) for item in model.predict(x_valid)]
    test_pred = [int(item) for item in model.predict(x_test)]
    majority = train_majority(y_train)
    all_prev = previous_bar_predictions(rows, majority)
    valid_prev = all_prev[split.train_end + embargo : split.valid_end]
    test_prev = all_prev[split.valid_end + embargo :]
    wf_train = max(8, len(rows) // 3)
    wf_test = max(4, len(rows) // 10)
    folds = walk_forward_metrics(
        rows,
        columns,
        label_horizon=horizon,
        train_size=wf_train,
        test_size=wf_test,
        cutoff=cutoff_stamp,
    )
    chrono = {
        "validation": score_split(y_valid, valid_pred, _proba(model, x_valid), name="validation"),
        "test": score_split(y_test, test_pred, _proba(model, x_test), name="test"),
        "baselines": {
            "majority_train_class": majority,
            "majority_validation": score_split(
                y_valid, [majority] * len(y_valid), None, name="majority_validation"
            ),
            "majority_test": score_split(y_test, [majority] * len(y_test), None, name="majority_test"),
            "previous_bar_validation": score_split(y_valid, valid_prev, None, name="previous_bar_validation"),
            "previous_bar_test": score_split(y_test, test_prev, None, name="previous_bar_test"),
        },
    }
    for split_name, scored in (("validation", chrono["validation"]), ("test", chrono["test"])):
        acc = scored["directional_accuracy"]
        if acc >= 0.70:
            scored["leakage_warning"] = True
        precision = scored["precision"]
        up_rate = scored["up_rate"]
        if scored["recall"] >= 0.9 and abs(precision - up_rate) < 0.05:
            scored["always_up_warning"] = True
    metrics = {
        "chronological": chrono,
        "walk_forward": folds,
        "pnl_requires_core_backtester": True,
        "diagnostics_only": True,
    }
    created = datetime.now(timezone.utc)
    git_commit, git_dirty = git_identity()
    write_artifact(
        output_dir,
        model=model,
        model_version=MODEL_VERSION,
        feature_version=meta.get("feature_version", ""),
        timeframe=meta.get("timeframe", ""),
        training_data_cutoff=cutoff_stamp,
        trained_at=created,
        label_horizon=horizon,
        embargo_bars=split.embargo_bars,
        diagnostics=metrics,
        feature_columns=tuple(columns),
        training_data=meta.get("training_data", "real_snapshot"),
        cutoff_source=meta.get("cutoff_source", "explicit"),
        label_version=meta.get("label_version", LABEL_VERSION),
        snapshot_id=meta.get("snapshot_id", ""),
        snapshot_sha256=meta.get("candle_sha256", ""),
        dataset_schema_version=meta.get("dataset_schema_version", ""),
    )
    record = {
        "experiment_id": str(uuid.uuid4()),
        "snapshot_id": meta.get("snapshot_id", ""),
        "snapshot_sha256": meta.get("candle_sha256", ""),
        "dataset_schema_version": meta.get("dataset_schema_version", ""),
        "feature_version": meta.get("feature_version", ""),
        "model_version": MODEL_VERSION,
        "label_version": meta.get("label_version", LABEL_VERSION),
        "label_horizon": horizon,
        "training_data_cutoff": cutoff_stamp.isoformat(),
        "timeframe": meta.get("timeframe", ""),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "model": "sklearn.linear_model.LogisticRegression",
        "hyperparameters": {"random_state": 0, "max_iter": 200},
        "training_period": _period(train_rows),
        "validation_period": _period(valid_rows),
        "test_period": _period(test_rows),
        "split": {
            "train": {"start_index": 0, "end_index": split.train_end, **_period(train_rows)},
            "validation": {
                "start_index": split.train_end + embargo,
                "end_index": split.valid_end,
                **_period(valid_rows),
            },
            "test": {"start_index": split.valid_end + embargo, "end_index": len(rows), **_period(test_rows)},
            "embargo_bars": embargo,
        },
        "metrics": metrics,
        "limitations": {
            "survivorship_bias": "current_nifty50_constituents",
            "prices_adjusted": "unspecified",
            "five_minute_samples_correlated": True,
            "no_costs": True,
            "diagnostics_only": True,
        },
        "created_at": created.isoformat(),
    }
    append_experiment_log(log_path, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a logistic baseline from a snapshot parquet")
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--log", type=Path, default=Path("experiments/log.jsonl"))
    args = parser.parse_args()
    run_experiment(args.parquet, args.output_dir, args.log)


if __name__ == "__main__":
    main()
