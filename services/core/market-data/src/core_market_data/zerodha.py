"""Zerodha market-data adapter. Order placement is not implemented here."""

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time as clock, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Protocol
from zoneinfo import ZoneInfo

from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle, Quote
from core_db.repository import CoreRepository

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = clock(9, 15)
SESSION_CLOSE = clock(15, 30)
SEED_HISTORY = (Timeframe.D1, Timeframe.M5)
SEED_HISTORY_DAYS = 100

_KITE_INTERVAL = {
    Timeframe.M1: "minute",
    Timeframe.M5: "5minute",
    Timeframe.M15: "15minute",
    Timeframe.M30: "30minute",
    Timeframe.H1: "60minute",
    Timeframe.D1: "day",
}
_CHUNK_DAYS = {
    Timeframe.M1: 60,
    Timeframe.M5: 100,
    Timeframe.M15: 200,
    Timeframe.M30: 200,
    Timeframe.H1: 400,
    Timeframe.D1: 2000,
}
_BAR_MINUTES = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
}


class ZerodhaUnavailable(RuntimeError):
    """Raised when broker credentials or a client are absent."""


class IngestionStatus(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class IngestionRow:
    symbol: str
    daily_count: int
    intraday_count: int
    daily_first_bar: datetime | None
    daily_last_bar: datetime | None
    intraday_first_bar: datetime | None
    intraday_last_bar: datetime | None
    status: IngestionStatus
    detail: str


@dataclass(frozen=True, slots=True)
class IngestionReport:
    written: int
    rows: tuple[IngestionRow, ...]


class KiteMarketClient(Protocol):
    def instruments(self, exchange: str) -> list[dict[str, object]]:
        """Return broker instrument rows."""

    def quote(self, key: str) -> dict[str, object]:
        """Return one quote payload, flat or keyed by exchange:symbol."""

    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str,
    ) -> list[dict[str, object]]:
        """Return candle rows for one window. Equity calls keep continuous and oi off."""

    def login_url(self) -> str:
        """Return the Kite login redirect."""

    def generate_session(self, request_token: str) -> dict[str, object]:
        """Exchange a request token for an access token."""


