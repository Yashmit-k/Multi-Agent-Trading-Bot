"""Pull index context into a new snapshot id. Never writes the frozen stock ids.

A name is accepted only when the Kite instrument dump contains that tradingsymbol.
The INDICES segment wins when the same name appears twice. Missing names abort the pull.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from core_market_data.kite_client import kite_client_from_env
from core_market_data.zerodha import RequestPace, _CHUNK_DAYS, _KITE_INTERVAL, _chunks

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
GATE_DAY = date(2024, 6, 3)
GATE_SYMBOL = "NIFTY 50"
OIL_GAS_SYMBOL = "NIFTY OIL & GAS"
CONTEXT_PULL_NAMES = (
    "INDIA VIX",
    "NIFTY BANK",
    "NIFTY FIN SERVICE",
    "NIFTY IT",
    "NIFTY AUTO",
    "NIFTY FMCG",
    "NIFTY METAL",
    "NIFTY PHARMA",
    "NIFTY ENERGY",
    "NIFTY REALTY",
    "NIFTY CONSR DURBL",
)

FROZEN_SNAPSHOT_IDS = ("nifty50_5m_20261005", "nifty50_1d_20261005")
# Searched, not confirmed. confirm_index_symbols is the only acceptance step.
CONTEXT_CANDIDATES = (
    "NIFTY 50",
    "INDIA VIX",
    "NIFTY BANK",
    "NIFTY FIN SERVICE",
    "NIFTY IT",
    "NIFTY AUTO",
    "NIFTY FMCG",
    "NIFTY METAL",
    "NIFTY PHARMA",
    "NIFTY ENERGY",
    "NIFTY OIL & GAS",
    "NIFTY REALTY",
    "NIFTY CONSR DURBL",
)


class UnconfirmedSymbols(RuntimeError):
    """The instrument dump did not contain every requested tradingsymbol."""


def confirm_index_symbols(rows: list[dict[str, object]], wanted: tuple[str, ...]) -> dict[str, int]:
    """Exact NSE tradingsymbol match. Prefer the INDICES segment when both exist."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        trading = str(row.get("tradingsymbol", "")).strip().upper()
        if trading:
            grouped.setdefault(trading, []).append(row)
    confirmed: dict[str, int] = {}
    missing: list[str] = []
    for name in wanted:
        matches = grouped.get(name.strip().upper(), [])
        if not matches:
            missing.append(name)
            continue
        indices = [row for row in matches if str(row.get("segment", "")).upper() == "INDICES"]
        chosen = indices[0] if indices else matches[0]
        confirmed[name] = int(chosen["instrument_token"])
    if missing:
        raise UnconfirmedSymbols(", ".join(missing))
    return confirmed


def assert_holdout_starts_after_frozen_file(start: datetime) -> None:
    """The forward file is sessions after 2026-10-05. It is not a training set."""
    cutoff = datetime(2026, 10, 6, tzinfo=timezone.utc)
    if start.astimezone(timezone.utc) < cutoff:
        raise SystemExit("forward holdout must start after 2026-10-05")


def assert_new_snapshot_id(snapshot_id: str) -> None:
    if snapshot_id in FROZEN_SNAPSHOT_IDS or snapshot_id.startswith("nifty50_"):
        raise SystemExit(f"refusing to write frozen snapshot id {snapshot_id}")


def exact_rows(rows: list[dict[str, object]], tradingsymbol: str) -> list[dict[str, object]]:
    """Every instrument row whose tradingsymbol matches. No spelling is guessed."""
    name = tradingsymbol.strip().upper()
    return [row for row in rows if str(row.get("tradingsymbol", "")).strip().upper() == name]


def _public_row(row: dict[str, object], raw_5m: int, raw_day: int) -> dict[str, object]:
    return {
        "instrument_token": int(row["instrument_token"]),
        "exchange": row.get("exchange"),
        "segment": row.get("segment"),
        "name": row.get("name"),
        "tradingsymbol": str(row.get("tradingsymbol", "")).strip(),
        "raw_5m": raw_5m,
        "raw_day": raw_day,
    }


