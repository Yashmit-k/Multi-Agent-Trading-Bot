"""One experimental logistic fit at minority bar 34. Official bar remains 50. Opens no holdout."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np

from quant_agents.research.h001.authorization import refuse_restricted_source
from quant_agents.research.h001.calendar import research_calendar, select_entry
from quant_agents.research.h001.events import Exclusion, classify_rows
from quant_agents.research.h001.features import build_features
from quant_agents.research.h001.labels import horizon_close, make_label
from quant_agents.research.h001.model import fit_h001, positive_probability, take_trade
from quant_agents.research.h001.net import net_return, validation_net_summary
from quant_agents.research.h001.scores import (
    ScoredRow,
    acceptance_gate,
    always_flat_contributions,
    always_long_mean,
    bootstrap,
    brier_score,
    log_loss,
    quant_agent_comparison,
)
from quant_agents.research.h001.split import (
    MINORITY_BAR,
    UnexpectedDecisionDate,
    assign_partition,
    smaller_class_check,
)
from quant_agents.research.h001_integrity import (
    DAILY_CANDLE_SHA256,
    DAILY_CANDLES,
    DAILY_MANIFEST,
    FIVE_MINUTE_CANDLE_SHA256,
    FIVE_MINUTE_CANDLES,
    FIVE_MINUTE_MANIFEST,
)
from run_h001_eligibility_audit import (
    _assert_allowed,
    _load_daily,
    _load_entry_bars,
    _load_rows,
    _sha256_file,
)

OFFICIAL_JSON = Path("services/quant/docs/h001-eligibility-audit-result.json")
FIT_JSON = Path("services/quant/docs/h001-threshold-34-fit.json")
GRANT = (
    "EXPERIMENTAL FIT GRANTED 2026-10-14: one logistic fit on "
    "experiment/h001-threshold-34 using frozen Scope A tape. Official minority "
    "bar remains 50. Do not access snapshots/holdout_after_20261005. Do not "
    "merge to main. Do not rewrite the protocol."
)


def assert_research_path(path: str, *, freeze_open: bool = False) -> None:
    """Path inspection only. No bytes are read."""
    refuse_restricted_source(path, authorization_present=freeze_open)
    _assert_allowed(path)


@dataclass(frozen=True, slots=True)
class FitRow:
    seq_id: str
    symbol: str
    partition: str
    y: int
    x: tuple[float, float, float, float]
    p0: Decimal
    p1: Decimal


def collect_fit_rows(rows, daily_bars, five_minute_bars) -> list[FitRow]:
    classified = classify_rows(rows)
    calendar = research_calendar(daily_bars)
    collected: list[FitRow] = []
    for event in classified.events:
        entry = select_entry(
            event.seq_id,
            event.symbol,
            event.available_at,
            calendar,
            five_minute_bars,
        )
        if isinstance(entry, Exclusion):
            continue
        horizon = horizon_close(
            event.seq_id,
            event.symbol,
            entry.decision,
            calendar,
            daily_bars,
        )
        if isinstance(horizon, Exclusion):
            continue
        h1_session, p1 = horizon
        labeled = make_label(event.seq_id, event.symbol, entry.p0, p1)
        if isinstance(labeled, Exclusion):
            continue
        feats = build_features(
            event.seq_id,
            event.symbol,
            entry.decision,
            event.available_at,
            calendar,
            daily_bars,
        )
        if isinstance(feats, Exclusion):
            continue
        try:
            assignment = assign_partition(event.seq_id, event.symbol, entry.decision, h1_session)
        except UnexpectedDecisionDate:
            continue
        if assignment.reason is not None:
            continue
        minute, ret1, ret5, ret20 = feats.as_tuple()
        collected.append(
            FitRow(
                event.seq_id,
                event.symbol,
                assignment.partition,
                labeled.y,
                (float(minute), float(ret1), float(ret5), float(ret20)),
                labeled.p0,
                labeled.p1,
            )
        )
    return collected


def _split_status(fit_rows: list[FitRow]) -> dict[str, object]:
    labels = tuple(row.y for row in fit_rows)
    check = smaller_class_check(labels) if labels else smaller_class_check(())
    positives = sum(labels)
    return {
        "n": len(fit_rows),
        "positive": positives,
        "negative": len(labels) - positives,
        "minority": check.minority_count,
        "status": check.status,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    official = root / OFFICIAL_JSON
    if not official.exists():
        print("missing official audit JSON", file=sys.stderr)
        return 2
    official_before = official.read_bytes()

    five_c = root / FIVE_MINUTE_CANDLES
    five_m = root / FIVE_MINUTE_MANIFEST
    day_c = root / DAILY_CANDLES
    day_m = root / DAILY_MANIFEST
    freeze = root / "datasets" / "h001-nse-raw-20261010T140237Z"
    for path in (five_c, five_m, day_c, day_m, freeze):
        assert_research_path(str(path), freeze_open=True)
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            return 2

    five_manifest = json.loads(five_m.read_text(encoding="utf-8"))
    day_manifest = json.loads(day_m.read_text(encoding="utf-8"))
    five_hash = _sha256_file(five_c)
    day_hash = _sha256_file(day_c)
    if five_manifest.get("snapshot_id") != "nifty50_5m_20261005":
        print("FAIL snapshot id 5m", file=sys.stderr)
        return 3
    if day_manifest.get("snapshot_id") != "nifty50_1d_20261005":
        print("FAIL snapshot id 1d", file=sys.stderr)
        return 3
    if five_hash != FIVE_MINUTE_CANDLE_SHA256 or five_manifest.get("candle_sha256") != FIVE_MINUTE_CANDLE_SHA256:
        print("FAIL 5m hash", file=sys.stderr)
        return 3
    if day_hash != DAILY_CANDLE_SHA256 or day_manifest.get("candle_sha256") != DAILY_CANDLE_SHA256:
        print("FAIL 1d hash", file=sys.stderr)
        return 3

    rows = _load_rows(freeze)
    daily_bars = _load_daily(day_c)
    entry_bars = _load_entry_bars(five_c)
    sample = collect_fit_rows(rows, daily_bars, entry_bars)
    train_rows = [row for row in sample if row.partition == "train"]
    val_rows = [row for row in sample if row.partition == "validation"]
    train_counts = _split_status(train_rows)
    val_counts = _split_status(val_rows)
    if MINORITY_BAR != 34:
        print("experimental runner requires MINORITY_BAR=34", file=sys.stderr)
        return 4
    if not train_rows or not val_rows:
        print("empty train or validation after eligibility", file=sys.stderr)
        return 4

    x_train = np.asarray([row.x for row in train_rows], dtype=float)
    y_train = np.asarray([row.y for row in train_rows], dtype=int)
    fitted = fit_h001(x_train, y_train)
    x_valid = np.asarray([row.x for row in val_rows], dtype=float)
    probabilities = positive_probability(fitted, x_valid)
    scored: list[ScoredRow] = []
    for row, probability in zip(val_rows, probabilities, strict=True):
        traded = take_trade(float(probability), fitted.threshold)
        scored.append(
            ScoredRow(
                row.symbol,
                row.y,
                float(probability),
                net_return(row.p0, row.p1),
                traded,
            )
        )
    labels = [row.y for row in scored]
    probs = [row.probability for row in scored]
    nets = [row.net for row in scored]
    takes = [row.take_trade for row in scored]
    summary = validation_net_summary(nets, takes)
    boot = bootstrap(tuple(scored))
    gate = acceptance_gate(
        mean_net=summary.mean_all,
        lower_bound=boot.mean_net.lower,
        leakage_ok=True,
        train_status=str(train_counts["status"]),
        validation_status=str(val_counts["status"]),
    )
    payload = {
        "mark": "EXPERIMENTAL_NOT_APPROVED",
        "grant": GRANT,
        "approved_minority_bar": 50,
        "experimental_minority_bar": 34,
        "official_readiness_decision": "AUDIT_COMPLETE_INCONCLUSIVE",
        "protocol_id": "H001-2026-10-12",
        "protocol_status": "PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED",
        "execution_authorized": True,
        "authorization_scope": "EXPERIMENTAL_THRESHOLD_34_FIT_ONLY",
        "holdout_accessed": False,
        "model_fitted": True,
        "snapshot_ids": [
            "nifty50_5m_20261005",
            "nifty50_1d_20261005",
            "h001-nse-raw-20261010T140237Z",
        ],
        "five_file_sha256": five_hash,
        "daily_file_sha256": day_hash,
        "train": train_counts,
        "validation": val_counts,
        "minority_threshold": MINORITY_BAR,
        "coefficients": fitted.coefficients.ravel().tolist(),
        "intercept": float(fitted.model.intercept_[0]),
        "training_prevalence": fitted.threshold,
        "predictor_count": fitted.predictor_count,
        "validation_brier": brier_score(labels, probs),
        "validation_log_loss": log_loss(labels, probs),
        "mean_net_all": str(summary.mean_all),
        "mean_net_trades": None if summary.mean_trades is None else str(summary.mean_trades),
        "trade_count": summary.trade_count,
        "always_flat_mean": str(sum(always_flat_contributions(len(scored)), Decimal(0)) / Decimal(len(scored))),
        "always_long_mean": str(always_long_mean(nets)),
        "quant_agent_comparison": quant_agent_comparison(),
        "bootstrap_mean_net_lower": boot.mean_net.lower,
        "bootstrap_mean_net_upper": boot.mean_net.upper,
        "bootstrap_limitation": boot.limitation,
        "acceptance_gate_passed": gate.passed,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "fit_h001_parameters": list(fit_h001.__code__.co_varnames[: fit_h001.__code__.co_argcount]),
        "official_audit_json": str(official),
        "official_audit_json_unmodified": True,
    }
    out = root / FIT_JSON
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if official.read_bytes() != official_before:
        print("official audit JSON changed; refusing", file=sys.stderr)
        return 5
    print("wrote", out)
    print("acceptance_gate_passed", gate.passed)
    print("mean_net_all", summary.mean_all)
    print("bootstrap_mean_net_lower", boot.mean_net.lower)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