class RequestPace:
    """At most three Kite calls per second. Tests pass a zero interval."""

    def __init__(
        self,
        min_interval: float = 1 / 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._next = 0.0
        self.waits = 0

    def wait(self) -> None:
        self.waits += 1
        if self.min_interval <= 0:
            return
        now = self._clock()
        if now < self._next:
            self._sleep(self._next - now)
            now = self._clock()
        self._next = now + self.min_interval


class ZerodhaMarketDataProvider:
    """NSE token sync, quotes, and historical candles for symbols already stored."""

    def __init__(
        self,
        repository: CoreRepository,
        client: KiteMarketClient | None = None,
        pace: RequestPace | None = None,
        partial_gap_days: int = 10,
    ) -> None:
        self._repository = repository
        self._client = client
        self._pace = pace or RequestPace()
        self._partial_gap_days = partial_gap_days
        self._broker_rows: list[dict[str, object]] = []

    @classmethod
    def from_env(cls, repository: CoreRepository) -> "ZerodhaMarketDataProvider":
        return cls(repository, client=None)

    def available(self) -> bool:
        return self._client is not None

    def credentials_present(self) -> bool:
        return bool(os.environ.get("ZERODHA_API_KEY") and os.environ.get("ZERODHA_ACCESS_TOKEN"))

    def sync_instruments(self, *, known_only: bool = False) -> int:
        known: set[str] | None = None
        if known_only:
            known = {item.symbol for item in self._repository.list_instruments()}
            if not known:
                return 0
        client = self._require()
        self._pace.wait()
        rows = list(client.instruments("NSE"))
        self._broker_rows = rows
        written = 0
        for row in rows:
            symbol = str(row["tradingsymbol"]).strip().upper()
            if known is not None and symbol not in known:
                continue
            self._repository.upsert_instrument(
                symbol=symbol,
                exchange="NSE",
                trading_symbol=symbol,
                instrument_token=int(row["instrument_token"]),
            )
            written += 1
        return written

    def download_seed_candles(self, start: datetime, end: datetime) -> IngestionReport:
        """Day and 5-minute bars for current universe members. Every member gets a report row."""
        written = 0
        rows: list[IngestionRow] = []
        window_end = _aware(end)
        for instrument in self._repository.members_at(window_end):
            if instrument.instrument_token is None:
                rows.append(_missing_token_row(instrument.symbol, self._broker_rows))
                continue
            stored: dict[Timeframe, list[Candle]] = {}
            for timeframe in SEED_HISTORY:
                candles = [
                    bar
                    for bar in self.get_candles(instrument.symbol, timeframe, start, window_end)
                    if bar.end <= window_end
                ]
                if candles:
                    self._repository.upsert_candles(candles)
                    written += len(candles)
                stored[timeframe] = candles
            rows.append(
                _report_row(
                    instrument.symbol,
                    stored[Timeframe.D1],
                    stored[Timeframe.M5],
                    start,
                    self._partial_gap_days,
                )
            )
        return IngestionReport(written=written, rows=tuple(rows))

    def ingest_seed_history(self, start: datetime, end: datetime) -> IngestionReport:
        self.sync_instruments(known_only=True)
        return self.download_seed_candles(start, end)

    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        del as_of
        client = self._require()
        key = f"NSE:{symbol.strip().upper()}"
        payload = _quote_row(client.quote(key), key)
        stamp = payload["timestamp"]
        if isinstance(stamp, datetime):
            timestamp = stamp if stamp.tzinfo else stamp.replace(tzinfo=IST)
        else:
            timestamp = datetime.fromisoformat(str(stamp))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=IST)
        return Quote(
            symbol=symbol.strip().upper(),
            exchange=Exchange.NSE,
            timestamp=timestamp.astimezone(timezone.utc),
            last_price=Decimal(str(payload["last_price"])),
            volume=int(payload["volume"]),
        )

    def get_candles(self, symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[Candle]:
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        instrument = self._repository.get_by_symbol(symbol)
        if instrument is None or instrument.instrument_token is None:
            raise ZerodhaUnavailable(f"missing instrument token for {symbol.strip().upper()}")
        client = self._require()
        interval = _KITE_INTERVAL[parsed]
        window_end = _aware(end)
        candles: list[Candle] = []
        for chunk_start, chunk_end in _chunks(start, window_end, _CHUNK_DAYS[parsed]):
            self._pace.wait()
            rows = client.historical_data(instrument.instrument_token, chunk_start, chunk_end, interval)
            for row in rows:
                bar = _candle_from_kite(instrument.symbol, parsed, row)
                if bar.end <= window_end:
                    candles.append(bar)
        return candles

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        end = datetime.now(timezone.utc)
        candles = self.get_candles(symbol, timeframe, end - timedelta(days=5), end)
        if not candles:
            raise ZerodhaUnavailable(f"no candle for {symbol.strip().upper()}")
        return candles[-1]

    def _require(self) -> KiteMarketClient:
        if self._client is None:
            raise ZerodhaUnavailable("Zerodha credentials are not configured")
        return self._client


def format_ingestion_report(report: IngestionReport) -> str:
    """One text table. Logged on every seed run, including a clean one."""
    lines = [
        f"seed ingestion wrote {report.written} bars across {len(report.rows)} symbols",
        "symbol daily_count intraday_count daily_first_bar daily_last_bar intraday_first_bar intraday_last_bar status detail",
    ]
    for row in report.rows:
        lines.append(
            " ".join(
                [
                    row.symbol,
                    str(row.daily_count),
                    str(row.intraday_count),
                    _stamp(row.daily_first_bar),
                    _stamp(row.daily_last_bar),
                    _stamp(row.intraday_first_bar),
                    _stamp(row.intraday_last_bar),
                    row.status.value,
                    row.detail or "-",
                ]
            )
        )
    return "\n".join(lines)


def _missing_token_row(symbol: str, broker_rows: list[dict[str, object]]) -> IngestionRow:
    candidates = _broker_candidates(symbol, broker_rows)
    detail = "no NSE tradingsymbol"
    if candidates:
        detail = f"{detail}; candidates {', '.join(candidates)}"
    return IngestionRow(
        symbol=symbol,
        daily_count=0,
        intraday_count=0,
        daily_first_bar=None,
        daily_last_bar=None,
        intraday_first_bar=None,
        intraday_last_bar=None,
        status=IngestionStatus.MISSING,
        detail=detail,
    )


def _report_row(
    symbol: str,
    daily: list[Candle],
    intraday: list[Candle],
    start: datetime,
    partial_gap_days: int,
) -> IngestionRow:
    daily_first, daily_last = _span(daily)
    intra_first, intra_last = _span(intraday)
    if not daily and not intraday:
        status = IngestionStatus.MISSING
        detail = "empty kite window"
    elif not daily or not intraday:
        status = IngestionStatus.PARTIAL
        detail = "one timeframe empty"
    else:
        assert daily_first is not None
        gap = (_aware(daily_first).date() - _aware(start).date()).days
        if gap > partial_gap_days:
            status = IngestionStatus.PARTIAL
            detail = f"daily history starts {gap} calendar days after the requested start"
        else:
            status = IngestionStatus.OK
            detail = ""
    return IngestionRow(
        symbol=symbol,
        daily_count=len(daily),
        intraday_count=len(intraday),
        daily_first_bar=daily_first,
        daily_last_bar=daily_last,
        intraday_first_bar=intra_first,
        intraday_last_bar=intra_last,
        status=status,
        detail=detail,
    )


def _span(candles: list[Candle]) -> tuple[datetime | None, datetime | None]:
    if not candles:
        return None, None
    ordered = sorted(candles, key=lambda bar: bar.end)
    return ordered[0].start, ordered[-1].end


def _broker_candidates(symbol: str, rows: list[dict[str, object]], limit: int = 5) -> list[str]:
    seed = symbol.strip().upper()
    found: list[str] = []
    for row in rows:
        trading = str(row.get("tradingsymbol", "")).strip().upper()
        if not trading or trading == seed:
            continue
        compact = str(row.get("name") or "").upper().replace(" ", "")
        shares_symbol = trading.startswith(seed[:4]) or seed.startswith(trading[:4])
        shares_name = len(compact) >= 4 and (seed.startswith(compact[:4]) or compact.startswith(seed[:4]))
        if (shares_symbol or shares_name) and trading not in found:
            found.append(trading)
        if len(found) == limit:
            break
    return found


def _stamp(moment: datetime | None) -> str:
    if moment is None:
        return "-"
    return _aware(moment).isoformat()


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _quote_row(payload: dict[str, object], key: str) -> dict[str, object]:
    if "last_price" in payload:
        return payload
    nested = payload.get(key)
    if isinstance(nested, dict):
        return nested
    raise ZerodhaUnavailable("quote payload has no last price")


def _chunks(start: datetime, end: datetime, days: int) -> list[tuple[datetime, datetime]]:
    if end <= start:
        return []
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    span = timedelta(days=days)
    while cursor < end:
        nxt = min(cursor + span, end)
        windows.append((cursor, nxt))
        cursor = nxt
    return windows


def _candle_from_kite(symbol: str, timeframe: Timeframe, row: dict[str, object]) -> Candle:
    stamp = row["date"]
    if isinstance(stamp, str):
        parsed = datetime.fromisoformat(stamp)
    elif isinstance(stamp, datetime):
        parsed = stamp
    else:
        raise ZerodhaUnavailable("historical candle date is missing")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    if timeframe == Timeframe.D1:
        local_day = parsed.astimezone(IST).date()
        start = datetime.combine(local_day, SESSION_OPEN, tzinfo=IST).astimezone(timezone.utc)
        end = datetime.combine(local_day, SESSION_CLOSE, tzinfo=IST).astimezone(timezone.utc)
    else:
        start = parsed.astimezone(timezone.utc)
        end = start + timedelta(minutes=_BAR_MINUTES[timeframe])
    return Candle(
        symbol=symbol,
        exchange=Exchange.NSE,
        timeframe=timeframe,
        open=Decimal(str(row["open"])),
        high=Decimal(str(row["high"])),
        low=Decimal(str(row["low"])),
        close=Decimal(str(row["close"])),
        volume=int(row["volume"]),
        start=start,
        end=end,
    )
