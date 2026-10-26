"""Incremental candle polling. The fake client never contacts Zerodha."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from contracts.enums import Exchange, Timeframe, TradingMode
from contracts.fixtures import FIXTURE_AS_OF, candles_for, sample_agent_signal
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.market import Candle
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_db.session import create_schema
from core_ingestion.service import MemoryEventPublisher, ingest_signal
from core_market_data.collector import IngestionState, run_incremental_once
from core_market_data.nse_sessions import IST
from core_market_data.schedule import candle_is_fresh, expected_completed_end, incremental_range
from core_market_data.zerodha import RequestPace, ZerodhaMarketDataProvider
from core_paper import run_paper_cycle

UTC = timezone.utc
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
HEADERS = {"Authorization": "Bearer core"}


class ReadTimeout(Exception):
    pass


class TokenException(Exception):
    pass


class ScriptedKite:
    def __init__(self, fail_symbols: set[str] | None = None, fail_times: int = 0) -> None:
        self.fail_symbols = fail_symbols or set()
        self.fail_times = fail_times
        self.calls: list[tuple[int, str]] = []
        self.sleeps: list[float] = []
        self._failures: dict[int, int] = {}

    def historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str):
        self.calls.append((instrument_token, interval))
        seen = self._failures.get(instrument_token, 0)
        if instrument_token in self.fail_symbols or seen < self.fail_times:
            self._failures[instrument_token] = seen + 1
            if instrument_token in self.fail_symbols or seen < self.fail_times:
                raise ReadTimeout("read timed out")
        day = to_date.astimezone(UTC)
        if interval == "day":
            return [{"date": datetime(day.year, day.month, day.day), "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}]
        stamp = to_date.astimezone(UTC) - timedelta(minutes=5)
        return [{"date": stamp, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}]

    def instruments(self, exchange: str) -> list[dict[str, object]]:
        return []

    def quote(self, key: str) -> dict[str, object]:
        return {}


def test_incremental_range_is_the_gap_after_the_last_bar() -> None:
    last = datetime(2026, 10, 9, 9, 45, tzinfo=UTC)
    window = incremental_range(last, Timeframe.M5, NOW)
    assert window is not None
    start, end = window
    assert start == last - timedelta(minutes=5)
    assert end == NOW
    assert incremental_range(None, Timeframe.M5, NOW) is None
    caught_up = expected_completed_end(Timeframe.M5, NOW)
    assert incremental_range(caught_up, Timeframe.M5, NOW) is None


def test_daily_bar_stays_incomplete_until_after_the_close_delay() -> None:
    during = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)
    assert expected_completed_end(Timeframe.D1, during) == datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    # The official NSE close is published after 15:30: the daily bar waits 30 minutes for it.
    for still_previous in (datetime(2026, 10, 12, 10, 2, tzinfo=UTC), datetime(2026, 10, 12, 10, 29, tzinfo=UTC)):  # 15:32 and 15:59 IST
        assert expected_completed_end(Timeframe.D1, still_previous) == datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    after = datetime(2026, 10, 12, 10, 30, tzinfo=UTC)  # 16:00 IST
    assert expected_completed_end(Timeframe.D1, after) == datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


def test_after_the_close_the_expected_five_minute_end_is_1515() -> None:
    ready = datetime(2026, 10, 13, 15, 31, 30, tzinfo=IST)
    expected = expected_completed_end(Timeframe.M5, ready)
    close_grace = datetime(2026, 10, 13, 15, 15, tzinfo=IST).astimezone(UTC)
    assert expected == close_grace
    assert expected != datetime(2026, 10, 13, 15, 25, tzinfo=IST).astimezone(UTC)
    assert expected != datetime(2026, 10, 13, 15, 30, tzinfo=IST).astimezone(UTC)


def test_weekend_and_holiday_use_the_previous_session() -> None:
    sunday = datetime(2026, 10, 11, 4, 0, tzinfo=UTC)
    assert expected_completed_end(Timeframe.D1, sunday) == datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    holiday = datetime(2026, 10, 2, 8, 0, tzinfo=UTC)
    assert expected_completed_end(Timeframe.D1, holiday) == datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def test_repeated_upsert_does_not_duplicate_a_bar() -> None:
    repository = _repo("RELIANCE", 1)
    bar = _bar("RELIANCE", datetime(2026, 10, 9, 3, 45, tzinfo=UTC), datetime(2026, 10, 9, 3, 50, tzinfo=UTC))
    repository.upsert_candles([bar, bar])
    assert len(repository.stored_candles("RELIANCE", Timeframe.M5)) == 1


def test_complete_chunk_is_not_downloaded_again() -> None:
    repository = _repo("RELIANCE", 1)
    start = datetime(2026, 10, 9, 3, 45, tzinfo=UTC)
    end = datetime(2026, 10, 9, 3, 50, tzinfo=UTC)
    repository.upsert_candles([_bar("RELIANCE", start, end)])
    client = ScriptedKite()
    provider = ZerodhaMarketDataProvider(repository, client, pace=RequestPace(0), retry_sleep=lambda _seconds: None)
    candles = provider.get_candles("RELIANCE", Timeframe.M5, start, end)
    assert len(candles) == 1
    assert client.calls == []


def test_timeout_is_isolated_and_retried_then_the_next_symbol_continues() -> None:
    repository = _repo("AAA", 1)
    _add(repository, "BBB", 2)
    _add(repository, "CCC", 3)
    client = ScriptedKite(fail_symbols={2})
    sleeps: list[float] = []
    provider = ZerodhaMarketDataProvider(
        repository,
        client,
        pace=RequestPace(0),
        retry_attempts=2,
        retry_sleep=sleeps.append,
    )
    report = provider.download_seed_candles(datetime(2026, 10, 9, 3, 0, tzinfo=UTC), datetime(2026, 10, 9, 10, 0, tzinfo=UTC))
    by_symbol = {row.symbol: row for row in report.rows}
    assert by_symbol["AAA"].status.value == "OK"
    assert "ReadTimeout" in by_symbol["BBB"].detail
    assert by_symbol["CCC"].status.value == "OK"
    assert sleeps


def test_authentication_failure_is_not_retried() -> None:
    repository = _repo("RELIANCE", 1)

    class Denied:
        def historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str):
            raise TokenException("incorrect api_key or access_token")

        def instruments(self, exchange: str) -> list[dict[str, object]]:
            return []

        def quote(self, key: str) -> dict[str, object]:
            return {}

    provider = ZerodhaMarketDataProvider(repository, Denied(), pace=RequestPace(0), retry_attempts=3, retry_sleep=lambda _seconds: None)
    report = provider.download_seed_candles(datetime(2026, 10, 9, 3, 0, tzinfo=UTC), datetime(2026, 10, 9, 10, 0, tzinfo=UTC))
    assert report.rows[0].detail.endswith("authentication_failed")


def test_interrupted_incremental_recovers_on_the_next_pass() -> None:
    repository = _repo("RELIANCE", 1)
    old = datetime(2026, 10, 7, 7, 50, tzinfo=UTC)
    repository.upsert_candles([_bar("RELIANCE", old - timedelta(minutes=5), old)])
    state = IngestionState()
    run_incremental_once(repository, ScriptedKite(fail_times=5), state, now=NOW, pace=RequestPace(0))
    assert state.symbols[0].last_error is not None
    assert "ReadTimeout" in state.symbols[0].last_error
    second = IngestionState()
    run_incremental_once(repository, ScriptedKite(), second, now=NOW, pace=RequestPace(0))
    assert second.symbols[0].last_error == "needs_seed"
    assert second.last_success_at is not None
    stored = repository.latest_candle("RELIANCE", Timeframe.M5)
    assert stored is not None
    assert stored.end > old


def test_overlap_skips_a_second_pass() -> None:
    repository = _repo("RELIANCE", 1)
    state = IngestionState()
    assert state._lock.acquire(blocking=False)
    try:
        assert run_incremental_once(repository, ScriptedKite(), state, now=NOW, pace=RequestPace(0)) is False
        assert state.skipped_overlap == 1
    finally:
        state._lock.release()


def test_collector_status_hides_credentials_and_reports_freshness() -> None:
    repository = _repo("RELIANCE", 1)
    end = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    start = datetime(2026, 10, 9, 3, 45, tzinfo=UTC)
    repository.upsert_candles(
        [
            Candle(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10"),
                volume=1,
                start=start,
                end=end,
            )
        ]
    )
    state = IngestionState()
    run_incremental_once(repository, ScriptedKite(), state, now=datetime(2026, 10, 9, 10, 30, tzinfo=UTC), pace=RequestPace(0))
    body = state.snapshot()
    assert body["live_enabled"] is False
    assert "access_token" not in str(body)
    assert body["symbols"][0]["daily_fresh"] is True
    assert candle_is_fresh(end, Timeframe.D1, datetime(2026, 10, 9, 10, 30, tzinfo=UTC))


def test_returned_status_matches_the_bar_just_persisted() -> None:
    """The status row is the stored candle, not the candle read before the upsert."""
    clock = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)
    repository = _repo("RELIANCE", 1)
    old_daily_end = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    old_intraday_end = datetime(2026, 10, 13, 3, 50, tzinfo=UTC)
    repository.upsert_candles(
        [
            Candle(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10"),
                volume=1,
                start=datetime(2026, 10, 9, 3, 45, tzinfo=UTC),
                end=old_daily_end,
            ),
            _bar("RELIANCE", old_intraday_end - timedelta(minutes=5), old_intraday_end),
        ]
    )
    state = IngestionState()
    assert run_incremental_once(repository, _FreshBars(), state, now=clock, pace=RequestPace(0)) is True
    row = state.symbols[0]
    stored_daily = repository.latest_candle("RELIANCE", Timeframe.D1)
    stored_intraday = repository.latest_candle("RELIANCE", Timeframe.M5)
    assert stored_daily is not None and stored_intraday is not None
    assert stored_daily.end > old_daily_end
    assert stored_intraday.end > old_intraday_end
    assert row.daily_end == stored_daily.end.isoformat()
    assert row.intraday_end == stored_intraday.end.isoformat()
    assert row.daily_fresh is candle_is_fresh(stored_daily.end, Timeframe.D1, clock)
    assert row.intraday_fresh is candle_is_fresh(stored_intraday.end, Timeframe.M5, clock)
    assert row.daily_fresh is True
    assert row.intraday_fresh is True


class _FreshBars:
    """Returns one completed daily bar and one completed five-minute bar. No network."""

    def historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str):
        if interval == "day":
            return [{"date": datetime(2026, 10, 12), "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}]
        start = datetime(2026, 10, 13, 4, 50, tzinfo=UTC)
        return [{"date": start, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}]

    def instruments(self, exchange: str) -> list[dict[str, object]]:
        return []

    def quote(self, key: str) -> dict[str, object]:
        return {}


def test_stale_candle_does_not_open_a_new_paper_order(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    signal = sample_agent_signal("RELIANCE")
    stored = AgentSignal.model_validate({**signal.model_dump(), "signal_id": "sig-stale-guard", "timestamp": FIXTURE_AS_OF, "as_of": FIXTURE_AS_OF})
    result = ingest_signal(
        repository,
        MemoryEventPublisher(),
        stored,
        mode=TradingMode.BACKTEST,
        now=FIXTURE_AS_OF,
        replay_as_of=FIXTURE_AS_OF,
        skew_seconds=5,
    )
    assert result.accepted
    run_paper_cycle(
        repository,
        MemoryEventPublisher(),
        mode=TradingMode.PAPER,
        starting_cash=Decimal("1000000"),
        require_fresh=True,
        now=NOW,
    )
    assert repository.list_orders() == []
    assert repository.list_proposals() == []


def test_ingestion_route_reports_auth_required_without_a_token() -> None:
    app = create_app(
        Settings(
            database_url="sqlite://",
            redis_url="redis://localhost:6379/0",
            core_api_token="core",
            internal_signal_token="internal",
            max_clock_skew_seconds=5,
            trading_mode=TradingMode.PAPER,
        ),
        CoreRepository(create_schema("sqlite://")),
    )
    client = TestClient(app)
    response = client.get("/api/v1/market/ingestion", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is False
    assert body["live_enabled"] is False
    assert body["collector_enabled"] is False


def test_collector_module_does_not_submit_orders() -> None:
    from pathlib import Path

    source = Path("services/core/market-data/src/core_market_data/collector.py").read_text(encoding="utf-8")
    assert "place_order" not in source
    assert "run_paper_cycle" not in source


def _repo(symbol: str, token: int) -> CoreRepository:
    repository = CoreRepository(create_schema("sqlite://"))
    _add(repository, symbol, token)
    return repository


def _add(repository: CoreRepository, symbol: str, token: int) -> None:
    instrument = repository.upsert_instrument(
        symbol=symbol,
        exchange="NSE",
        trading_symbol=symbol,
        instrument_token=token,
    )
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)


def _bar(symbol: str, start: datetime, end: datetime) -> Candle:
    return Candle(
        symbol=symbol,
        exchange=Exchange.NSE,
        timeframe=Timeframe.M5,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        volume=1,
        start=start,
        end=end,
    )
