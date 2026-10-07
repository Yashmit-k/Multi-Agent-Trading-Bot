"""Insert only candles Zerodha returns for audited holes. Never invents a bar.

Frozen snapshot ids are not written. A stored start is never replaced.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from contracts.enums import Timeframe
from contracts.schemas.market import Candle
from core_market_data.context_pull import FROZEN_SNAPSHOT_IDS
from core_market_data.kite_client import kite_client_from_env
from core_market_data.snapshot import _line
from core_market_data.zerodha import RequestPace, _KITE_INTERVAL, _candle_from_kite

logger = logging.getLogger(__name__)

CLEAN_SNAPSHOT_ID = "nifty50_clean_20261007"


def assert_clean_snapshot_id(snapshot_id: str) -> None:
    if snapshot_id in FROZEN_SNAPSHOT_IDS:
        raise SystemExit(f"refusing to write frozen snapshot id {snapshot_id}")


def fetch_jobs(report: dict[str, object], timeframe: str) -> list[dict[str, object]]:
    """One request per symbol and session. Exchange-wide days are probed on the first symbol."""
    frame = report[timeframe]
    names = list(frame["symbols"])
    jobs: list[dict[str, object]] = []
    for bucket in ("missing_trading_days_all_symbols", "missing_clocks_all_symbols"):
        for item in frame[bucket]:
            if item["class"] == "short_session_candidate":
                jobs.append(_job(names[0], item, timeframe, probe=True))
            elif item["class"] == "exchange_wide" and bucket == "missing_trading_days_all_symbols":
                jobs.append(_job(names[0], item, timeframe, probe=True))
            else:
                for name in names:
                    jobs.append(_job(name, item, timeframe, probe=False))
    for item in frame["missing_clocks_some_symbols"]:
        for name in item["symbols"]:
            jobs.append(_job(name, item, timeframe, probe=False))
    for item in frame.get("weekend_sessions_already_stored", []):
        if item.get("class") != "short_session_candidate" or timeframe != "5m":
            continue
        jobs.append(
            {
                "symbol": names[0],
                "session": item["session"],
                "clocks_ist": _session_clocks(),
                "timeframe": timeframe,
                "klass": "short_session_candidate",
                "probe": True,
            }
        )
    return jobs


def _job(symbol: str, item: dict[str, object], timeframe: str, *, probe: bool) -> dict[str, object]:
    session = str(item["session"])
    clocks = [str(clock) for clock in item["clocks_ist"]]
    return {
        "symbol": symbol,
        "session": session,
        "clocks_ist": clocks,
        "timeframe": timeframe,
        "klass": item["class"],
        "probe": probe,
    }


def collect_bars(client, jobs: list[dict[str, object]], pace: RequestPace | None = None) -> tuple[list[Candle], list[dict[str, object]]]:
    """Download hole windows. A clock Kite omits stays unresolved and is not invented."""
    limiter = pace or RequestPace()
    tokens = _tokens(client.instruments("NSE"))
    inserted: list[Candle] = []
    unresolved: list[dict[str, object]] = []
    names = sorted({str(job["symbol"]) for job in jobs if not job.get("probe")} | {str(job["symbol"]) for job in jobs})
    for job in jobs:
        token = tokens.get(str(job["symbol"]))
        if token is None:
            unresolved.append({**_public_job(job), "status": "symbol_not_in_instrument_dump"})
            continue
        limiter.wait()
        bars, raw_count = _download(client, token, job)
        wanted = set(job["clocks_ist"])
        got = {bar.start.astimezone(_ist()).strftime("%H:%M") for bar in bars}
        filled = [bar for bar in bars if bar.start.astimezone(_ist()).strftime("%H:%M") in wanted]
        missing = sorted(wanted - got)
        if job["klass"] == "short_session_candidate" and missing:
            unresolved.append({"session": job["session"], "status": "real_short_session", "missing_clocks": len(missing)})
            continue
        if job["probe"] and missing:
            for name in job.get("probe_symbols", names):
                unresolved.append(
                    {
                        "symbol": name,
                        "session": job["session"],
                        "clocks_ist": missing,
                        "status": _raw_status(raw_count, bars),
                        "raw_rows": raw_count,
                    }
                )
            continue
        inserted.extend(filled)
        if missing and not job["probe"]:
            unresolved.append({**_public_job(job), "clocks_ist": missing, "status": _raw_status(raw_count, bars), "raw_rows": raw_count})
        elif job["probe"] and not missing:
            for name in job.get("probe_symbols", names):
                if name == job["symbol"]:
                    continue
                other = dict(job)
                other["symbol"] = name
                other["probe"] = False
                other_token = tokens.get(str(name))
                if other_token is None:
                    unresolved.append({"symbol": name, "session": job["session"], "status": "symbol_not_in_instrument_dump"})
                    continue
                limiter.wait()
                more, _raw = _download(client, other_token, other)
                inserted.extend(bar for bar in more if bar.start.astimezone(_ist()).strftime("%H:%M") in wanted)
    return inserted, unresolved


def _public_job(job: dict[str, object]) -> dict[str, object]:
    return {key: job[key] for key in ("symbol", "session", "timeframe") if key in job}


def backfill_snapshot(
    source: Path,
    directory: Path,
    *,
    snapshot_id: str,
    timeframe: str,
    report: dict[str, object],
    client=None,
    pace: RequestPace | None = None,
) -> dict[str, object]:
    """Copy the frozen file and append bars Kite returned for holes."""
    assert_clean_snapshot_id(snapshot_id)
    if client is None:
        client = kite_client_from_env()
    if client is None or not getattr(client, "access_token", None):
        raise SystemExit("Kite access token is not set. No hole was downloaded and the frozen file was not copied.")
    jobs = fetch_jobs(report, timeframe)
    names = list(report[timeframe]["symbols"])
    for job in jobs:
        if job["probe"]:
            job["probe_symbols"] = names
    inserted, unresolved = collect_bars(client, jobs, pace)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "candles.jsonl"
    shutil.copyfile(source, target)
    existing = _stored_starts(target, timeframe)
    fresh = [bar for bar in inserted if (bar.symbol, bar.start.astimezone(timezone.utc).isoformat()) not in existing]
    with target.open("a", encoding="utf-8") as handle:
        for bar in fresh:
            handle.write(_line(bar))
    manifest = {
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "base_snapshot_unchanged": True,
        "timeframe": timeframe,
        "candle_sha256": _sha256(target),
        "appended_bars": len(fresh),
        "unresolved": unresolved,
        "trainable_2026": False,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _raw_status(raw_count: int, bars: list[Candle]) -> str:
    """A raw payload that failed to parse is not an empty exchange day."""
    if raw_count == 0:
        return "exchange_returned_no_bar"
    if not bars:
        return "raw_rows_unparsed"
    return "clock_filter_dropped_rows"


def _download(client, token: int, job: dict[str, object]) -> tuple[list[Candle], int]:
    if not token:
        return [], 0
    frame = Timeframe(str(job["timeframe"]))
    start, end = _window(str(job["session"]), list(job["clocks_ist"]), frame)
    rows = list(client.historical_data(token, start, end, _KITE_INTERVAL[frame]))
    logger.info("raw candles symbol=%s interval=%s count=%s", job["symbol"], _KITE_INTERVAL[frame], len(rows))
    bars = []
    for row in rows:
        bar = _candle_from_kite(str(job["symbol"]), frame, row)
        if bar is not None:
            bars.append(bar)
    return bars, len(rows)


def _session_clocks() -> list[str]:
    clocks = []
    minute = 9 * 60 + 15
    while minute < 15 * 60 + 30:
        clocks.append(f"{minute // 60:02d}:{minute % 60:02d}")
        minute += 5
    return clocks


def _window(session: str, clocks: list[str], timeframe: Timeframe) -> tuple[datetime, datetime]:
    from zoneinfo import ZoneInfo

    ist = ZoneInfo("Asia/Kolkata")
    day = datetime.fromisoformat(session).date()
    if timeframe == Timeframe.D1:
        start = datetime.combine(day, datetime.min.time(), tzinfo=ist)
        return start, start + timedelta(days=1)
    first = min(datetime.strptime(clock, "%H:%M").time() for clock in clocks)
    last = max(datetime.strptime(clock, "%H:%M").time() for clock in clocks)
    start = datetime.combine(day, first, tzinfo=ist)
    end = datetime.combine(day, last, tzinfo=ist) + timedelta(minutes=5)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _tokens(rows: list[dict[str, object]]) -> dict[str, int]:
    """Use a tradingsymbol only when the dump has one row. Several rows need a candle test."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        trading = str(row.get("tradingsymbol", "")).strip().upper()
        if trading:
            grouped.setdefault(trading, []).append(row)
    return {trading: int(matches[0]["instrument_token"]) for trading, matches in grouped.items() if len(matches) == 1}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stored_starts(path: Path, timeframe: str) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get("timeframe")) != timeframe:
                continue
            start = datetime.fromisoformat(str(row["start"])).astimezone(timezone.utc).isoformat()
            found.add((str(row["symbol"]), start))
    return found


def _ist():
    from zoneinfo import ZoneInfo

    return ZoneInfo("Asia/Kolkata")
