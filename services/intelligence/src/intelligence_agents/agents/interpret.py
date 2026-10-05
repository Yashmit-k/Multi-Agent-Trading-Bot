"""LLM interpretation helper. Agents keep deterministic metrics; the model only interprets context."""

from __future__ import annotations

from contracts.fixtures import content_hash

from intelligence_agents.agents.grounding import sanitize_llm_text
from intelligence_agents.llm.router import LLMRouter
from intelligence_agents.llm.types import LLMAssessment, LLMRequest


def interpret(
    router: LLMRouter,
    *,
    task: str,
    payload: str,
    high_impact_hint: bool = False,
) -> LLMAssessment:
    evidence = sanitize_llm_text(payload)
    return router.assess(
        LLMRequest(
            content_hash=content_hash(payload),
            user_payload=evidence,
            task=task,
            high_impact_hint=high_impact_hint,
        )
    )
