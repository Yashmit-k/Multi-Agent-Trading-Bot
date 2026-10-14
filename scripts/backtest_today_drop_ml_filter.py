"""Fit the Today-Drop ML filter on the permitted NIFTY 50 snapshots.

Does not open the holdout, does not place orders, and does not change Compose.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for relative in (
    "packages/contracts/src",
    "services/core/db/src",
    "services/core/candle-engine/src",
    "services/core/feature-engine/src",
    "services/core/signal-ingestion/src",
    "services/core/market-data/src",
    "services/core/worker/src",
    "services/core/api/src",
    "services/core/signal-fusion/src",
    "services/core/decision-engine/src",
    "services/core/risk-engine/src",
    "services/core/paper-execution/src",
    "services/quant/src",
):
    sys.path.insert(0, str(ROOT / relative))

from core_market_data.replay import stream_candles
from quant_agents.ml.artifact import read_manifest, write_artifact
from quant_agents.ml.registry import ModelRegistry
from quant_agents.research.rebound import simulate_symbol
from quant_agents.research.today_drop_ml_filter import (
    ALGORITHM_ID,
    AUC_INTEREST,
    DATASET_VERSION,
    ENGINE_COLUMNS,
    EVENT_COLUMNS,
    FEATURE_COLUMNS,
    FEATURE_VERSION,
    MIN_CLASS,
    MIN_SPLIT_ROWS,
    MIN_TRAIN_ROWS,
    MODEL_VERSION,
    PR_LIFT,
    PRIMARY_COST,
    TRAIN_END,
    VALIDATION_END,
    assign_split,
    classification_report,
    cluster_mean_interval,
    collect_events,
    equity_drawdown,
    engine_features_for_prefixes,
    vector_from_engine,
    fit_pipeline,
    label_event,
    net_return,
    predict_probability,
    select_threshold,
    _sessions,
)

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
OUT = ROOT / "datasets" / "research" / "today_drop_ml_filter" / "algo1-v1"
TRAINED_AT = datetime(2026, 10, 12, 4, 40, tzinfo=timezone.utc)


def symbols_from_manifest() -> tuple[str, ...]:
    path = ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json"
    daily = ROOT / "snapshots 2" / "nifty50" / "1D" / "manifest.json"
    if not path.is_file() or not daily.is_file():
        raise SystemExit("missing snapshots 2/nifty50 manifest; not substituting another dataset")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("snapshot_id") != "nifty50_5m_20261005":
        raise SystemExit(f"5m manifest snapshot_id is {manifest.get('snapshot_id')}")
    daily_manifest = json.loads(daily.read_text(encoding="utf-8"))
    if daily_manifest.get("snapshot_id") != "nifty50_1d_20261005":
        raise SystemExit(f"1d manifest snapshot_id is {daily_manifest.get('snapshot_id')}")
    daily_counts = {row["symbol"]: int(row["count"]) for row in daily_manifest["symbols"]}
    chosen = []
    for row in manifest["symbols"]:
        if row["symbol"] == "TATAMOTORS" or int(row["count"]) <= 0 or daily_counts.get(row["symbol"], 0) <= 0:
            continue
        chosen.append(row["symbol"])
    return tuple(chosen)


def _coverage(bars: list) -> dict:
    counts: dict[str, int] = defaultdict(int)
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    duplicates = 0
    seen: set[tuple[str, str]] = set()
    for bar in bars:
        key = (bar.symbol, bar.end.isoformat())
        if key in seen:
            duplicates += 1
        seen.add(key)
        counts[bar.symbol] += 1
        stamp = bar.end.isoformat()
        first.setdefault(bar.symbol, stamp)
        last[bar.symbol] = stamp
    return {
        "bars": len(bars),
        "symbols": len(counts),
        "duplicate_ends": duplicates,
        "min_end": min(first.values()) if first else None,
        "max_end": max(last.values()) if last else None,
        "per_symbol": {symbol: {"bars": counts[symbol], "first": first[symbol], "last": last[symbol]} for symbol in sorted(counts)},
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _num(value: object) -> str:
    if value is None:
        return "undefined"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _trade_stats(rows: list[dict], cost: float = PRIMARY_COST) -> dict:
    nets = [net_return(row["entry_price"], row["exit_price"], cost) for row in rows]
    if not nets:
        return {"trades": 0, "mean_net": None, "median_net": None, "win_rate": None, "total_net": None, "drawdown": None}
    ordered = sorted(nets)
    return {
        "trades": len(nets),
        "mean_net": sum(nets) / len(nets),
        "median_net": ordered[len(ordered) // 2],
        "win_rate": sum(value > 0 for value in nets) / len(nets),
        "total_net": sum(nets),
        "drawdown": equity_drawdown(nets),
    }


def _conclusion(train_n: int, train_pos: int, valid_n: int, eval_report: dict, filtered_mean: float | None, unfiltered_mean: float | None, interval: dict | None) -> str:
    if train_n < MIN_TRAIN_ROWS or train_pos < MIN_CLASS or train_n - train_pos < MIN_CLASS or valid_n < MIN_SPLIT_ROWS or int(eval_report["rows"]) < MIN_SPLIT_ROWS:
        return "INSUFFICIENT DATA"
    auc = eval_report.get("roc_auc")
    precision = eval_report.get("average_precision")
    base = eval_report["positives"] / eval_report["rows"] if eval_report["rows"] else 0
    predictive = isinstance(auc, float) and auc > AUC_INTEREST
    if isinstance(precision, float) and precision > base + PR_LIFT:
        predictive = True
    edge = (
        predictive
        and filtered_mean is not None
        and unfiltered_mean is not None
        and filtered_mean > unfiltered_mean
        and filtered_mean > 0
        and interval is not None
        and interval["p05"] > 0
    )
    if edge:
        return "CANDIDATE EDGE — REQUIRES PROSPECTIVE PAPER VALIDATION"
    if predictive:
        return "PREDICTIVE SIGNAL — TRADING EDGE NOT ESTABLISHED"
    return "NO DEMONSTRATED PREDICTIVE EDGE"


def main() -> None:
    if (OUT / "model.joblib").exists():
        raise SystemExit(f"{OUT} already contains a model; refusing to overwrite it")
    names = symbols_from_manifest()
    bars_5m, missing_5m, sha_5m = stream_candles("nifty50_5m_20261005", names, START, END)
    bars_1d, missing_1d, sha_1d = stream_candles("nifty50_1d_20261005", names, START, END)
    cover_5m = _coverage(bars_5m)
    cover_1d = _coverage(bars_1d)
    index_names = sorted(symbol for symbol in cover_5m["per_symbol"] if "NIFTY" in symbol or "VIX" in symbol)
    readiness = [
        "# Today-Drop ML filter data readiness",
        "",
        "Written before the logistic model is fit. The holdout path was not opened.",
        "",
        f"- 5m snapshot `nifty50_5m_20261005` sha `{sha_5m}` bars {cover_5m['bars']} symbols {cover_5m['symbols']}",
        f"- 5m range {cover_5m['min_end']} through {cover_5m['max_end']}; duplicate ends {cover_5m['duplicate_ends']}; gap steps counted by the loader {missing_5m}",
        f"- 1d snapshot `nifty50_1d_20261005` sha `{sha_1d}` bars {cover_1d['bars']} symbols {cover_1d['symbols']}",
        f"- 1d range {cover_1d['min_end']} through {cover_1d['max_end']}; duplicate ends {cover_1d['duplicate_ends']}; long gaps counted by the loader {missing_1d}",
        f"- Symbols used: {len(names)}. TATAMOTORS and any symbol with an empty 5m or 1d count are omitted.",
        f"- Index symbols inside the 5m candle file: {index_names or 'none'}. Relative strength against NIFTY is not a feature.",
        "- Trigger: completed 5m close at or below 99% of the previous completed daily close, inside 09:15–15:00 IST.",
        "- Entry: next stored same-session 5m open. A missing same-session entry bar is excluded.",
        "- One delivery position per symbol. A new trigger while that stop/target position is open is not a new event.",
        "- Primary label: two-session research variant. Exit price is the close of the second completed daily session after the entry session.",
        "- Net return uses 2 bp on entry and 2 bp on exit. This is not Strategy A's 3% stop / 5% target result.",
        f"- Feature version `{FEATURE_VERSION}`. Engine columns {', '.join(ENGINE_COLUMNS)}. Event columns {', '.join(EVENT_COLUMNS)}.",
        "- Missing engine values are exclusions. They are not filled with zero.",
        "",
    ]
    _write(OUT / "data-readiness.md", "\n".join(readiness))

    grouped_5m: dict[str, list] = defaultdict(list)
    grouped_1d: dict[str, list] = defaultdict(list)
    for bar in bars_5m:
        grouped_5m[bar.symbol].append(bar)
    for bar in bars_1d:
        grouped_1d[bar.symbol].append(bar)
    rows: list[dict] = []
    exclusions: dict[str, int] = defaultdict(int)
    print(f"loaded 5m={len(bars_5m)} 1d={len(bars_1d)} symbols={len(names)}", flush=True)
    for index, symbol in enumerate(names, start=1):
        events, counts = collect_events(symbol, grouped_5m[symbol], grouped_1d[symbol])
        reference = simulate_symbol(symbol, grouped_5m[symbol], grouped_1d[symbol], variants=("baseline_today_drop",), modes=("delivery",))
        expected = {(trade["signal_time"], float(trade["entry_price"])) for trade in reference}
        actual = {(event.signal_time, event.entry_price) for event in events}
        if actual != expected:
            raise SystemExit(f"{symbol} entry set does not match Strategy A delivery entries")
        for key, value in counts.items():
            exclusions[key] += value
        sessions = _sessions(grouped_1d[symbol], symbol)
        symbol_bars = grouped_5m[symbol]
        needed = {index for index, bar in enumerate(symbol_bars) if bar.end in {event.signal_time for event in events}}
        cached = engine_features_for_prefixes(symbol_bars, needed)
        by_end = {bar.end: cached[index] for index, bar in enumerate(symbol_bars) if index in needed}
        for event in events:
            if event.signal_time < START:
                continue
            labeled = label_event(event, sessions)
            if labeled is None:
                exclusions["missing_two_session_outcome"] += 1
                continue
            values, reason = vector_from_engine(event, by_end.get(event.signal_time, {}))
            if values is None:
                exclusions[reason or "missing_feature"] += 1
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "signal_time": event.signal_time.isoformat(),
                    "entry_session": event.entry_session.isoformat(),
                    "outcome_session": labeled["outcome_session"].isoformat(),
                    "entry_price": event.entry_price,
                    "exit_price": labeled["exit_price"],
                    "net_return": labeled["net_return"],
                    "label": labeled["label"],
                    "one_session_net_return": labeled["one_session_net_return"],
                    "split": assign_split(event.entry_session, labeled["outcome_session"]),
                    "features": values,
                }
            )
        print(f"events {index}/{len(names)} {symbol} rows={len(rows)}", flush=True)
    readiness.extend(
        [
            "## Event counts before the fit",
            "",
            f"- Trigger candidates: {exclusions['trigger_candidates']}",
            f"- Strategy A delivery entries: {exclusions['entries']}",
            f"- Blocked while a position was open: {exclusions['blocked_by_open_position']}",
            f"- Next bar in another session: {exclusions['next_bar_other_session']}",
            f"- Invalid next open: {exclusions['next_bar_open_invalid']}",
            f"- Below one share at the 20000 cap: {exclusions['entry_below_one_share']}",
            f"- Missing two-session outcome: {exclusions['missing_two_session_outcome']}",
            f"- Rows with a feature vector: {len(rows)}",
            "",
        ]
    )
    for key in sorted(exclusions):
        if key.startswith("missing_feature"):
            readiness.append(f"- {key}: {exclusions[key]}")
    readiness.append("")
    _write(OUT / "data-readiness.md", "\n".join(readiness))
    by_split: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_split[row["split"]].append(row)
    train = by_split["train"]
    validation = by_split["validation"]
    evaluation = by_split["evaluation"]
    if len(train) < MIN_TRAIN_ROWS or len({row["label"] for row in train}) < 2:
        _write(OUT / "report.md", "\n".join(readiness + ["", "INSUFFICIENT DATA", "", "The training split does not contain both classes at the required size.", ""]))
        return
    model = fit_pipeline([row["features"] for row in train], [row["label"] for row in train])
    train_rate = sum(row["label"] for row in train) / len(train)
    for split_rows in (validation, evaluation, train):
        for row in split_rows:
            row["probability"] = predict_probability(model, row["features"])
    threshold = select_threshold([row["probability"] for row in validation], [row["net_return"] for row in validation]) if validation else 0.5
    reports = {
        name: classification_report([row["label"] for row in split_rows], [row["probability"] for row in split_rows], train_rate)
        for name, split_rows in (("train", train), ("validation", validation), ("evaluation", evaluation))
    }
    filtered = [row for row in evaluation if row["probability"] >= threshold]
    deep = [row for row in evaluation if row["features"][0] <= -0.02]
    unfiltered_stats = _trade_stats(evaluation)
    filtered_stats = _trade_stats(filtered)
    deep_stats = _trade_stats(deep)
    interval = cluster_mean_interval(defaultdict(list, {symbol: [row["net_return"] for row in filtered if row["symbol"] == symbol] for symbol in {row["symbol"] for row in filtered}}))
    conclusion = _conclusion(
        len(train),
        sum(row["label"] for row in train),
        len(validation),
        reports["evaluation"],
        filtered_stats["mean_net"],
        unfiltered_stats["mean_net"],
        interval,
    )
    artifact = OUT / "artifact"
    write_artifact(
        artifact,
        model=model,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        timeframe="5m",
        training_data_cutoff=datetime(2025, 6, 30, 10, 0, tzinfo=timezone.utc),
        trained_at=TRAINED_AT,
        label_horizon=2,
        embargo_bars=2,
        feature_columns=FEATURE_COLUMNS,
        training_data="nifty50_5m_20261005+nifty50_1d_20261005",
        snapshot_id="nifty50_5m_20261005",
        snapshot_sha256=sha_5m,
        dataset_schema_version=DATASET_VERSION,
        diagnostics={
            "research_only": True,
            "algorithm_id": ALGORITHM_ID,
            "label_definition": "two_session_close_net_return_strictly_positive_at_2bp_each_side",
            "training_positive_rate": train_rate,
            "training_positive_rate_is_decision_threshold": False,
            "validation_threshold": threshold,
            "validation_rows_used_for_fit": False,
            "not_strategy_a_exit": True,
            "daily_snapshot_id": "nifty50_1d_20261005",
            "daily_snapshot_sha256": sha_1d,
        },
    )
    manifest = read_manifest(artifact / "manifest.json")
    manifest["label_definition"] = "two-session research variant: net return from the next 5m open to the second later daily close is strictly positive after 2 bp per side"
    (artifact / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    loaded = ModelRegistry(artifact).load(artifact)
    if loaded.manifest["sha256"] != manifest["sha256"]:
        raise SystemExit("artifact hash was not preserved")
    contract = {
        "algorithm_id": ALGORITHM_ID,
        "dataset_version": DATASET_VERSION,
        "entry_trigger": "5m close <= 0.99 * previous completed daily close, 09:15-15:00 IST",
        "target": "two-session net return > 0 at 2 bp per side",
        "feature_version": FEATURE_VERSION,
        "feature_columns": list(FEATURE_COLUMNS),
        "cost": "0.0002 entry and 0.0002 * exit/entry",
        "splits": {"train_through": TRAIN_END.isoformat(), "validation_through": VALIDATION_END.isoformat(), "purge": "outcome session must stay inside the split"},
        "model": "StandardScaler + LogisticRegression lbfgs seed 0",
        "artifact": str(artifact.relative_to(ROOT)),
        "status": conclusion,
        "historical_reuse": "The 2024-2026 snapshot was already used by earlier Today-Drop studies. The evaluation period is not an untouched test set.",
    }
    _write(OUT / "experiment-contract.json", json.dumps(contract, indent=2) + "\n")
    lines = [
        "# Today-Drop ML filter",
        "",
        conclusion,
        "",
        "This is a research result. It is not production-ready and it is not live-trading-ready.",
        "The artifact is not configured in Compose and was not loaded by the running paper worker.",
        "",
        "## Outcome",
        "",
        "Strategy A delivery exits at a 3% stop or a 5% target. That is not a fixed session horizon, so it is not the label.",
        "The label is the separate two-session research variant: entry at the next same-session 5-minute open, outcome at the close of the second later daily session.",
        "A one-session net return is stored as a diagnostic and was not used to fit or to choose the threshold.",
        "",
        "## Sample",
        "",
        f"- Trigger candidates: {exclusions['trigger_candidates']}",
        f"- Strategy A delivery entries: {exclusions['entries']}",
        f"- Blocked while a position was open: {exclusions['blocked_by_open_position']}",
        f"- Next bar in another session: {exclusions['next_bar_other_session']}",
        f"- Invalid next open: {exclusions['next_bar_open_invalid']}",
        f"- Below one share at the 20000 cap: {exclusions['entry_below_one_share']}",
        f"- Missing two-session outcome: {exclusions['missing_two_session_outcome']}",
    ]
    for key in sorted(exclusions):
        if key.startswith("missing_feature"):
            lines.append(f"- {key}: {exclusions[key]}")
    lines.extend(["", "| Split | Rows | Positive | Negative | Symbols |", "|---|---:|---:|---:|---:|"])
    for name in ("train", "purged_train", "validation", "purged_validation", "evaluation"):
        split_rows = by_split[name]
        lines.append(
            f"| {name} | {len(split_rows)} | {sum(row['label'] for row in split_rows)} | {len(split_rows) - sum(row['label'] for row in split_rows)} | {len({row['symbol'] for row in split_rows})} |"
        )
    lines.extend(["", "## Classification", ""])
    for name, report in reports.items():
        lines.append(f"- {name}: ROC AUC {_num(report['roc_auc'])}, PR AUC {_num(report['average_precision'])}, log loss {_num(report['log_loss'])} vs constant {_num(report['baseline_log_loss'])}, Brier {_num(report['brier'])} vs constant {_num(report['baseline_brier'])}")
    lines.extend(
        [
            "",
            f"Training positive rate {train_rate:.6f} is the constant-probability baseline. It is not the decision threshold.",
            f"Validation selected probability threshold {threshold:.2f}.",
            "",
            "## Two-session trading utility on the evaluation period",
            "",
            "Each number is an equal-weight event, not the cash-constrained Strategy A book.",
            "",
            f"- All eligible labeled entries: {json.dumps(unfiltered_stats)}",
            f"- Precommitted non-ML baseline, drop of at least 2%: {json.dumps(deep_stats)}",
            f"- ML filter at the frozen validation threshold: {json.dumps(filtered_stats)}",
            f"- Symbol-cluster interval for the filtered mean net: {json.dumps(interval)}",
            "",
            "### Cost sensitivity of the filtered evaluation events",
            "",
        ]
    )
    for bps in (0, 2, 5):
        lines.append(f"- {bps} bp per side: {json.dumps(_trade_stats(filtered, bps / 10000))}")
    one = [row["one_session_net_return"] for row in evaluation if row["one_session_net_return"] is not None]
    lines.extend(
        [
            "",
            f"One-session diagnostic on evaluation events, mean net {sum(one) / len(one) if one else 'undefined'} across {len(one)} events. It did not change the primary label.",
            "",
            "## Reuse",
            "",
            "Earlier Today-Drop studies already used this 2024-01-01 through 2026-10-05 snapshot, including the dates in the evaluation split. That split is not a pristine test set. A later paper-only forward check would be a new sample. The holdout directory was not used.",
            "",
            "## Integration",
            "",
            "Do not point the generic `MlAgent` at this artifact. Two columns, `drop_from_previous_close` and `previous_daily_return`, exist only on a Today-Drop candidate. The paper loop does not import this module.",
            f"Artifact directory: `{artifact.relative_to(ROOT)}`. Registry hash check passed in this run.",
            "",
            "## Tests",
            "",
            "`python -m pytest tests/test_today_drop_ml_filter.py -q --tb=line`",
            "",
        ]
    )
    _write(OUT / "report.md", "\n".join(lines))
    print(conclusion)
    print(f"rows train={len(train)} validation={len(validation)} evaluation={len(evaluation)} threshold={threshold}")


if __name__ == "__main__":
    main()
