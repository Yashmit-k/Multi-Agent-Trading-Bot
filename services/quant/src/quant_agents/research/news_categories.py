"""Pre-registered event study: news-category volume spikes versus the NIFTY 50 index.

The rules live in services/quant/docs/news-categories-nifty-protocol.md.
This module does not score agents, place orders, or change fusion.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np


IST = timezone(timedelta(hours=5, minutes=30))
SESSION_CLOSE = time(15, 30)
SESSION_OPEN = time(9, 15)
GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
VOLUME_START = date(2017, 1, 1)
TRAIN_START = date(2017, 1, 1)
TRAIN_END = date(2022, 12, 31)
VALIDATE_START = date(2023, 1, 1)
RV_START = date(2024, 1, 1)
WINDOW = 60
Z_SCORE = 2.0
BLOCK = 5
N_BOOT = 5000
BOOT_SEED = 0
MISMATCH_TOLERANCE = 0.005

OUTCOMES: tuple[str, ...] = (
    "ret_0",
    "ret_1",
    "ret_1_5",
    "abs_0",
    "abs_1",
    "abs_1_5",
    "vix_0",
    "vix_1",
    "vix_1_5",
    "rv_0",
    "rv_1",
    "rv_1_5",
)

# Queries are the protocol text, character for character.
CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "geopolitics_war",
        "Geopolitics and war",
        (
            '(war OR warfare OR invasion OR bombardment OR "missile strike" OR "missile strikes" OR "military escalation" OR "terror attack" OR "terrorist attack")',
            '("India Pakistan" OR "India-Pakistan" OR "Line of Control") AND (strike OR attack OR shelling OR ceasefire OR tension OR conflict)',
            '("India China" OR "India-China" OR Galwan OR Ladakh OR "Line of Actual Control") AND (clash OR standoff OR incursion OR tension OR border)',
        ),
    ),
    (
        "crude_commodities",
        "Crude oil and commodity shocks",
        (
            '(crude OR brent OR OPEC OR "oil price" OR "oil prices") AND (surge OR jump OR plunge OR shock OR spike OR slump OR embargo OR "supply cut")',
            '("commodity prices" OR "commodities selloff" OR "gold price") AND (surge OR jump OR plunge OR shock OR record)',
        ),
    ),
    (
        "central_banks",
        "Central banks",
        (
            '("Reserve Bank of India" OR "repo rate" OR "monetary policy committee" OR "RBI policy")',
            '("Federal Reserve" OR FOMC OR "Fed rate" OR "interest rate decision") AND (hike OR cut OR hold OR pause OR decision)',
        ),
    ),
    (
        "inflation_macro",
        "Inflation and macro data",
        (
            '(CPI OR "consumer price index" OR "retail inflation" OR "wholesale inflation") AND (India OR Indian)',
            '(GDP OR "gross domestic product" OR IIP OR "industrial production") AND (India OR Indian)',
        ),
    ),
    (
        "india_policy",
        "Indian government policy, budget, and tax",
        (
            '("Union Budget" OR "India budget" OR "finance bill") AND (India OR Indian)',
            '(GST OR "tax cut" OR "tax hike" OR "import duty" OR "government policy") AND (India OR Indian OR "New Delhi")',
        ),
    ),
    (
        "elections",
        "Elections and political instability",
        (
            '("Lok Sabha" OR "assembly election" OR "general election" OR "vote counting") AND (India OR Indian)',
            '("political crisis" OR "no-confidence" OR "coalition" OR resignation) AND (India OR "prime minister" OR "chief minister")',
        ),
    ),
    (
        "global_selloff",
        "Global market sell-offs",
        (
            '("S&P 500" OR Nasdaq OR "Dow Jones" OR "Wall Street") AND (plunge OR selloff OR "sell-off" OR crash OR tumble OR slump)',
            '(Shanghai OR "Hong Kong stocks" OR "China stocks" OR "CSI 300") AND (plunge OR selloff OR crash OR tumble OR slump)',
        ),
    ),
    (
        "fii_rupee",
        "Foreign investor flows and the rupee",
        (
            '(FII OR FPI OR "foreign institutional" OR "foreign portfolio") AND (outflow OR inflow OR selling OR buying OR selloff)',
            '(rupee) AND (slide OR slump OR "record low" OR "all-time low" OR depreciation OR weakens OR tumbles)',
        ),
    ),
    (
        "disasters_pandemics",
        "Disasters and pandemics",
        (
            "(pandemic OR COVID OR COVID-19 OR coronavirus OR lockdown)",
            "(earthquake OR cyclone OR flood OR landslide) AND (India OR Indian)",
        ),
    ),
    (
        "trade_wars",
        "Trade wars, tariffs, and sanctions",
        (
            '("trade war" OR tariff OR tariffs OR sanctions OR "trade dispute") AND (China OR India OR "United States" OR US OR Trump OR Biden)',
        ),
    ),
)



def event_flags(volume: Sequence[float], *, window: int = WINDOW, z: float = Z_SCORE) -> list[bool]:
    """True when today's volume is at least z sample-SDs above the previous `window` days.

    Index i uses volume[i - window : i] only. The value at i, and everything after it,
    cannot change a flag at or before i.
    """
    if window < 2:
        raise ValueError("window must be at least 2")
    values = [float(item) for item in volume]
    flags = [False] * len(values)
    for index in range(window, len(values)):
        past = values[index - window : index]
        mean = sum(past) / window
        var = sum((item - mean) ** 2 for item in past) / (window - 1)
        if var <= 0.0:
            continue
        if values[index] >= mean + z * math.sqrt(var):
            flags[index] = True
    return flags




def _as_ist(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return moment.astimezone(IST)


def assign_timestamp(moment: datetime, sessions: Sequence[date]) -> date | None:
    """Session that may trade on a timestamped headline.

    Before 15:30 IST on a session, that session. At 15:30 or later, or on a
    day that is not a session, the next session after the IST date.
    """
    ist = _as_ist(moment)
    day = ist.date()
    ordered = tuple(sorted(sessions))
    if day in set(ordered) and ist.time() < SESSION_CLOSE:
        return day
    for session in ordered:
        if session > day:
            return session
    return None


def assign_gdelt_day(day: date, sessions: Sequence[date]) -> date | None:
    """GDELT daily buckets have no clock, so they always take the next session."""
    for session in sorted(sessions):
        if session > day:
            return session
    return None


def event_sessions(days: Sequence[tuple[date, bool]], sessions: Sequence[date]) -> set[date]:
    """Map event calendar days onto sessions. Two days can share one session."""
    found: set[date] = set()
    for day, flag in days:
        if not flag:
            continue
        session = assign_gdelt_day(day, sessions)
        if session is not None:
            found.add(session)
    return found



def _dates(*items: str) -> frozenset[date]:
    return frozenset(date.fromisoformat(item) for item in items)


# 2017-2023 are frozen in the protocol. 2024-2026 match static-nse-2024-2026.1.
CASH_HOLIDAYS: frozenset[date] = _dates(
    "2017-01-26", "2017-02-24", "2017-03-13", "2017-04-04", "2017-04-14", "2017-05-01",
    "2017-06-26", "2017-08-15", "2017-08-25", "2017-10-02", "2017-10-19", "2017-10-20", "2017-12-25",
    "2018-01-26", "2018-02-13", "2018-03-02", "2018-03-29", "2018-03-30", "2018-05-01",
    "2018-08-15", "2018-08-22", "2018-09-13", "2018-09-20", "2018-10-02", "2018-10-18",
    "2018-11-07", "2018-11-08", "2018-11-23", "2018-12-25",
    "2019-03-04", "2019-03-21", "2019-04-17", "2019-04-19", "2019-04-29", "2019-05-01",
    "2019-06-05", "2019-08-12", "2019-08-15", "2019-09-02", "2019-09-10", "2019-10-02",
    "2019-10-08", "2019-10-21", "2019-10-27", "2019-10-28", "2019-11-12", "2019-12-25",
    "2020-02-21", "2020-03-10", "2020-04-02", "2020-04-06", "2020-04-10", "2020-04-14",
    "2020-05-01", "2020-05-25", "2020-10-02", "2020-11-14", "2020-11-16", "2020-11-30", "2020-12-25",
    "2021-01-26", "2021-03-11", "2021-03-29", "2021-04-02", "2021-04-14", "2021-04-21",
    "2021-05-13", "2021-07-21", "2021-08-19", "2021-09-10", "2021-10-15", "2021-11-04",
    "2021-11-05", "2021-11-19",
    "2022-01-26", "2022-03-01", "2022-03-18", "2022-04-14", "2022-04-15", "2022-05-03",
    "2022-08-09", "2022-08-15", "2022-08-31", "2022-10-05", "2022-10-24", "2022-10-26", "2022-11-08",
    "2023-01-26", "2023-03-07", "2023-03-30", "2023-04-04", "2023-04-07", "2023-04-14",
    "2023-05-01", "2023-06-28", "2023-08-15", "2023-09-19", "2023-10-02", "2023-10-24",
    "2023-11-12", "2023-11-14", "2023-11-27", "2023-12-25",
    "2024-01-22", "2024-01-26", "2024-03-08", "2024-03-25", "2024-03-29", "2024-04-11",
    "2024-04-17", "2024-05-01", "2024-05-20", "2024-06-17", "2024-07-17", "2024-08-15",
    "2024-10-02", "2024-11-01", "2024-11-15", "2024-12-25",
    "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10", "2025-04-14", "2025-04-18",
    "2025-05-01", "2025-08-15", "2025-08-27", "2025-10-02", "2025-10-21", "2025-10-22",
    "2025-11-05", "2025-12-25",
    "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31", "2026-04-01", "2026-04-03",
    "2026-04-14", "2026-05-01", "2026-05-27", "2026-06-26", "2026-08-15", "2026-09-14",
    "2026-10-02", "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25",
)


def trading_sessions(closes: Mapping[date, float], holidays: Iterable[date] = CASH_HOLIDAYS) -> list[date]:
    """Weekday dates with a close that are not on the frozen holiday list."""
    closed = set(holidays)
    return [day for day in sorted(closes) if day.weekday() < 5 and day not in closed]


def calendar_audit(closes: Mapping[date, float], holidays: Iterable[date] = CASH_HOLIDAYS) -> dict[str, int]:
    closed = set(holidays)
    weekend_closes = sum(1 for day in closes if day.weekday() >= 5)
    holiday_closes = sum(1 for day in closes if day.weekday() < 5 and day in closed)
    return {"weekend_closes_dropped": weekend_closes, "holiday_closes_dropped": holiday_closes}



PUBLIC_DAILY_NIFTY = "https://13-238-176-73.sslip.io/api/v1/market/candles/NIFTY50?timeframe=1d&limit=2000"
PUBLIC_DAILY_VIX = "https://13-238-176-73.sslip.io/api/v1/market/candles/INDIAVIX?timeframe=1d&limit=2000"
PUBLIC_INTRADAY_NIFTY = "https://13-238-176-73.sslip.io/api/v1/market/candles/NIFTY50?timeframe=5m&limit=2000"


def close_mismatches(
    yahoo: Mapping[date, float],
    api: Mapping[date, float],
    *,
    tolerance: float = MISMATCH_TOLERANCE,
) -> list[dict[str, float | str]]:
    """Sessions where the two closes differ by more than half of one percent."""
    rows: list[dict[str, float | str]] = []
    for day in sorted(set(yahoo) & set(api)):
        api_close = float(api[day])
        yahoo_close = float(yahoo[day])
        if api_close == 0:
            continue
        gap = abs(yahoo_close / api_close - 1.0)
        if gap > tolerance:
            rows.append(
                {
                    "date": day.isoformat(),
                    "yahoo": yahoo_close,
                    "api": api_close,
                    "abs_pct": gap,
                }
            )
    return rows


def alignment_report(yahoo: Mapping[date, float], api: Mapping[date, float]) -> dict[str, object]:
    """Compare two close series. On an overlap the API close is the one kept."""
    yahoo_days = set(yahoo)
    api_days = set(api)
    mismatches = close_mismatches(yahoo, api)
    return {
        "overlap": len(yahoo_days & api_days),
        "yahoo_only": len(yahoo_days - api_days),
        "api_only": len(api_days - yahoo_days),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "preferred_on_overlap": "api",
    }


def prefer_api(yahoo: Mapping[date, float], api: Mapping[date, float]) -> dict[date, float]:
    """API close wins on overlap. Yahoo fills dates the API does not have."""
    merged = {day: float(value) for day, value in yahoo.items()}
    merged.update({day: float(value) for day, value in api.items()})
    return merged


def _parse_moment(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_api_daily(payload: object) -> dict[date, float]:
    if not isinstance(payload, list):
        raise ValueError("daily candle payload is not a list")
    closes: dict[date, float] = {}
    for bar in payload:
        if not isinstance(bar, dict) or "close" not in bar or "end" not in bar:
            continue
        end = _parse_moment(str(bar["end"]))
        closes[end.astimezone(IST).date()] = float(bar["close"])
    return closes


def parse_api_intraday(payload: object) -> list[tuple[datetime, float]]:
    """5-minute bars as (IST start, close). Bars outside the cash session are dropped."""
    if not isinstance(payload, list):
        raise ValueError("intraday candle payload is not a list")
    bars: list[tuple[datetime, float]] = []
    for bar in payload:
        if not isinstance(bar, dict) or "close" not in bar or "start" not in bar:
            continue
        start = _parse_moment(str(bar["start"])).astimezone(IST)
        if start.date() < RV_START:
            continue
        if start.time() < SESSION_OPEN or start.time() >= SESSION_CLOSE:
            continue
        bars.append((start, float(bar["close"])))
    bars.sort(key=lambda item: item[0])
    return bars


def session_realised_variance(bars: Sequence[tuple[datetime, float]]) -> dict[date, float]:
    """Sum of squared log returns. Sessions with fewer than two bars are absent."""
    grouped: dict[date, list[tuple[datetime, float]]] = {}
    for start, close in bars:
        grouped.setdefault(start.astimezone(IST).date(), []).append((start, close))
    out: dict[date, float] = {}
    for day, items in grouped.items():
        items.sort(key=lambda item: item[0])
        closes = [close for _, close in items]
        if len(closes) < 2:
            continue
        total = 0.0
        usable = 0
        for left, right in zip(closes, closes[1:]):
            if left <= 0 or right <= 0:
                continue
            change = math.log(right / left)
            total += change * change
            usable += 1
        if usable:
            out[day] = total
    return out




def gdelt_windows(start: date, end: date, *, span_days: int = 700) -> list[tuple[str, str]]:
    """Inclusive UTC windows. GDELT 429s the full 2017-to-today call, so the span is sliced.

    The queries, modes, and covered dates stay the ones in the protocol.
    """
    if span_days < 1:
        raise ValueError("span_days must be positive")
    if end < start:
        raise ValueError("end before start")
    windows: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        stop = min(end, cursor + timedelta(days=span_days - 1))
        windows.append((cursor.strftime("%Y%m%d") + "000000", stop.strftime("%Y%m%d") + "000000"))
        cursor = stop + timedelta(days=1)
    return windows


def gdelt_request_url(query: str, mode: str, start: str, end: str) -> str:
    params = {
        "query": query,
        "mode": mode,
        "format": "json",
        "startdatetime": start,
        "enddatetime": end,
    }
    return GDELT_DOC + "?" + urllib.parse.urlencode(params)


def parse_stamped(payload: object) -> list[tuple[str, date, float]]:
    if not isinstance(payload, dict):
        raise ValueError("GDELT payload is not an object")
    timeline = payload.get("timeline") or []
    if not timeline:
        return []
    data = timeline[0].get("data") or []
    points: list[tuple[str, date, float]] = []
    for row in data:
        stamp = str(row["date"])
        digits = "".join(ch for ch in stamp if ch.isdigit())
        if len(digits) < 8:
            raise ValueError(f"bad GDELT date {stamp}")
        day = date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
        points.append((stamp, day, float(row["value"])))
    return points


def volume_by_day(points: Sequence[tuple[str, date, float]]) -> dict[date, float]:
    totals: dict[date, float] = {}
    for _stamp, day, value in points:
        totals[day] = totals.get(day, 0.0) + value
    return totals


def tone_by_day(
    tone_points: Sequence[tuple[str, date, float]],
    volume_points: Sequence[tuple[str, date, float]],
) -> dict[date, float]:
    """Volume-weighted tone inside each UTC date. Equal weights when volume is missing."""
    weights: dict[str, float] = {}
    for stamp, _day, value in volume_points:
        weights[stamp] = weights.get(stamp, 0.0) + value
    buckets: dict[date, list[tuple[float, float | None]]] = {}
    for stamp, day, tone in tone_points:
        weight = weights.get(stamp)
        buckets.setdefault(day, []).append((tone, weight))
    out: dict[date, float] = {}
    for day, rows in buckets.items():
        weighted = [(tone, weight) for tone, weight in rows if weight]
        denom = sum(weight for _, weight in weighted)
        if denom > 0:
            out[day] = sum(tone * weight for tone, weight in weighted) / denom
        else:
            out[day] = sum(tone for tone, _ in rows) / len(rows)
    return out


def filled_volume(daily: Mapping[date, float], start: date, end: date) -> list[tuple[date, float]]:
    """Calendar days from start through end. A day GDELT did not return is volume 0."""
    if end < start:
        return []
    rows: list[tuple[date, float]] = []
    day = start
    while day <= end:
        rows.append((day, float(daily.get(day, 0.0))))
        day += timedelta(days=1)
    return rows


def sum_category_volume(parts: Sequence[Mapping[date, float]], start: date, end: date) -> list[tuple[date, float]]:
    combined: dict[date, float] = {}
    for part in parts:
        for day, value in part.items():
            combined[day] = combined.get(day, 0.0) + float(value)
    return filled_volume(combined, start, end)


class IncompleteCoverage(RuntimeError):
    """A category is missing fetched days. Those days are not zeros."""

    def __init__(self, missing_days: dict[str, int]) -> None:
        self.missing_days = missing_days
        detail = ", ".join(f"{key}={value}" for key, value in missing_days.items())
        super().__init__(f"GDELT volume is incomplete ({detail})")


def combine_observed(
    parts: Sequence[Mapping[date, float]], start: date, end: date
) -> tuple[list[tuple[date, float]], int]:
    """Sum query volumes only on days every query has already observed.

    A day missing from any query is counted as missing. It is not appended as 0.
    """
    if end < start:
        return [], 0
    if not parts:
        raise ValueError("a category needs at least one query")
    rows: list[tuple[date, float]] = []
    missing = 0
    day = start
    while day <= end:
        if all(day in part for part in parts):
            rows.append((day, sum(float(part[day]) for part in parts)))
        else:
            missing += 1
        day += timedelta(days=1)
    return rows, missing


def retry_after_seconds(response: object) -> float | None:
    """Honor a numeric Retry-After, capped at two minutes. Absent or junk headers are ignored."""
    headers = getattr(response, "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(seconds, 120.0)




def cache_file(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.json"


def write_cache_atomic(path: Path, text: str) -> None:
    """Write the whole body, then replace. A crash leaves the previous file intact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _is_gdelt_url(url: str) -> bool:
    return "gdeltproject.org" in url


