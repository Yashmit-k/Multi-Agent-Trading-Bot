"""Portfolio limits on new BUYs: positions, sector, exposure, per stock, entries per day."""

from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import Horizon, Side, TradingMode
from contracts.schemas.trade_proposal import TradeProposal
from core_risk import assess
from core_risk.portfolio import PortfolioContext, sector_of

NOW = datetime(2026, 10, 15, 4, 0, tzinfo=timezone.utc)
CASH = Decimal("1000000")


def _proposal(symbol: str = "INFY", side: Side = Side.BUY, price: str = "1000", quantity: int = 19) -> TradeProposal:
    entry = Decimal(price)
    stop, target = (entry * Decimal("0.98"), entry * Decimal("1.04")) if side == Side.BUY else (entry * Decimal("1.02"), entry * Decimal("0.96"))
    return TradeProposal(
        proposal_id=f"p-{symbol}-{side.value}", symbol=symbol, timestamp=NOW, horizon=Horizon.SWING, side=side, quantity=quantity,
        entry_price=entry, stop_loss=stop.quantize(Decimal("0.01")), take_profit=target.quantize(Decimal("0.01")),
        strategy_id="paper-fusion", strategy_version="1.0.0", aggregated_signal=0.3, aggregated_confidence=0.4,
        supporting_signal_ids=["s1"], metadata={},
    )


def _decide(proposal: TradeProposal, portfolio: PortfolioContext | None, held: int = 0):
    return assess(proposal, mode=TradingMode.PAPER, in_universe=True, cash=CASH, held_quantity=held, timestamp=NOW, portfolio=portfolio)


def _failed(decision) -> set[str]:
    return {check.name for check in decision.checks if not check.passed}


def test_empty_book_approves_and_names_all_eleven_checks() -> None:
    decision = _decide(_proposal(), PortfolioContext(starting_cash=CASH))
    assert decision.status.value == "APPROVED"
    assert {check.name for check in decision.checks} >= {"max_open_positions", "sector_concentration", "exposure_cap", "per_stock_cap", "daily_entry_cap"}
    assert len(decision.checks) == 11


def test_eleventh_name_is_rejected() -> None:
    book = {f"S{i}": Decimal("19000") for i in range(10)}
    decision = _decide(_proposal("NTPC"), PortfolioContext(starting_cash=CASH, exposure=book))
    assert decision.status.value == "REJECTED"
    assert "max_open_positions" in _failed(decision)


def test_third_stock_in_a_sector_is_rejected() -> None:
    book = {"TCS": Decimal("19000"), "WIPRO": Decimal("19000")}
    decision = _decide(_proposal("INFY"), PortfolioContext(starting_cash=CASH, exposure=book))
    assert _failed(decision) == {"sector_concentration"}
    other = _decide(_proposal("NTPC"), PortfolioContext(starting_cash=CASH, exposure=book))
    assert other.status.value == "APPROVED"


def test_exposure_cap_is_thirty_percent_of_starting_cash() -> None:
    book = {f"S{i}": Decimal("36000") for i in range(8)}  # 2.88 lakh deployed; +19k = 3.07 lakh > 3 lakh
    decision = _decide(_proposal("NTPC"), PortfolioContext(starting_cash=CASH, exposure=book))
    assert "exposure_cap" in _failed(decision)


def test_per_stock_cap_is_forty_thousand() -> None:
    decision = _decide(_proposal("INFY"), PortfolioContext(starting_cash=CASH, exposure={"INFY": Decimal("25000")}))
    assert _failed(decision) == {"per_stock_cap"}


def test_seventh_entry_of_the_day_is_rejected() -> None:
    decision = _decide(_proposal(), PortfolioContext(starting_cash=CASH, entries_today=6))
    assert _failed(decision) == {"daily_entry_cap"}
    assert "6 entries already today" in (decision.rejection_reason or "")


def test_sells_and_callers_without_a_book_are_unchanged() -> None:
    sell = _decide(_proposal(side=Side.SELL), PortfolioContext(starting_cash=CASH, entries_today=99), held=19)
    assert sell.status.value == "APPROVED" and len(sell.checks) == 6
    legacy = _decide(_proposal(), None)
    assert legacy.status.value == "APPROVED" and len(legacy.checks) == 6


def test_unknown_stocks_are_their_own_sector() -> None:
    assert sector_of("LT") == "OWN:LT" and sector_of("INFY") == "NIFTY IT"
