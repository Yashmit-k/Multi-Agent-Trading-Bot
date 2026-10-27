"""Global markets agent: world markets before 09:15 IST -> an expected NIFTY 50 opening gap. Observe-only.

The rules are the pre-registered composite of services/quant/docs/global-markets-protocol.md, unchanged. The study
found it predicts the opening gap (+0.41 / +0.61 / +0.51 Spearman by period) but not returns after the open, so this
agent never trades: fusion gives it weight 0 (core_fusion MARKET_FILTER_AGENTS) and the specialists decision has no
role for it. It publishes one market-level signal on NIFTY50 at 08:45 and 09:10 IST on trading days.

Signal: the composite / 2, clipped to [-1, 1]. Confidence: the trailing 250-session correlation of the composite with
NIFTY's gap (0 if negative). The expected gap is a straight-line fit of the gap on the composite over those sessions.
"""

from __future__ import annotations

import logging
import statistics
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from contracts.enums import AgentName, Exchange, Horizon
from contracts.schemas.agent_signal import AgentSignal

logger = logging.getLogger(__name__)
AGENT_VERSION = "1.0.0"
IST = ZoneInfo("Asia/Kolkata")
SLOTS = (time(8, 45), time(9, 10))
SESSION_CLOSE = time(15, 30)
WINDOW = 250
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# name -> (Yahoo symbol, kind, sign): "close" = latest close before D vs the one before the previous Indian session;
# "asia_gap" = open of D vs the previous close. The sign makes "good for risk" positive.
INPUTS: dict[str, tuple[str, str, int]] = {
    "sp500": ("^GSPC", "close", 1),
    "nasdaq": ("^IXIC", "close", 1),
    "vix": ("^VIX", "close", -1),
    "nikkei": ("^N225", "asia_gap", 1),
    "kospi": ("^KS11", "asia_gap", 1),
    "hang_seng": ("^HSI", "asia_gap", 1),
    "brent": ("BZ=F", "close", -1),
    "usdinr": ("INR=X", "close", -1),
    "dollar": ("DX-Y.NYB", "close", -1),
    "us10y": ("^TNX", "close", -1),
}
ASIA = ("nikkei", "kospi", "hang_seng")
COMPOSITE = ("sp500", "nasdaq", "asia", "vix", "brent", "usdinr", "dollar", "us10y")
NIFTY = "^NSEI"

Bars = list[tuple[date, float, float]]  # (exchange-local date, open, close), sorted


class InsufficientHistory(ValueError):
    pass


def parse_chart(payload: Mapping) -> Bars:
    result = payload["chart"]["result"][0]
    zone = ZoneInfo(result["meta"]["exchangeTimezoneName"])
    quote = result["indicators"]["quote"][0]
    out: dict[date, tuple[float, float]] = {}
    for stamp, o, c in zip(result.get("timestamp") or [], quote["open"], quote["close"]):
        if o is None or c is None or not (o > 0 and c > 0):
            continue
        out[datetime.fromtimestamp(stamp, zone).date()] = (float(o), float(c))
    return [(d, o, c) for d, (o, c) in sorted(out.items())]


def fetch_all(client: httpx.Client) -> dict[str, Bars]:
    """About three years of daily bars for every input and NIFTY (two windows of history are needed)."""
    out = {}
    for name, symbol in [(name, spec[0]) for name, spec in INPUTS.items()] + [("nifty", NIFTY)]:
        response = client.get(CHART_URL.format(symbol=symbol), params={"range": "3y", "interval": "1d"}, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        out[name] = parse_chart(response.json())
    return out


def _last_before(dates: list[date], day: date) -> int:
    """Index of the last bar dated before day, or -1."""
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] < day:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


def input_value(bars: Bars, kind: str, day: date, previous: date) -> float:
    """One input for Indian session `day` (previous = the Indian session before it). 0 when nothing new is known."""
    dates = [d for d, _, _ in bars]
    if kind == "close":
        k, k_prev = _last_before(dates, day), _last_before(dates, previous)
        return bars[k][2] / bars[k_prev][2] - 1 if k > k_prev >= 0 else 0.0
    k = _last_before(dates, day) + 1
    if k < len(bars) and dates[k] == day and k > 0:
        return bars[k][1] / bars[k - 1][2] - 1
    return 0.0