def _query_param(url: str, name: str) -> str | None:
    values = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get(name)
    if not values:
        return None
    return values[0]


def gdelt_payload_problem(payload: object, *, query: str | None = None, mode: str | None = None) -> str | None:
    """Reject a body that cannot prove which days GDELT answered.

    An empty timeline is not a run of zero-article days. A title that disagrees
    with the requested query is a different request and must not be reused.
    """
    if not isinstance(payload, dict):
        return "malformed payload"
    timeline = payload.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        return "empty timeline"
    block = timeline[0]
    if not isinstance(block, dict):
        return "malformed timeline"
    data = block.get("data")
    if not isinstance(data, list) or not data:
        return "empty data"
    series = str(block.get("series") or "")
    expected = {"timelinevolraw": "Article Count", "timelinetone": "Average Tone"}.get(mode or "")
    if expected and series and series != expected:
        return "wrong series"
    details = payload.get("query_details")
    if query and isinstance(details, dict):
        recorded = str(details.get("title") or "")
        if recorded and recorded != query:
            return "query mismatch"
    for row in data:
        if not isinstance(row, dict) or "date" not in row or "value" not in row:
            return "malformed point"
    return None


# Extra waits used only when GDELT answers 429. They are not part of the study design.
GDELT_RETRY_PAUSES: tuple[float, ...] = (15.0, 30.0, 60.0, 90.0)


