import numpy as np

from quant_agents.research import risk_sizing as rs


def test_weighted_mean_uses_only_positions_that_traded() -> None:
    assert rs.weighted({1: 0.02, 2: -0.01}, {1: 3.0, 2: 1.0, 3: 100.0}) == (0.06 - 0.01) / 4.0
    assert rs.weighted({}, {1: 1.0}) == 0.0


def test_stats_and_bounds_behave() -> None:
    rng = np.random.default_rng(0)
    equal = list(rng.normal(0.001, 0.03, 60))
    calmer = [value * 0.5 + 0.0005 for value in equal]
    s = rs.stats(equal)
    assert s["windows"] == 60 and s["annualized_vol"] > 0 and 0 <= s["max_drawdown"] < 1
    low, high = rs.sharpe_improvement_bounds(calmer, equal, resamples=300)
    assert low < high
    assert rs.stats(calmer)["annualized_vol"] < s["annualized_vol"]
