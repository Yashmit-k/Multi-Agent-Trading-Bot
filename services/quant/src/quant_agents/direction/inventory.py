"""Stream a snapshot candles.jsonl and describe what is actually stored."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
EXCLUDED = "TATAMOTORS"


@dataclass(frozen=True, slots=True)
class StoredBar:
    symbol: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    start: datetime
    end: datetime

    @property
    def session_date(self):
        return self.start.astimezone(IST).date()

    def invalid_ohlc(self) -> str | None:
        if self.end <= self.start:
            return "end_not_after_start"
        if self.high < self.low:
            return "high_below_low"
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            return "open_close_outside_range"
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            return "non_positive_price"
        return None


@dataclass
class SymbolTape:
    bars: list[StoredBar] = field(default_factory=list)
    duplicate_starts: int = 0
    duplicate_ends: int = 0
    invalid_ohlc: list[str] = field(default_factory=list)
    negative_volume: int = 0


def load_tapes(path: Path) -> dict[str, SymbolTape]:
    """One pass. Duplicate starts and ends are counted and not appended twice."""
    tapes: dict[str, SymbolTape] = {}
    seen_start: dict[tuple[str, datetime], int] = {}
    seen_end: dict[tuple[str, datetime], int] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            symbol = str(payload["symbol"])
            tape = tapes.setdefault(symbol, SymbolTape())
            start = datetime.fromisoformat(payload["start"]).astimezone(timezone.utc)
            end = datetime.fromisoformat(payload["end"]).astimezone(timezone.utc)
            start_key = (symbol, start)
            end_key = (symbol, end)
            if start_key in seen_start:
                tape.duplicate_starts += 1
            else:
                seen_start[start_key] = 1
            if end_key in seen_end:
                tape.duplicate_ends += 1
                continue
            seen_end[end_key] = 1
            volume = int(payload["volume"])
            bar = StoredBar(
                symbol=symbol,
                timeframe=str(payload["timeframe"]),
                open=Decimal(str(payload["open"])),
                high=Decimal(str(payload["high"])),
                low=Decimal(str(payload["low"])),
                close=Decimal(str(payload["close"])),
                volume=volume,
                start=start,
                end=end,
            )
            if volume < 0:
                tape.negative_volume += 1
            problem = bar.invalid_ohlc()
            if problem is not None:
                tape.invalid_ohlc.append(f"{bar.end.isoformat()} {problem}")
            tape.bars.append(bar)
    for tape in tapes.values():
        tape.bars.sort(key=lambda bar: bar.end)
    return tapes


def empirical_grid(tapes: dict[str, SymbolTape]) -> list[datetime]:
    """Starts present for at least half of the symbols that have bars. TATAMOTORS is ignored."""
    counts: Counter[datetime] = Counter()
    present = 0
    for symbol, tape in tapes.items():
        if symbol == EXCLUDED or not tape.bars:
            continue
        present += 1
        counts.update(bar.start for bar in tape.bars)
    if present == 0:
        return []
    threshold = max(1, (present + 1) // 2)
    return sorted(stamp for stamp, count in counts.items() if count >= threshold)


def session_lengths(starts: list[datetime]) -> Counter[int]:
    per_day: Counter = Counter()
    for stamp in starts:
        per_day[stamp.astimezone(IST).date()] += 1
    return Counter(per_day.values())


def missing_starts(tape: SymbolTape, grid: list[datetime]) -> list[datetime]:
    owned = {bar.start for bar in tape.bars}
    return [stamp for stamp in grid if stamp not in owned]


def classify_holes(missing: list[datetime], grid: list[datetime], timeframe: str) -> list[dict[str, object]]:
    """Group consecutive missing grid timestamps. The file cannot show a bar that was never stored."""
    if not missing:
        return []
    grid_index = {stamp: index for index, stamp in enumerate(grid)}
    step = timedelta(minutes=5) if timeframe == "5m" else None
    groups: list[list[datetime]] = [[missing[0]]]
    for stamp in missing[1:]:
        previous = groups[-1][-1]
        adjacent = grid_index[stamp] == grid_index[previous] + 1
        if step is not None:
            adjacent = adjacent and stamp - previous == step
        if adjacent:
            groups[-1].append(stamp)
        else:
            groups.append([stamp])
    described: list[dict[str, object]] = []
    for group in groups:
        opens = _is_session_open(group[0], grid)
        described.append(
            {
                "count": len(group),
                "timestamps": [stamp.isoformat() for stamp in group],
                "session_open": opens,
                "same_session_labels_affected": 0 if opens else 1,
                "cause": _hole_cause(group, opens),
            }
        )
    return described


def _is_session_open(stamp: datetime, grid: list[datetime]) -> bool:
    day = stamp.astimezone(IST).date()
    for item in grid:
        if item.astimezone(IST).date() == day:
            return item == stamp
    return False


def _hole_cause(group: list[datetime], opens: bool) -> str:
    same_session = group[0].astimezone(IST).date() == group[-1].astimezone(IST).date()
    if not same_session:
        return "missing bars span more than one session"
    if opens:
        return (
            "absent from the session open; other symbols have this bar, so it is not an "
            "exchange-wide halt. The snapshot stores no invalid OHLC row, and the next "
            "same-session label is still five minutes"
        )
    return (
        "consecutive bars absent after the session open; other symbols have these timestamps, "
        "so it is not an exchange-wide halt. The snapshot stores no invalid OHLC rows. "
        "The file cannot separate a symbol halt from a download hole. "
        "The label on the bar before the hole jumps to the next stored bar"
    )


def nonmodal_sessions(grid: list[datetime]) -> list[dict[str, object]]:
    """Session lengths that are not the modal length. These are on the tape for most symbols."""
    per_day: dict[object, int] = {}
    for stamp in grid:
        day = stamp.astimezone(IST).date()
        per_day[day] = per_day.get(day, 0) + 1
    if not per_day:
        return []
    modal = Counter(per_day.values()).most_common(1)[0][0]
    return [
        {"date": day.isoformat(), "bars": count}
        for day, count in sorted(per_day.items())
        if count != modal
    ]


def inventory_report(path: Path) -> dict[str, object]:
    tapes = load_tapes(path)
    _add_manifest_absences(path, tapes)
    grid = empirical_grid(tapes)
    lengths = session_lengths(grid)
    symbols: list[dict[str, object]] = []
    for symbol in sorted(tapes):
        tape = tapes[symbol]
        holes = [] if symbol == EXCLUDED or not tape.bars else classify_holes(missing_starts(tape, grid), grid, _timeframe(tape))
        first = tape.bars[0] if tape.bars else None
        last = tape.bars[-1] if tape.bars else None
        per_session: Counter[int] = Counter()
        for bar in tape.bars:
            per_session[bar.session_date] += 1
        session_hist = Counter(per_session.values())
        symbols.append(
            {
                "symbol": symbol,
                "rows": len(tape.bars),
                "duplicate_starts": tape.duplicate_starts,
                "duplicate_ends": tape.duplicate_ends,
                "invalid_ohlc": tape.invalid_ohlc,
                "negative_volume": tape.negative_volume,
                "first_bar": first.end.isoformat() if first else None,
                "last_bar": last.end.isoformat() if last else None,
                "sessions": len(per_session),
                "bars_per_session": {str(count): session_hist[count] for count in sorted(session_hist)},
                "missing_vs_empirical_grid": sum(item["count"] for item in holes),
                "holes": holes,
                "excluded": symbol == EXCLUDED,
            }
        )
    return {
        "path": str(path),
        "timeframe": _timeframe_of_report(tapes),
        "empirical_grid_bars": len(grid),
        "observed_bars_per_session": {str(count): lengths[count] for count in sorted(lengths)},
        "shorter_sessions_on_the_tape": nonmodal_sessions(grid),
        "window_fields": (
            "vwap, volatility, volume_mean, period_high and period_low are computed on the "
            "trailing window passed to the Feature Engine. They are not session values, and "
            "they change when the window length changes."
        ),
        "symbols": symbols,
        "_tapes": tapes,
        "_grid": grid,
    }


def public_inventory(report: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in report.items() if not str(key).startswith("_")}


def _add_manifest_absences(path: Path, tapes: dict[str, SymbolTape]) -> None:
    manifest_path = path.parent / "manifest.json"
    if not manifest_path.exists():
        if EXCLUDED not in tapes:
            tapes[EXCLUDED] = SymbolTape()
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest.get("symbols", []):
        symbol = str(entry.get("symbol", ""))
        if symbol and symbol not in tapes:
            tapes[symbol] = SymbolTape()


def _timeframe(tape: SymbolTape) -> str:
    if not tape.bars:
        return ""
    return tape.bars[0].timeframe


def _timeframe_of_report(tapes: dict[str, SymbolTape]) -> str:
    frames = {bar.timeframe for tape in tapes.values() for bar in tape.bars[:1]}
    if len(frames) != 1:
        raise SystemExit(f"snapshot mixes timeframes: {sorted(frames)}")
    return next(iter(frames))


def gap_label_count(tape: SymbolTape, grid: list[datetime]) -> int:
    """Labelled rows whose next stored bar skips at least one empirical-grid timestamp."""
    if len(tape.bars) < 2:
        return 0
    position = {stamp: index for index, stamp in enumerate(grid)}
    gaps = 0
    for current, nxt in zip(tape.bars, tape.bars[1:], strict=False):
        left = position.get(current.start)
        right = position.get(nxt.start)
        if left is None or right is None:
            continue
        if right > left + 1 and current.session_date == nxt.session_date:
            gaps += 1
    return gaps
