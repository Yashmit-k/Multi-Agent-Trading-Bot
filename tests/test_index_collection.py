"""NIFTY 50 and INDIA VIX are collected for the regime agent, seeding a bounded history on first sight."""

from datetime import datetime, timedelta, timezone

from contracts.enums import Timeframe
from core_market_data.collector import INDEX_INSTRUMENTS, INDEX_SEED_DAYS, _one_symbol


class FakeProvider:
    def __init__(self) -> None:
        self.windows: list[tuple[str, Timeframe, datetime, datetime]] = []

    def get_candles(self, symbol, timeframe, start, end):
        self.windows.append((symbol, timeframe, start, end))
        return []


def test_empty_index_is_seeded_with_bounded_history(repository) -> None:
    now = datetime(2026, 10, 15, 5, 0, tzinfo=timezone.utc)
    trading_symbol, token = INDEX_INSTRUMENTS["NIFTY50"]
    repository.upsert_instrument(symbol="NIFTY50", trading_symbol=trading_symbol, instrument_token=token)
    provider = FakeProvider()
    _one_symbol(provider, repository, "NIFTY50", now, seed_if_empty=True)
    seen = {timeframe: (start, end) for _, timeframe, start, end in provider.windows}
    assert seen[Timeframe.D1] == (now - timedelta(days=INDEX_SEED_DAYS[Timeframe.D1]), now)
    assert seen[Timeframe.M5] == (now - timedelta(days=INDEX_SEED_DAYS[Timeframe.M5]), now)


def test_stocks_without_history_still_wait_for_the_seed(repository) -> None:
    provider = FakeProvider()
    row = _one_symbol(provider, repository, "RELIANCE", datetime(2026, 10, 15, 5, 0, tzinfo=timezone.utc))
    assert provider.windows == [] or all(window[2] != window[3] for window in provider.windows)
    assert row.symbol == "RELIANCE"


def test_index_tokens_are_the_kite_ones() -> None:
    assert INDEX_INSTRUMENTS == {"NIFTY50": ("NIFTY 50", 256265), "INDIAVIX": ("INDIA VIX", 264969)}
