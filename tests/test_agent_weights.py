"""Reliability weights: worse than a coin flip -> 0, unproven -> 0.5, better -> 1.0-1.5; regime is a filter."""

from datetime import datetime, timezone

from contracts.enums import Horizon
from core_api.scorecard import reliability_weight
from core_db.repository import CoreRepository
from core_worker.agent_weights import compute_weights


def _row(hit: float, n: int) -> dict:
    return {"hit_rate": hit, "directional": n}


def test_reliability_weight_bands() -> None:
    assert reliability_weight(_row(0.60, 50)) == (0.5, "unproven")  # too few after the 5x design effect
    assert reliability_weight(_row(0.40, 2000))[0] == 0.0  # clearly worse than a coin flip
    weight, basis = reliability_weight(_row(0.60, 2000))
    assert basis == "better_than_coin_flip" and 1.0 < weight <= 1.5
    assert reliability_weight(_row(0.51, 2000)) == (0.5, "unproven")  # not distinguishable from 50%
    assert reliability_weight({"hit_rate": None, "directional": 0}) == (0.5, "unproven")


def test_compute_weights_defaults_and_filters(repository: CoreRepository) -> None:
    table, detail = compute_weights(repository, datetime(2026, 10, 20, tzinfo=timezone.utc), {"fundamental"})
    assert table[Horizon.SWING]["regime"] == 0.0 and table[Horizon.INTRADAY]["regime"] == 0.0
    assert table[Horizon.SWING]["fundamental"] == 0.0
    assert table[Horizon.SWING]["technical"] == 0.5  # no graded signals yet: unproven
