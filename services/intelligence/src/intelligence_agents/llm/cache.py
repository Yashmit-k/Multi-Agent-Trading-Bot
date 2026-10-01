"""In-process LLM cache. Not used for BACKTEST reproducibility — FixtureLLM is."""

from __future__ import annotations

from intelligence_agents.llm.types import LLMAssessment
from intelligence_agents.llm.types import PROMPT_VERSION


class LLMCache:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], LLMAssessment] = {}
        self.hits = 0

    def get(self, content_hash: str, model: str) -> LLMAssessment | None:
        key = (PROMPT_VERSION, content_hash, model)
        value = self._items.get(key)
        if value is not None:
            self.hits += 1
        return value

    def put(self, content_hash: str, model: str, assessment: LLMAssessment) -> None:
        self._items[(PROMPT_VERSION, content_hash, model)] = assessment
