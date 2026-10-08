# Strategy acceptance gate

Positive gross P&L is not enough to wire a strategy into production.

Where the run can measure them, report gross P&L, net P&L, return, Sharpe, maximum drawdown, turnover, trade count, average trade, transaction costs, slippage, exposure, per-symbol results, and an appropriate baseline.

A candidate must:

1. Beat that baseline.
2. Stay viable after at least the 2 bp transaction-cost gate. The gate is not lowered.
3. Survive realistic slippage.
4. Show chronological out-of-sample performance.
5. Contain no look-ahead.
6. Not simply reproduce always-long or always-short behavior.

Do not claim statistical significance unless that test was actually run. A near-always-long book that matches buy-and-hold is not a timing edge.
