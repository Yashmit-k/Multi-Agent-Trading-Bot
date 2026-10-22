"""The only indicator implementation in the platform.

Agents consume FeatureSet. They do not recompute these values.
A missing numeric feature is omitted. It is not stored as 0 or false.
"""

import math
from datetime import datetime, timezone
from statistics import pstdev

from contracts.enums import Timeframe
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.market import Candle

FEATURE_VERSION = "1.2.0"


def build_feature_set(
    symbol: str,
    timeframe: Timeframe | str,
    candles: list[Candle],
    as_of: datetime,
    *,
    nifty_return: float | None = None,
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
    _put(features, "vwap", _vwap(_vwap_window(visible, parsed)))
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
    _put(features, "bollinger_pct_b", _pct_b(closes[-1], lower, upper))
    _put(features, "distance_from_mean", None if mid is None else closes[-1] - mid)
    _put(features, "zscore_20", _zscore(closes))
    _put(features, "reversion_half_life", _half_life(closes))
    _put(features, "relative_volume", _relative_volume(volumes))
    _put(features, "volume_acceleration", _volume_acceleration(volumes))
    _put(features, "price_volume_corr", _price_volume_corr(closes, volumes))
    _put(features, "roc_10", _roc(closes, 10))
    _put(features, "trend_strength_adx", _adx(visible, 14))
    if nifty_return is not None and "return_1" in features:
        _put(features, "relative_strength_nifty", float(features["return_1"]) - nifty_return)
    _put(features, "volume_confirmation", _volume_confirmation(features))
    _put(features, "support_level", _window_low(lows, 20))
    _put(features, "resistance_level", _window_high(highs, 20))
    _put(features, "trend_slope", _slope(closes, 20))
    _put(features, "volatility_percentile", _volatility_percentile(closes))
    # Normalised gaps for the quant agents, which may only compare features, never compute on them.
    atr = features.get("atr_14")
    for name, a, b in (
        ("ema_gap_atr", "ema_12", "ema_26"),
        ("sma_gap_atr", "sma_10", "sma_20"),
        ("close_sma20_atr", "last_close", "sma_20"),
        ("close_vwap_atr", "last_close", "vwap"),
        ("macd_gap_atr", "macd", "macd_signal"),
    ):
        if isinstance(atr, (int, float)) and atr > 0 and a in features and b in features:
            _put(features, name, (float(features[a]) - float(features[b])) / float(atr))
    if "roc_10" in features and isinstance(features.get("volatility"), (int, float)) and float(features["volatility"]) > 0:
        # 10-bar return in units of its expected noise (per-bar volatility x sqrt(10)).
        _put(features, "roc_10_z", float(features["roc_10"]) / (float(features["volatility"]) * 10 ** 0.5))
    last = visible[-1]
    return FeatureSet(
        symbol=symbol,
        timestamp=moment,
        timeframe=parsed,
        feature_version=FEATURE_VERSION,
        features=features,
        unavailable=["volume_imbalance"],
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


def _vwap_window(candles: list[Candle], timeframe) -> list[Candle]:  # type: ignore[no-untyped-def]
    """Intraday: today's session only (a real session VWAP). Daily: the last 20 sessions."""
    from zoneinfo import ZoneInfo

    if getattr(timeframe, "value", timeframe) == "1d":
        return candles[-20:]
    ist = ZoneInfo("Asia/Kolkata")
    day = candles[-1].end.astimezone(ist).date()
    return [bar for bar in candles if bar.end.astimezone(ist).date() == day]


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


def _pct_b(close: float, lower: float | None, upper: float | None) -> float | None:
    if lower is None or upper is None or upper == lower:
        return None
    return (close - lower) / (upper - lower)


def _zscore(closes: list[float]) -> float | None:
    if len(closes) < 20:
        return None
    window = closes[-20:]
    mid = sum(window) / 20
    deviation = pstdev(window)
    if deviation == 0:
        return None
    return (closes[-1] - mid) / deviation


def _half_life(closes: list[float]) -> float | None:
    if len(closes) < 20:
        return None
    window = closes[-20:]
    mean = sum(window) / len(window)
    demeaned = [value - mean for value in window]
    xs = demeaned[:-1]
    variance = sum(value * value for value in xs)
    if variance == 0:
        return None
    phi = sum(left * right for left, right in zip(xs, demeaned[1:], strict=False)) / variance
    if phi <= 0 or phi >= 1:
        return None
    return math.log(0.5) / math.log(phi)


def _relative_volume(volumes: list[int]) -> float | None:
    if not volumes:
        return None
    mean = sum(volumes) / len(volumes)
    if mean == 0:
        return None
    return volumes[-1] / mean


def _volume_acceleration(volumes: list[int]) -> float | None:
    if len(volumes) < 2 or volumes[-2] == 0:
        return None
    return (volumes[-1] / volumes[-2]) - 1


def _price_volume_corr(closes: list[float], volumes: list[int]) -> float | None:
    if len(closes) < 21:
        return None
    returns = [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes))]
    paired = list(zip(returns, volumes[1:], strict=False))[-20:]
    if len(paired) < 20:
        return None
    xs = [item[0] for item in paired]
    ys = [float(item[1]) for item in paired]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None
    return covariance / math.sqrt(var_x * var_y)


