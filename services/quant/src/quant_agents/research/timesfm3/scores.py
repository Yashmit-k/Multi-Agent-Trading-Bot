"""Next-session return, cost, and sign score. No model and no candle files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
CLOSE_CLOCK = time(15, 30)
EXCLUDED_SYMBOL = "TATAMOTORS"
MIN_CONTEXT = 32
ENTRY_FEE = Decimal("0.0002")
EXIT_FEE = Decimal("0.0002")
SCORE_YEAR = 2024


@dataclass(frozen=True, slots=True)
class ClosePoint:
    symbol: str
    end: datetime
    close: Decimal

    @property
    def session(self) -> date:
        session = official_session_date(self.end)
        if session is None:
            raise ValueError("close is not a 15:30 IST daily bar")
        return session


@dataclass(frozen=True, slots=True)
class DecisionRow:
    symbol: str
    decision: date
    decision_end: datetime
    next_session: date
    next_end: datetime
    p0: Decimal
    p1: Decimal
    context: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class ScoreSummary:
    scored: int
    nonzero_realized: int
    hits: int
    trade_count: int
    mean_net_all: Decimal
    mean_net_trades: Decimal | None
    mean_price_error: Decimal

    @property
    def hit_rate(self) -> Decimal | None:
        if self.nonzero_realized == 0:
            return None
        return Decimal(self.hits) / Decimal(self.nonzero_realized)


def official_session_date(end: datetime) -> date | None:
    """Date of a daily bar whose end is exactly 15:30 IST."""
    if end.tzinfo is None:
        raise ValueError("bar end must be timezone-aware")
    moment = end.astimezone(IST)
    if moment.timetz().replace(tzinfo=None) != CLOSE_CLOCK:
        return None
    return moment.date()


def net_return(p0: Decimal, p1: Decimal) -> Decimal:
    """`(P1-P0)/P0 - 0.0002 - (P1/P0)*0.0002`. Each fee is applied once."""
    if not isinstance(p0, Decimal) or not isinstance(p1, Decimal) or p0 <= 0 or p1 <= 0:
        raise ValueError("invalid price")
    ratio = p1 / p0
    return (ratio - Decimal(1)) - ENTRY_FEE - ratio * EXIT_FEE


def sign(value: Decimal) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def context_is_safe(context_ends: tuple[datetime, ...] | list[datetime], decision_end: datetime, label_end: datetime) -> bool:
    """Every context bar ends at or before the decision, and the label is strictly later."""
    if label_end <= decision_end:
        return False
    return all(end <= decision_end for end in context_ends)


def decision_rows(points: tuple[ClosePoint, ...] | list[ClosePoint], *, year: int = SCORE_YEAR) -> tuple[DecisionRow, ...]:
    """One next-session row per symbol. 2025 labels and short histories stay out."""
    grouped: dict[str, list[ClosePoint]] = {}
    for point in points:
        if point.symbol == EXCLUDED_SYMBOL:
            continue
        if official_session_date(point.end) is None:
            continue
        grouped.setdefault(point.symbol, []).append(point)
    rows: list[DecisionRow] = []
    for symbol, series in grouped.items():
        ordered = sorted(series, key=lambda item: item.end)
        for index, point in enumerate(ordered):
            if point.session.year != year or index + 1 >= len(ordered):
                continue
            nxt = ordered[index + 1]
            if nxt.session.year != year or nxt.end <= point.end:
                continue
            context_points = ordered[: index + 1]
            if len(context_points) < MIN_CONTEXT:
                continue
            if not context_is_safe([item.end for item in context_points], point.end, nxt.end):
                raise ValueError("context includes a bar after the decision")
            rows.append(
                DecisionRow(
                    symbol=symbol,
                    decision=point.session,
                    decision_end=point.end,
                    next_session=nxt.session,
                    next_end=nxt.end,
                    p0=point.close,
                    p1=nxt.close,
                    context=tuple(item.close for item in context_points),
                )
            )
    return tuple(rows)


def score_forecasts(rows: tuple[DecisionRow, ...] | list[DecisionRow], forecasts: tuple[Decimal, ...] | list[Decimal]) -> ScoreSummary:
    """Long only when the forecast is above P0. A flat forecast contributes zero net."""
    if len(rows) != len(forecasts) or not rows:
        raise ValueError("forecasts must match a non-empty row list")
    hits = 0
    nonzero = 0
    traded_nets: list[Decimal] = []
    contributions: list[Decimal] = []
    errors: list[Decimal] = []
    for row, forecast in zip(rows, forecasts, strict=True):
        if not isinstance(forecast, Decimal) or forecast <= 0:
            raise ValueError("forecast must be a positive price")
        realized = sign(row.p1 - row.p0)
        predicted = sign(forecast - row.p0)
        if realized != 0:
            nonzero += 1
            if predicted != 0 and predicted == realized:
                hits += 1
        errors.append(abs(forecast - row.p1))
        if predicted > 0:
            traded = net_return(row.p0, row.p1)
            traded_nets.append(traded)
            contributions.append(traded)
        else:
            contributions.append(Decimal(0))
    count = Decimal(len(rows))
    mean_trades = sum(traded_nets, Decimal(0)) / Decimal(len(traded_nets)) if traded_nets else None
    return ScoreSummary(
        scored=len(rows),
        nonzero_realized=nonzero,
        hits=hits,
        trade_count=len(traded_nets),
        mean_net_all=sum(contributions, Decimal(0)) / count,
        mean_net_trades=mean_trades,
        mean_price_error=sum(errors, Decimal(0)) / count,
    )


def last_close_forecasts(rows: tuple[DecisionRow, ...] | list[DecisionRow]) -> tuple[Decimal, ...]:
    return tuple(row.p0 for row in rows)


def flat_mean_net(rows: tuple[DecisionRow, ...] | list[DecisionRow]) -> Decimal:
    if not rows:
        raise ValueError("rows must be non-empty")
    return Decimal(0)
