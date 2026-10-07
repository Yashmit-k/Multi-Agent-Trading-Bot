"""Replay stored NSE data. A bar is knowable only when its end is at or before as_of.

Filtering on start would admit a candle that started before as_of and ended after it.
That bar is not knowable yet, so visibility uses end only.
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from contracts.enums import Timeframe
from contracts.schemas.market import Candle, Quote
from core_db.repository import CoreRepository
from core_market_data.snapshot import CandleSnapshot, load_snapshot


class HistoricalReplayMarketDataProvider:
    def __init__(self, repository: CoreRepository | None, as_of: datetime, *, candles: tuple[Candle, ...] | None = None) -> None:
        self._repository = repository
        self._as_of = _aware(as_of)
        self._candles = candles
        self.snapshot: CandleSnapshot | None = None

    @classmethod
    def from_snapshot(cls, path: str | Path, as_of: datetime) -> "HistoricalReplayMarketDataProvider":
        snapshot = load_snapshot(Path(path))
        provider = cls(None, as_of, candles=snapshot.candles)
        provider.snapshot = snapshot
        return provider

    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        moment = min(_aware(as_of), self._as_of)
        if self._repository is not None:
            ticks = self._repository.ticks_until(f"NSE:{symbol.strip().upper()}", moment)
            if ticks:
                last = ticks[-1]
                return Quote(
                    symbol=last.symbol,
                    exchange="NSE",
                    timestamp=last.timestamp,
                    last_price=last.price,
                    volume=last.volume,
                )
        candles = self._visible(symbol, Timeframe.D1, datetime.min.replace(tzinfo=timezone.utc), moment)
        if not candles:
            raise LookupError(symbol)
        bar = candles[-1]
        return Quote(symbol=bar.symbol, exchange=bar.exchange, timestamp=bar.end, last_price=bar.close, volume=bar.volume)

    def get_candles(self, symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[Candle]:
        """Bars whose end is inside (start, min(end, as_of)]. start is not a visibility test."""
        moment = min(_aware(end), self._as_of)
        return self._visible(symbol, timeframe, _aware(start), moment)

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        candles = self._visible(symbol, timeframe, datetime.min.replace(tzinfo=timezone.utc), self._as_of)
        if not candles:
            raise LookupError(symbol)
        return candles[-1]

    def _visible(self, symbol: str, timeframe: Timeframe | str, start: datetime, moment: datetime) -> list[Candle]:
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        name = symbol.strip().upper()
        if self._candles is not None:
            pool = self._candles
        elif self._repository is not None:
            pool = self._repository.candles_until(name, parsed, moment)
        else:
            pool = ()
        visible = [
            bar
            for bar in pool
            if bar.symbol == name and bar.timeframe == parsed and start < bar.end and bar_visible(bar.end, moment)
        ]
        visible.sort(key=lambda bar: bar.end)
        return visible


HOLDOUT_SNAPSHOT_ID = "holdout_after_20261005"
HOLDOUT_OPENS = datetime(2026, 10, 6, tzinfo=timezone.utc)
SNAPSHOT_FILES = {
    "nifty50_5m_20261005": ("5m", "5m"),
    "nifty50_1d_20261005": ("1D", "1d"),
}


class SnapshotRefused(RuntimeError):
    """The requested snapshot or window is not available to the backtester."""


def snapshots_root() -> Path:
    """The read-only copy. The space in the directory name is significant."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "snapshots 2" / "nifty50"
        if candidate.is_dir():
            return candidate
    raise SnapshotRefused("snapshots 2/nifty50 is not available")


def open_snapshot(snapshot_id: str, start: datetime) -> tuple[Path, str]:
    """Return the candle file for an allowed snapshot. Holdout paths are refused first."""
    if snapshot_id == HOLDOUT_SNAPSHOT_ID or "holdout" in snapshot_id:
        raise SnapshotRefused("refusing holdout snapshot")
    if _aware(start) >= HOLDOUT_OPENS:
        raise SnapshotRefused("refusing a window that starts on or after 2026-10-06")
    chosen = SNAPSHOT_FILES.get(snapshot_id)
    if chosen is None:
        raise SnapshotRefused(f"unknown snapshot {snapshot_id}")
    folder, timeframe = chosen
    path = snapshots_root() / folder / "candles.jsonl"
    if not path.is_file():
        raise SnapshotRefused(f"missing candle file for {snapshot_id}")
    return path, timeframe


def stream_candles(
    snapshot_id: str,
    symbols: tuple[str, ...],
    start: datetime,
    end: datetime,
    *,
    warmup: timedelta = timedelta(days=15),
) -> tuple[list[Candle], int, str]:
    """Read bars inside the window. Bars after end are not returned. Gaps are counted, not filled."""
    path, timeframe = open_snapshot(snapshot_id, start)
    window_start = _aware(start)
    window_end = _aware(end)
    if window_end <= window_start:
        raise SnapshotRefused("end must be after start")
    wanted = {symbol.strip().upper() for symbol in symbols}
    earliest = window_start - warmup
    manifest = json.loads(path.with_name("manifest.json").read_text(encoding="utf-8"))
    if manifest.get("snapshot_id") != snapshot_id:
        raise SnapshotRefused("manifest snapshot_id does not match the request")
    needles = tuple(f'"symbol":"{symbol}"' for symbol in wanted)
    selected: list[Candle] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip() or not any(needle in line for needle in needles):
                continue
            payload = json.loads(line)
            if payload.get("symbol") not in wanted or payload.get("timeframe") != timeframe:
                continue
            bar_end = datetime.fromisoformat(payload["end"]).astimezone(timezone.utc)
            if not bar_visible(bar_end, window_end) or bar_end < earliest:
                continue
            selected.append(
                Candle(
                    symbol=payload["symbol"],
                    exchange=payload["exchange"],
                    timeframe=payload["timeframe"],
                    open=Decimal(str(payload["open"])),
                    high=Decimal(str(payload["high"])),
                    low=Decimal(str(payload["low"])),
                    close=Decimal(str(payload["close"])),
                    volume=int(payload["volume"]),
                    start=datetime.fromisoformat(payload["start"]),
                    end=datetime.fromisoformat(payload["end"]),
                )
            )
    selected.sort(key=lambda bar: (bar.symbol, bar.end))
    return selected, _missing_steps(selected, timeframe), str(manifest["candle_sha256"])


def _missing_steps(candles: list[Candle], timeframe: str) -> int:
    step = timedelta(minutes=5) if timeframe == "5m" else timedelta(days=1)
    missing = 0
    previous: dict[str, datetime] = {}
    for bar in candles:
        prior = previous.get(bar.symbol)
        if prior is not None:
            gap = bar.end - prior
            if timeframe == "5m" and gap > step and bar.start.astimezone(timezone.utc).date() == prior.astimezone(timezone.utc).date():
                missing += int(gap / step) - 1
            elif timeframe == "1d" and gap > timedelta(days=3):
                missing += 1
        previous[bar.symbol] = bar.end
    return missing


def bar_visible(bar_end: datetime, as_of: datetime) -> bool:
    """A bar is knowable only when its end is at or before as_of. Missing bars stay missing."""
    return _aware(bar_end) <= _aware(as_of)


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
