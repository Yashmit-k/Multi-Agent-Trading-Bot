from decimal import Decimal

import pytest

from quant_agents.research.h001.model import take_trade
from quant_agents.research.h001.net import net_return, validation_net_summary


def test_unchanged_and_one_percent() -> None:
    assert net_return(Decimal("100"), Decimal("100")) == Decimal("-0.0004")
    assert net_return(Decimal("100"), Decimal("101")) == Decimal("0.01") - Decimal("0.0002") - Decimal("1.01") * Decimal("0.0002")


def test_deterministic_and_fee_is_not_applied_twice() -> None:
    first = net_return(Decimal("250.5"), Decimal("250.5"))
    second = net_return(Decimal("250.5"), Decimal("250.5"))
    assert first == second == Decimal("-0.0004")


def test_invalid_prices_fail() -> None:
    with pytest.raises(ValueError):
        net_return(Decimal("0"), Decimal("1"))
    with pytest.raises(ValueError):
        net_return(Decimal("-1"), Decimal("1"))
    with pytest.raises(ValueError):
        net_return(1, Decimal("1"))  # type: ignore[arg-type]


def test_no_trade_changes_the_all_event_mean_only() -> None:
    nets = [Decimal("0.02"), Decimal("-0.01")]
    summary = validation_net_summary(nets, [True, False])
    assert summary.mean_all == Decimal("0.01")
    assert summary.mean_trades == Decimal("0.02")
    assert summary.trade_count == 1
    assert summary.total_net == Decimal("0.02")
    assert take_trade(0.4, 0.4) is False


def test_net_module_does_not_call_shared_cost_helpers() -> None:
    text = (__import__("pathlib").Path(__file__).resolve().parents[2] / "src" / "quant_agents" / "research" / "h001" / "net.py").read_text()
    imports = [line for line in text.splitlines() if line.startswith(("import ", "from "))]
    assert all("fee_on" not in line and "price_trade" not in line for line in imports)
    assert "fee_on(" not in text
    assert "price_trade(" not in text
