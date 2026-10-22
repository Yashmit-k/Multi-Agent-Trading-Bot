"""Trade-level risk checks for a new BUY: losses so far, the trade's own risk, price drift, evidence, re-entry.

The paper cycle builds a TradeContext from the book and the market at decision time. Every limit
comes from the user's risk settings, so each check can be tightened or loosened but not removed by
a typo (see core_risk.settings bounds).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from contracts.schemas.trade_proposal import TradeProposal


@dataclass(frozen=True)
class TradeContext:
    now: datetime
    starting_cash: Decimal
    equity: Decimal  # cash plus open positions at the latest price
    start_of_day_equity: Decimal  # equity at the previous close (starting cash on the first day)
    peak_equity: Decimal
    last_price: Decimal | None = None  # newest 5-minute close
    last_stop_exit_at: datetime | None = None  # newest stop-loss exit in this stock
    evidence_checked: bool = False  # supporting signals were found and inspected
    evidence_fallback_only: bool = False  # every supporting opinion came from a fallback heuristic, not a model or rule
    # Limits (from RiskSettings).
    max_daily_loss_pct: Decimal = Decimal("2")
    max_drawdown_pct: Decimal = Decimal("10")
    max_risk_per_trade_pct: Decimal = Decimal("1")
    min_reward_risk: Decimal = Decimal("1")
    max_price_drift_pct: Decimal = Decimal("3")
    stop_cooldown_hours: int = 24
    block_fallback_evidence: bool = True

    def checks(self, proposal: TradeProposal) -> list[tuple[str, bool, str]]:
        entry, stop, target = proposal.entry_price, proposal.stop_loss, proposal.take_profit
        day_loss_pct = (self.start_of_day_equity - self.equity) / self.starting_cash * 100 if self.starting_cash > 0 else Decimal("0")
        drawdown_pct = (self.peak_equity - self.equity) / self.peak_equity * 100 if self.peak_equity > 0 else Decimal("0")
        risk = (entry - stop) * proposal.quantity
        risk_pct = risk / self.starting_cash * 100 if self.starting_cash > 0 else Decimal("0")
        reward_risk = (target - entry) / (entry - stop) if entry > stop else Decimal("0")
        drift_pct = abs(entry - self.last_price) / self.last_price * 100 if self.last_price else None
        cooling = self.last_stop_exit_at is not None and self.now - self.last_stop_exit_at < timedelta(hours=self.stop_cooldown_hours)
        return [
            ("daily_loss_limit", day_loss_pct <= self.max_daily_loss_pct,
             f"book is down {day_loss_pct:.2f}% of starting cash today; limit is {self.max_daily_loss_pct}%"),
            ("drawdown_limit", drawdown_pct <= self.max_drawdown_pct,
             f"book is {drawdown_pct:.2f}% below its peak; limit is {self.max_drawdown_pct}%"),
            ("risk_per_trade", risk_pct <= self.max_risk_per_trade_pct,
             f"loss at the stop would be {risk:.2f} ({risk_pct:.2f}% of starting cash); limit is {self.max_risk_per_trade_pct}%"),
            ("reward_to_risk", reward_risk >= self.min_reward_risk,
             f"target is {reward_risk:.2f}x the stop distance; minimum is {self.min_reward_risk}x"),
            ("price_drift", drift_pct is None or drift_pct <= self.max_price_drift_pct,
             f"price moved {drift_pct or 0:.2f}% since the signal (now {self.last_price}); limit is {self.max_price_drift_pct}%"),
            ("stop_out_cooldown", not cooling,
             f"{proposal.symbol} was stopped out at {self.last_stop_exit_at}; no re-entry for {self.stop_cooldown_hours} h"),
            ("evidence_quality", not (self.block_fallback_evidence and self.evidence_checked and self.evidence_fallback_only),
             "every opinion behind this BUY came from a fallback heuristic, not an LLM or a rule (and no later re-check replaced it)"),
        ]
