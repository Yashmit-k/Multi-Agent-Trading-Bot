"""Turn one aggregate and one completed candle into a TradeProposal.

Quantity is 1 share. That is a bootstrap, not a position-sizing model.
Stop loss and take profit are recorded on the proposal and are not monitored.
"""

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import Horizon, Side
from contracts.schemas.market import Candle
from contracts.schemas.trade_proposal import TradeProposal
from core_fusion import Aggregate

STRATEGY_ID = "paper-fusion"
STRATEGY_VERSION = "1.0.0"
PAPER_QUANTITY = 1
SIGNAL_THRESHOLD = Decimal("0.2")
CONFIDENCE_THRESHOLD = Decimal("0.3")
_CENT = Decimal("0.01")


def proposal_id_for(symbol: str, horizon: Horizon, as_of: datetime, *, session_id: str | None = None) -> str:
    """Deterministic id from symbol, horizon, as_of, strategy, and the paper session when one is set."""
    stamp = as_of.astimezone(timezone.utc).isoformat()
    parts = [symbol.strip().upper(), horizon.value, stamp, STRATEGY_ID, STRATEGY_VERSION]
    if session_id:
        parts.append(session_id.strip())
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def build_proposal(
    aggregate: Aggregate,
    candle: Candle,
    as_of: datetime,
    *,
    session_id: str | None = None,
) -> TradeProposal | None:
    if candle.end.astimezone(timezone.utc) != as_of.astimezone(timezone.utc):
        return None
    signal = Decimal(str(aggregate.aggregated_signal))
    confidence = Decimal(str(aggregate.aggregated_confidence))
    if abs(signal) < SIGNAL_THRESHOLD or confidence < CONFIDENCE_THRESHOLD:
        return None
    if not aggregate.supporting_signal_ids:
        return None
    entry = candle.close
    side = Side.BUY if signal > 0 else Side.SELL
    stop, target = _brackets(entry, side)
    moment = as_of.astimezone(timezone.utc)
    return TradeProposal(
        proposal_id=proposal_id_for(aggregate.symbol, aggregate.horizon, moment, session_id=session_id),
        symbol=aggregate.symbol,
        timestamp=moment,
        horizon=aggregate.horizon,
        side=side,
        quantity=PAPER_QUANTITY,
        entry_price=entry,
        stop_loss=stop,
        take_profit=target,
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        aggregated_signal=aggregate.aggregated_signal,
        aggregated_confidence=aggregate.aggregated_confidence,
        supporting_signal_ids=list(aggregate.supporting_signal_ids),
        metadata={"quantity_model": "bootstrap_one_share", "stops_monitored": False},
    )


def _brackets(entry: Decimal, side: Side) -> tuple[Decimal, Decimal]:
    if side == Side.BUY:
        return (entry * Decimal("0.98")).quantize(_CENT), (entry * Decimal("1.04")).quantize(_CENT)
    return (entry * Decimal("1.02")).quantize(_CENT), (entry * Decimal("0.96")).quantize(_CENT)
