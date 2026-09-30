"""Vote objects. Agents pass these as data; they never multiply weights."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vote:
    name: str
    value: int
    weight: float

    def __post_init__(self) -> None:
        if self.value not in (-1, 0, 1):
            raise ValueError("Vote.value must be -1, 0, or 1")
        if self.weight < 0:
            raise ValueError("Vote.weight must be >= 0")
