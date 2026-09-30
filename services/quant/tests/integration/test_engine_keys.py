import pytest
from datetime import datetime, timedelta, timezone

from contracts.enums import Timeframe
from contracts.schemas.market import Candle
from contracts.enums import Exchange
from quant_agents.testing.core_compatible import engine_key_snapshot


@pytest.mark.integration
def test_core_engine_keys_match_snapshot() -> None:
    from core_features.engine import build_feature_set

    candles: list[Candle] = []
    start = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)
    for index in range(40):
        begin = start + timedelta(days=index)
        end = begin.replace(hour=10, minute=0)
        open_p = 100 + index
        candles.append(
            Candle(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=str(open_p),
                high=str(open_p + 2),
                low=str(open_p - 1),
                close=str(open_p + 1),
                volume=1000 + index,
                start=begin,
                end=end,
            )
        )
    as_of = candles[-1].end
    feature_set = build_feature_set("RELIANCE", Timeframe.D1, candles, as_of)
    assert feature_set is not None
    assert sorted(feature_set.features) == sorted(engine_key_snapshot())
