"""The portfolio-manager gate: agent BUYs wait for the manager's verdict, which can shrink or veto them."""

import json
from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from contracts.enums import Horizon, RiskStatus, Side, TradingMode
from contracts.fixtures import FIXTURE_AS_OF, candles_for, sample_agent_signal
from contracts.schemas.review import ProposalReview
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher, ingest_signal
from core_paper import run_paper_cycle
from core_paper.review_gate import REVIEW_TIMEOUT

INTERNAL = {"Authorization": "Bearer internal"}
USER = {"Authorization": "Bearer core"}


def _bullish(repository: CoreRepository) -> MemoryEventPublisher:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    repository.open_paper_session(Decimal("1000000"))
    signal = sample_agent_signal("RELIANCE").model_copy(
        update={"signal_id": "sig-bull", "horizon": Horizon.SWING, "signal": 0.9, "confidence": 0.9, "timestamp": FIXTURE_AS_OF, "as_of": FIXTURE_AS_OF, "valid_until": FIXTURE_AS_OF + timedelta(hours=6)}
    )
    publisher = MemoryEventPublisher()
    ingest_signal(repository, publisher, signal, mode=TradingMode.BACKTEST, now=FIXTURE_AS_OF, replay_as_of=FIXTURE_AS_OF, skew_seconds=5)
    return publisher


def _cycle(repository: CoreRepository, publisher: MemoryEventPublisher, now) -> None:
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=Decimal("1000000"), now=now, enforce_entry_window=False, manager_review=True)


def _verdict(repository: CoreRepository, verdict: str, fraction: float) -> None:
    row = repository.list_reviews(limit=1)[0]
    repository.complete_review(
        ProposalReview(review_id=row["review_id"], kind="pipeline", proposal_id=row["proposal_id"], symbol="RELIANCE", verdict=verdict, size_fraction=fraction,
                       conflicts=["news: negative headline vs bullish momentum"], critique="Test verdict with enough words to explain itself.", reviewer="test-model", steps=3, timestamp=FIXTURE_AS_OF),
        FIXTURE_AS_OF,
    )


def _event_types(publisher: MemoryEventPublisher) -> list[str]:
    return [json.loads(payload)["event_type"] for _, payload in publisher.events]


def test_a_buy_waits_for_the_manager_and_is_queued_for_review(repository: CoreRepository) -> None:
    publisher = _bullish(repository)
    _cycle(repository, publisher, FIXTURE_AS_OF)
    assert [o for o in repository.list_orders() if o.side == Side.BUY] == []
    reviews = repository.list_reviews()
    assert len(reviews) == 1 and reviews[0]["status"] == "pending" and reviews[0]["kind"] == "pipeline"
    proposal = repository.get_proposal(reviews[0]["proposal_id"])
    assert repository.risk_for_proposal(proposal.proposal_id) is None
    assert "review.requested" in _event_types(publisher)
    _cycle(repository, publisher, FIXTURE_AS_OF + timedelta(seconds=30))
    assert len(repository.list_reviews()) == 1  # no duplicate request


def test_a_veto_fails_the_portfolio_manager_risk_check(repository: CoreRepository) -> None:
    publisher = _bullish(repository)
    _cycle(repository, publisher, FIXTURE_AS_OF)
    _verdict(repository, "VETO", 0.0)
    _cycle(repository, publisher, FIXTURE_AS_OF + timedelta(seconds=30))
    proposal_id = repository.list_reviews()[0]["proposal_id"]
    decision = repository.risk_for_proposal(proposal_id)
    assert decision.status == RiskStatus.REJECTED
    check = next(item for item in decision.checks if item.name == "portfolio_manager")
    assert not check.passed and "vetoed" in check.detail
    assert repository.order_for_proposal(proposal_id) is None


def test_a_reduce_shrinks_the_order(repository: CoreRepository) -> None:
    publisher = _bullish(repository)
    _cycle(repository, publisher, FIXTURE_AS_OF)
    proposal = repository.get_proposal(repository.list_reviews()[0]["proposal_id"])
    _verdict(repository, "REDUCE", 0.5)
    _cycle(repository, publisher, FIXTURE_AS_OF + timedelta(seconds=30))
    decision = repository.risk_for_proposal(proposal.proposal_id)
    assert decision.status == RiskStatus.APPROVED
    assert decision.approved_quantity == max(1, int(proposal.quantity * 0.5))
    order = repository.order_for_proposal(proposal.proposal_id)
    assert order is not None and order.quantity <= decision.approved_quantity


def test_no_answer_in_time_is_recorded_and_the_rules_decide(repository: CoreRepository) -> None:
    publisher = _bullish(repository)
    _cycle(repository, publisher, FIXTURE_AS_OF)
    _cycle(repository, publisher, FIXTURE_AS_OF + REVIEW_TIMEOUT + timedelta(seconds=1))
    row = repository.list_reviews()[0]
    assert row["status"] == "done" and row["verdict"]["verdict"] == "UNAVAILABLE"
    decision = repository.risk_for_proposal(row["proposal_id"])
    assert decision.status == RiskStatus.APPROVED
    assert all(item.name != "portfolio_manager" for item in decision.checks)
    assert "review.completed" in _event_types(publisher)


