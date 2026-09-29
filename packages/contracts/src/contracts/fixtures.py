"""Deterministic sample data for RELIANCE, TCS, INFY, HDFCBANK, and ICICIBANK.

Prices are daily NSE session bars. Session bounds are 09:15 and 15:30 IST,
stored as 03:45 and 10:00 UTC. ``FIXTURE_AS_OF`` is the close of 2024-06-03.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from contracts.enums import AgentName, Exchange, Horizon, Timeframe
from contracts.pit import filter_available
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.fundamental import FundamentalDataPoint
from contracts.schemas.market import Candle, Quote
from contracts.schemas.news_article import NewsArticle
from contracts.time import require_aware

FIXTURE_SYMBOLS: tuple[str, ...] = ("RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK")
FIXTURE_EXCHANGE = Exchange.NSE
FIXTURE_AS_OF = datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc)
TRADING_DAYS: tuple[date, ...] = (
    date(2024, 5, 28),
    date(2024, 5, 29),
    date(2024, 5, 30),
    date(2024, 5, 31),
    date(2024, 6, 3),
)
FEATURE_VERSION = "1.0.0"

_BASE_PRICE: dict[str, Decimal] = {
    "RELIANCE": Decimal("2900.00"),
    "TCS": Decimal("3850.00"),
    "INFY": Decimal("1480.00"),
    "HDFCBANK": Decimal("1560.00"),
    "ICICIBANK": Decimal("1125.00"),
}
_DAILY_STEP: dict[str, Decimal] = {
    "RELIANCE": Decimal("6.00"),
    "TCS": Decimal("8.00"),
    "INFY": Decimal("2.00"),
    "HDFCBANK": Decimal("4.00"),
    "ICICIBANK": Decimal("2.00"),
}
_CENTS = Decimal("0.01")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized not in _BASE_PRICE:
        raise KeyError(normalized)
    return normalized


def candles_for(symbol: str) -> tuple[Candle, ...]:
    """Five daily bars ending 2024-06-03. Identical on every call."""
    name = normalize_symbol(symbol)
    base = _BASE_PRICE[name]
    step = _DAILY_STEP[name]
    half = (step / 2).quantize(_CENTS)
    symbol_index = FIXTURE_SYMBOLS.index(name)
    bars: list[Candle] = []
    for day_index, trading_day in enumerate(TRADING_DAYS):
        open_price = (base + step * day_index).quantize(_CENTS)
        bars.append(
            Candle(
                symbol=name,
                exchange=FIXTURE_EXCHANGE,
                timeframe=Timeframe.D1,
                open=open_price,
                high=(open_price + step).quantize(_CENTS),
                low=(open_price - half).quantize(_CENTS),
                close=(open_price + half).quantize(_CENTS),
                volume=100_000 + day_index * 1_000 + symbol_index * 100,
                start=datetime(trading_day.year, trading_day.month, trading_day.day, 3, 45, tzinfo=timezone.utc),
                end=datetime(trading_day.year, trading_day.month, trading_day.day, 10, 0, tzinfo=timezone.utc),
            )
        )
    return tuple(bars)


def quote_for(symbol: str, as_of: datetime) -> Quote:
    """Last daily close whose bar end is at or before as_of."""
    aware_as_of = require_aware(as_of, "as_of")
    visible = [bar for bar in candles_for(symbol) if bar.end <= aware_as_of]
    if not visible:
        raise LookupError(f"no quote for {normalize_symbol(symbol)} at {aware_as_of.isoformat()}")
    bar = visible[-1]
    return Quote(
        symbol=bar.symbol,
        exchange=bar.exchange,
        timestamp=bar.end,
        last_price=bar.close,
        volume=bar.volume,
    )


def candles_between(symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[Candle]:
    parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
    if parsed != Timeframe.D1:
        raise LookupError(f"fixture market data only includes {Timeframe.D1.value} bars")
    start_at = require_aware(start, "start")
    end_at = require_aware(end, "end")
    return [bar for bar in candles_for(symbol) if bar.start >= start_at and bar.end <= end_at]


def latest_candle(symbol: str, timeframe: Timeframe | str) -> Candle:
    parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
    if parsed != Timeframe.D1:
        raise LookupError(f"fixture market data only includes {Timeframe.D1.value} bars")
    return candles_for(symbol)[-1]


def feature_set_for(symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
    """Features from daily bars visible at as_of. Agents must not recompute these."""
    parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
    aware_as_of = require_aware(as_of, "as_of")
    if parsed != Timeframe.D1:
        raise LookupError(f"fixture features only include {Timeframe.D1.value}")
    visible = [bar for bar in candles_for(symbol) if bar.end <= aware_as_of]
    if len(visible) < 2:
        raise LookupError(f"not enough bars for {normalize_symbol(symbol)} at {aware_as_of.isoformat()}")
    last = visible[-1]
    previous = visible[-2]
    return_1d = ((last.close - previous.close) / previous.close).quantize(Decimal("0.00000001"))
    return FeatureSet(
        symbol=last.symbol,
        timestamp=aware_as_of,
        timeframe=parsed,
        feature_version=FEATURE_VERSION,
        features={
            "last_close": str(last.close),
            "previous_close": str(previous.close),
            "return_1d": str(return_1d),
            "volume": last.volume,
        },
        source_data_timestamp=last.end,
    )


def _article(symbol: str, published_at: datetime, article_id: str, raw_text: str) -> NewsArticle:
    return NewsArticle(
        article_id=article_id,
        source="fixture-wire",
        title=f"{symbol} fixture headline {article_id}",
        url=f"https://example.test/news/{symbol.lower()}/{article_id}",
        published_at=published_at,
        retrieved_at=published_at + timedelta(minutes=5),
        content_hash=content_hash(raw_text),
        symbols=[symbol],
        raw_text=raw_text,
        metadata={"fixture": True, "symbol": symbol},
    )


def all_articles(symbol: str) -> tuple[NewsArticle, ...]:
    name = normalize_symbol(symbol)
    visible_text = f"{name} reported steady operating updates on 2024-06-03."
    future_text = f"{name} announced a result after the fixture as_of."
    return (
        _article(
            name,
            datetime(2024, 6, 3, 4, 0, tzinfo=timezone.utc),
            f"news-{name.lower()}-20240603",
            visible_text,
        ),
        _article(
            name,
            datetime(2024, 6, 4, 4, 0, tzinfo=timezone.utc),
            f"news-{name.lower()}-20240604",
            future_text,
        ),
    )


def articles_for(symbol: str, as_of: datetime) -> list[NewsArticle]:
    """Articles whose publication and retrieval are both at or before as_of."""
    aware_as_of = require_aware(as_of, "as_of")
    return [
        article
        for article in all_articles(symbol)
        if article.published_at <= aware_as_of and article.retrieved_at <= aware_as_of
    ]


def _fundamental(
    symbol: str,
    metric: str,
    value: str,
    period: str,
    announced_at: datetime,
    available_at: datetime,
    source_id: str,
) -> FundamentalDataPoint:
    return FundamentalDataPoint(
        symbol=symbol,
        metric=metric,
        value=Decimal(value),
        unit="INR",
        period=period,
        announced_at=announced_at,
        available_at=available_at,
        source="fixture-filings",
        source_id=source_id,
        metadata={"fixture": True, "symbol": symbol, "period": period},
    )


def all_fundamentals(symbol: str) -> tuple[FundamentalDataPoint, ...]:
    """Includes one row that is not yet available at FIXTURE_AS_OF."""
    name = normalize_symbol(symbol)
    return (
        _fundamental(
            name,
            "eps",
            "48.25",
            "FY2024",
            datetime(2024, 4, 20, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 4, 20, 12, 0, tzinfo=timezone.utc),
            f"{name}-eps-fy2024",
        ),
        _fundamental(
            name,
            "eps",
            "12.10",
            "Q1FY2025",
            datetime(2024, 7, 20, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 7, 20, 12, 0, tzinfo=timezone.utc),
            f"{name}-eps-q1fy2025",
        ),
    )


def fundamentals_for(symbol: str, as_of: datetime) -> list[FundamentalDataPoint]:
    return filter_available(all_fundamentals(symbol), as_of)


def sample_agent_signal(symbol: str = "RELIANCE") -> AgentSignal:
    """A valid technical signal whose features come from the fixture feature set."""
    name = normalize_symbol(symbol)
    features = feature_set_for(name, Timeframe.D1, FIXTURE_AS_OF)
    return AgentSignal(
        signal_id=f"sig-{name.lower()}-technical-20240603",
        symbol=name,
        exchange=FIXTURE_EXCHANGE,
        agent_name=AgentName.TECHNICAL,
        agent_version="1.0.0",
        timestamp=FIXTURE_AS_OF,
        as_of=FIXTURE_AS_OF,
        horizon=Horizon.INTRADAY,
        signal=0.25,
        confidence=0.8,
        valid_until=FIXTURE_AS_OF + timedelta(hours=6),
        reason_codes=["close_above_prior_close"],
        features=dict(features.features),
        metadata={
            "feature_version": features.feature_version,
            "source_data_timestamp": features.source_data_timestamp.isoformat(),
            "timeframe": features.timeframe.value,
        },
    )
