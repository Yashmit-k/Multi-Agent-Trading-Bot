"""Portfolio manager: tool use, code-side critique, model failover, and the rule fallback."""

import json

import httpx

from intelligence_agents.manager.agent import PortfolioManager
from intelligence_agents.manager.llm import ManagerLLMError, ToolCallingLLM, Turn

REVIEW = {
    "review_id": "rv-test",
    "kind": "pipeline",
    "proposal_id": "p-1",
    "symbol": "INFY",
    "horizon": "SWING",
    "side": "BUY",
    "quantity": 12,
    "entry_price": "1500",
    "aggregated_signal": 0.35,
    "aggregated_confidence": 0.5,
    "metadata": {"stop_loss": "1470", "take_profit": "1560"},
}

OPINIONS = {
    "symbol": "INFY",
    "fused_signal": 0.35,
    "agents": [
        {"agent": "momentum", "score": 0.6, "confidence": 0.7, "fusion_weight": 0.0},
        {"agent": "news", "score": -0.5, "confidence": 0.6, "fusion_weight": 0.5},
    ],
    "agents_disagreeing_with_fusion": ["news"],
}


class FakeCore:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.verdicts: list[dict] = []
        self.tool_calls: list[str] = []

    def post_step(self, review_id: str, body: dict) -> None:
        self.steps.append(body)

    def post_verdict(self, review_id: str, body: dict) -> bool:
        self.verdicts.append(body)
        return True

    def tool(self, name: str, **params: str) -> dict:
        self.tool_calls.append(name)
        if name == "opinions":
            return OPINIONS
        if name == "market":
            raise httpx.ConnectError("down")
        return {"ok": True}


class FakeIntel:
    def __init__(self) -> None:
        self.reassessed: list[dict] = []

    def news(self, symbol: str) -> list[dict]:
        return [{"title": "Infosys cuts guidance", "source": "ET", "published_at": "2026-10-20T03:00:00+00:00"}]

    def fundamentals(self, symbol: str) -> list[dict]:
        return []

    def reassess(self, **kwargs) -> dict:
        self.reassessed.append(kwargs)
        return {"agent": kwargs["agent"], "score": -0.6, "confidence": 0.7, "model": "gemini-x", "llm_fallback": False, "signal_id": "sig-new"}


def _call(name: str, args: dict, call_id: str) -> dict:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class ScriptedLLM(ToolCallingLLM):
    def __init__(self, model: str, turns: list) -> None:
        super().__init__("http://llm", "key", model, min_interval_seconds=0)
        self.turns = list(turns)
        self.seen: list[list[dict]] = []

    def complete(self, messages, tools, *, tool_choice="auto"):
        self.seen.append(list(messages))
        item = self.turns.pop(0)
        if isinstance(item, Exception):
            raise item
        text, calls = item
        return Turn(message={"role": "assistant", "content": text, "tool_calls": calls}, tool_calls=calls, text=text, model=self.model)


def _manager(*models: ScriptedLLM) -> tuple[PortfolioManager, FakeCore, FakeIntel]:
    core, intel = FakeCore(), FakeIntel()
    return PortfolioManager(core, intel, models[0], models[1] if len(models) > 1 else None, sleeper=lambda _: None), core, intel


def test_plans_uses_tools_asks_an_agent_and_is_made_to_address_the_conflict() -> None:
    verdict_without_conflict = {"verdict": "APPROVE", "size_fraction": 1, "conflicts": [], "critique": "Momentum is strong and the fused signal is positive.", "purpose": "done"}
    final = {"verdict": "VETO", "size_fraction": 0, "conflicts": ["news: guidance cut vs bullish momentum"], "critique": "The news agent re-checked and still sees a guidance cut; momentum alone is not enough.", "purpose": "done"}
    llm = ScriptedLLM(
        "gemini-main",
        [
            ("Plan: read the agents, then check the news.", [_call("get_agent_opinions", {"symbol": "INFY", "horizon": "SWING", "purpose": "who disagrees"}, "c1")]),
            ("", [_call("get_market_context", {"purpose": "is the market risk-off"}, "c2"), _call("ask_agent_to_recheck", {"agent": "news", "symbol": "INFY", "question": "Is the guidance cut confirmed?", "purpose": "news conflicts with momentum"}, "c3")]),
            ("", [_call("submit_verdict", verdict_without_conflict, "c4")]),
            ("", [_call("submit_verdict", final, "c5")]),
        ],
    )
    manager, core, intel = _manager(llm)
    body = manager.review(REVIEW)
    assert body["verdict"] == "VETO" and body["size_fraction"] == 0.0 and body["reviewer"] == "gemini-main"
    kinds = [step.get("kind") for step in core.steps if "kind" in step]
    assert kinds[0] == "plan" and "critique" in kinds and "agent_reply" in kinds
    assert any(step.get("to_agent") == "news" for step in core.steps)  # the agent.request message
    assert intel.reassessed and intel.reassessed[0]["review_id"] == "rv-test"
    market_result = next(step for step in core.steps if step.get("kind") == "tool_result" and step.get("tool") == "get_market_context")
    assert market_result["summary"].startswith("error")  # a failed tool is reported back, not fatal
    tool_messages = [m for m in llm.seen[-1] if m["role"] == "tool"]
    assert any("verdict rejected" in m["content"] and "news" in m["content"] for m in tool_messages)
    assert core.verdicts == [body]


