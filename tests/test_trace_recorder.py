"""The trace recorder stores bus messages once, and the trace routes read them back."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from contracts.enums import TradingMode
from contracts.events import EventType, channel_for
from contracts.fixtures import sample_agent_signal
from contracts.schemas.event import EventEnvelope
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher, ingest_signal
from core_ingestion.trace_recorder import record_message, run


def _signal_envelope(symbol: str = "RELIANCE") -> tuple[str, str, str]:
    signal = sample_agent_signal(symbol)
    envelope = EventEnvelope(
        event_id=f"agent.signal:{signal.signal_id}",
        event_type=EventType.AGENT_SIGNAL,
        timestamp=signal.timestamp,
        source="signal-ingestion",
        correlation_id=signal.signal_id,
        payload=signal,
    )
    return channel_for(EventType.AGENT_SIGNAL).value, envelope.model_dump_json(), signal.signal_id


def test_message_is_stored_once(repository: CoreRepository) -> None:
    channel, raw, signal_id = _signal_envelope()
    assert record_message(repository, channel, raw.encode())
    assert not record_message(repository, channel, raw)
    events = repository.list_system_events()
    assert len(events) == 1
    assert events[0]["envelope"]["channel"] == "agent.events"
    assert events[0]["envelope"]["correlation_id"] == signal_id


def test_invalid_message_is_skipped(repository: CoreRepository) -> None:
    assert not record_message(repository, "agent.events", b"{not json")
    assert repository.list_system_events() == []


def test_run_ignores_subscribe_notices(repository: CoreRepository) -> None:
    channel, raw, _ = _signal_envelope()
    messages = [
        {"type": "subscribe", "channel": b"agent.events", "data": 1},
        {"type": "message", "channel": channel.encode(), "data": raw.encode()},
    ]
    assert run(repository, messages) == 1


def test_filters_by_source_agent_and_correlation(repository: CoreRepository) -> None:
    channel, raw, signal_id = _signal_envelope("RELIANCE")
    other_channel, other_raw, _ = _signal_envelope("TCS")
    record_message(repository, channel, raw)
    record_message(repository, other_channel, other_raw)
    assert len(repository.list_system_events(correlation_id=signal_id)) == 1
    agent = sample_agent_signal("RELIANCE").agent_name.value
    assert len(repository.list_system_events(source=agent)) == 2
    assert repository.list_system_events(event_type="decision.created") == []


def test_ingested_signal_reaches_trace_route(repository: CoreRepository) -> None:
    publisher = MemoryEventPublisher()
    signal = sample_agent_signal("RELIANCE")
    result = ingest_signal(
        repository,
        publisher,
        signal,
        mode=TradingMode.PAPER,
        now=signal.timestamp,
        replay_as_of=signal.timestamp,
        skew_seconds=5,
    )
    assert result.accepted
    for channel, payload in publisher.events:
        record_message(repository, channel, payload, now=datetime.now(timezone.utc))
    app = create_app(
        Settings(
            database_url="sqlite://",
            redis_url="redis://localhost:6379/0",
            core_api_token="core",
            internal_signal_token="internal",
            max_clock_skew_seconds=5,
            trading_mode=TradingMode.PAPER,
        ),
        repository,
        MemoryEventPublisher(),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer core"}
    assert client.get("/api/v1/trace").status_code == 401
    listed = client.get("/api/v1/trace", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] == 1
    assert body["live_enabled"] is False
    item = body["events"][0]
    assert item["event_type"] == "agent.signal"
    assert item["agent"] == signal.agent_name.value
    assert item["symbol"] == "RELIANCE"
    chain = client.get(f"/api/v1/trace/{signal.signal_id}", headers=headers)
    assert chain.status_code == 200
    assert chain.json()["count"] == 1
    assert client.get("/api/v1/trace/missing", headers=headers).status_code == 404


def test_cycle_handoffs_share_one_correlation_id(repository: CoreRepository) -> None:
    from datetime import timedelta
    from decimal import Decimal

    from contracts.enums import Horizon
    from contracts.fixtures import FIXTURE_AS_OF, candles_for
    from core_paper import run_paper_cycle

    repository.upsert_candles(list(candles_for("RELIANCE")))
    signal = sample_agent_signal("RELIANCE").model_copy(
        update={
            "signal_id": "sig-trace",
            "horizon": Horizon.SWING,
            "signal": 0.5,
            "confidence": 0.8,
            "timestamp": FIXTURE_AS_OF,
            "as_of": FIXTURE_AS_OF,
            "valid_until": FIXTURE_AS_OF + timedelta(hours=6),
        }
    )
    publisher = MemoryEventPublisher()
    assert ingest_signal(
        repository, publisher, signal, mode=TradingMode.BACKTEST, now=FIXTURE_AS_OF, replay_as_of=FIXTURE_AS_OF, skew_seconds=5
    ).accepted
    repository.open_paper_session(Decimal("1000000"))
    run_paper_cycle(
        repository, publisher, mode=TradingMode.PAPER, starting_cash=Decimal("1000000"), now=FIXTURE_AS_OF, enforce_entry_window=False
    )
    for channel, payload in publisher.events:
        record_message(repository, channel, payload)
    proposal = repository.list_proposals()[0]
    chain = repository.list_system_events(correlation_id=proposal.proposal_id)
    types = {item["event_type"] for item in chain}
    assert {"decision.created", "risk.approved", "order.updated"} <= types
    assert {item["envelope"]["channel"] for item in chain} == {"decision.events", "risk.events", "order.events"}
    assert "sig-trace" in proposal.supporting_signal_ids
    assert repository.list_system_events(correlation_id="sig-trace")[0]["event_type"] == "agent.signal"


def test_latest_signal_per_agent(repository: CoreRepository) -> None:
    from contracts.enums import AgentName

    first = sample_agent_signal("RELIANCE")
    second = first.model_copy(update={"signal_id": "sig-other", "agent_name": AgentName.NEWS})
    for item in (first, second):
        repository.insert_signal(item.signal_id, item.symbol, item.exchange.value, item.model_dump(mode="json"), datetime.now(timezone.utc))
    names = [row["agent_name"] for row in repository.latest_signal_per_agent()]
    assert sorted(names) == sorted({first.agent_name.value, "news"})


def test_quant_length_signal_ids_are_recorded(repository: CoreRepository) -> None:
    signal = sample_agent_signal("RELIANCE").model_copy(update={"signal_id": "f" * 64})
    envelope = EventEnvelope(
        event_id=f"agent.signal:{signal.signal_id}", event_type=EventType.AGENT_SIGNAL, timestamp=signal.timestamp,
        source="signal-ingestion", correlation_id=signal.signal_id, payload=signal,
    )
    assert record_message(repository, "agent.events", envelope.model_dump_json())
    assert repository.list_system_events(correlation_id=signal.signal_id)[0]["event_id"] == envelope.event_id


def test_a_failing_store_does_not_crash_the_recorder(repository: CoreRepository) -> None:
    channel, raw, _ = _signal_envelope()

    class Broken:
        def insert_system_event(self, *args, **kwargs):
            raise RuntimeError("database down")

    assert record_message(Broken(), channel, raw) is False