def _quantile(values: list[float], q: float) -> float:
    """Linear interpolation between order statistics (numpy's default)."""
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def outlook(bars: Mapping[str, Bars], day: date) -> dict[str, object]:
    """The composite and expected NIFTY gap for Indian session `day`, from bars known before its open."""
    nifty = [bar for bar in bars["nifty"] if bar[0] < day]
    sessions = [d for d, _, _ in nifty] + [day]
    n = len(sessions)
    if n < 2 * WINDOW + 2:
        raise InsufficientHistory(f"{n} sessions, need {2 * WINDOW + 2}")
    raw: dict[str, list[float]] = {}
    for name, (_, kind, sign) in INPUTS.items():
        raw[name] = [0.0] + [sign * input_value(bars[name], kind, sessions[i], sessions[i - 1]) for i in range(1, n)]
    raw["asia"] = [sum(raw[name][i] for name in ASIA) / len(ASIA) for i in range(n)]

    def scaled(name: str, i: int) -> float:
        sd = statistics.pstdev(raw[name][i - WINDOW: i])
        return raw[name][i] / sd if sd > 0 else 0.0

    composite = [0.0] * n
    for i in range(WINDOW, n):
        composite[i] = sum(scaled(name, i) for name in COMPOSITE) / len(COMPOSITE)
    today = n - 1
    past = range(today - WINDOW, today)
    low = _quantile([composite[i] for i in past], 0.2)
    high = _quantile([composite[i] for i in past], 0.8)
    gaps = {i: nifty[i][1] / nifty[i - 1][2] - 1 for i in past}
    xs, ys = [composite[i] for i in past], [gaps[i] for i in past]
    slope, intercept = statistics.linear_regression(xs, ys)
    residual = statistics.pstdev([y - (intercept + slope * x) for x, y in zip(xs, ys)])
    expected = intercept + slope * composite[today]
    value = composite[today]
    return {
        "session_date": day.isoformat(),
        "composite": value,
        "risk_off": value <= low,
        "risk_on": value >= high,
        "risk_off_threshold": low,
        "risk_on_threshold": high,
        "expected_gap_pct": expected * 100,
        "expected_gap_range_pct": [(expected - residual) * 100, (expected + residual) * 100],
        "fit": {"slope_pct": slope * 100, "intercept_pct": intercept * 100, "correlation": statistics.correlation(xs, ys), "sessions": WINDOW},
        "inputs": {
            name: {"symbol": INPUTS[name][0] if name in INPUTS else "+".join(INPUTS[a][0] for a in ASIA), "move_pct": raw[name][today] * 100 * (INPUTS[name][2] if name in INPUTS else 1), "z": scaled(name, today)}
            for name in (*INPUTS, "asia")
        },
        "previous_session": sessions[-2].isoformat(),
    }


def build_signal(view: Mapping[str, object], now: datetime, slot: time) -> AgentSignal:
    day = date.fromisoformat(str(view["session_date"]))
    composite = float(view["composite"])  # type: ignore[arg-type]
    fit = view["fit"]
    confidence = float(fit["correlation"])  # type: ignore[index]
    reasons = ["global.risk_off" if view["risk_off"] else "global.risk_on" if view["risk_on"] else "global.neutral", "global.observe_only"]
    close = datetime.combine(day, SESSION_CLOSE, IST).astimezone(timezone.utc)
    moment = now.astimezone(timezone.utc)
    inputs = view["inputs"]
    return AgentSignal(
        signal_id=f"global-markets-{day.isoformat()}-{slot.strftime('%H%M')}",
        symbol="NIFTY50",
        exchange=Exchange.NSE,
        agent_name=AgentName.GLOBAL_MARKETS,
        agent_version=AGENT_VERSION,
        timestamp=moment,
        as_of=moment,
        horizon=Horizon.INTRADAY,
        signal=max(-1.0, min(1.0, composite / 2)),
        confidence=max(0.0, min(1.0, confidence)),
        valid_until=max(close, moment),
        reason_codes=reasons,
        features={f"{name}_move_pct": round(float(item["move_pct"]), 4) for name, item in inputs.items()},  # type: ignore[union-attr]
        metadata={**view, "observe_only": True, "slot_ist": slot.strftime("%H:%M"), "protocol": "services/quant/docs/global-markets-protocol.md"},
    )


def due_slot(now: datetime, done: set[tuple[date, time]], is_trading_day) -> time | None:
    """The latest slot that has passed today and not yet run, before the close on a trading day."""
    local = now.astimezone(IST)
    if local.time() >= SESSION_CLOSE or not is_trading_day(local.date()):
        return None
    passed = [slot for slot in SLOTS if local.time() >= slot]
    if not passed or (local.date(), passed[-1]) in done:
        return None
    return passed[-1]


def run_once(sink, now: datetime, slot: time, *, client: httpx.Client | None = None) -> AgentSignal:
    owned = client or httpx.Client(timeout=30.0)
    try:
        bars = fetch_all(owned)
    finally:
        if client is None:
            owned.close()
    signal = build_signal(outlook(bars, now.astimezone(IST).date()), now, slot)
    result = sink.submit(signal)
    meta = signal.metadata
    logger.info("global_markets slot=%s expected_gap_pct=%.2f composite=%.2f risk_off=%s accepted=%s", slot, meta["expected_gap_pct"], meta["composite"], meta["risk_off"], getattr(result, "accepted", None))
    return signal


def trading_day(day: date) -> bool:
    from quant_agents.calendar.static_nse import StaticNseCalendar

    calendar = StaticNseCalendar()
    if calendar.covers(day):
        return calendar.is_trading_day(day)
    return day.weekday() < 5


RETRY = timedelta(minutes=5)