def fetch_json(
    url: str,
    cache_dir: Path,
    client: object,
    sleeper: Callable[[float], None],
    *,
    pause: float = 5.0,
    attempts: int | None = None,
) -> tuple[object, bool]:
    """Return (payload, did_http). Sleep only after a cache miss, never between hits.

    A 429 is retried with the pauses above. A cached file is still returned with no sleep.
    """
    path = cache_file(cache_dir, url)
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cached = None
        if cached is not None and (
            not _is_gdelt_url(url)
            or gdelt_payload_problem(cached, query=_query_param(url, "query"), mode=_query_param(url, "mode")) is None
        ):
            return cached, False
    limit = len(GDELT_RETRY_PAUSES) + 1 if attempts is None else attempts
    if limit < 1:
        raise ValueError("attempts must be positive")
    forced: float | None = None
    for attempt in range(limit):
        if attempt:
            sleeper(forced if forced is not None else GDELT_RETRY_PAUSES[attempt - 1])
            forced = None
        response = None
        last_error: Exception | None = None
        for _try in range(3):
            try:
                response = client.get(url)  # type: ignore[attr-defined]
                break
            except Exception as exc:
                last_error = exc
                sleeper(10.0)
        if response is None:
            raise RuntimeError(f"GDELT request failed: {url}") from last_error
        status = int(getattr(response, "status_code", 200))
        if status == 429:
            forced = retry_after_seconds(response)
            continue
        response.raise_for_status()
        text = response.text
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"GDELT did not return JSON: {text[:180]}") from exc
        if _is_gdelt_url(url):
            problem = gdelt_payload_problem(payload, query=_query_param(url, "query"), mode=_query_param(url, "mode"))
            if problem:
                raise RuntimeError(f"GDELT payload rejected: {problem}")
        write_cache_atomic(path, text)
        sleeper(pause)
        return payload, True
    raise RuntimeError(f"GDELT kept returning 429: {url}")




@dataclass(frozen=True)
class MeanDiff:
    diff: float | None
    p: float
    event_mean: float | None
    other_mean: float | None
    n_event: int
    n_other: int
    draws: tuple[float, ...]
    ci_low: float | None = None
    ci_high: float | None = None


def _finite_pairs(values: Sequence[float], event: Sequence[bool]) -> tuple[np.ndarray, np.ndarray]:
    if len(values) != len(event):
        raise ValueError("values and event mask differ in length")
    ys: list[float] = []
    es: list[bool] = []
    for value, flag in zip(values, event):
        if value is None or not math.isfinite(float(value)):
            continue
        ys.append(float(value))
        es.append(bool(flag))
    return np.asarray(ys, dtype=float), np.asarray(es, dtype=bool)


def block_bootstrap_diff(
    values: Sequence[float],
    event: Sequence[bool],
    *,
    block: int = BLOCK,
    n_boot: int = N_BOOT,
    seed: int = BOOT_SEED,
) -> MeanDiff:
    """Unmatched difference of means and a recentered circular block-bootstrap p-value."""
    y, mask = _finite_pairs(values, event)
    n_event = int(mask.sum())
    n_other = int((~mask).sum())
    if n_event < 2 or n_other < 2:
        return MeanDiff(None, 1.0, None, None, n_event, n_other, ())
    observed = float(y[mask].mean() - y[~mask].mean())
    n = len(y)
    generator = np.random.Generator(np.random.PCG64(seed))
    n_blocks = int(math.ceil(n / block))
    starts = generator.integers(0, n, size=(n_boot, n_blocks))
    offsets = np.arange(block)
    index = (starts[..., None] + offsets) % n
    index = index.reshape(n_boot, n_blocks * block)[:, :n]
    samples = y[index]
    flags = mask[index]
    event_n = flags.sum(axis=1)
    other_n = n - event_n
    event_sum = (samples * flags).sum(axis=1)
    other_sum = samples.sum(axis=1) - event_sum
    ok = (event_n > 0) & (other_n > 0)
    draws = np.full(n_boot, observed, dtype=float)
    draws[ok] = event_sum[ok] / event_n[ok] - other_sum[ok] / other_n[ok]
    # 1e-8 relative slack keeps a float tie on the protocol's >= side.
    gap = np.abs(draws - observed)
    slack = 1e-8 * max(1.0, abs(observed))
    p_value = (1.0 + float(np.sum(gap + slack >= np.abs(observed)))) / (n_boot + 1.0)
    low, high = np.quantile(draws, [0.025, 0.975])
    return MeanDiff(
        observed,
        float(p_value),
        float(y[mask].mean()),
        float(y[~mask].mean()),
        n_event,
        n_other,
        tuple(float(item) for item in draws),
        float(low),
        float(high),
    )




