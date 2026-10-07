"""Cap LLM confidence so intelligence cannot dominate fusion."""

from __future__ import annotations

from collections.abc import Sequence

CAPS = {
    "news": 0.55,
    "fundamental": 0.50,
    "valuation": 0.50,
    "earnings": 0.55,
}

INSUFFICIENT_CONFIDENCE = 0.15


def cap_and_rank_normalize(values: Sequence[float], cap: float) -> float:
    if not values:
        return 0.0
    n = len(values)
    order = sorted(range(n), key=lambda index: values[index])
    ranks = [0.0] * n
    for rank, index in enumerate(order, start=1):
        ranks[index] = rank / n
    rank_sum = sum(ranks)
    mixed = sum(values[index] * ranks[index] for index in range(n)) / rank_sum
    return min(max(mixed, 0.0), cap)
