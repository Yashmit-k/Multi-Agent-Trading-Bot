"""Agent-tuning mechanics: the array scorer equals score_votes; cross-sectional IC is a per-row rank correlation."""

import numpy as np

from quant_agents.research import agent_tuning as at
from quant_agents.scoring import score_votes
from quant_agents.vote import Vote


def test_array_score_matches_score_votes() -> None:
    rng = np.random.default_rng(0)
    for _ in range(200):
        k = rng.integers(1, 5)
        values = rng.integers(-1, 2, k)
        weights = rng.uniform(0.1, 1.0, k)
        present = rng.random(k) > 0.2
        votes = [Vote(f"v{i}", int(values[i]), float(weights[i])) for i in range(k) if present[i]]
        ratio = float(rng.choice([1.0, 0.5, 2 / 3]))
        expected = score_votes(tuple(votes), required=(), missing=())
        signal, confidence = at._score([(np.array([float(values[i])]), float(weights[i]), np.array([present[i]])) for i in range(k)], np.array([ratio]), 1)
        assert abs(signal[0] - expected.signal) < 1e-12
        assert abs(confidence[0] - expected.confidence * ratio) < 1e-12


def test_cross_sectional_ic_is_rank_correlation_per_row() -> None:
    effective = np.array([[1.0, 2.0, 3.0] * 4, [3.0, 2.0, 1.0] * 4])
    forward = np.array([[0.1, 0.2, 0.3] * 4, [0.1, 0.2, 0.3] * 4])
    ic = at.cross_sectional_ic(effective, forward, np.array([0, 1]))
    assert ic[0] > 0.9 and ic[1] < -0.9
    few = at.cross_sectional_ic(effective[:, :5], forward[:, :5], np.array([0]))
    assert np.isnan(few[0])  # fewer than 10 stocks: no IC
