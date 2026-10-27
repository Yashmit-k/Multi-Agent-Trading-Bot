"""Agents with no live data source can be excluded from the fused vote."""

from datetime import timedelta

from contracts.enums import AgentName, Horizon
from contracts.fixtures import FIXTURE_AS_OF, sample_agent_signal
from core_fusion import fuse
from core_worker.paper_schedule import excluded_agent_weights


def _signal(signal_id: str, agent: AgentName, value: float):
    return sample_agent_signal("RELIANCE").model_copy(
        update={
            "signal_id": signal_id,
            "agent_name": agent,
            "horizon": Horizon.SWING,
            "signal": value,
            "confidence": 0.8,
            "timestamp": FIXTURE_AS_OF,
            "as_of": FIXTURE_AS_OF,
            "valid_until": FIXTURE_AS_OF + timedelta(hours=6),
        }
    )


def test_excluded_agent_does_not_move_the_aggregate() -> None:
    weights = excluded_agent_weights("fundamental, valuation,earnings")
    quant = _signal("sig-momentum", AgentName.MOMENTUM, 0.5)
    fixture = _signal("sig-fundamental", AgentName.FUNDAMENTAL, -1.0)
    alone = fuse([quant], horizon=Horizon.SWING, as_of=FIXTURE_AS_OF, weights=weights)
    mixed = fuse([quant, fixture], horizon=Horizon.SWING, as_of=FIXTURE_AS_OF, weights=weights)
    assert alone is not None and mixed is not None
    assert mixed.aggregated_signal == alone.aggregated_signal
    assert mixed.supporting_signal_ids == ("sig-momentum",)


def test_only_excluded_signals_produce_no_aggregate() -> None:
    weights = excluded_agent_weights("fundamental")
    fixture = _signal("sig-fundamental", AgentName.FUNDAMENTAL, 1.0)
    assert fuse([fixture], horizon=Horizon.SWING, as_of=FIXTURE_AS_OF, weights=weights) is None


def test_empty_list_keeps_default_weights() -> None:
    assert excluded_agent_weights("") is None
    assert excluded_agent_weights(" , ") is None


def test_entry_end_env_is_bounded() -> None:
    from datetime import time

    from core_paper.trading_calendar import DEFAULT_ENTRY_END, _entry_end_from_env

    assert _entry_end_from_env(None) == DEFAULT_ENTRY_END == time(10, 30)
    assert _entry_end_from_env("15:15") == time(15, 15)
    assert _entry_end_from_env("15:25") == DEFAULT_ENTRY_END
    assert _entry_end_from_env("09:15") == DEFAULT_ENTRY_END
    assert _entry_end_from_env("12:07") == DEFAULT_ENTRY_END
    assert _entry_end_from_env("noon") == DEFAULT_ENTRY_END


def test_global_markets_agent_never_votes() -> None:
    """Observe-only (services/quant/docs/global-markets-result.md): weight 0 by default and in the worker's table."""
    from core_decision.specialists import decide
    from core_worker.agent_weights import prior_table

    quant = _signal("sig-momentum", AgentName.MOMENTUM, 0.5)
    world = _signal("sig-global", AgentName.GLOBAL_MARKETS, -1.0)
    assert fuse([world], horizon=Horizon.SWING, as_of=FIXTURE_AS_OF) is None
    alone = fuse([quant], horizon=Horizon.SWING, as_of=FIXTURE_AS_OF)
    mixed = fuse([quant, world], horizon=Horizon.SWING, as_of=FIXTURE_AS_OF)
    assert alone == mixed
    assert all(table["global_markets"] == 0.0 for table in prior_table(set()).values())
    verdicts = decide([quant, world], as_of=FIXTURE_AS_OF).verdicts
    assert "global_markets" not in {item["agent"] for item in verdicts}
