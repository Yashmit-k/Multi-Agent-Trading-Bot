"""Synthetic checks for the pre-registered daily rules. No snapshot and no model."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from quant_agents.research.daily_rules.costs import trade_pnl
from quant_agents.research.daily_rules.evaluate import score_rules
from quant_agents.research.daily_rules.rules import low_volatility_names, momentum_12_1, momentum_20, realized_volatility
from quant_agents.research.timesfm3.paths import SnapshotRefused, daily_candle_file


def _series(symbols: dict[str, list[str]], days: int = 120) -> dict[str, tuple[tuple[date, Decimal], ...]]:
    start = date(2024, 1, 1)
    out = {}
    for symbol, pattern in symbols.items():
        rows = []
        price = Decimal("100")
        for offset in range(days):
            move = pattern[offset % len(pattern)]
            price = price * (Decimal(1) + Decimal(move))
            rows.append((start + timedelta(days=offset), price))
        out[symbol] = tuple(rows)
    return out


def test_flat_delivery_trade_loses_money():
    pnl = trade_pnl(Decimal("100"), Decimal("100"), Decimal("100000"))
    assert pnl < 0


def test_momentum_and_low_volatility_filters():
    rising = tuple(Decimal(100 + index) for index in range(30))
    falling = tuple(Decimal(200 - index) for index in range(30))
    assert momentum_20(rising) is True
    assert momentum_20(falling) is False
    assert momentum_20(rising[:10]) is None
    quiet = tuple(Decimal("100") for _ in range(25))
    wild = tuple(Decimal(100 + (index % 2) * 10) for index in range(25))
    assert realized_volatility(quiet) < realized_volatility(wild)
    assert low_volatility_names({"QUIET": Decimal("0.01"), "WILD": Decimal("0.05")}) == frozenset({"QUIET"})


def test_twelve_minus_one_ignores_the_latest_month():
    history = [Decimal("100")] * 253
    history[0] = Decimal("50")
    history[-22] = Decimal("80")
    history[-1] = Decimal("40")
    assert momentum_12_1(tuple(Decimal(str(item)) for item in history)) is True


def test_selective_momentum_can_pass_and_always_long_cannot():
    selective = score_rules(_series({"UP": ["0.01"], "DOWN": ["-0.01"], "FLAT": ["0"]}))
    momentum = next(item for item in selective if item.rule == "momentum_20" and item.horizon == 5)
    assert momentum.passed is True
    assert momentum.average_selected_fraction < Decimal("0.90")
    always = score_rules(_series({"A": ["0.002"], "B": ["0.002"], "C": ["0.002"]}))
    crowded = next(item for item in always if item.rule == "momentum_20" and item.horizon == 5)
    assert crowded.passed is False
    assert crowded.average_selected_fraction >= Decimal("0.90")


def test_runner_uses_the_daily_snapshot_only(tmp_path: Path):
    nifty = tmp_path / "snapshots 2" / "nifty50"
    (nifty / "1D").mkdir(parents=True)
    (nifty / "1D" / "candles.jsonl").write_text("{}\n", encoding="utf-8")
    path = daily_candle_file(nifty)
    assert path.parent.name == "1D"
    assert path.parent.parent.parent.name == "snapshots 2"
    assert "holdout" not in str(path)
    root = Path(__file__).resolve().parents[2]
    research_init = (root / "src" / "quant_agents" / "research" / "__init__.py").read_text(encoding="utf-8")
    worker = (root.parents[0] / "core" / "worker" / "src" / "core_worker" / "__main__.py").read_text(encoding="utf-8")
    assert "daily_rules" not in research_init
    assert "daily_rules" not in worker
    with pytest.raises(SnapshotRefused):
        daily_candle_file(Path("/tmp/holdout_after_20261005"))
    other = tmp_path / "short-tape" / "nifty50"
    (other / "1D").mkdir(parents=True)
    (other / "1D" / "candles.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SnapshotRefused):
        daily_candle_file(other)
