"""Seed ingestion reports every symbol and never stores a bar that ends after the window."""

import logging
import os
from datetime import datetime, timedelta, timezone

import pytest

from contracts.enums import Timeframe
from core_api.app import _ingest_seed_history
from core_db.repository import CoreRepository
from core_db.session import create_schema
from core_market_data.replay import HistoricalReplayMarketDataProvider
from core_market_data.zerodha import IngestionStatus, RequestPace, ZerodhaMarketDataProvider

UTC = timezone.utc
START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2024, 6, 1, tzinfo=UTC)


class ReportingKite:
    def __init__(self, *, late_days: int = 0, future: bool = False) -> None:
        self.late_days = late_days
        self.future = future

    def instruments(self, exchange: str) -> list[dict[str, object]]:
        assert exchange == "NSE"
        return [
            {"tradingsymbol": "RELIANCE", "instrument_token": 1, "name": "RELIANCE"},
            {"tradingsymbol": "LATESTART", "instrument_token": 2, "name": "LATE START"},
            {"tradingsymbol": "TMPV", "instrument_token": 3, "name": "TATA MOTORS"},
        ]

    def quote(self, key: str) -> dict[str, object]:
        return {}

    def historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str) -> list[dict[str, object]]:
        moment = from_date
        if moment.tzinfo is not None and moment.astimezone(UTC).hour >= 4:
            moment = moment + timedelta(days=1)
        day = moment.date()
        if instrument_token == 2:
            day = (moment + timedelta(days=self.late_days)).date()
        rows = [_bar(day, interval)]
        if self.future:
            rows.append(_bar(to_date.date() + timedelta(days=3), interval))
        return rows

    def login_url(self) -> str:
        return "https://kite.example/login"

    def generate_session(self, request_token: str) -> dict[str, object]:
        return {"access_token": "token"}


def _bar(day, interval: str) -> dict[str, object]:
    stamp = datetime(day.year, day.month, day.day, 9, 15) if interval != "day" else datetime(day.year, day.month, day.day)
    return {"date": stamp, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 10}


def _repository(*symbols: str) -> CoreRepository:
    repository = CoreRepository(create_schema("sqlite://"))
    for symbol in symbols:
        instrument = repository.upsert_instrument(symbol=symbol, exchange="NSE", trading_symbol=symbol)
        repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    return repository


def _ingest(repository: CoreRepository, kite: ReportingKite, partial_gap_days: int = 10):
    provider = ZerodhaMarketDataProvider(repository, kite, pace=RequestPace(0), partial_gap_days=partial_gap_days)
    return provider.ingest_seed_history(START, END)


def test_report_flags_missing_partial_and_ok() -> None:
    repository = _repository("RELIANCE", "TATAMOTORS", "LATESTART")
    report = _ingest(repository, ReportingKite(late_days=30))
    by_symbol = {row.symbol: row for row in report.rows}
    assert set(by_symbol) == {"RELIANCE", "TATAMOTORS", "LATESTART"}
    ok = by_symbol["RELIANCE"]
    assert ok.status == IngestionStatus.OK
    assert ok.daily_count >= 1
    assert ok.intraday_count >= 1
    assert ok.daily_first_bar is not None and ok.daily_last_bar is not None
    assert ok.intraday_first_bar is not None and ok.intraday_last_bar is not None
    assert ok.daily_last_bar <= END
    missing = by_symbol["TATAMOTORS"]
    assert missing.status == IngestionStatus.MISSING
    assert missing.daily_count == 0
    assert "TMPV" in missing.detail
    assert by_symbol["LATESTART"].status == IngestionStatus.PARTIAL
    widened = _ingest(repository, ReportingKite(late_days=30), partial_gap_days=40)
    assert {row.symbol: row.status for row in widened.rows}["LATESTART"] == IngestionStatus.OK
    stored = repository.get_by_symbol("RELIANCE")
    assert stored is not None
    assert stored.instrument_id == "NSE:RELIANCE"


def test_future_bar_is_absent_from_the_table_and_from_replay() -> None:
    _assert_future_bar_absent(_repository("RELIANCE"))


def test_future_bar_is_absent_from_postgres_when_configured() -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("plain Postgres is not configured")
    try:
        repository = CoreRepository(create_schema(url))
    except ModuleNotFoundError:
        pytest.skip("psycopg is not installed")
    instrument = repository.upsert_instrument(symbol="PROOF", exchange="NSE", trading_symbol="PROOF")
    joined = datetime(2024, 1, 1, tzinfo=UTC)
    repository.add_membership(instrument.instrument_id, "NIFTY50", joined, None)
    try:
        _assert_future_bar_absent(repository, symbol="PROOF")
    finally:
        repository.remove_membership(instrument.instrument_id, "NIFTY50", joined)


def test_remove_membership_restores_the_prior_universe() -> None:
    repository = _repository("RELIANCE")
    before = repository.members_at(END)
    instrument = repository.upsert_instrument(symbol="PROOF", exchange="NSE", trading_symbol="PROOF")
    joined = datetime(2024, 1, 1, tzinfo=UTC)
    repository.add_membership(instrument.instrument_id, "NIFTY50", joined, None)
    assert any(item.symbol == "PROOF" for item in repository.members_at(END))
    repository.remove_membership(instrument.instrument_id, "NIFTY50", joined)
    assert repository.members_at(END) == before


def test_in_process_migration_keeps_application_loggers(tmp_path, monkeypatch) -> None:
    from alembic import command
    from alembic.config import Config

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'alembic-log.db'}")
    config = Config(os.path.join(root, "services/core/db/alembic.ini"))
    config.set_main_option("script_location", os.path.join(root, "services/core/db/alembic"))
    command.upgrade(config, "head")
    assert logging.getLogger("core_api.app").disabled is False


def test_callback_logs_the_report_on_every_run(caplog: pytest.LogCaptureFixture) -> None:
    repository = _repository("RELIANCE", "TATAMOTORS")
    with caplog.at_level(logging.INFO, logger="core_api.app"):
        _ingest_seed_history(repository, ReportingKite(), RequestPace(0))
    assert "OK" in caplog.text
    assert "MISSING" in caplog.text
    assert "TMPV" in caplog.text
    assert "seed ingestion wrote" in caplog.text


def _assert_future_bar_absent(repository: CoreRepository, symbol: str = "RELIANCE") -> None:
    kite = ReportingKite(future=True)
    kite_rows = kite.instruments("NSE")
    kite_rows[0] = {"tradingsymbol": symbol, "instrument_token": 1, "name": symbol}

    class _Client(ReportingKite):
        def instruments(self, exchange: str) -> list[dict[str, object]]:
            assert exchange == "NSE"
            return [{"tradingsymbol": symbol, "instrument_token": 1, "name": symbol}]

    report = ZerodhaMarketDataProvider(repository, _Client(future=True), pace=RequestPace(0)).ingest_seed_history(START, END)
    assert report.rows[0].status == IngestionStatus.OK
    stored = repository.stored_candles(symbol, Timeframe.D1)
    assert stored
    assert all(bar.end <= END for bar in stored)
    replay = HistoricalReplayMarketDataProvider(repository, END + timedelta(days=30))
    visible = replay.get_candles(symbol, Timeframe.D1, START, END + timedelta(days=30))
    assert visible
    assert all(bar.end <= END for bar in visible)
    assert repository.candles_until(symbol, Timeframe.D1, END + timedelta(days=30)) == visible
