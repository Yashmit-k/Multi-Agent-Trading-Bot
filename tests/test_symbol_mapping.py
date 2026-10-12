"""TMPV is the current Nifty 50 member. TATAMOTORS candles stay on the old instrument."""

from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle
from core_db.repository import CoreRepository
from core_db.seed import load_seed
from core_db.session import create_schema
from core_market_data.snapshot import seed_symbols
from core_market_data.zerodha import IngestionStatus, RequestPace, ZerodhaMarketDataProvider

UTC = timezone.utc
CUTOFF = datetime(2025, 10, 24, tzinfo=UTC)
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
WINDOW_START = datetime(2026, 7, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 10, 1, tzinfo=UTC)
OLD_CLOSE = Decimal("482.5000")


class ScriptedKite:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[int, str]] = []

    def instruments(self, exchange: str) -> list[dict[str, object]]:
        assert exchange == "NSE"
        return self.rows

    def quote(self, key: str) -> dict[str, object]:
        return {}

    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str,
    ) -> list[dict[str, object]]:
        del from_date, to_date
        self.calls.append((instrument_token, interval))
        return [_bar(interval)]

    def login_url(self) -> str:
        return "https://kite.example/login"

    def generate_session(self, request_token: str) -> dict[str, object]:
        del request_token
        return {}


def _bar(interval: str) -> dict[str, object]:
    stamp = datetime(2026, 7, 1, 9, 15) if interval != "day" else datetime(2026, 7, 1)
    return {"date": stamp, "open": 300, "high": 310, "low": 290, "close": 305, "volume": 20}


def _repository() -> CoreRepository:
    return CoreRepository(create_schema("sqlite://"))


def _names(repository: CoreRepository, moment: datetime) -> set[str]:
    return {item.symbol for item in repository.members_at(moment)}


def _old_candle() -> Candle:
    return Candle(
        symbol="TATAMOTORS",
        exchange=Exchange.NSE,
        timeframe=Timeframe.D1,
        open=OLD_CLOSE - Decimal("1"),
        high=OLD_CLOSE + Decimal("1"),
        low=OLD_CLOSE - Decimal("2"),
        close=OLD_CLOSE,
        volume=100,
        start=datetime(2025, 10, 1, 3, 45, tzinfo=UTC),
        end=datetime(2025, 10, 1, 10, 0, tzinfo=UTC),
    )


def test_current_universe_resolves_tmpv_and_keeps_history() -> None:
    repository = _repository()
    legacy = repository.upsert_instrument(symbol="TATAMOTORS", exchange="NSE", trading_symbol="TATAMOTORS")
    repository.add_membership(legacy.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    repository.upsert_candles([_old_candle()])
    load_seed(repository)
    load_seed(repository)

    current = repository.members_at(NOW)
    symbols = {item.symbol for item in current}
    assert len(current) == len(symbols) == 50
    assert "TMPV" in symbols
    assert "TATAMOTORS" not in symbols
    assert "TMCV" not in symbols
    tmpv = repository.get_by_symbol("TMPV")
    assert tmpv is not None
    assert tmpv.instrument_id == "NSE:TMPV"
    assert tmpv.trading_symbol == "TMPV"

    before = _names(repository, datetime(2025, 10, 23, 10, 0, tzinfo=UTC))
    assert "TATAMOTORS" in before
    assert "TMPV" not in before
    assert len(before) == 50
    after = _names(repository, CUTOFF)
    assert "TMPV" in after
    assert "TATAMOTORS" not in after
    assert len(after) == 50

    stored = repository.stored_candles("TATAMOTORS", Timeframe.D1)
    assert [(bar.symbol, bar.close) for bar in stored] == [("TATAMOTORS", OLD_CLOSE)]
    assert repository.stored_candles("TMPV", Timeframe.D1) == []
    research = seed_symbols()
    assert len(research) == 50
    assert "TATAMOTORS" in research
    assert "TMPV" not in research
    assert "TMCV" not in research


def test_seed_selects_tmpv_daily_and_five_minute_without_renaming_history() -> None:
    repository = _repository()
    load_seed(repository)
    repository.upsert_candles([_old_candle()])
    held = repository.upsert_instrument(symbol="SBIN", exchange="NSE", trading_symbol="SBIN", instrument_token=4242)
    kite = ScriptedKite(
        [
            {"tradingsymbol": "RELIANCE", "instrument_token": 1, "name": "RELIANCE"},
            {"tradingsymbol": "TMPV", "instrument_token": 3, "name": "TATA MOTORS PASSENGER VEHICLES"},
        ]
    )
    provider = ZerodhaMarketDataProvider(repository, kite, pace=RequestPace(0), partial_gap_days=30)
    report = provider.ingest_seed_history(WINDOW_START, WINDOW_END)
    by_symbol = {row.symbol: row for row in report.rows}

    assert "TATAMOTORS" not in by_symbol
    assert "TMCV" not in by_symbol
    assert by_symbol["TMPV"].status == IngestionStatus.OK
    assert by_symbol["TMPV"].daily_count >= 1
    assert by_symbol["TMPV"].intraday_count >= 1
    assert {interval for token, interval in kite.calls if token == 3} == {"day", "5minute"}
    daily = repository.stored_candles("TMPV", Timeframe.D1)
    intraday = repository.stored_candles("TMPV", Timeframe.M5)
    assert daily and all(bar.symbol == "TMPV" for bar in daily)
    assert intraday and all(bar.symbol == "TMPV" for bar in intraday)
    assert [(bar.symbol, bar.close) for bar in repository.stored_candles("TATAMOTORS", Timeframe.D1)] == [
        ("TATAMOTORS", OLD_CLOSE)
    ]
    unchanged = repository.get_by_symbol("SBIN")
    assert unchanged is not None
    assert unchanged.instrument_id == held.instrument_id == "NSE:SBIN"
    assert unchanged.instrument_token == 4242
    reliance = repository.get_by_symbol("RELIANCE")
    assert reliance is not None and reliance.instrument_id == "NSE:RELIANCE" and reliance.instrument_token == 1


def test_missing_tmpv_is_reported_and_other_symbols_continue() -> None:
    repository = _repository()
    load_seed(repository)
    repository.upsert_candles([_old_candle()])
    kite = ScriptedKite(
        [
            {"tradingsymbol": "RELIANCE", "instrument_token": 1, "name": "RELIANCE"},
            {"tradingsymbol": "TMCV", "instrument_token": 9, "name": "TATA MOTORS"},
        ]
    )
    provider = ZerodhaMarketDataProvider(repository, kite, pace=RequestPace(0), partial_gap_days=30)
    report = provider.ingest_seed_history(WINDOW_START, WINDOW_END)
    by_symbol = {row.symbol: row for row in report.rows}

    missing = by_symbol["TMPV"]
    assert missing.status == IngestionStatus.MISSING
    assert missing.daily_count == 0
    assert missing.intraday_count == 0
    assert "no NSE tradingsymbol" in missing.detail
    assert by_symbol["RELIANCE"].status == IngestionStatus.OK
    assert "TMCV" not in by_symbol
    assert repository.get_by_symbol("TMPV") is not None
    assert repository.get_by_symbol("TMPV").instrument_token is None
    assert repository.get_by_symbol("TMCV") is None
    assert [(bar.symbol, bar.close) for bar in repository.stored_candles("TATAMOTORS", Timeframe.D1)] == [
        ("TATAMOTORS", OLD_CLOSE)
    ]
    assert repository.stored_candles("TMPV", Timeframe.D1) == []