def test_review_off_keeps_the_old_path(repository: CoreRepository) -> None:
    publisher = _bullish(repository)
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=Decimal("1000000"), now=FIXTURE_AS_OF, enforce_entry_window=False)
    assert repository.list_reviews() == []
    assert [o for o in repository.list_orders() if o.side == Side.BUY]


def _client(repository: CoreRepository) -> tuple[TestClient, MemoryEventPublisher]:
    from core_api.app import create_app
    from core_api.settings import Settings

    settings = Settings(database_url="sqlite://", redis_url="redis://localhost:6379/0", core_api_token="core", internal_signal_token="internal", max_clock_skew_seconds=5, trading_mode=TradingMode.PAPER)
    publisher = MemoryEventPublisher()
    return TestClient(create_app(settings, repository, publisher)), publisher


def test_ad_hoc_review_round_trip_through_the_api(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    client, publisher = _client(repository)
    assert client.post("/api/v1/reviews", json={"symbol": "RELIANCE"}).status_code == 401
    assert client.post("/api/v1/reviews", json={"symbol": "NOPE"}, headers=USER).status_code == 422
    asked = client.post("/api/v1/reviews", json={"symbol": "reliance"}, headers=USER).json()
    review_id = asked["review_id"]
    claimed = client.post("/api/v1/internal/reviews/claim", headers=INTERNAL).json()
    assert [item["review_id"] for item in claimed] == [review_id]
    assert client.post("/api/v1/internal/reviews/claim", headers=INTERNAL).json() == []  # already running
    step = {"review_id": review_id, "step": 1, "kind": "tool_call", "actor": "portfolio_manager", "timestamp": FIXTURE_AS_OF.isoformat(), "tool": "get_agent_opinions", "purpose": "see who disagrees"}
    assert client.post(f"/api/v1/internal/reviews/{review_id}/steps", json=step, headers=INTERNAL).json() == {"stored": True}
    ask = {"request_id": "req-1", "review_id": review_id, "to_agent": "news", "symbol": "RELIANCE", "question": "Any fresh headline?", "timestamp": FIXTURE_AS_OF.isoformat()}
    assert client.post(f"/api/v1/internal/reviews/{review_id}/steps", json=ask, headers=INTERNAL).status_code == 200
    assert client.post(f"/api/v1/internal/reviews/{review_id}/steps", json={**step, "kind": "nonsense"}, headers=INTERNAL).status_code == 422
    bad = {"review_id": review_id, "kind": "ad_hoc", "symbol": "RELIANCE", "verdict": "REDUCE", "size_fraction": 1.5, "critique": "x", "reviewer": "m", "steps": 2, "timestamp": FIXTURE_AS_OF.isoformat()}
    assert client.post(f"/api/v1/internal/reviews/{review_id}/verdict", json=bad, headers=INTERNAL).status_code == 422
    good = {**bad, "verdict": "VETO", "size_fraction": 0.0, "critique": "News and momentum disagree; no edge after costs."}
    assert client.post(f"/api/v1/internal/reviews/{review_id}/verdict", json=good, headers=INTERNAL).status_code == 200
    assert client.post(f"/api/v1/internal/reviews/{review_id}/verdict", json=good, headers=INTERNAL).status_code == 409
    detail = client.get(f"/api/v1/reviews/{review_id}", headers=USER).json()
    assert detail["status"] == "done" and detail["verdict"]["verdict"] == "VETO" and len(detail["steps"]) == 2
    assert detail["correlation_id"] == review_id
    types = _event_types(publisher)
    assert types.count("review.requested") == 1 and "review.step" in types and "agent.request" in types and "review.completed" in types
    channels = {channel for channel, _ in publisher.events}
    assert {"review.events", "agent.events"} <= channels


def test_manager_tools_are_internal_and_tolerate_bad_input(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    client, _ = _client(repository)
    assert client.get("/api/v1/internal/tools/opinions?symbol=RELIANCE", headers=USER).status_code == 401
    opinions = client.get("/api/v1/internal/tools/opinions?symbol=RELIANCE", headers=INTERNAL).json()
    assert opinions["symbol"] == "RELIANCE" and "agents" in opinions
    assert "error" in client.get("/api/v1/internal/tools/opinions?symbol=NOPE", headers=INTERNAL).json()
    assert "close" in client.get("/api/v1/internal/tools/features?symbol=RELIANCE", headers=INTERNAL).json()
    assert "entries_today" in client.get("/api/v1/internal/tools/portfolio", headers=INTERNAL).json()
    assert client.get("/api/v1/internal/tools/track_record?symbol=RELIANCE", headers=INTERNAL).json()["past_reviews"] == []
    assert client.get("/api/v1/internal/tools/teleport", headers=INTERNAL).status_code == 404
