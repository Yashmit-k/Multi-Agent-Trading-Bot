"""Kite historical bounds. The stand-in never contacts Zerodha."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from core_db.repository import CoreRepository
from core_db.session import create_schema
from core_market_data.kite_client import KiteConnectMarketClient, kite_historical_bound
from core_market_data.zerodha import RequestPace, ZerodhaMarketDataProvider
from contracts.enums import Timeframe

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")
MONDAY_AFTERNOON_UTC = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


class RecordingKite:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.rows = rows or []

    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime | str,
        to_date: datetime | str,
        interval: str,
        continuous: bool,
        oi: bool,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "instrument_token": instrument_token,
                "from_date": from_date,
                "to_date": to_date,
                "interval": interval,
                "continuous": continuous,
                "oi": oi,
            }
        )
        return list(self.rows)


def test_utc_instant_is_sent_as_the_ist_wall_clock() -> None:
    assert kite_historical_bound(MONDAY_AFTERNOON_UTC) == "2026-10-12 14:30:00"


def test_both_boundaries_use_ist() -> None:
    start = datetime(2026, 10, 9, 9, 40, tzinfo=UTC)
    end = MONDAY_AFTERNOON_UTC
    kite = RecordingKite()
    KiteConnectMarketClient("key", "secret", kite=kite).historical_data(1, start, end, "5minute")
    call = kite.calls[0]
    assert call["from_date"] == "2026-10-09 15:10:00"
    assert call["to_date"] == "2026-10-12 14:30:00"
    assert call["from_date"] != "2026-10-09 09:40:00"
    assert call["to_date"] != "2026-10-12 09:00:00"


def test_monday_afternoon_is_not_sent_as_monday_morning() -> None:
    kite = RecordingKite()
    KiteConnectMarketClient("key", "secret", kite=kite).historical_data(
        1,
        MONDAY_AFTERNOON_UTC,
        MONDAY_AFTERNOON_UTC + timedelta(minutes=30),
        "5minute",
    )
    assert kite.calls[0]["from_date"] == "2026-10-12 14:30:00"
    assert kite.calls[0]["to_date"] == "2026-10-12 15:00:00"


def test_utc_evening_uses_the_next_ist_calendar_date() -> None:
    evening = datetime(2026, 10, 12, 20, 30, tzinfo=UTC)
    assert kite_historical_bound(evening) == "2026-10-13 02:00:00"


def test_naive_bound_is_not_shifted() -> None:
    naive = datetime(2026, 10, 12, 14, 30)
    assert kite_historical_bound(naive) is naive
    kite = RecordingKite()
    KiteConnectMarketClient("key", "secret", kite=kite).historical_data(1, naive, datetime(2026, 10, 12, 15, 30), "day")
    assert kite.calls[0]["from_date"] is naive
    assert kite.calls[0]["to_date"] == datetime(2026, 10, 12, 15, 30)


def test_the_same_instant_is_not_shifted_twice() -> None:
    ist = MONDAY_AFTERNOON_UTC.astimezone(IST)
    first = kite_historical_bound(MONDAY_AFTERNOON_UTC)
    again = kite_historical_bound(MONDAY_AFTERNOON_UTC)
    already_local = kite_historical_bound(ist)
    assert first == again == already_local == "2026-10-12 14:30:00"


def test_daily_and_five_minute_requests_use_ist_and_keep_the_utc_filter() -> None:
    repository = CoreRepository(create_schema("sqlite://"))
    instrument = repository.upsert_instrument(symbol="RELIANCE", exchange="NSE", trading_symbol="RELIANCE", instrument_token=1)
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    rows = [
        _row(datetime(2026, 10, 9, 9, 15, tzinfo=IST)),
        _row(datetime(2026, 10, 12, 14, 30, tzinfo=IST)),
    ]
    kite = RecordingKite(rows)
    client = KiteConnectMarketClient("key", "secret", kite=kite)
    provider = ZerodhaMarketDataProvider(repository, client, pace=RequestPace(0))
    start = datetime(2026, 10, 9, 3, 45, tzinfo=UTC)
    end = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    daily = provider.get_candles("RELIANCE", Timeframe.D1, start, end)
    intraday = provider.get_candles("RELIANCE", Timeframe.M5, start, end)
    by_interval = {call["interval"]: call for call in kite.calls}
    assert by_interval["day"]["from_date"] == "2026-10-09 09:15:00"
    assert by_interval["day"]["to_date"] == "2026-10-09 15:30:00"
    assert by_interval["5minute"]["from_date"] == "2026-10-09 09:15:00"
    assert by_interval["5minute"]["to_date"] == "2026-10-09 15:30:00"
    assert len(daily) == 1
    assert daily[0].start == datetime(2026, 10, 9, 3, 45, tzinfo=UTC)
    assert daily[0].end == datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    assert len(intraday) == 1
    assert intraday[0].start == datetime(2026, 10, 9, 3, 45, tzinfo=UTC)
    assert intraday[0].end == datetime(2026, 10, 9, 3, 50, tzinfo=UTC)


def _row(stamp: datetime) -> dict[str, object]:
    return {"date": stamp, "open": 10, "high": 11, "low": 9, "close": Decimal("10"), "volume": 1}