def prove_exact_symbol(client, rows: list[dict[str, object]], tradingsymbol: str, day: date, pace: RequestPace) -> dict[str, object]:
    """Call historical_data on every exact row. Keep the first row with raw 5m and daily candles."""
    matches = exact_rows(rows, tradingsymbol)
    if not matches:
        return {"symbol": tradingsymbol, "passed": False, "status": "symbol_not_in_instrument_dump", "chosen": None, "candidates": []}
    start = datetime.combine(day, time(9, 15), tzinfo=IST).astimezone(timezone.utc)
    end = datetime.combine(day, time(15, 30), tzinfo=IST).astimezone(timezone.utc)
    candidates: list[dict[str, object]] = []
    chosen: dict[str, object] | None = None
    for row in matches:
        token = int(row["instrument_token"])
        pace.wait()
        raw_5m = list(client.historical_data(token, start, end, "5minute"))
        logger.info("raw candles symbol=%s interval=5minute count=%s", tradingsymbol, len(raw_5m))
        pace.wait()
        raw_day = list(client.historical_data(token, start, end, "day"))
        logger.info("raw candles symbol=%s interval=day count=%s", tradingsymbol, len(raw_day))
        record = _public_row(row, len(raw_5m), len(raw_day))
        candidates.append(record)
        if chosen is None and record["raw_5m"] > 0 and record["raw_day"] > 0:
            chosen = record
    return {
        "symbol": tradingsymbol,
        "passed": chosen is not None,
        "status": "passed" if chosen is not None else "no_raw_candles",
        "chosen": chosen,
        "candidates": candidates,
    }


def prove_nifty_gate(client, pace: RequestPace | None = None) -> dict[str, object]:
    """NIFTY 50 on 2024-06-03. A miss stops the context pull before any other name is requested."""
    limiter = pace or RequestPace()
    report = prove_exact_symbol(client, client.instruments("NSE"), GATE_SYMBOL, GATE_DAY, limiter)
    report["gate_day"] = GATE_DAY.isoformat()
    report["pull_started"] = False
    return report


def pull_verified_context(client, gate: dict[str, object], pace: RequestPace | None = None) -> dict[str, object]:
    """After the NIFTY 50 gate passes, one-day test each exact name, then pull through 2026-10-05."""
    if not gate.get("passed") or gate.get("symbol") != GATE_SYMBOL:
        return {"pull_started": False, "reason": "nifty_gate_failed", "gate": gate}
    limiter = pace or RequestPace()
    dump = client.instruments("NSE")
    accepted = {GATE_SYMBOL: gate["chosen"]}
    skipped: list[dict[str, object]] = []
    for name in CONTEXT_PULL_NAMES:
        report = prove_exact_symbol(client, dump, name, GATE_DAY, limiter)
        if report["passed"]:
            accepted[name] = report["chosen"]
        else:
            skipped.append({"symbol": name, "status": report["status"], "candidates": report["candidates"]})
    oil_rows = exact_rows(dump, OIL_GAS_SYMBOL)
    if not oil_rows:
        oil = {"symbol": OIL_GAS_SYMBOL, "status": "unavailable"}
    else:
        oil_report = prove_exact_symbol(client, dump, OIL_GAS_SYMBOL, GATE_DAY, limiter)
        if oil_report["passed"]:
            accepted[OIL_GAS_SYMBOL] = oil_report["chosen"]
            oil = {"symbol": OIL_GAS_SYMBOL, "status": "passed", "chosen": oil_report["chosen"]}
        else:
            oil = {"symbol": OIL_GAS_SYMBOL, "status": oil_report["status"], "candidates": oil_report["candidates"]}
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 6, tzinfo=timezone.utc)
    candles = []
    for name, chosen in accepted.items():
        token = int(chosen["instrument_token"])
        for timeframe in (Timeframe.M5, Timeframe.D1):
            interval = _KITE_INTERVAL[timeframe]
            for chunk_start, chunk_end in _chunks(start, end, _CHUNK_DAYS[timeframe]):
                limiter.wait()
                raw = list(client.historical_data(token, chunk_start, chunk_end, interval))
                logger.info("raw candles symbol=%s interval=%s count=%s", name, interval, len(raw))
                for row in raw:
                    line = context_line(name, timeframe, row)
                    if line is None:
                        continue
                    bar_start = datetime.fromisoformat(json.loads(line)["start"]).astimezone(timezone.utc)
                    if start <= bar_start < end:
                        candles.append(line)
    return {
        "pull_started": True,
        "symbols": sorted(accepted),
        "instruments": accepted,
        "skipped": skipped,
        "oil_and_gas": oil,
        "candles": candles,
        "bars": len(candles),
    }


