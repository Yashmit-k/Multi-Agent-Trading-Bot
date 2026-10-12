"""Point-in-time regime labels for the frozen today-drop book.

A NIFTY print that ends at the signal is not used for the return or the trend.
The signal day's official daily close is not used. The VIX median uses only
daily closes from earlier sessions.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from statistics import median

from contracts.schemas.market import Candle
from core_features.engine import _sma

from quant_agents.research.rebound import session_date

NIFTY_BUCKETS = (
    "< -1%",
    "-1% to -0.5%",
    "-0.5% to 0%",
    "0% to +0.5%",
    "+0.5% to +1%",
    "> +1%",
    "unavailable",
)
TREND_BUCKETS = ("above", "below", "unavailable")
VIX_BUCKETS = ("below_median", "above_median", "unavailable")
HISTORY = 20


def return_bucket(percent: Decimal) -> str:
    if percent < Decimal("-1"):
        return "< -1%"
    if percent < Decimal("-0.5"):
        return "-1% to -0.5%"
    if percent < 0:
        return "-0.5% to 0%"
    if percent < Decimal("0.5"):
        return "0% to +0.5%"
    if percent <= 1:
        return "+0.5% to +1%"
    return "> +1%"


@dataclass(frozen=True, slots=True)
class _Bar:
    end: datetime
    close: Decimal
    session: date


def _bars(candles: list[Candle], *, one_per_session: bool = False) -> list[_Bar]:
    rows = [_Bar(end=bar.end, close=bar.close, session=session_date(bar.end)) for bar in candles]
    rows.sort(key=lambda bar: bar.end)
    if not one_per_session:
        return rows
    collapsed: list[_Bar] = []
    for bar in rows:
        if collapsed and collapsed[-1].session == bar.session:
            collapsed[-1] = bar
        else:
            collapsed.append(bar)
    return collapsed


@dataclass(slots=True)
class IndexView:
    nifty_5m: list[_Bar]
    nifty_1d: list[_Bar]
    vix: list[_Bar]
    vix_daily: list[_Bar]

    @classmethod
    def build(
        cls,
        nifty_5m: list[Candle],
        nifty_1d: list[Candle],
        vix_5m: list[Candle],
        vix_1d: list[Candle],
    ) -> "IndexView":
        return cls(
            _bars(nifty_5m),
            _bars(nifty_1d, one_per_session=True),
            _bars([*vix_5m, *vix_1d]),
            _bars(vix_1d, one_per_session=True),
        )

    def classify(self, signal_time: datetime) -> dict:
        signal_day = session_date(signal_time)
        spot = _last_before(self.nifty_5m, signal_time, strict=True)
        prior_daily = _last_session_before(self.nifty_1d, signal_day)
        nifty_return = None
        nifty_name = "unavailable"
        trend = "unavailable"
        if spot is not None and prior_daily is not None and prior_daily.close != 0:
            nifty_return = (spot.close - prior_daily.close) / prior_daily.close * Decimal(100)
            nifty_name = return_bucket(nifty_return)
            history = [bar.close for bar in self.nifty_1d if bar.session < signal_day]
            average = _sma([float(close) for close in history], HISTORY)
            if average is not None:
                trend = "above" if spot.close > Decimal(str(average)) else "below"
        level, vix_name, vix_median = self._vix(signal_time, signal_day)
        return {
            "nifty_return_pct": nifty_return,
            "nifty_return_bucket": nifty_name,
            "nifty_trend": trend,
            "vix_level": level,
            "vix_median": vix_median,
            "vix_bucket": vix_name,
        }

    def _vix(self, signal_time: datetime, signal_day: date) -> tuple[Decimal | None, str, Decimal | None]:
        latest = _last_before(self.vix, signal_time, strict=False)
        history = [bar.close for bar in self.vix_daily if bar.session < signal_day]
        if latest is None or len(history) < HISTORY:
            return (latest.close if latest is not None else None, "unavailable", None)
        midpoint = Decimal(str(median([float(close) for close in history])))
        name = "above_median" if latest.close > midpoint else "below_median"
        return latest.close, name, midpoint


def _last_before(bars: list[_Bar], moment: datetime, *, strict: bool) -> _Bar | None:
    if not bars:
        return None
    ends = [bar.end for bar in bars]
    index = (bisect_left(ends, moment) if strict else bisect_right(ends, moment)) - 1
    if index < 0:
        return None
    return bars[index]


def _last_session_before(bars: list[_Bar], day: date) -> _Bar | None:
    if not bars:
        return None
    sessions = [bar.session for bar in bars]
    index = bisect_left(sessions, day) - 1
    if index < 0:
        return None
    return bars[index]


def _positive_years(row: dict) -> int:
    count = 0
    for year in row["years"].values():
        if year["trades"] >= HISTORY and year["net_2"] > 0 and year["net_5"] > 0:
            count += 1
    return count


def _consistently_poor(row: dict) -> bool:
    examined = 0
    for year in row["years"].values():
        if year["trades"] < HISTORY:
            continue
        examined += 1
        if year["net_2"] >= 0 or year["net_5"] >= 0:
            return False
    return examined > 0


def loss_explained_by_regime(rows: list[dict]) -> bool:
    """True only when every 2026 loss bucket was already negative in earlier years."""
    saw_history = False
    for row in rows:
        if row["bucket"] == "unavailable":
            continue
        year_2026 = row["years"].get("2026")
        if year_2026 is None or year_2026["trades"] == 0:
            continue
        if year_2026["net_2"] >= 0 and year_2026["net_5"] >= 0:
            continue
        for name, year in row["years"].items():
            if name == "2026" or year["trades"] < HISTORY:
                continue
            saw_history = True
            if year["net_2"] > 0 or year["net_5"] > 0:
                return False
    return saw_history


def classify_direction(rows: list[dict], *, nifty_5m_count: int, nifty_1d_count: int, unavailable_share: float) -> dict:
    if nifty_5m_count == 0 or nifty_1d_count == 0 or unavailable_share > 0.5:
        return {
            "code": "D",
            "decision": "INSUFFICIENT EVIDENCE",
            "reasons": ["NIFTY bars are missing or most trades have no point-in-time NIFTY return."],
        }
    usable = [row for row in rows if row["bucket"] != "unavailable"]
    profitable = [row for row in usable if row["trades"] >= 30 and row["net_2"] > 0 and row["net_5"] > 0]
    if not profitable:
        return {
            "code": "A",
            "decision": "ABANDON",
            "reasons": ["No NIFTY-return bucket with at least 30 trades is positive at both 2 bp and 5 bp."],
        }
    poor = [row for row in usable if _consistently_poor(row)]
    others = [row for row in usable if row not in poor]
    populated_others = [row for row in others if any(year["trades"] >= HISTORY for year in row["years"].values())]
    if len(poor) == 1 and populated_others and all(_positive_years(row) >= 2 for row in populated_others):
        return {
            "code": "C",
            "decision": "CONTINUE WITH REGIME HYPOTHESIS",
            "reasons": [f"{poor[0]['bucket']} is negative at both costs in every year with at least 20 trades, and the other populated buckets are positive in at least two years."],
        }
    if len(profitable) >= 2:
        return {
            "code": "B",
            "decision": "CONTINUE WITHOUT REGIME FILTER",
            "reasons": ["At least two NIFTY-return buckets are positive at both 2 bp and 5 bp, and the regime-filter rule does not hold."],
        }
    return {
        "code": "D",
        "decision": "INSUFFICIENT EVIDENCE",
        "reasons": ["Fewer than two NIFTY-return buckets clear both costs, and no regime filter meets the out-of-sample rule."],
    }