def _roc(closes: list[float], length: int) -> float | None:
    if len(closes) <= length or closes[-1 - length] == 0:
        return None
    return (closes[-1] / closes[-1 - length]) - 1


def _adx(candles: list[Candle], length: int) -> float | None:
    if len(candles) <= length * 2:
        return None
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    true_ranges: list[float] = []
    for index in range(1, len(candles)):
        up = float(candles[index].high) - float(candles[index - 1].high)
        down = float(candles[index - 1].low) - float(candles[index].low)
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        high = float(candles[index].high)
        low = float(candles[index].low)
        previous = float(candles[index - 1].close)
        true_ranges.append(max(high - low, abs(high - previous), abs(low - previous)))

    def _wilder(values: list[float]) -> list[float]:
        seed = sum(values[:length])
        series = [seed]
        for value in values[length:]:
            seed = seed - (seed / length) + value
            series.append(seed)
        return series

    smoothed_tr = _wilder(true_ranges)
    smoothed_plus = _wilder(plus_dm)
    smoothed_minus = _wilder(minus_dm)
    dx: list[float] = []
    for atr, plus, minus in zip(smoothed_tr, smoothed_plus, smoothed_minus, strict=False):
        if atr == 0:
            continue
        plus_di = 100 * plus / atr
        minus_di = 100 * minus / atr
        total = plus_di + minus_di
        if total == 0:
            continue
        dx.append(100 * abs(plus_di - minus_di) / total)
    if len(dx) < length:
        return None
    value = sum(dx[:length]) / length
    for item in dx[length:]:
        value = ((value * (length - 1)) + item) / length
    return value


def _volume_confirmation(features: dict[str, str | int | float | bool]) -> float | None:
    if "return_1" not in features or "relative_volume" not in features:
        return None
    ret = float(features["return_1"])
    relative = float(features["relative_volume"]) - 1
    if ret == 0 or relative == 0:
        return 0.0
    return 1.0 if (ret > 0) == (relative > 0) else 0.0


def _window_low(lows: list[float], length: int) -> float | None:
    if len(lows) < length:
        return None
    return min(lows[-length:])


def _window_high(highs: list[float], length: int) -> float | None:
    if len(highs) < length:
        return None
    return max(highs[-length:])


def _slope(closes: list[float], length: int) -> float | None:
    if len(closes) < length:
        return None
    window = closes[-length:]
    mean_x = (length - 1) / 2
    mean_y = sum(window) / length
    variance = sum((index - mean_x) ** 2 for index in range(length))
    if variance == 0:
        return None
    return sum((index - mean_x) * (value - mean_y) for index, value in enumerate(window)) / variance


def _volatility_percentile(closes: list[float]) -> float | None:
    if len(closes) < 42:
        return None
    returns = [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes))]
    vols = [pstdev(returns[index - 20 : index]) for index in range(20, len(returns) + 1)]
    if len(vols) < 21:
        return None
    current = vols[-1]
    prior = vols[-21:-1]
    return 100 * sum(1 for value in prior if value <= current) / len(prior)


def _put(features: dict[str, str | int | float | bool], name: str, value: float | None) -> None:
    if value is not None:
        features[name] = _num(value)


def _num(value: float) -> float:
    return round(float(value), 8)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