def test_verdict_before_reading_opinions_is_sent_back() -> None:
    final = {"verdict": "REDUCE", "size_fraction": 0.5, "conflicts": ["news: negative vs momentum positive"], "critique": "Mixed evidence: the news is negative while momentum is positive, so half size.", "purpose": "done"}
    llm = ScriptedLLM(
        "gemini-main",
        [
            ("", [_call("submit_verdict", final, "c1")]),
            ("", [_call("get_agent_opinions", {"symbol": "INFY", "horizon": "SWING", "purpose": "look first"}, "c2")]),
            ("", [_call("submit_verdict", final, "c3")]),
        ],
    )
    manager, core, _ = _manager(llm)
    body = manager.review(REVIEW)
    assert body["verdict"] == "REDUCE" and body["size_fraction"] == 0.5
    assert any(step.get("kind") == "critique" and "opinions" in step["summary"] for step in core.steps)


def test_switches_to_the_backup_model_when_the_first_is_out_of_quota() -> None:
    final = {"verdict": "APPROVE", "size_fraction": 1, "conflicts": ["news: negative but low weight"], "critique": "The negative news is old and the trade is small; the risk engine still applies.", "purpose": "done"}
    broken = ScriptedLLM("gemini-main", [ManagerLLMError("quota_exhaustion")])
    backup = ScriptedLLM("gemini-backup", [("", [_call("get_agent_opinions", {"symbol": "INFY", "horizon": "SWING", "purpose": "start"}, "c1")]), ("", [_call("submit_verdict", final, "c2")])])
    manager, core, _ = _manager(broken, backup)
    body = manager.review(REVIEW)
    assert body["reviewer"] == "gemini-backup" and body["verdict"] == "APPROVE"
    kinds = [step.get("kind") for step in core.steps]
    assert "llm_error" in kinds and "replan" in kinds


def test_rule_fallback_when_no_model_answers() -> None:
    manager, core, _ = _manager(ScriptedLLM("a", [ManagerLLMError("quota_exhaustion")]), ScriptedLLM("b", [ManagerLLMError("http_error")]))
    body = manager.review(REVIEW)
    assert body["reviewer"] == "rule_fallback"
    assert body["verdict"] == "VETO"  # news -0.5 at confidence 0.6 is strong bad news
    assert "Fallback rules" in body["critique"]


def test_transient_errors_are_retried_once() -> None:
    final = {"verdict": "APPROVE", "size_fraction": 1, "conflicts": ["news: negative"], "critique": "Retried after a rate limit; evidence is acceptable for a small paper trade.", "purpose": "done"}
    llm = ScriptedLLM("gemini-main", [ManagerLLMError("http_429"), ("", [_call("get_agent_opinions", {"symbol": "INFY", "horizon": "SWING", "purpose": "start"}, "c1")]), ("", [_call("submit_verdict", final, "c2")])])
    manager, core, _ = _manager(llm)
    assert manager.review(REVIEW)["reviewer"] == "gemini-main"
    assert any(step.get("kind") == "llm_error" and "retrying" in step["summary"] for step in core.steps)


def test_a_weighted_opinion_from_fallback_heuristics_must_be_rechecked_first(monkeypatch) -> None:
    shaky = {**OPINIONS, "agents": [{"agent": "news", "score": 0.4, "confidence": 0.5, "fusion_weight": 0.5, "llm_fallback": True}], "agents_disagreeing_with_fusion": []}
    final = {"verdict": "APPROVE", "size_fraction": 1, "conflicts": [], "critique": "The news agent re-checked with the model and still sees a positive story.", "purpose": "done"}
    llm = ScriptedLLM(
        "gemini-main",
        [
            ("", [_call("get_agent_opinions", {"symbol": "INFY", "horizon": "SWING", "purpose": "start"}, "c1")]),
            ("", [_call("submit_verdict", final, "c2")]),
            ("", [_call("ask_agent_to_recheck", {"agent": "news", "symbol": "INFY", "question": "Re-score with the model", "purpose": "fallback"}, "c3")]),
            ("", [_call("submit_verdict", final, "c4")]),
        ],
    )
    manager, core, intel = _manager(llm)
    monkeypatch.setattr(core, "tool", lambda name, **params: shaky if name == "opinions" else {"ok": True})
    body = manager.review(REVIEW)
    assert body["verdict"] == "APPROVE"
    assert any(step.get("kind") == "critique" and "fallback" in step["summary"] for step in core.steps)
    assert intel.reassessed


def test_reassess_endpoint_accepts_a_json_body(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from contracts.enums import TradingMode
    from intelligence_agents.service import create_app
    from intelligence_agents.settings import IntelligenceSettings

    settings = IntelligenceSettings.from_env()
    settings = type(settings)(**{**{f: getattr(settings, f) for f in settings.__dataclass_fields__}, "trading_mode": TradingMode.PAPER, "internal_signal_token": "t", "symbols": ("INFY",)})

    class Sink:
        def submit(self, signal):
            raise AssertionError("not reached")

    client = TestClient(create_app(settings, sink=Sink()))
    body = {"agent": "news", "symbol": "INFY", "request_id": "r", "review_id": "v"}
    assert client.post("/reassess", json=body).status_code == 401
    assert client.post("/reassess", json={**body, "agent": "astrology"}, headers={"Authorization": "Bearer t"}).status_code == 422
    assert client.post("/reassess", json={**body, "symbol": "NOPE"}, headers={"Authorization": "Bearer t"}).json()["detail"] == "unknown_symbol"
