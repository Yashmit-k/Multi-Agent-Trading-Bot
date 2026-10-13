"""Deterministic Scope A announcement-tape preparation.

Does not mutate the freeze. Does not generate research labels.
Fail closed when the freeze or universe is missing.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from intelligence_agents.h001v2.normalize import (
    QUARTERS,
    ist_calendar_quarter,
    parse_exchdisstime,
    results_like_section15,
    v1_class,
)

SCHEMA_VERSION = "h001-scope-a-prep-1.0"
REQUIRED = ("symbol", "seq_id", "desc", "exchdisstime")


def _stable_id(symbol: str, seq_id: str) -> str:
    return hashlib.sha256(f"nse_corporate_announcements|{symbol}|{seq_id}".encode("utf-8")).hexdigest()


def exclude_reason(row: dict, universe: set[str]) -> str | None:
    if not isinstance(row, dict):
        return "invalid_schema_not_object"
    missing = [key for key in REQUIRED if key not in row]
    if missing:
        return "missing_required_fields:" + ",".join(missing)
    symbol = str(row.get("symbol") or "").strip().upper()
    if not symbol:
        return "empty_symbol"
    if symbol not in universe:
        return "unmapped_symbol"
    if not str(row.get("seq_id") or "").strip():
        return "empty_seq_id"
    ts = parse_exchdisstime(row.get("exchdisstime"))
    if ts is None:
        return "invalid_or_missing_exchdisstime"
    return None


def to_record(row: dict) -> dict:
    symbol = str(row.get("symbol") or "").strip().upper()
    seq_id = str(row.get("seq_id") or "").strip()
    ts = parse_exchdisstime(row.get("exchdisstime"))
    assert ts is not None
    keep, evidence = results_like_section15(row)
    return {
        "event_id": _stable_id(symbol, seq_id),
        "source": "nse_corporate_announcements",
        "freeze_id": "h001-nse-raw-20261010T140237Z",
        "symbol": symbol,
        "seq_id": seq_id,
        "desc": row.get("desc"),
        "exchdisstime_raw": row.get("exchdisstime"),
        "an_dt_raw": row.get("an_dt"),
        "sort_date_raw": row.get("sort_date"),
        "hasXbrl": row.get("hasXbrl"),
        "available_at": ts.isoformat(),
        "available_at_basis": "exchdisstime_ist_convention",
        "ist_quarter": ist_calendar_quarter(ts),
        "v1_class": v1_class(row.get("desc")),
        "section15": keep,
        "section15_evidence": evidence,
        "data_origin": "nse_freeze",
        "fixture": False,
        "schema_version": SCHEMA_VERSION,
    }


def prepare_scope_a(rows: list[dict], universe: list[str]) -> dict:
    allowed = set(universe)
    kept: list[dict] = []
    exclusions: Counter[str] = Counter()
    seen: dict[str, dict] = {}
    duplicate_identical = 0
    duplicate_conflict = 0
    for row in rows:
        reason = exclude_reason(row, allowed)
        if reason:
            exclusions[reason] += 1
            continue
        record = to_record(row)
        key = f"{record['symbol']}|{record['seq_id']}"
        prior = seen.get(key)
        if prior is None:
            seen[key] = record
            kept.append(record)
            continue
        if prior["exchdisstime_raw"] == record["exchdisstime_raw"] and prior["desc"] == record["desc"]:
            duplicate_identical += 1
            exclusions["duplicate_identical_seq"] += 1
        else:
            duplicate_conflict += 1
            exclusions["duplicate_conflict_seq"] += 1

    payload = json.dumps(kept, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    output_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    quarters_span = sorted({item["ist_quarter"] for item in kept if item["ist_quarter"]})
    times = [datetime.fromisoformat(item["available_at"]) for item in kept]
    return {
        "schema_version": SCHEMA_VERSION,
        "scope": "A",
        "scope_note": "Announcement tape only. Not restatement-safe earnings values (Scope B).",
        "n_input_rows": len(rows),
        "n_kept": len(kept),
        "n_excluded": sum(exclusions.values()),
        "exclusions": dict(exclusions),
        "duplicate_identical": duplicate_identical,
        "duplicate_conflict": duplicate_conflict,
        "output_sha256": output_sha256,
        "time_coverage": {
            "first_available_at": min(times).isoformat() if times else None,
            "last_available_at": max(times).isoformat() if times else None,
            "ist_quarters_present": quarters_span,
        },
        "records": kept,
        "fixture": False,
        "labels_generated": False,
    }


def write_prepared(result: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    public = {k: v for k, v in result.items() if k != "records"}
    dest.write_text(json.dumps(public, indent=2) + "\n", encoding="utf-8")
