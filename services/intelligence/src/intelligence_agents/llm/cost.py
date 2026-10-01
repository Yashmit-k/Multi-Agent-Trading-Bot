"""Token and USD tracking with a daily budget."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone


USD_PER_1K_PROMPT = 0.0005
USD_PER_1K_COMPLETION = 0.0015


@dataclass
class CostTracker:
    daily_budget_usd: float
    _spent: float = 0.0
    _day: date = field(default_factory=lambda: datetime.now(timezone.utc).date())
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def estimate(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens / 1000.0) * USD_PER_1K_PROMPT + (completion_tokens / 1000.0) * USD_PER_1K_COMPLETION

    def remaining(self) -> float:
        self._roll()
        if self.daily_budget_usd <= 0:
            return 0.0
        return max(0.0, self.daily_budget_usd - self._spent)

    def can_spend(self, prompt_tokens: int, completion_tokens: int) -> bool:
        if self.daily_budget_usd <= 0:
            return False
        return self.estimate(prompt_tokens, completion_tokens) <= self.remaining()

    def record(self, prompt_tokens: int, completion_tokens: int) -> float:
        self._roll()
        cost = self.estimate(prompt_tokens, completion_tokens)
        self._spent += cost
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        return cost

    def _roll(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._day:
            self._day = today
            self._spent = 0.0
            self.prompt_tokens = 0
            self.completion_tokens = 0
