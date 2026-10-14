"""Authorization B eligibility-only runner. Does not fit a model. Opens no holdout."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from quant_agents.research.h001.authorization import (
    REQUIRED_AUTHORIZATION_B_STATEMENT,
    AuthorizationB,
    refuse_restricted_source,
    require_authorization_b,
)
from quant_agents.research.h001.calendar import DailyBar, FiveMinuteBar
from quant_agents.research.h001.eligibility import (
    ORIGIN_FROZEN,
    EligibilityBundle,
    run_frozen_eligibility_audit,
)
from quant_agents.research.h001.events import parse_exchdisstime
from quant_agents.research.h001_integrity import (
    DAILY_CANDLE_SHA256,
    FIVE_MINUTE_CANDLE_SHA256,
    DAILY_CANDLES,
    DAILY_MANIFEST,
    FIVE_MINUTE_CANDLES,
    FIVE_MINUTE_MANIFEST,
)

IST = ZoneInfo("Asia/Kolkata")
ENTRY_START = time(9, 15)
ENTRY_END = time(9, 20)
CLOSE_CLOCK = time(15, 30)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _assert_allowed(path: Path) -> None:
    text = str(path).replace("\\", "/")
    refuse_restricted_source(text, authorization_present=True)
    parts = Path(text).parts
    if "snapshots" in parts and "nifty50" in parts and "snapshots 2" not in parts:
        raise RuntimeError(f"refusing short tape path {path}")


def _load_rows(freeze: Path) -> list[dict[str, object]]:
    folder = freeze / "corporate-announcements"
    rows: list[dict[str, object]] = []
    for path in sorted(folder.glob("*.json")):
        _assert_allowed(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            raw = item.get("exchdisstime", "")
            try:
                available = parse_exchdisstime(raw).isoformat() if isinstance(raw, str) else ""
            except ValueError:
                available = ""
            rows.append(
                {
                    "seq_id": item.get("seq_id", ""),
                    "symbol": item.get("symbol", ""),
                    "desc": item.get("desc", ""),
                    "exchdisstime": raw,
                    "available_at": available,
                    "attchmntText": item.get("attchmntText", ""),
                    "hasXbrl": item.get("hasXbrl", False),
                }
            )
    return rows


def _aware(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo("UTC"))
    return moment.astimezone(IST)


def _load_daily(path: Path) -> list[DailyBar]:
    bars: list[DailyBar] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            end = _aware(str(row["end"]))
            if end.timetz().replace(tzinfo=None) != CLOSE_CLOCK:
                continue
            bars.append(DailyBar(str(row["symbol"]), end, Decimal(str(row["close"]))))
    return bars


def _load_entry_bars(path: Path) -> list[FiveMinuteBar]:
    bars: list[FiveMinuteBar] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            start = _aware(str(row["start"]))
            end = _aware(str(row["end"]))
            if start.timetz().replace(tzinfo=None) != ENTRY_START:
                continue
            if end.timetz().replace(tzinfo=None) != ENTRY_END:
                continue
            bars.append(FiveMinuteBar(str(row["symbol"]), start, end, Decimal(str(row["open"]))))
    return bars


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    token = AuthorizationB(
        statement=REQUIRED_AUTHORIZATION_B_STATEMENT,
        granted_by="user",
        granted_on="2026-10-14",
    )
    require_authorization_b(token)

    five_c = root / FIVE_MINUTE_CANDLES
    five_m = root / FIVE_MINUTE_MANIFEST
    day_c = root / DAILY_CANDLES
    day_m = root / DAILY_MANIFEST
    freeze = root / "datasets" / "h001-nse-raw-20261010T140237Z"
    for path in (five_c, five_m, day_c, day_m, freeze):
        _assert_allowed(path)
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            return 2

    five_manifest = json.loads(five_m.read_text(encoding="utf-8"))
    day_manifest = json.loads(day_m.read_text(encoding="utf-8"))
    five_hash = _sha256_file(five_c)
    day_hash = _sha256_file(day_c)
    print("five_snapshot_id", five_manifest.get("snapshot_id"))
    print("daily_snapshot_id", day_manifest.get("snapshot_id"))
    print("five_file_sha256", five_hash)
    print("five_manifest_candle_sha256", five_manifest.get("candle_sha256"))
    print("five_expected", FIVE_MINUTE_CANDLE_SHA256)
    print("daily_file_sha256", day_hash)
    print("daily_manifest_candle_sha256", day_manifest.get("candle_sha256"))
    print("daily_expected", DAILY_CANDLE_SHA256)
    print("five_bytes", five_c.stat().st_size)
    print("daily_bytes", day_c.stat().st_size)

    configured = root / "snapshots 2" / "nifty50"
    if not configured.is_dir():
        print("configured snapshots 2/nifty50 is missing", file=sys.stderr)
        return 2
    print("configured_snapshots_root", configured)
    print("loader_five", (configured / "5m" / "candles.jsonl").resolve() == five_c.resolve())
    print("loader_daily", (configured / "1D" / "candles.jsonl").resolve() == day_c.resolve())

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
    print("announcement_rows", len(rows))
    daily_bars = _load_daily(day_c)
    entry_bars = _load_entry_bars(five_c)
    print("daily_close_bars", len(daily_bars))
    print("entry_five_minute_bars", len(entry_bars))

    bundle = EligibilityBundle(
        tuple(rows),
        tuple(daily_bars),
        tuple(entry_bars),
        ORIGIN_FROZEN,
        (
            str(five_manifest.get("snapshot_id")),
            str(day_manifest.get("snapshot_id")),
            "h001-nse-raw-20261010T140237Z",
        ),
    )
    report = run_frozen_eligibility_audit(
        token,
        bundle,
        alternative_eligibility_basis=True,
    )
    print("integrity_status", report.integrity_verification_status)
    print("readiness_decision", report.readiness_decision)
    print("readiness_reason", report.readiness_reason)
    print("execution_authorized", report.execution_authorized)
    print("stage_counts", json.dumps(report.stage_counts, sort_keys=True))
    print("exclusion_counts", json.dumps(report.exclusion_counts, sort_keys=True))
    print(
        "train",
        report.train.n,
        "pos",
        report.train.positive,
        "neg",
        report.train.negative,
        "minority",
        report.train.minority,
        report.train.status,
    )
    print(
        "validation",
        report.validation.n,
        "pos",
        report.validation.positive,
        "neg",
        report.validation.negative,
        "minority",
        report.validation.minority,
        report.validation.status,
    )
    print("threshold", report.minority_threshold)
    print("executed_at", report.executed_at)
    print("protocol", report.protocol_id, report.protocol_status)
    official = root / "services" / "quant" / "docs" / "h001-eligibility-audit-result.json"
    if official.exists():
        print("leaving official", official, "unmodified")
    out = root / "services" / "quant" / "docs" / "h001-threshold-34-experiment.json"
    payload = {
        "mark": "EXPERIMENTAL_NOT_APPROVED",
        "approved_minority_bar": 50,
        "official_readiness_decision": "AUDIT_COMPLETE_INCONCLUSIVE",
        "protocol_id": report.protocol_id,
        "protocol_status": report.protocol_status,
        "integrity_verification_status": report.integrity_verification_status,
        "readiness_decision": report.readiness_decision,
        "readiness_reason": report.readiness_reason,
        "execution_authorized": False,
        "snapshot_ids": list(report.snapshot_ids),
        "five_file_sha256": five_hash,
        "daily_file_sha256": day_hash,
        "stage_counts": report.stage_counts,
        "exclusion_counts": report.exclusion_counts,
        "train": asdict(report.train),
        "validation": asdict(report.validation),
        "minority_threshold": report.minority_threshold,
        "executed_at": report.executed_at,
        "reproducibility": report.reproducibility,
        "configured_snapshots_root": str(configured),
        "holdout_accessed": False,
        "model_fitted": False,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
