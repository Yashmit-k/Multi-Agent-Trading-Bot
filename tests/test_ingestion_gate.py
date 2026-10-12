"""Seed and incremental polling share one gate. No broker calls."""

from datetime import datetime, timezone

from core_api.app import _ingest_seed_history
from core_db.repository import CoreRepository
from core_db.session import create_schema
from core_market_data.collector import HistoricalGate, IngestionState, run_incremental_once
from core_market_data.zerodha import RequestPace

UTC = timezone.utc


class Exploding:
    def instruments(self, exchange: str) -> list[dict[str, object]]:
        raise RuntimeError("disk")

    def historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str) -> list[dict[str, object]]:
        raise AssertionError("historical data must not be called")


class Idle:
    calls = 0

    def historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str) -> list[dict[str, object]]:
        type(self).calls += 1
        return []


def test_poll_skips_while_a_seed_is_queued_and_a_second_seed_is_refused() -> None:
    gate = HistoricalGate(RequestPace(0))
    state = IngestionState()
    assert gate.mark_queued() is True
    assert gate.mark_queued() is False
    assert run_incremental_once(CoreRepository(create_schema("sqlite://")), Idle(), state, gate=gate, pace=gate.pace) is False
    assert state.skipped_for_seed == 1
    assert state.poll_skip_reason == "seed_active"
    assert Idle.calls == 0
    gate.begin_seed()
    gate.finish_seed()
    assert gate.begin_poll() == "acquired"
    gate.finish_poll()


def test_seed_failure_releases_the_gate() -> None:
    repository = CoreRepository(create_schema("sqlite://"))
    instrument = repository.upsert_instrument(symbol="RELIANCE", exchange="NSE", trading_symbol="RELIANCE")
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    gate = HistoricalGate(RequestPace(0))
    state = IngestionState()
    assert gate.mark_queued() is True
    _ingest_seed_history(repository, Exploding(), gate.pace, state, gate)
    assert state.seed_status == "failed"
    assert state.last_error == "RuntimeError"
    assert gate.begin_poll() == "acquired"
    gate.finish_poll()


def test_rejected_credentials_are_not_tried_again() -> None:
    state = IngestionState()
    state.credentials_rejected = True
    client = Idle()
    assert run_incremental_once(CoreRepository(create_schema("sqlite://")), client, state, pace=RequestPace(0)) is False
    assert client.calls == 0
    assert state.last_error == "authentication_failed"


def test_seed_and_poll_share_one_pace() -> None:
    pace = RequestPace(0)
    gate = HistoricalGate(pace)
    assert gate.pace is pace