def pull_context(
    directory: Path,
    *,
    snapshot_id: str,
    start: datetime,
    end: datetime,
    symbols: tuple[str, ...] = CONTEXT_CANDIDATES,
    timeframes: tuple[Timeframe, ...] = (Timeframe.M5, Timeframe.D1),
) -> dict[str, object]:
    """Download only names that return candles. A failed NIFTY 50 gate writes nothing."""
    assert_new_snapshot_id(snapshot_id)
    client = kite_client_from_env()
    if client is None or not client.access_token:
        raise SystemExit("Kite access token is not set. Symbols were not confirmed and nothing was pulled.")
    gate = prove_nifty_gate(client)
    if not gate["passed"]:
        return {"snapshot_id": snapshot_id, "pull_started": False, "gate": {key: value for key, value in gate.items()}}
    pulled = pull_verified_context(client, gate)
    directory.mkdir(parents=True, exist_ok=True)
    _write_candles(directory, snapshot_id, pulled["candles"], pulled)
    return {"snapshot_id": snapshot_id, "symbols": pulled["symbols"], "bars": pulled["bars"], "pull_started": True}


def context_line(symbol: str, timeframe: Timeframe, row: dict[str, object]) -> str | None:
    """Same field order as a stock candle line. Index names contain spaces, so they are not Candle models."""
    stamp = row.get("date")
    if isinstance(stamp, str):
        parsed = datetime.fromisoformat(stamp)
    elif isinstance(stamp, datetime):
        parsed = stamp
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    if timeframe == Timeframe.D1:
        local_day = parsed.astimezone(IST).date()
        bar_start = datetime.combine(local_day, time(9, 15), tzinfo=IST).astimezone(timezone.utc)
        bar_end = datetime.combine(local_day, time(15, 30), tzinfo=IST).astimezone(timezone.utc)
    else:
        bar_start = parsed.astimezone(timezone.utc)
        bar_end = bar_start + timedelta(minutes=5 if timeframe == Timeframe.M5 else 24 * 60)
    try:
        prices = {key: Decimal(str(row[key])) for key in ("open", "high", "low", "close")}
    except (KeyError, ValueError, ArithmeticError):
        return None
    if any(value <= 0 for value in prices.values()):
        return None
    if prices["high"] < prices["low"] or prices["high"] < max(prices["open"], prices["close"]) or prices["low"] > min(prices["open"], prices["close"]):
        return None
    raw_volume = row.get("volume")
    volume = 0 if raw_volume is None else int(raw_volume)
    fields = [
        ("close", format(prices["close"], "f")),
        ("end", json.dumps(bar_end.isoformat())),
        ("exchange", json.dumps("NSE")),
        ("high", format(prices["high"], "f")),
        ("low", format(prices["low"], "f")),
        ("open", format(prices["open"], "f")),
        ("start", json.dumps(bar_start.isoformat())),
        ("symbol", json.dumps(symbol)),
        ("timeframe", json.dumps(timeframe.value)),
        ("volume", str(volume)),
    ]
    return "{" + ",".join(f"{json.dumps(key)}:{value}" for key, value in fields) + "}\n"


def _write_candles(directory: Path, snapshot_id: str, candles: list, pulled: dict[str, object] | None = None) -> None:
    """Same candle line layout as the stock snapshot, with this folder's own id."""
    ordered = sorted(candles, key=lambda line: (json.loads(line)["symbol"], json.loads(line)["timeframe"], json.loads(line)["end"]))
    body = "".join(ordered)
    (directory / "candles.jsonl").write_text(body, encoding="utf-8")
    import hashlib
    import json

    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    names = sorted({json.loads(line)["symbol"] for line in ordered})
    manifest = {
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "universe": "CONTEXT",
        "candle_sha256": digest,
        "symbols": names,
        "trainable": False,
        "instruments": {} if pulled is None else pulled.get("instruments", {}),
        "skipped": [] if pulled is None else pulled.get("skipped", []),
        "oil_and_gas": None if pulled is None else pulled.get("oil_and_gas"),
    }
    assert_new_snapshot_id(snapshot_id)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
