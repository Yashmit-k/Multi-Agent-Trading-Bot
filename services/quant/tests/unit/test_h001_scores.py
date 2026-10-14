import math
from decimal import Decimal

from quant_agents.research.h001.scores import (
    BOOTSTRAP_LIMITATION,
    BOOTSTRAP_RESAMPLES,
    acceptance_gate,
    always_flat_contributions,
    always_long_mean,
    bootstrap,
    brier_score,
    clip_probability,
    draw_symbols,
    log_loss,
    pool_rows,
    quant_agent_comparison,
)
from quant_agents.research.h001.split import INCONCLUSIVE, SATISFIED
from quant_agents.research.h001.scores import ScoredRow


def test_brier_and_clipped_log_loss() -> None:
    labels = [0, 1]
    probabilities = [0.25, 0.75]
    assert brier_score(labels, probabilities) == 0.0625
    assert log_loss(labels, probabilities) == pytest_log()
    assert clip_probability(0.0) == 1e-6
    assert clip_probability(1.0) == 1 - 1e-6
    clipped = log_loss([1], [0.0])
    assert clipped == -math.log(1e-6)


def pytest_log() -> float:
    return -math.log(0.75)


def test_baselines_and_quant_agent() -> None:
    assert always_flat_contributions(3) == (Decimal(0), Decimal(0), Decimal(0))
    assert always_long_mean([Decimal("0.02"), Decimal("-0.01")]) == Decimal("0.005")
    assert quant_agent_comparison(None) == "not_applicable"
    assert quant_agent_comparison(object()) == "not_applicable"


def test_repeated_symbol_is_included_again_and_seed_is_stable() -> None:
    rows = (
        ScoredRow("AAA", 1, 0.8, Decimal("0.01"), True),
        ScoredRow("AAA", 0, 0.2, Decimal("-0.02"), False),
        ScoredRow("BBB", 1, 0.7, Decimal("0.03"), True),
    )
    pooled = pool_rows(("AAA", "AAA"), rows)
    assert [row.symbol for row in pooled] == ["AAA", "AAA", "AAA", "AAA"]
    assert len(pooled) == 4
    first = draw_symbols(("AAA", "BBB"), resamples=BOOTSTRAP_RESAMPLES)
    second = draw_symbols(("AAA", "BBB"))
    assert first == second
    assert len(first) == 1000


def test_bootstrap_reports_the_common_shock_limit() -> None:
    rows = [
        ScoredRow("AAA", 1, 0.9, Decimal("0.02"), True),
        ScoredRow("BBB", 0, 0.1, Decimal("-0.02"), True),
    ]
    result = bootstrap(rows)
    assert result.limitation == BOOTSTRAP_LIMITATION
    assert result.mean_net.lower <= result.mean_net.upper
    assert result.brier.lower <= result.brier.upper
    assert result.log_loss.lower <= result.log_loss.upper


def test_gate_requires_a_strictly_positive_lower_bound_and_the_sample_bar() -> None:
    failed = acceptance_gate(
        mean_net=Decimal("0.01"),
        lower_bound=0.0,
        leakage_ok=True,
        train_status=SATISFIED,
        validation_status=SATISFIED,
    )
    assert failed.passed is False
    inconclusive = acceptance_gate(
        mean_net=Decimal("0.01"),
        lower_bound=0.01,
        leakage_ok=True,
        train_status=INCONCLUSIVE,
        validation_status=SATISFIED,
    )
    assert inconclusive.passed is False
    passed = acceptance_gate(
        mean_net=Decimal("0.01"),
        lower_bound=0.001,
        leakage_ok=True,
        train_status=SATISFIED,
        validation_status=SATISFIED,
    )
    assert passed.passed is True
    assert passed.limitation == BOOTSTRAP_LIMITATION
