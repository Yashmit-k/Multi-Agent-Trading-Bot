"""Build candles and one feature snapshot per instrument from stored ticks."""

from datetime import datetime

from contracts.enums import Timeframe
from core_candles import build_candles
from core_db.repository import CoreRepository
from core_features import FEATURE_VERSION, build_feature_set

TIMEFRAMES = (Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.M30, Timeframe.H1, Timeframe.D1)


def run_once(repository: CoreRepository, as_of: datetime, timeframes: tuple[Timeframe, ...] = TIMEFRAMES) -> int:
    written = 0
    for instrument in repository.members_at(as_of):
        ticks = repository.ticks_until(instrument.instrument_id, as_of)
        for timeframe in timeframes:
            candles = build_candles(ticks, timeframe, as_of)
            if not candles:
                continue
            repository.upsert_candles(candles)
            feature_set = build_feature_set(instrument.symbol, timeframe, candles, as_of)
            if feature_set is None:
                continue
            repository.upsert_feature(feature_set, instrument.instrument_id)
            written += 1
    return written


def feature_version() -> str:
    return FEATURE_VERSION
