"""Write the direction-dataset review for one snapshot folder.

Stops after inventory, labels, warm-up, and leakage. It does not fit a model.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from quant_agents.direction.inventory import EXCLUDED, gap_label_count, inventory_report, public_inventory
from quant_agents.direction.rows import assert_window_leakage, far_cutoff, feature_census, label_counts, leakage_cases
from quant_agents.direction.window import PURGE_BARS, model_version

FOCUS = ("BHARTIARTL", "HDFCBANK", "ICICIBANK", "SBILIFE", "HINDUNILVR", "ITC")


def build_review(snapshot: Path) -> dict[str, object]:
    raw = inventory_report(snapshot / "candles.jsonl")
    tapes = raw.pop("_tapes")
    grid = raw.pop("_grid")
    grid_starts = set(grid)
    timeframe = str(raw["timeframe"])
    labels: Counter[str] = Counter()
    gaps = 0
    census_totals: Counter[str] = Counter()
    feature_dropped: Counter[str] = Counter()
    first_session = 0
    per_symbol: list[dict[str, object]] = []
    leakage_rows = 0
    for symbol, tape in sorted(tapes.items()):
        if symbol == EXCLUDED or not tape.bars:
            continue
        cutoff = far_cutoff(tape)
        counted = label_counts(tape, cutoff)
        labels.update(counted)
        symbol_gaps = gap_label_count(tape, grid)
        gaps += symbol_gaps
        census = feature_census(tape)
        census_totals["short_window_dropped"] += int(census["short_window_dropped"])
        census_totals["warmup_missing_engine_field"] += int(census["warmup_missing_engine_field"])
        census_totals["rows_remaining"] += int(census["rows_remaining"])
        feature_dropped.update(census["feature_dropped"])
        first_session += int(census["first_bars_of_session"])
        cases = leakage_cases(tape, grid_starts)
        assert_window_leakage(tape, cases)
        leakage_rows += len(cases)
        if symbol in FOCUS or symbol_gaps:
            per_symbol.append(
                {
                    "symbol": symbol,
                    "labels": dict(counted),
                    "same_session_gap_labels": symbol_gaps,
                    "short_window_dropped": census["short_window_dropped"],
                    "warmup_missing_engine_field": census["warmup_missing_engine_field"],
                    "feature_dropped": census["feature_dropped"],
                    "rows_remaining": census["rows_remaining"],
                    "first_bars_of_session": census["first_bars_of_session"],
                    "first_bar_up_rate": census["first_bar_up_rate"],
                    "other_bar_up_rate": census["other_bar_up_rate"],
                }
            )
    labelled = labels["up"] + labels["down"]
    dropped = labels["equal"] + labels["cross_session"] + labels["no_next_bar"] + labels["cutoff"]
    stored = sum(len(tape.bars) for symbol, tape in tapes.items() if symbol != EXCLUDED)
    if labelled + dropped != stored:
        raise SystemExit(f"label buckets {labelled + dropped} != stored rows {stored}")
    return {
        "model_version": model_version(timeframe),
        "window_bars": int(model_version(timeframe).rsplit("=", 1)[-1]),
        "purge_bars": PURGE_BARS,
        "model_fit": False,
        "inventory": public_inventory(raw),
        "labels": {
            "up": labels["up"],
            "down": labels["down"],
            "equal": labels["equal"],
            "cross_session": labels["cross_session"],
            "no_next_bar": labels["no_next_bar"],
            "cutoff": labels["cutoff"],
            "sum": labelled + dropped,
            "stored_rows_excluding_tatamotors": stored,
            "same_session_gap_labels": gaps,
            "note": (
                "same_session_gap_labels are rows whose next stored bar skips an empirical-grid "
                "timestamp inside the same IST session, so the next valid candle is a longer gap. "
                "They stay in up or down. future_close is not a feature."
            ),
        },
        "warmup": {
            "short_window_dropped": census_totals["short_window_dropped"],
            "warmup_missing_engine_field": census_totals["warmup_missing_engine_field"],
            "feature_dropped": dict(feature_dropped),
            "rows_remaining": census_totals["rows_remaining"],
            "first_bars_of_session_in_remaining": first_session,
            "overnight_window": (
                "A 5-minute trailing window crosses sessions. return_1 at the first bar, the window "
                "VWAP, and volatility include the previous session."
                if timeframe == "5m"
                else "The daily window is a sequence of daily bars."
            ),
        },
        "leakage": {"samples": leakage_rows, "passed": True},
        "focus": per_symbol,
        "stopped_before": "time split, scaling, logistic regression, calibration",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Direction dataset review. Does not train.")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    review = build_review(args.snapshot)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model_version": review["model_version"], "labels": review["labels"], "warmup": review["warmup"], "leakage": review["leakage"]}))


if __name__ == "__main__":
    main()
