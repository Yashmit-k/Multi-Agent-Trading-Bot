"""The only indicator implementation in the platform.

Agents consume FeatureSet. They do not recompute these values.
"""

from datetime import datetime, timezone
from statistics import pstdev

from contracts.enums import Timeframe
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.market import Candle

FEATURE_VERSION = "1.0.0"


def build_feature_set(
    symbol: str,
    timeframe: Timeframe | str,
    candles: list[Candle],
    as_of: datetime,
) -> FeatureSet | None:
    parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
    moment = _aware(as_of)
    visible = [bar for bar in candles if bar.symbol == symbol and bar.timeframe == parsed and _aware(bar.end) <= moment]
    visible.sort(key=lambda bar: _aware(bar.end))
    if not visible:
        return None
    closes = [float(bar.close) for bar in visible]
    highs = [float(bar.high) for bar in visible]
    lows = [float(bar.low) for bar in visible]
    volumes = [bar.volume for bar in visible]
    features: dict[str, str | int | float | bool] = {
        "last_close": _num(closes[-1]),
        "period_high": _num(max(highs)),
        "period_low": _num(min(lows)),
        "last_volume": volumes[-1],
        "volume_mean": _num(sum(volumes) / len(volumes)),
    }
    _put(features, "sma_10", _sma(closes, 10))
    _put(features, "sma_20", _sma(closes, 20))
    _put(features, "ema_12", _last(_ema(closes, 12)))
    _put(features, "ema_26", _last(_ema(closes, 26)))
    macd_line, macd_signal = _macd(closes)
    _put(features, "macd", macd_line)
    _put(features, "macd_signal", macd_signal)
    _put(features, "rsi_14", _rsi(closes, 14))
    _put(features, "atr_14", _atr(visible, 14))
    _put(features, "vwap", _vwap(visible))
    mid, upper, lower = _bollinger(closes, 20)
    _put(features, "bollinger_mid", mid)
    _put(features, "bollinger_upper", upper)
    _put(features, "bollinger_lower", lower)
    if len(closes) >= 2:
        returns = [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes))]
        features["return_1"] = _num(returns[-1])
        if len(returns) >= 2:
            features["volatility"] = _num(pstdev(returns))
    if len(closes) >= 10:
        features["momentum_10"] = _num(closes[-1] - closes[-10])
    last = visible[-1]
    return FeatureSet(
        symbol=symbol,
        timestamp=moment,
        timeframe=parsed,
        feature_version=FEATURE_VERSION,
        features=features,
        source_data_timestamp=_aware(last.end),
    )


def _sma(values: list[float], length: int) -> float | None:
    if len(values) < length:
        return None
    return sum(values[-length:]) / length


def _ema(values: list[float], length: int) -> list[float]:
    if len(values) < length:
        return []
    seed = sum(values[:length]) / length
    series = [seed]
    weight = 2 / (length + 1)
    for value in values[length:]:
        seed = value * weight + seed * (1 - weight)
        series.append(seed)
    return series


def _last(values: list[float]) -> float | None:
    return values[-1] if values else None


def _macd(closes: list[float]) -> tuple[float | None, float | None]:
    ema_fast = _ema(closes, 12)
    ema_slow = _ema(closes, 26)
    if not ema_fast or not ema_slow:
        return None, None
    offset = len(ema_fast) - len(ema_slow)
    line = [fast - slow for fast, slow in zip(ema_fast[offset:], ema_slow, strict=False)]
    signal = _last(_ema(line, 9))
    return line[-1], signal


def _rsi(closes: list[float], length: int) -> float | None:
    if len(closes) <= length:
        return None
    deltas = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]
    average_gain = sum(gains[:length]) / length
    average_loss = sum(losses[:length]) / length
    for index in range(length, len(deltas)):
        average_gain = ((average_gain * (length - 1)) + gains[index]) / length
        average_loss = ((average_loss * (length - 1)) + losses[index]) / length
    if average_loss == 0:
        return 100.0
    relative = average_gain / average_loss
    return 100 - (100 / (1 + relative))


def _atr(candles: list[Candle], length: int) -> float | None:
    if len(candles) <= length:
        return None
    ranges: list[float] = []
    for index in range(1, len(candles)):
        high = float(candles[index].high)
        low = float(candles[index].low)
        previous = float(candles[index - 1].close)
        ranges.append(max(high - low, abs(high - previous), abs(low - previous)))
    if len(ranges) < length:
        return None
    value = sum(ranges[:length]) / length
    for true_range in ranges[length:]:
        value = ((value * (length - 1)) + true_range) / length
    return value


def _vwap(candles: list[Candle]) -> float | None:
    weighted = 0.0
    volume = 0
    for bar in candles:
        typical = (float(bar.high) + float(bar.low) + float(bar.close)) / 3
        weighted += typical * bar.volume
        volume += bar.volume
    if volume == 0:
        return None
    return weighted / volume


def _bollinger(closes: list[float], length: int) -> tuple[float | None, float | None, float | None]:
    if len(closes) < length:
        return None, None, None
    window = closes[-length:]
    mid = sum(window) / length
    deviation = pstdev(window)
    return mid, mid + 2 * deviation, mid - 2 * deviation


def _put(features: dict[str, str | int | float | bool], name: str, value: float | None) -> None:
    if value is not None:
        features[name] = _num(value)


def _num(value: float) -> float:
    return round(float(value), 8)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
