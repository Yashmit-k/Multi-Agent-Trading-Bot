"""Risk-off NIFTY mechanics: entries only on flagged days, variant A vs B prices, ETF costs below stock costs."""

from datetime import date, timedelta

import numpy as np

from quant_agents.research import risk_off_nifty as ro


def test_trades_use_the_right_prices_and_days() -> None:
    days = [date(2026, 1, 5) + timedelta(days=i) for i in range(4)]
    flag = np.array([True, False, False, False])
    opens = np.array([100.0, 101.0, 102.0, 103.0])
    closes = np.array([100.0, 102.0, 103.0, 104.0])
    period = (date(2026, 1, 1), date(2026, 12, 31))
    a = ro.trades("A", period, days, flag, opens, closes)
    b = ro.trades("B", period, days, flag, opens, closes)
    assert len(a) == len(b) == 1
    assert 0.019 < a[0] < 0.02  # close 100 -> next close 102, less 4 bp slippage and about 3.5 bp of ETF costs
    assert 0.009 < b[0] < 0.01  # next open 101 -> close 102
    assert ro.etf_costs(1e5, 1e5) < ro.stock_costs(1e5, 1e5)
