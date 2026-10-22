"""scripts/decision_audit.py: forward returns without look-ahead, and joining proposals to their outcomes."""

import importlib.util
from datetime import date
from pathlib import Path

from pytest import approx

_SPEC = importlib.util.spec_from_file_location("decision_audit", Path(__file__).resolve().parents[1] / "scripts" / "decision_audit.py")
audit = importlib.util.module_from_spec(_SPEC)  # type: ignore[arg-type]
_SPEC.loader.exec_module(audit)  # type: ignore[union-attr]


def _bar(day: str, close: float) -> dict:
    return {"start": f"{day}T03:45:00Z", "end": f"{day}T10:00:00Z", "close": str(close)}


CANDLES = [_bar("2026-10-14", 90), _bar("2026-10-15", 500), _bar("2026-10-16", 110), _bar("2026-10-19", 120), _bar("2026-10-21", 80)]


def test_returns_use_only_sessions_after_the_decision() -> None:
    # Decided at 11:45 IST on 15 Oct at 100. That session's own close (500) is after the decision bar: never used.
    returns = audit.forward_returns(CANDLES, "2026-10-15T06:15:00Z", 100.0, horizons=(1, 2, 3, 4))
    assert returns[1] == approx(0.10) and returns[2] == approx(0.20) and returns[3] == approx(-0.20)  # 110, 120, 80
    assert returns[4] is None  # no fourth later session yet


def test_session_date_is_the_ist_day() -> None:
    assert audit.session_date("2026-10-15T19:00:00Z") == date(2026, 10, 16)  # 00:30 IST the next day
    # A decision made after the 15 Oct close is still on 15 Oct (IST): its first later session is 16 Oct.
    assert audit.forward_returns(CANDLES, "2026-10-15T10:00:00Z", 100.0, horizons=(1,))[1] == approx(0.10)


def _event(event_type: str, payload: dict) -> dict:
    return {"event_type": event_type, "payload": payload}


def _proposal(pid: str, symbol: str, *, side: str = "BUY", strategy: str = "paper-fusion", ts: str = "2026-10-15T06:15:00Z", signal: float = 0.4, ids: list[str] | None = None) -> dict:
    return {
        "proposal_id": pid, "symbol": symbol, "side": side, "horizon": "SWING", "timestamp": ts, "quantity": 10, "entry_price": "100",
        "strategy_id": strategy, "aggregated_signal": signal, "aggregated_confidence": 0.5, "supporting_signal_ids": ids or [],
    }


def _risk(pid: str, status: str, failed: tuple[str, ...] = (), quantity: int = 10) -> dict:
    checks = [{"name": "mode_is_paper", "passed": True}] + [{"name": name, "passed": False} for name in failed]
    return {"proposal_id": pid, "status": status, "checks": checks, "approved_quantity": quantity if status == "APPROVED" else None}


def _payloads() -> dict:
    decisions = [
        _proposal("p-filled", "AAA", ids=["s-tech", "s-news", "s-flat"]),
        _proposal("p-full", "AAA", ids=["s-tech"]),
        _proposal("p-veto", "AAA"),
        _proposal("p-reduced", "AAA"),
        _proposal("manual-1", "AAA", strategy="manual"),  # not an agent proposal
        _proposal("p-old", "AAA", ts="2026-10-13T06:15:00Z"),  # before --since
    ]
    return {
        "decision.created": {"events": [_event("decision.created", p) for p in decisions]},
        "risk.approved": {"events": [_event("risk.approved", _risk("p-filled", "APPROVED")), _event("risk.approved", _risk("p-reduced", "APPROVED", quantity=5))]},
        "risk.rejected": {
            "events": [
                _event("risk.rejected", _risk("p-full", "REJECTED", ("max_open_positions", "daily_entry_cap"))),
                _event("risk.rejected", _risk("p-veto", "REJECTED", ("portfolio_manager",))),
            ]
        },
        "review.completed": {"events": [_event("review.completed", {"proposal_id": "p-veto", "verdict": "VETO"}), _event("review.completed", {"proposal_id": None, "verdict": "VETO"})]},
        "orders": [{"proposal_id": "p-filled", "status": "FILLED"}, {"proposal_id": "p-reduced", "status": "EXPIRED"}],
    }


SIGNALS = {
    "AAA": [
        {"signal_id": "s-tech", "agent_name": "technical", "signal": 0.6},
        {"signal_id": "s-news", "agent_name": "news", "signal": 0.3},
        {"signal_id": "s-flat", "agent_name": "volume", "signal": 0.01},  # too small to support either side
    ]
}


def test_proposals_join_to_review_risk_order_and_returns() -> None:
    records = audit.build_records(_payloads(), {"AAA": CANDLES}, SIGNALS, since=date(2026, 10, 15))
    by_id = {row["proposal_id"]: row for row in records}
    assert set(by_id) == {"p-filled", "p-full", "p-veto", "p-reduced"}  # manual and pre-since proposals left out
    filled = by_id["p-filled"]
    assert filled["supporting_agents"] == ["news", "technical"] and filled["voters"] == ["news", "technical", "volume"]
    assert filled["filled"] and filled["paths"] == ["approved and filled"]
    assert filled["return_1s"] == approx(0.10) and filled["return_5s"] is None
    assert by_id["p-full"]["paths"] == ["rejected: max_open_positions", "rejected: daily_entry_cap"]
    assert by_id["p-veto"]["manager_verdict"] == "VETO" and by_id["p-veto"]["paths"] == ["vetoed by the manager"]
    assert by_id["p-reduced"]["paths"] == ["approved, not filled", "reduced (manager or risk)"]
    # Rejected and vetoed proposals still get a return: the counterfactual.
    assert all(row["return_1s"] is not None for row in records)


def test_summary_counts_each_failed_check_and_each_supporting_agent() -> None:
    summary = audit.summarize(audit.build_records(_payloads(), {"AAA": CANDLES}, SIGNALS, since=date(2026, 10, 15)))
    assert summary["buys"] == 4 and summary["rejected_buys"]["count"] == 2
    assert summary["by_path"]["rejected: max_open_positions"]["count"] == 1 and summary["by_path"]["rejected: daily_entry_cap"]["count"] == 1
    assert summary["capacity_rejections"]["count"] == 1  # the vetoed one is not a capacity rejection
    assert summary["by_agent"]["technical"]["count"] == 2 and "volume" not in summary["by_agent"]
    assert summary["by_threshold"]["0.45"]["count"] == 0 and summary["by_threshold"]["0.35"]["count"] == 4
    text = "\n".join(audit.answer(summary))
    assert "statistical significance" in text  # the caveat is always printed
