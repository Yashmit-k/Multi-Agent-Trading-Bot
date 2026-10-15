"""Incremental candle polling. This module does not place orders.

The paper worker is a separate process. A cycle fetches only the gap after
the last stored daily or 5-minute bar. A symbol with no stored bar is left
for the 100-day seed. One symbol error does not stop the others.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from contracts.enums import Timeframe
from core_db.repository import CoreRepository
from core_market_data.nse_sessions import expected_starts
from core_market_data.schedule import candle_is_fresh, incremental_range
from core_market_data.zerodha import RequestPace, ZerodhaAuthError, ZerodhaMarketDataProvider

@dataclass
class SymbolIngestion:
    symbol: str
    daily_end: str | None = None
    intraday_end: str | None = None
    daily_fresh: bool = False
    intraday_fresh: bool = False
    missing_bars: int = 0
    last_error: str | None = None
    written: int = 0


class HistoricalGate:
    """One historical operation at a time, with one shared request pace.

    The seed waits for an in-flight poll, then holds the gate until it finishes.
    A poll that finds a seed queued or running skips that pass. A second seed
    is refused. finish methods release the lock after an exception.
    """

    def __init__(self, pace: RequestPace | None = None) -> None:
        self.pace = pace or RequestPace()
        self.holder: str | None = None
        self._lock = threading.Lock()
        self._state = threading.Lock()
        self._seed_pending = False

    def mark_queued(self) -> bool:
        with self._state:
            if self._seed_pending:
                return False
            self._seed_pending = True
            return True

    def begin_seed(self) -> None:
        self._lock.acquire()
        self.holder = "seed"

    def finish_seed(self) -> None:
        self.holder = None
        with self._state:
            self._seed_pending = False
        self._lock.release()

    def begin_poll(self) -> str:
        """Return acquired, seed, or busy. seed means a seed is queued or running."""
        with self._state:
            pending = self._seed_pending
        if pending:
            return "seed"
        if not self._lock.acquire(blocking=False):
            return "busy"
        self.holder = "poll"
        return "acquired"

    def finish_poll(self) -> None:
        self.holder = None
        self._lock.release()


@dataclass
class IngestionState:
    """In-memory collector status. It is empty again after a process restart."""

    authenticated: bool = False
    running: bool = False
    skipped_overlap: int = 0
    skipped_for_seed: int = 0
    poll_skip_reason: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    retry_attempt: int = 0
    credentials_rejected: bool = False
    seed_status: str = "idle"
    seed_symbols_completed: int = 0
    seed_symbols_failed: int = 0
    seed_retries: int = 0
    seed_timeouts: int = 0
    seed_results: list[dict[str, str]] = field(default_factory=list)
    symbols: list[SymbolIngestion] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def mark_unauthenticated(self) -> None:
        self.authenticated = False
        self.last_error = "authentication_required"

    def snapshot(self) -> dict[str, object]:
        daily_ends = [item.daily_end for item in self.symbols if item.daily_end]
        intra_ends = [item.intraday_end for item in self.symbols if item.intraday_end]
        return {
            "authenticated": self.authenticated,
            "live_enabled": False,
            "running": self.running,
            "skipped_overlap": self.skipped_overlap,
            "skipped_for_seed": self.skipped_for_seed,
            "poll_skip_reason": self.poll_skip_reason,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "retry_attempt": self.retry_attempt,
            "credentials_rejected": self.credentials_rejected,
            "seed_status": self.seed_status,
            "seed_symbols_completed": self.seed_symbols_completed,
            "seed_symbols_failed": self.seed_symbols_failed,
            "seed_retries": self.seed_retries,
            "seed_timeouts": self.seed_timeouts,
            "seed_results": list(self.seed_results),
            "latest_daily_end": max(daily_ends) if daily_ends else None,
            "latest_intraday_end": max(intra_ends) if intra_ends else None,
            "symbols_fresh_daily": sum(1 for item in self.symbols if item.daily_fresh),
            "symbols_fresh_intraday": sum(1 for item in self.symbols if item.intraday_fresh),
            "symbols_stale": sum(1 for item in self.symbols if not (item.daily_fresh and item.intraday_fresh)),
            "missing_bars": sum(item.missing_bars for item in self.symbols),
            "symbols": [
                {
                    "symbol": item.symbol,
                    "daily_end": item.daily_end,
                    "intraday_end": item.intraday_end,
                    "daily_fresh": item.daily_fresh,
                    "intraday_fresh": item.intraday_fresh,
                    "missing_bars": item.missing_bars,
                    "last_error": item.last_error,
                    "written": item.written,
                }
                for item in self.symbols
            ],
        }


def run_incremental_once(
    repository: CoreRepository,
    client: object,
    state: IngestionState,
    *,
    now: datetime | None = None,
    pace: object | None = None,
    gate: HistoricalGate | None = None,
) -> bool:
    """Poll one incremental pass. Returns False when a seed or another pass holds the gate."""
    if state.credentials_rejected:
        state.authenticated = False
        state.last_error = "authentication_failed"
        return False
    if gate is not None:
        admission = gate.begin_poll()
        if admission == "seed":
            state.skipped_for_seed += 1
            state.poll_skip_reason = "seed_active"
            return False
        if admission != "acquired":
            state.skipped_overlap += 1
            return False
    try:
        return _poll_locked(repository, client, state, now=now, pace=pace if pace is not None else (gate.pace if gate else None))
    finally:
        if gate is not None:
            gate.finish_poll()


def _poll_locked(
    repository: CoreRepository,
    client: object,
    state: IngestionState,
    *,
    now: datetime | None,
    pace: object | None,
) -> bool:
    if not state._lock.acquire(blocking=False):
        state.skipped_overlap += 1
        return False
    moment = now or datetime.now(timezone.utc)
    state.running = True
    state.authenticated = True
    provider = ZerodhaMarketDataProvider(repository, client, pace=pace)  # type: ignore[arg-type]
    rows: list[SymbolIngestion] = []
    try:
        for instrument in repository.members_at(moment):
            row = _one_symbol(provider, repository, instrument.symbol, moment)
            rows.append(row)
            if row.last_error == "authentication_failed":
                state.symbols = rows
                state.authenticated = False
                state.credentials_rejected = True
                state.last_error = "authentication_failed"
                return True
        state.symbols = rows
        # Market context for the regime agent. Not tradable and not part of the freshness counts.
        for index in INDEX_INSTRUMENTS:
            if repository.get_by_symbol(index) is not None:
                _one_symbol(provider, repository, index, moment, seed_if_empty=True)
        errors = [row.last_error for row in rows if row.last_error]
        fetch_errors = [item for item in errors if item not in {"needs_seed"}]
        if any(row.written > 0 or row.last_error is None for row in rows) or not rows:
            state.last_success_at = datetime.now(timezone.utc).isoformat()
        if fetch_errors:
            state.last_error = fetch_errors[0]
            state.retry_attempt = 0 if fetch_errors[0] == "authentication_failed" else provider._retry_attempts
        elif errors:
            state.last_error = errors[0]
            state.retry_attempt = 0
        else:
            state.last_error = None
            state.retry_attempt = 0
        return True
    except ZerodhaAuthError:
        state.symbols = rows
        state.authenticated = False
        state.credentials_rejected = True
        state.last_error = "authentication_failed"
        return True
    finally:
        state.running = False
        state._lock.release()


# NSE indices the regime agent reads: symbol -> (Kite trading symbol, instrument token).
INDEX_INSTRUMENTS: dict[str, tuple[str, int]] = {"NIFTY50": ("NIFTY 50", 256265), "INDIAVIX": ("INDIA VIX", 264969)}
INDEX_SEED_DAYS = {Timeframe.D1: 400, Timeframe.M5: 5}


def _one_symbol(
    provider: ZerodhaMarketDataProvider,
    repository: CoreRepository,
    symbol: str,
    now: datetime,
    *,
    seed_if_empty: bool = False,
) -> SymbolIngestion:
    row = SymbolIngestion(symbol=symbol)
    for timeframe, label in ((Timeframe.D1, "daily"), (Timeframe.M5, "intraday")):
        latest = repository.latest_candle(symbol, timeframe)
        end = None if latest is None else latest.end
        fresh = candle_is_fresh(end, timeframe, now)
        if label == "daily":
            row.daily_end = None if end is None else end.isoformat()
            row.daily_fresh = fresh
        else:
            row.intraday_end = None if end is None else end.isoformat()
            row.intraday_fresh = fresh
        window = incremental_range(end, timeframe, now)
        if window is None and end is None and seed_if_empty:
            window = (now - timedelta(days=INDEX_SEED_DAYS[timeframe]), now)
        if window is None:
            if end is None:
                row.last_error = "needs_seed"
            continue
        start, stop = window
        try:
            candles = [
                bar
                for bar in provider.get_candles(symbol, timeframe, start, stop)
                if bar.end <= stop
            ]
        except ZerodhaAuthError:
            row.last_error = "authentication_failed"
            return row
        except Exception as exc:
            row.last_error = f"{timeframe.value}:{type(exc).__name__}"
            continue
        if candles:
            repository.upsert_candles(candles)
            row.written += len(candles)
            stored = repository.latest_candle(symbol, timeframe)
            stored_end = None if stored is None else stored.end
            stored_fresh = candle_is_fresh(stored_end, timeframe, now)
            if label == "daily":
                row.daily_end = None if stored_end is None else stored_end.isoformat()
                row.daily_fresh = stored_fresh
            else:
                row.intraday_end = None if stored_end is None else stored_end.isoformat()
                row.intraday_fresh = stored_fresh
        expected = expected_starts(start, stop, Timeframe.D1 if timeframe == Timeframe.D1 else Timeframe.M5)
        have = {bar.start.astimezone(timezone.utc) for bar in repository.stored_candles(symbol, timeframe, start=start, end=stop)}
        row.missing_bars += len({item for item in expected if item not in have})
    return row