def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Holm adjusted p-values, in the original order, capped at 1."""
    p = [float(item) for item in p_values]
    order = sorted(range(len(p)), key=lambda index: (p[index], index))
    adjusted = [1.0] * len(p)
    running = 0.0
    m = len(p)
    for rank, index in enumerate(order):
        step = min(1.0, (m - rank) * p[index])
        running = max(running, step)
        adjusted[index] = running
    return adjusted




def _pct(curr: float | None, prev: float | None) -> float:
    if curr is None or prev is None or prev == 0 or not math.isfinite(curr) or not math.isfinite(prev):
        return math.nan
    return curr / prev - 1.0


def build_outcomes(
    sessions: Sequence[date],
    nifty: Mapping[date, float],
    vix: Mapping[date, float],
    rv: Mapping[date, float],
    in_split: Sequence[bool],
) -> dict[str, list[float]]:
    """Outcome rows for sessions inside the split.

    A forward window that would read a session outside the split is missing.
    The previous close used by a session's own return may sit just before the split.
    """
    if len(sessions) != len(in_split):
        raise ValueError("split mask length")
    n = len(sessions)
    close = [float(nifty[day]) if day in nifty else math.nan for day in sessions]
    vix_close = [float(vix[day]) if day in vix else math.nan for day in sessions]
    ret = [math.nan] * n
    vix_chg = [math.nan] * n
    for index in range(1, n):
        ret[index] = _pct(close[index], close[index - 1])
        vix_chg[index] = _pct(vix_close[index], vix_close[index - 1])
    columns = {name: [math.nan] * n for name in OUTCOMES}

    def inside(index: int) -> bool:
        return 0 <= index < n and bool(in_split[index])

    for index in range(n):
        if not in_split[index]:
            continue
        if math.isfinite(ret[index]):
            columns["ret_0"][index] = ret[index]
            columns["abs_0"][index] = abs(ret[index])
        if math.isfinite(vix_chg[index]):
            columns["vix_0"][index] = vix_chg[index]
        rv_0 = rv.get(sessions[index])
        if rv_0 is not None and sessions[index] >= RV_START:
            columns["rv_0"][index] = float(rv_0)
        if inside(index + 1) and math.isfinite(ret[index + 1]):
            columns["ret_1"][index] = ret[index + 1]
            columns["abs_1"][index] = abs(ret[index + 1])
        if inside(index + 1) and math.isfinite(vix_chg[index + 1]):
            columns["vix_1"][index] = vix_chg[index + 1]
        nxt = rv.get(sessions[index + 1]) if inside(index + 1) else None
        if nxt is not None and sessions[index + 1] >= RV_START:
            columns["rv_1"][index] = float(nxt)
        if inside(index + 5) and all(inside(index + step) for step in range(1, 6)):
            if math.isfinite(close[index]) and math.isfinite(close[index + 5]) and close[index] != 0:
                cumulative = close[index + 5] / close[index] - 1.0
                columns["ret_1_5"][index] = cumulative
                columns["abs_1_5"][index] = abs(cumulative)
            if math.isfinite(vix_close[index]) and math.isfinite(vix_close[index + 5]) and vix_close[index] != 0:
                columns["vix_1_5"][index] = vix_close[index + 5] / vix_close[index] - 1.0
            window = []
            for step in range(1, 6):
                value = rv.get(sessions[index + step])
                if value is None or sessions[index + step] < RV_START:
                    window = []
                    break
                window.append(float(value))
            if len(window) == 5:
                columns["rv_1_5"][index] = sum(window) / 5.0
    return columns


def split_flags(sessions: Sequence[date], start: date, end: date | None) -> list[bool]:
    """True for sessions inside the inclusive start and optional inclusive end."""
    flags = []
    for day in sessions:
        if day < start:
            flags.append(False)
        elif end is not None and day > end:
            flags.append(False)
        else:
            flags.append(True)
    return flags




def tercile_edges(previous_vix: Sequence[float]) -> tuple[float, float]:
    values = np.asarray([float(item) for item in previous_vix if math.isfinite(float(item))], dtype=float)
    if len(values) < 3:
        raise ValueError("need at least three train VIX observations for terciles")
    low, high = np.quantile(values, [1.0 / 3.0, 2.0 / 3.0])
    return float(low), float(high)


def vix_tercile(value: float, edges: tuple[float, float]) -> int | None:
    if not math.isfinite(value):
        return None
    low, high = edges
    if value <= low:
        return 0
    if value <= high:
        return 1
    return 2


def previous_vix(sessions: Sequence[date], vix: Mapping[date, float]) -> list[float]:
    out = [math.nan] * len(sessions)
    for index in range(1, len(sessions)):
        value = vix.get(sessions[index - 1])
        out[index] = float(value) if value is not None else math.nan
    return out


def stratified_diff(
    values: Sequence[float],
    event: Sequence[bool],
    strata: Sequence[tuple[int, int] | None],
) -> float | None:
    """Event-weighted average of within-stratum differences of means."""
    if not (len(values) == len(event) == len(strata)):
        raise ValueError("stratified inputs differ in length")
    buckets: dict[tuple[int, int], list[tuple[float, bool]]] = {}
    for value, flag, stratum in zip(values, event, strata):
        if stratum is None or not math.isfinite(float(value)):
            continue
        buckets.setdefault(stratum, []).append((float(value), bool(flag)))
    numerator = 0.0
    denominator = 0
    for rows in buckets.values():
        event_vals = [value for value, flag in rows if flag]
        other_vals = [value for value, flag in rows if not flag]
        if not event_vals or not other_vals:
            continue
        difference = sum(event_vals) / len(event_vals) - sum(other_vals) / len(other_vals)
        numerator += len(event_vals) * difference
        denominator += len(event_vals)
    if denominator == 0:
        return None
    return numerator / denominator




def _mean_ratio(event_mean: float | None, other_mean: float | None) -> float | None:
    if event_mean is None or other_mean is None or other_mean == 0:
        return None
    return event_mean / other_mean


def score_mask(
    values: Sequence[float],
    event: Sequence[bool],
    strata: Sequence[tuple[int, int] | None],
    *,
    n_boot: int = N_BOOT,
) -> dict[str, object]:
    result = block_bootstrap_diff(values, event, n_boot=n_boot)
    return {
        "diff": result.diff,
        "p": result.p,
        "ci_low": result.ci_low,
        "ci_high": result.ci_high,
        "event_mean": result.event_mean,
        "other_mean": result.other_mean,
        "mean_ratio": _mean_ratio(result.event_mean, result.other_mean),
        "n_event": result.n_event,
        "n_other": result.n_other,
        "matched_diff": stratified_diff(values, event, strata),
    }


def score_category(
    sessions: Sequence[date],
    outcomes: dict[str, list[float]],
    is_event: Sequence[bool],
    strata: Sequence[tuple[int, int] | None],
    in_split: Sequence[bool],
    *,
    n_boot: int = N_BOOT,
) -> dict[str, object]:
    indexes = [index for index, flag in enumerate(in_split) if flag]
    event = [bool(is_event[index]) for index in indexes]
    split_strata = [strata[index] for index in indexes]
    scored = {
        name: score_mask([outcomes[name][index] for index in indexes], event, split_strata, n_boot=n_boot)
        for name in OUTCOMES
    }
    return {"n_event_sessions": int(sum(event)), "outcomes": scored}


def apply_holm(train_categories: list[dict[str, object]]) -> None:
    flat: list[float] = []
    for category in train_categories:
        outcomes = category["outcomes"]
        assert isinstance(outcomes, dict)
        for name in OUTCOMES:
            flat.append(float(outcomes[name]["p"]))
    adjusted = holm_adjust(flat)
    cursor = 0
    for category in train_categories:
        outcomes = category["outcomes"]
        assert isinstance(outcomes, dict)
        for name in OUTCOMES:
            outcomes[name]["holm_p"] = adjusted[cursor]
            cursor += 1


def category_matters(train: dict[str, object], validate: dict[str, object]) -> list[str]:
    """Outcomes that clear the pre-registered train Holm gate and the validate gate."""
    passing: list[str] = []
    train_outcomes = train["outcomes"]
    validate_outcomes = validate["outcomes"]
    assert isinstance(train_outcomes, dict) and isinstance(validate_outcomes, dict)
    for name in OUTCOMES:
        left = train_outcomes[name]
        right = validate_outcomes[name]
        holm_p = left.get("holm_p")
        train_diff = left.get("diff")
        validate_diff = right.get("diff")
        if holm_p is None or train_diff is None or validate_diff is None:
            continue
        if float(holm_p) >= 0.05 or float(right["p"]) >= 0.05:
            continue
        if float(train_diff) == 0 or float(validate_diff) == 0:
            continue
        if (float(train_diff) > 0) != (float(validate_diff) > 0):
            continue
        passing.append(name)
    return passing


def strata_for(
    sessions: Sequence[date],
    previous: Sequence[float],
    edges: tuple[float, float],
) -> list[tuple[int, int] | None]:
    labels: list[tuple[int, int] | None] = []
    for day, value in zip(sessions, previous):
        bucket = vix_tercile(value, edges)
        if bucket is None:
            labels.append(None)
        else:
            labels.append((day.weekday(), bucket))
    return labels



API_URLS = {
    "nifty_daily": PUBLIC_DAILY_NIFTY,
    "vix_daily": PUBLIC_DAILY_VIX,
    "nifty_5m": PUBLIC_INTRADAY_NIFTY,
}


def load_yahoo_closes(symbol: str, start: str, end: str) -> dict[date, float]:
    import yfinance as yf

    frame = yf.download(symbol, start=start, end=end, auto_adjust=False, progress=False, threads=False)
    if frame is None or len(frame) == 0:
        return {}
    close = frame["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    out: dict[date, float] = {}
    for stamp, value in close.items():
        number = float(value)
        if not math.isfinite(number):
            continue
        day = stamp.date() if hasattr(stamp, "date") else stamp
        out[day] = number
    return out


def fetch_public_json(url: str, cache_dir: Path, client: object) -> object:
    """One public-API GET. A cache hit does not call the network again."""
    payload, _did_http = fetch_json(url, cache_dir, client, lambda _seconds: None, pause=0.0)
    return payload


def coverage(payload: object) -> dict[str, str | int | None]:
    if not isinstance(payload, list) or not payload:
        return {"bars": 0, "first": None, "last": None}
    first = str(payload[0].get("start") or payload[0].get("end"))
    last = str(payload[-1].get("end") or payload[-1].get("start"))
    return {"bars": len(payload), "first": first, "last": last}




def _event_masks(
    sessions: Sequence[date],
    category_days: Mapping[str, Sequence[tuple[date, bool]]],
) -> dict[str, list[bool]]:
    masks: dict[str, list[bool]] = {}
    for category_id, _label, _queries in CATEGORIES:
        flagged = event_sessions(category_days[category_id], sessions)
        masks[category_id] = [day in flagged for day in sessions]
    return masks


def train_document(
    sessions: Sequence[date],
    nifty: Mapping[date, float],
    vix: Mapping[date, float],
    rv: Mapping[date, float],
    category_days: Mapping[str, Sequence[tuple[date, bool]]],
    *,
    protocol_commit: str,
    n_boot: int = N_BOOT,
) -> dict[str, object]:
    """Train scores only. This is the first process. It does not score validate."""
    previous = previous_vix(sessions, vix)
    train_mask = split_flags(sessions, TRAIN_START, TRAIN_END)
    edges = tercile_edges([value for value, flag in zip(previous, train_mask) if flag])
    strata = strata_for(sessions, previous, edges)
    names = {item[0]: item[1] for item in CATEGORIES}
    masks = _event_masks(sessions, category_days)
    outcomes = build_outcomes(sessions, nifty, vix, rv, train_mask)
    categories: list[dict[str, object]] = []
    for category_id, _label, _queries in CATEGORIES:
        is_event = masks[category_id]
        categories.append(
            {
                "id": category_id,
                "name": names[category_id],
                "event_sessions": [day.isoformat() for day, flag in zip(sessions, is_event) if flag],
                "train": score_category(sessions, outcomes, is_event, strata, train_mask, n_boot=n_boot),
            }
        )
    apply_holm([item["train"] for item in categories])  # type: ignore[arg-type]
    return {
        "protocol_commit": protocol_commit,
        "train_window": [TRAIN_START.isoformat(), TRAIN_END.isoformat()],
        "vix_tercile_cuts": [edges[0], edges[1]],
        "categories": categories,
    }


def validate_document(
    sessions: Sequence[date],
    nifty: Mapping[date, float],
    vix: Mapping[date, float],
    rv: Mapping[date, float],
    train_doc: Mapping[str, object],
    *,
    n_boot: int = N_BOOT,
    nifty_mismatches: list[dict[str, object]] | None = None,
    vix_mismatches: list[dict[str, object]] | None = None,
    calendar: dict[str, int] | None = None,
    nifty_api_coverage: dict[str, object] | None = None,
    vix_api_coverage: dict[str, object] | None = None,
    intraday_coverage: dict[str, object] | None = None,
    tone: Mapping[str, Mapping[date, float]] | None = None,
) -> dict[str, object]:
    """Validate scores once, using the event sessions and Holm values frozen at train."""
    previous = previous_vix(sessions, vix)
    cuts = train_doc["vix_tercile_cuts"]
    assert isinstance(cuts, list)
    edges = (float(cuts[0]), float(cuts[1]))
    strata = strata_for(sessions, previous, edges)
    validate_mask = split_flags(sessions, VALIDATE_START, None)
    outcomes = build_outcomes(sessions, nifty, vix, rv, validate_mask)
    frozen = train_doc["categories"]
    assert isinstance(frozen, list)
    categories: list[dict[str, object]] = []
    for item in frozen:
        assert isinstance(item, dict)
        event_set = set(item["event_sessions"])
        is_event = [day.isoformat() in event_set for day in sessions]
        validate = score_category(sessions, outcomes, is_event, strata, validate_mask, n_boot=n_boot)
        train = item["train"]
        assert isinstance(train, dict)
        passing = category_matters(train, validate)
        row: dict[str, object] = {
            "id": item["id"],
            "name": item["name"],
            "train": train,
            "validate": validate,
            "passing_outcomes": passing,
            "matters": bool(passing),
        }
        if tone and item["id"] in tone:
            row["mean_event_tone"] = _event_tone(tone[item["id"]], is_event, sessions)
        categories.append(row)
    result: dict[str, object] = {
        "protocol_commit": train_doc["protocol_commit"],
        "train_window": train_doc["train_window"],
        "validate_window": [VALIDATE_START.isoformat(), sessions[-1].isoformat() if sessions else None],
        "vix_tercile_cuts": [edges[0], edges[1]],
        "nifty_mismatches": nifty_mismatches or [],
        "vix_mismatches": vix_mismatches or [],
        "calendar_audit": calendar or {},
        "nifty_api_coverage": nifty_api_coverage or {},
        "vix_api_coverage": vix_api_coverage or {},
        "intraday_coverage": intraday_coverage or {},
        "categories": categories,
    }
    result["conclusion"] = conclude(categories)
    return result


def assemble_study(
    sessions: Sequence[date],
    nifty: Mapping[date, float],
    vix: Mapping[date, float],
    rv: Mapping[date, float],
    category_days: Mapping[str, Sequence[tuple[date, bool]]],
    *,
    protocol_commit: str,
    nifty_mismatches: list[dict[str, object]] | None = None,
    vix_mismatches: list[dict[str, object]] | None = None,
    calendar: dict[str, int] | None = None,
    nifty_api_coverage: dict[str, object] | None = None,
    vix_api_coverage: dict[str, object] | None = None,
    intraday_coverage: dict[str, object] | None = None,
    tone: Mapping[str, Mapping[date, float]] | None = None,
    n_boot: int = N_BOOT,
) -> dict[str, object]:
    """Score both splits. The real study calls train_document and validate_document in separate processes."""
    trained = train_document(
        sessions,
        nifty,
        vix,
        rv,
        category_days,
        protocol_commit=protocol_commit,
        n_boot=n_boot,
    )
    return validate_document(
        sessions,
        nifty,
        vix,
        rv,
        trained,
        n_boot=n_boot,
        nifty_mismatches=nifty_mismatches,
        vix_mismatches=vix_mismatches,
        calendar=calendar,
        nifty_api_coverage=nifty_api_coverage,
        vix_api_coverage=vix_api_coverage,
        intraday_coverage=intraday_coverage,
        tone=tone,
    )


def _event_tone(tone: Mapping[date, float], is_event: Sequence[bool], sessions: Sequence[date]) -> dict[str, float | None]:
    """Descriptive tone only. It is not an outcome and it cannot make a category pass."""
    event_vals = [float(tone[day]) for day, flag in zip(sessions, is_event) if flag and day in tone]
    other_vals = [float(tone[day]) for day, flag in zip(sessions, is_event) if not flag and day in tone]

    def _avg(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    return {"event": _avg(event_vals), "other": _avg(other_vals)}




def _round(value: object, digits: int = 6) -> object:
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, digits)
    return value


def json_ready(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, float):
        return _round(value)
    return value


def render_markdown(result: dict[str, object]) -> str:
    """Plain-language result note. Numbers come only from the scored JSON."""
    lines = [
        "# News categories vs the NIFTY 50 index: result",
        "",
        f"Protocol commit: `{result.get('protocol_commit', 'unknown')}`.",
        "Validate was scored once. No query, window, or threshold was changed after train.",
        "",
        "## Price check",
        "",
        f"API daily NIFTY bars: {result.get('nifty_api_coverage')}.",
        f"API daily India VIX bars: {result.get('vix_api_coverage')}.",
        f"API 5-minute bars: {result.get('intraday_coverage')}.",
        f"Close mismatches above 0.5%: {len(result.get('nifty_mismatches', []))} NIFTY, {len(result.get('vix_mismatches', []))} VIX.",
        f"Calendar audit: {result.get('calendar_audit')}.",
        "",
    ]
    categories = result.get("categories")
    assert isinstance(categories, list)
    for category in categories:
        assert isinstance(category, dict)
        lines.append(f"## {category['name']}")
        lines.append("")
        lines.append("| Split | Events | Next-session return, event | Next-session return, other | Diff | Abs-move ratio | VIX diff | p | Holm p |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for split in ("train", "validate"):
            block = category[split]
            assert isinstance(block, dict)
            ret = block["outcomes"]["ret_0"]
            abs_row = block["outcomes"]["abs_0"]
            vix_row = block["outcomes"]["vix_0"]
            holm = ret.get("holm_p")
            lines.append(
                "| {split} | {events} | {em} | {om} | {diff} | {ratio} | {vix} | {p} | {holm} |".format(
                    split=split,
                    events=block["n_event_sessions"],
                    em=_fmt(ret.get("event_mean")),
                    om=_fmt(ret.get("other_mean")),
                    diff=_fmt(ret.get("diff")),
                    ratio=_fmt(abs_row.get("mean_ratio")),
                    vix=_fmt(vix_row.get("diff")),
                    p=_fmt(ret.get("p")),
                    holm=_fmt(holm) if split == "train" else "",
                )
            )
        lines.append("")
        lines.append(f"Matters: **{category['matters']}**. Passing outcomes: {category['passing_outcomes'] or 'none'}.")
        lines.append("")
        lines.append("Other windows (difference of means, unadjusted p):")
        lines.append("")
        lines.append("| Outcome | Train diff | Train p | Train Holm | Validate diff | Validate p |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for name in OUTCOMES:
            if name == "ret_0":
                continue
            left = category["train"]["outcomes"][name]
            right = category["validate"]["outcomes"][name]
            lines.append(
                f"| {name} | {_fmt(left.get('diff'))} | {_fmt(left.get('p'))} | {_fmt(left.get('holm_p'))} | {_fmt(right.get('diff'))} | {_fmt(right.get('p'))} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Conclusion",
            "",
            str(result.get("conclusion")),
            "",
            "## Limits",
            "",
            "GDELT refuses the full 2017-to-today call, so each query was fetched in non-overlapping windows of at most 700 days and concatenated. Some tone calls still returned 429 after those splits; tone is not in the pass rule, and those windows were left out of the tone cache. GDELT's crawl is global, not an Indian newspaper. A spike is a count of articles, not a measure of how important the news was. Average tone was downloaded into the local cache and is not part of the pass rule. A difference between event days and other days is not a cause, and it is not a trading rule. The daily GDELT bucket has no clock, so the study assigns it to the next NSE session. The 5-minute volatility window is only as long as one public API call. Stored RSS headlines from October 2026 are too short to test and were not used as evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return f"{value:.4f}"
    return str(value)


NOTHING_PASSES = (
    "Under this pre-registered design, no news category has a volume spike that lines up with "
    "the NIFTY 50 index on 2017-2022 and then again, in the same direction, on 2023 onward. "
    "That is a negative result. It does not support adding a market-wide news vote, changing fusion, "
    "or loosening the 2 standard-deviation rule. The forward capture switch stays off unless someone "
    "turns it on for storage only."
)


def conclude(categories: Sequence[Mapping[str, object]]) -> str:
    passed = [str(item["name"]) for item in categories if item.get("matters")]
    if not passed:
        return NOTHING_PASSES
    names = ", ".join(passed)
    return (
        f"Under this pre-registered design, {names} mattered: at least one outcome had a "
        "Holm-adjusted train p below 0.05 and the same sign on validate with an unadjusted p below 0.05. "
        "That is an association with the NIFTY 50 index, not a cause and not a trading rule. "
        "Fusion, risk, and agent scores were not changed. The capture switch stays off by default."
    )



import subprocess


def repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "services" / "quant" / "docs").exists():
            return parent
    raise RuntimeError("could not find the repository root")


def cache_directory(root: Path) -> Path:
    path = root / "services" / "quant" / ".cache" / "news-categories"
    path.mkdir(parents=True, exist_ok=True)
    return path


def git_protocol_commit(root: Path) -> str:
    output = subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "services/quant/docs/news-categories-nifty-protocol.md"],
        cwd=root,
        text=True,
    )
    return output.strip()


def covered_dates(start: date, end: date, present: Iterable[date]) -> tuple[date, date] | None:
    """Days a successful GDELT window actually answered.

    A short window, or a timeline that touches both ends, counts the whole
    request: days the timeline omits are zeros, not gaps. A response with no
    points inside the request is not coverage. A long timeline that stops
    early counts only the returned span, so the tail can be requested again.
    """
    if end < start:
        return None
    inside = {day for day in present if start <= day <= end}
    if not inside:
        return None
    first, last = min(inside), max(inside)
    if (end - start).days <= 21 or (first == start and last == end):
        return start, end
    return first, last


def remember_coverage(cache: Path, query: str, mode: str, start: date, end: date) -> None:
    """Append one inclusive range that GDELT has already answered."""
    if end < start:
        return
    path = cache / "coverage.json"
    rows: list[object] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = []
        if isinstance(loaded, list):
            rows = loaded
    rows.append({"query": query, "mode": mode, "start": start.isoformat(), "end": end.isoformat()})
    path.write_text(json.dumps(rows), encoding="utf-8")


def coverage_days(cache: Path) -> dict[tuple[str, str], set[date]]:
    """Expand recorded ranges. Missing files mean nothing has been answered yet."""
    path = cache / "coverage.json"
    found: dict[tuple[str, str], set[date]] = {}
    if not path.exists():
        return found
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return found
    if not isinstance(rows, list):
        return found
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            start = date.fromisoformat(str(row["start"]))
            end = date.fromisoformat(str(row["end"]))
        except (KeyError, ValueError):
            continue
        bucket = found.setdefault((str(row.get("query") or ""), str(row.get("mode") or "")), set())
        cursor = start
        while cursor <= end:
            bucket.add(cursor)
            cursor += timedelta(days=1)
    return found


def load_gdelt_days(
    query: str,
    mode: str,
    start: date,
    end: date,
    cache: Path,
    client: object,
    sleeper: Callable[[float], None],
    label: str,
    *,
    split: bool = True,
) -> dict[date, float]:
    """Fetch one window. If GDELT still returns 429, split the window and concatenate."""
    if end < start:
        return {}
    print(f"gdelt {label} {mode} {start.isoformat()} {end.isoformat()}", flush=True)
    request_end = end if end > start else end + timedelta(days=1)
    url = gdelt_request_url(query, mode, start.strftime("%Y%m%d") + "000000", request_end.strftime("%Y%m%d") + "000000")
    span = (end - start).days
    # Long windows are refused outright. Anything shorter gets one retry, then a split or a recorded gap.
    if span > 120 or mode == "timelinetone":
        attempts = 1
    else:
        attempts = 2
    try:
        payload, _ = fetch_json(url, cache, client, sleeper, attempts=attempts, pause=12.0)
    except RuntimeError as exc:
        if "429" not in str(exc):
            raise
        if span < 30:
            if mode == "timelinevolraw":
                sleeper(45.0)
                payload, _ = fetch_json(url, cache, client, sleeper, attempts=2, pause=12.0)
            else:
                print(f"unanswered {label} {mode} {start.isoformat()} {end.isoformat()}", flush=True)
                raise RuntimeError(f"GDELT kept returning 429: {url}")
        else:
            sleeper(30.0)
            try:
                payload, _ = fetch_json(url, cache, client, sleeper, attempts=1, pause=12.0)
            except RuntimeError as exc2:
                if "429" not in str(exc2) or not split:
                    raise
                mid = start + timedelta(days=span // 2)
                print(f"split {label} {mode} {start.isoformat()} {end.isoformat()} at {mid.isoformat()}", flush=True)
                left = load_gdelt_days(query, mode, start, mid, cache, client, sleeper, label, split=split)
                right = load_gdelt_days(query, mode, mid + timedelta(days=1), end, cache, client, sleeper, label, split=split)
                shared = set(left) & set(right)
                if shared:
                    raise RuntimeError(f"GDELT window overlap on {min(shared).isoformat()}") from exc2
                left.update(right)
                return left
    present = volume_by_day(parse_stamped(payload))
    answered = covered_dates(start, end, present)
    if answered is not None:
        remember_coverage(cache, query, mode, answered[0], answered[1])
    out: dict[date, float] = {}
    for day, value in present.items():
        if start <= day <= end:
            out[day] = value
    return out


def gap_windows(have: set[date], start: date, end: date, *, span_days: int = 45) -> list[tuple[date, date]]:
    """Dates still missing, in short inclusive windows. Days already cached are not requested again."""
    if span_days < 1:
        raise ValueError("span_days must be positive")
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        if cursor in have:
            cursor += timedelta(days=1)
            continue
        stop = cursor
        while stop < end and (stop - cursor).days + 1 < span_days and (stop + timedelta(days=1)) not in have:
            stop += timedelta(days=1)
        windows.append((cursor, stop))
        cursor = stop + timedelta(days=1)
    return windows


def read_cached_gdelt(cache: Path) -> dict[tuple[str, str], dict[date, float]]:
    """Reuse every cached GDELT body. The file name is a hash, so the query is read from the body."""
    found: dict[tuple[str, str], dict[date, float]] = {}
    if not cache.exists():
        return found
    for path in cache.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        timeline = payload.get("timeline") or []
        if not timeline:
            continue
        title = str((payload.get("query_details") or {}).get("title") or "")
        series = str(timeline[0].get("series") or "")
        if series == "Article Count":
            mode = "timelinevolraw"
        elif series == "Average Tone":
            mode = "timelinetone"
        else:
            continue
        if not title:
            continue
        try:
            points = volume_by_day(parse_stamped(payload))
        except (KeyError, TypeError, ValueError):
            continue
        if not points:
            continue
        first, last = min(points), max(points)
        span: dict[date, float] = {}
        day = first
        while day <= last:
            span[day] = 0.0
            day += timedelta(days=1)
        span.update(points)
        bucket = found.setdefault((title, mode), {})
        for day, value in span.items():
            bucket.setdefault(day, value)
    return found


def remaining_volume_windows(cache: Path, end_day: date, *, span_days: int = 150) -> list[tuple[str, str, date, date]]:
    """Windows still missing from the cache. This does not call GDELT."""
    cached = read_cached_gdelt(cache)
    answered = coverage_days(cache)
    windows: list[tuple[str, str, date, date]] = []
    for category_id, _name, queries in CATEGORIES:
        for query in queries:
            merged = dict(cached.get((query, "timelinevolraw"), {}))
            for day in answered.get((query, "timelinevolraw"), ()):
                if VOLUME_START <= day <= end_day:
                    merged.setdefault(day, 0.0)
            for start_day, stop_day in gap_windows(set(merged), VOLUME_START, end_day, span_days=span_days):
                windows.append((category_id, query, start_day, stop_day))
    return windows


def _missing_ranges(have: set[date], start: date, end: date) -> list[list[str]]:
    return [
        [start_day.isoformat(), stop_day.isoformat()]
        for start_day, stop_day in gap_windows(have, start, end, span_days=100000)
    ]


def coverage_report(cache: Path, end_day: date) -> dict[str, object]:
    """Per-query volume and tone coverage. This does not call GDELT."""
    cached = read_cached_gdelt(cache)
    categories: list[dict[str, object]] = []
    for category_id, _name, queries in CATEGORIES:
        query_rows: list[dict[str, object]] = []
        complete = True
        for index, query in enumerate(queries):
            modes: dict[str, object] = {}
            for mode in ("timelinevolraw", "timelinetone"):
                days = {day for day in cached.get((query, mode), {}) if VOLUME_START <= day <= end_day}
                missing = _missing_ranges(days, VOLUME_START, end_day)
                if missing:
                    complete = False
                modes[mode] = {
                    "observed_days": len(days),
                    "first": min(days).isoformat() if days else None,
                    "last": max(days).isoformat() if days else None,
                    "missing_ranges": missing,
                }
            query_rows.append({"index": index, "modes": modes})
        categories.append({"id": category_id, "complete": complete, "queries": query_rows})
    return {"start": VOLUME_START.isoformat(), "end": end_day.isoformat(), "categories": categories}


def utc_study_day() -> date:
    """The protocol's study end is the UTC calendar date, not the machine's local date."""
    return datetime.now(timezone.utc).date()


def resume_volume(
    cache: Path,
    client: object,
    sleeper: Callable[[float], None],
    end_day: date,
    *,
    max_windows: int = 1,
) -> dict[str, object]:
    """Fetch at most `max_windows` missing volume windows. A 429 stops the run."""
    if max_windows < 1:
        raise ValueError("max_windows must be positive")
    windows = remaining_volume_windows(cache, end_day)
    attempted = 0
    blocked: dict[str, object] | None = None
    for category_id, query, start_day, stop_day in windows:
        if attempted >= max_windows:
            break
        attempted += 1
        try:
            load_gdelt_days(query, "timelinevolraw", start_day, stop_day, cache, client, sleeper, category_id, split=False)
        except RuntimeError as exc:
            blocked = {
                "category": category_id,
                "window": [start_day.isoformat(), stop_day.isoformat()],
                "error": str(exc)[:180],
            }
            break
    remaining = len(remaining_volume_windows(cache, end_day))
    status = "BLOCKED" if blocked else ("COMPLETE" if remaining == 0 else "INCOMPLETE")
    return {"status": status, "attempted": attempted, "remaining_windows": remaining, "blocked": blocked}


def category_event_days(cache: Path, client: object, sleeper: Callable[[float], None], end_day: date) -> dict[str, list[tuple[date, bool]]]:
    """Pull each frozen query for the days not already cached, then flag event days.

    Volume is finished for every query before tone starts. Tone is descriptive
    and a 429 there must not throw away the volume already on disk.
    """
    cached = read_cached_gdelt(cache)
    merged_by_query: dict[str, list[dict[date, float]]] = {}
    for category_id, _name, queries in CATEGORIES:
        parts: list[dict[date, float]] = []
        for query in queries:
            merged = dict(cached.get((query, "timelinevolraw"), {}))
            for day in coverage_days(cache).get((query, "timelinevolraw"), ()):
                if VOLUME_START <= day <= end_day:
                    merged.setdefault(day, 0.0)
            # 150 days stays under the protocol's 700-day cap and is what GDELT will answer.
            pending = gap_windows(set(merged), VOLUME_START, end_day, span_days=150)
            rounds = 0
            while pending:
                rounds += 1
                if rounds > 6:
                    raise RuntimeError(
                        f"GDELT volume still missing for {category_id} at {pending[0][0].isoformat()} ({len(pending)} windows)"
                    )
                for start_day, end_bound in pending:
                    piece = load_gdelt_days(query, "timelinevolraw", start_day, end_bound, cache, client, sleeper, category_id)
                    for day, value in piece.items():
                        merged.setdefault(day, value)
                    for day in coverage_days(cache).get((query, "timelinevolraw"), ()):
                        if VOLUME_START <= day <= end_day:
                            merged.setdefault(day, 0.0)
                pending = gap_windows(set(merged), VOLUME_START, end_day, span_days=150)
            parts.append({day: value for day, value in merged.items() if VOLUME_START <= day <= end_day})
        merged_by_query[category_id] = parts
    for category_id, _name, queries in CATEGORIES:
        for query in queries:
            tone = set(cached.get((query, "timelinetone"), {}))
            tone.update(day for day in coverage_days(cache).get((query, "timelinetone"), ()) if VOLUME_START <= day <= end_day)
            for start_day, end_bound in gap_windows(tone, VOLUME_START, end_day, span_days=150):
                try:
                    load_gdelt_days(query, "timelinetone", start_day, end_bound, cache, client, sleeper, category_id, split=False)
                except RuntimeError as exc:
                    if "429" not in str(exc):
                        raise
                    print(f"tone skipped {category_id} {start_day.isoformat()} {end_bound.isoformat()}", flush=True)
                    break
    flagged: dict[str, list[tuple[date, bool]]] = {}
    missing_days: dict[str, int] = {}
    for category_id, _name, _queries in CATEGORIES:
        rows, missing = combine_observed(merged_by_query[category_id], VOLUME_START, end_day)
        if missing:
            missing_days[category_id] = missing
            continue
        bits = event_flags([value for _day, value in rows])
        flagged[category_id] = [(day, flag) for (day, _value), flag in zip(rows, bits)]
    if missing_days:
        raise IncompleteCoverage(missing_days)
    return flagged


def _payload_or_empty(cache: Path, client: object, url: str, errors: dict[str, str]) -> object:
    try:
        return fetch_public_json(url, cache, client)
    except Exception as exc:
        errors[url] = str(exc)[:200]
        return []


def load_market(
    cache: Path,
    client: object,
    yahoo: Callable[[str, str, str], dict[date, float]],
    end_day: date,
) -> dict[str, object]:
    """Yahoo history plus one cached call to each public candle URL."""
    end = (end_day + timedelta(days=1)).isoformat()
    yahoo_nifty = yahoo("^NSEI", "2015-01-01", end)
    yahoo_vix = yahoo("^INDIAVIX", "2015-01-01", end)
    errors: dict[str, str] = {}
    nifty_payload = _payload_or_empty(cache, client, PUBLIC_DAILY_NIFTY, errors)
    vix_payload = _payload_or_empty(cache, client, PUBLIC_DAILY_VIX, errors)
    intra_payload = _payload_or_empty(cache, client, PUBLIC_INTRADAY_NIFTY, errors)
    api_nifty = parse_api_daily(nifty_payload) if isinstance(nifty_payload, list) else {}
    api_vix = parse_api_daily(vix_payload) if isinstance(vix_payload, list) else {}
    bars = parse_api_intraday(intra_payload) if isinstance(intra_payload, list) else []
    nifty = prefer_api(yahoo_nifty, api_nifty)
    vix = prefer_api(yahoo_vix, api_vix)
    return {
        "nifty": nifty,
        "vix": vix,
        "sessions": trading_sessions(nifty),
        "rv": session_realised_variance(bars),
        "nifty_mismatches": close_mismatches(yahoo_nifty, api_nifty),
        "vix_mismatches": close_mismatches(yahoo_vix, api_vix),
        "calendar_audit": calendar_audit(nifty),
        "nifty_api_coverage": coverage(nifty_payload),
        "vix_api_coverage": coverage(vix_payload),
        "intraday_coverage": coverage(intra_payload),
        "api_errors": errors,
    }


def _dates(values: Mapping[object, float]) -> dict[date, float]:
    out: dict[date, float] = {}
    for key, value in values.items():
        out[key if isinstance(key, date) else date.fromisoformat(str(key))] = float(value)
    return out


def run_train(
    root: Path,
    *,
    today: date,
    client: object,
    sleeper: Callable[[float], None],
    yahoo: Callable[[str, str, str], dict[date, float]],
    n_boot: int = N_BOOT,
    protocol_commit: str | None = None,
) -> Path:
    """Download inputs if needed and write train scores. Does not score validate."""
    cache = cache_directory(root)
    if (cache / "validate-consumed").exists():
        raise RuntimeError("validate was already scored; refusing to recompute train")
    market = load_market(cache, client, yahoo, today)
    sessions = market["sessions"]
    assert isinstance(sessions, list)
    days = category_event_days(cache, client, sleeper, today)
    trained = train_document(
        sessions,
        market["nifty"],  # type: ignore[arg-type]
        market["vix"],  # type: ignore[arg-type]
        market["rv"],  # type: ignore[arg-type]
        days,
        protocol_commit=protocol_commit or git_protocol_commit(root),
        n_boot=n_boot,
    )
    trained["context"] = {
        "nifty_mismatches": market["nifty_mismatches"],
        "vix_mismatches": market["vix_mismatches"],
        "calendar_audit": market["calendar_audit"],
        "nifty_api_coverage": market["nifty_api_coverage"],
        "vix_api_coverage": market["vix_api_coverage"],
        "intraday_coverage": market["intraday_coverage"],
        "api_errors": market["api_errors"],
        "sessions": [day.isoformat() for day in sessions],
        "nifty": {day.isoformat(): value for day, value in market["nifty"].items()},  # type: ignore[attr-defined]
        "vix": {day.isoformat(): value for day, value in market["vix"].items()},  # type: ignore[attr-defined]
        "rv": {day.isoformat(): value for day, value in market["rv"].items()},  # type: ignore[attr-defined]
    }
    path = cache / "train.json"
    path.write_text(json.dumps(json_ready(trained)), encoding="utf-8")
    return path


def run_validate(root: Path, *, n_boot: int = N_BOOT) -> dict[str, object]:
    """Score validate once from the frozen train file and write the result documents."""
    cache = cache_directory(root)
    consumed = cache / "validate-consumed"
    if consumed.exists():
        raise RuntimeError("validate was already scored")
    trained = json.loads((cache / "train.json").read_text(encoding="utf-8"))
    context = trained["context"]
    sessions = [date.fromisoformat(item) for item in context["sessions"]]
    result = validate_document(
        sessions,
        _dates(context["nifty"]),
        _dates(context["vix"]),
        _dates(context["rv"]),
        trained,
        n_boot=n_boot,
        nifty_mismatches=context["nifty_mismatches"],
        vix_mismatches=context["vix_mismatches"],
        calendar=context["calendar_audit"],
        nifty_api_coverage=context["nifty_api_coverage"],
        vix_api_coverage=context["vix_api_coverage"],
        intraday_coverage=context["intraday_coverage"],
    )
    result["api_errors"] = context.get("api_errors", {})
    docs = root / "services" / "quant" / "docs"
    json_path = docs / "results" / "news-categories-nifty-result.json"
    md_path = docs / "news-categories-nifty-result.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(json_ready(result), indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    consumed.write_text("scored\n", encoding="utf-8")
    return result


def write_blocked(root: Path, missing_days: dict[str, int], protocol_commit: str) -> Path:
    """Record an incomplete run. No category mean and no p-value is invented."""
    docs = root / "services" / "quant" / "docs"
    payload = {
        "status": "BLOCKED",
        "reason": "GDELT volume does not cover every category. Missing days were not stored as zero.",
        "protocol_commit": protocol_commit,
        "missing_days": missing_days,
        "categories_scored": False,
        "validation_runs": 0,
    }
    json_path = docs / "results" / "news-categories-nifty-result.json"
    md_path = docs / "news-categories-nifty-result.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# News categories vs the NIFTY 50 index: result",
        "",
        f"Protocol commit: `{protocol_commit}`.",
        "",
        "Status: **BLOCKED**. Train was not scored. Validate was not opened.",
        "",
        "GDELT did not return a successful volume timeline for every day from 2017-01-01 through the study date, for every query. Those missing days are not zeros, and they are not control days. No pass or fail is reported.",
        "",
        "| Category | Missing volume days |",
        "|---|---:|",
    ]
    for key, value in missing_days.items():
        lines.append(f"| {key} | {value} |")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path


def main(argv: Sequence[str] | None = None) -> None:
    import sys

    import httpx

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {"train", "validate", "plan", "resume", "coverage"}:
        raise SystemExit("usage: python -m quant_agents.research.news_categories train|validate|plan|resume|coverage")
    root = repo_root()
    if args[0] == "coverage":
        print(json.dumps(coverage_report(cache_directory(root), utc_study_day())))
        return
    if args[0] == "plan":
        windows = remaining_volume_windows(cache_directory(root), utc_study_day())
        print(f"remaining_volume_windows {len(windows)}")
        for category_id, _query, start_day, stop_day in windows:
            print(f"{category_id} {start_day.isoformat()} {stop_day.isoformat()}")
        return
    if args[0] == "resume":
        client = httpx.Client(timeout=25.0, follow_redirects=True, headers={"User-Agent": "stockx-research/1.0"})
        try:
            outcome = resume_volume(
                cache_directory(root),
                client,
                lambda seconds: __import__("time").sleep(seconds),
                utc_study_day(),
                max_windows=1,
            )
        finally:
            client.close()
        print(json.dumps(json_ready(outcome)))
        if outcome["status"] == "BLOCKED":
            raise SystemExit(2)
        return
    if args[0] == "train":
        client = httpx.Client(timeout=25.0, follow_redirects=True, headers={"User-Agent": "stockx-research/1.0"})
        try:
            path = run_train(root, today=utc_study_day(), client=client, sleeper=lambda seconds: __import__("time").sleep(seconds), yahoo=load_yahoo_closes)
        except IncompleteCoverage as exc:
            blocked = write_blocked(root, exc.missing_days, git_protocol_commit(root))
            print(blocked)
            raise SystemExit(2) from exc
        finally:
            client.close()
        print(path)
        return
    result = run_validate(root)
    print(result["conclusion"])


if __name__ == "__main__":
    main()
