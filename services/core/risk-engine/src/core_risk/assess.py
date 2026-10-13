"""Risk checks for one proposal. PAPER is the only accepted mode in this phase.

BACKTEST becomes eligible when the backtester exists. This phase does not open shorts.
The kill switch is not a check here. It stays a no-op until shadow or live.
"""

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import RiskStatus, Side, TradingMode
from contracts.schemas.risk_decision import RiskCheck, RiskDecision
from contracts.schemas.trade_proposal import TradeProposal

RISK_VERSION = "1.0.0"
MAX_NOTIONAL = Decimal("20000")


def assess(
    proposal: TradeProposal,
    *,
    mode: TradingMode,
    in_universe: bool,
    cash: Decimal,
    held_quantity: int,
    timestamp: datetime,
    max_notional: Decimal | None = None,
) -> RiskDecision:
    bound = MAX_NOTIONAL if max_notional is None else max_notional
    notional = proposal.entry_price * proposal.quantity
    checks = [
        _check("mode_is_paper", mode == TradingMode.PAPER, f"mode {mode.value} is not PAPER"),
        _check("universe_member", in_universe, f"{proposal.symbol} is outside the universe at as_of"),
        _check("sufficient_cash", proposal.side != Side.BUY or notional <= cash, "buy notional exceeds cash"),
        _check("notional_cap", notional <= bound, f"order notional exceeds {bound}"),
        _check(
            "no_short",
            proposal.side != Side.SELL or proposal.quantity <= held_quantity,
            "sell quantity exceeds held quantity",
        ),
        _check("stop_and_target_side", _brackets_ok(proposal), "stop or target is on the wrong side of entry"),
    ]
    failed = [check for check in checks if not check.passed]
    approved = not failed
    return RiskDecision(
        risk_decision_id=_decision_id(proposal.proposal_id),
        proposal_id=proposal.proposal_id,
        timestamp=timestamp.astimezone(timezone.utc),
        status=RiskStatus.APPROVED if approved else RiskStatus.REJECTED,
        risk_version=RISK_VERSION,
        checks=checks,
        rejection_reason=None if approved else "; ".join(check.detail for check in failed),
        approved_quantity=proposal.quantity if approved else 0,
        approved_price=proposal.entry_price if approved else None,
        metadata={"kill_switch": "noop"},
    )


def _check(name: str, passed: bool, failure: str) -> RiskCheck:
    return RiskCheck(name=name, passed=passed, detail="passed" if passed else failure)


def _brackets_ok(proposal: TradeProposal) -> bool:
    if proposal.side == Side.BUY:
        return proposal.stop_loss < proposal.entry_price < proposal.take_profit
    return proposal.take_profit < proposal.entry_price < proposal.stop_loss


def _decision_id(proposal_id: str) -> str:
    return hashlib.sha256(f"risk|{proposal_id}|{RISK_VERSION}".encode("utf-8")).hexdigest()
