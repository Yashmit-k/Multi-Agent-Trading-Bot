# Current system status

Source of truth for the tree at `b4ab1ce`. Live trading is off.

## 1. Platform status

The platform is operational for paper trading, historical replay, and backtests. Contracts in `packages/contracts` are the only schema source. The wire `schema_version` is `"1.0"`. `live_enabled` is false.

## 2. Market data

Stored candles can be pulled from Zerodha history and replayed from frozen files. Replay shows a bar only when `end <= as_of`. Missing bars are counted and are not filled in. The paper clock is the latest completed candle end, not the wall clock.

## 3. Historical snapshots

The research copy is `snapshots 2/nifty50`. It is read-only. `snapshots 2/nifty50/candles.jsonl` is a short combined file and is not the research dataset.

Five-minute snapshot `nifty50_5m_20261005`, candle sha256 `0f2df34d35e5a02ab6cd725882afd3fca7354eff65e4c1d219cf7fa9bdf1cb9b`, from 2024-01-01 through 2026-10-05. Most populated symbols have 51,009 bars. `BHARTIARTL`, `HDFCBANK`, `ICICIBANK`, and `SBILIFE` have 51,008. `HINDUNILVR` has 51,005. `TATAMOTORS` has 0. Those gaps stay gaps. `TATAMOTORS` is not aliased to another name.

Daily snapshot `nifty50_1d_20261005`, candle sha256 `0411a89535ab50ae6488c7d93c5ce7572feba4f55fd9ecb0f73478bf33bd2a7d`. Populated symbols have 685 bars. `TATAMOTORS` has 0.

`snapshots/context_through_20261005` supplies index and sector bars. The files use `NIFTY 50` and `INDIA VIX`. Readers alias those to `NIFTY50` and `INDIAVIX`. Oil & Gas is unavailable.

## 4. Feature Engine

Version `1.1.0`. It emits the 1.0 OHLCV fields plus `bollinger_pct_b`, `distance_from_mean`, `zscore_20`, `reversion_half_life`, `relative_volume`, `volume_acceleration`, `price_volume_corr`, `roc_10`, `trend_strength_adx`, `relative_strength_nifty`, `volume_confirmation`, `support_level`, `resistance_level`, `trend_slope`, and `volatility_percentile`. Insufficient history omits the field. `volume_imbalance` is listed under `unavailable` because these candles have no bid or ask.

VWAP is typical price times volume over the bars passed into `build_feature_set`. `close / vwap - 1` is distance from that window VWAP. It is not a daily, session, or 09:15-reset VWAP.

Research ratios in `services/quant/src/quant_agents/ml/features.py` are not FeatureSet fields.

## 5. Quant agents

Technical, Momentum, Mean Reversion, Volume, and Regime publish. They read the FeatureSet and do not recompute 1.1 formulas. Most votes still use the older fields. Regime uses `volatility_percentile` and, when the caller supplies them, `NIFTY50` and `INDIAVIX`. The default paper loop passes an empty index list, so that loop does not fetch index views. The backtester passes `INTRADAY` / `5m` or `SWING` / `1d`. `QUANT_HORIZON` and `QUANT_TIMEFRAME` apply only when set.

## 6. Intelligence agents

News, Fundamental, Valuation, and Earnings exist. They are not part of the quantitative research loop. Core proxies their news and fundamentals routes and does not open the intelligence database. An empty list means the store has nothing. If the service is down, Core returns 503.

## 7. Backtester

Operational. It uses the same sizing, costs, next-bar fills, and stop-first rule as paper. `assess` is still called with `PAPER`. Routes are create, list, detail, performance, and trades under `/api/v1/backtests`. The July 1, 2025 acceptance run on `nifty50_5m_20261005` for RELIANCE, TCS, and INFY processed 225 candles, produced 35 signals, 3 orders, and 3 fills, and ended at RELIANCE 66, TCS 28, and INFY 63. Net P&L was -375.10 at 0 bp, -464.08 at 2 bp plus 1 bp slippage, and -523.10 at 5 bp. Two runs matched. That result is not a strategy to improve.

## 8. Paper execution

Operational. A market decision on candle `t` fills at the next stored open. No later bar means the order stays unfilled. Quantity is the largest whole share whose slipped notional and fees fit in cash and in the 100,000 cap. The default cost is 2 bp. An explicit schedule, including 0 bp, overrides it. The fill price is the slipped price. Fees and slippage are stored separately. If stop and target are both inside one later bar, the stop wins. The kill switch is separate from paper start and stop. Arming it rejects new buys and queues flatten sells. A flatten with no later bar stays open.

## 9. Risk

Operational for `PAPER`. `BACKTEST`, `SHADOW`, and `LIVE` are rejected. Buys must fit cash and the 100,000 notional cap. A sell cannot exceed the shares held. Stops and targets recorded on proposals are 2% and 4%.

## 10. ML status

`MlAgent` exists and is unloaded. It is not in the paper agent list and does not publish into fusion. A direction score of the form `signal = 2 * p_up - 1` is a probability-style direction score. It is not expected profit, expected return, position size, or an execution instruction. No production model is trained or loaded.

## 11. Research status

OHLCV direction research is closed. It was evaluated and does not demonstrate tradable edge after the 2 bp cost gate. The 1-day AUC lift interval included zero. The 5-minute level was about 0.52. Five-minute rules failed the 2 bp gate. Cross-sectional rank was about 0.58 bp gross and -1.42 bp after 2 bp. A 60-minute hold was about 0.92 bp gross and -1.08 bp after 2 bp. Daily relative strength and 20-day momentum were positive only because they were long on nearly every bar. Mean reversion failed. The 2 bp gate was not changed. Always-long behavior is not alpha.

## 12. H001 status

`BLOCKED — DATA READINESS`. H001 has not been run. This is not a model failure. See `services/quant/docs/h001-data-readiness.md`. The decision is DATA NOT READY.

## 13. Live trading status

Disabled. `live_enabled` is false. Shadow trading is disabled. No production path places broker orders. `place_order` and `KiteTicker` are not used.

## 14. Known limitations

Most quant votes ignore the new 1.1 fields. The default paper loop does not attach index sets. `volume_imbalance` and Oil & Gas are unavailable. Short symbols in the 5-minute manifest are not filled. There is no global news list. Normalized backtest tables sit beside the JSON report and are not a full order blotter. The root research snapshots and datasets stay outside git.

## 15. Next gates

A new strategy must pass `docs/strategy-acceptance.md` before production integration. H001 stays blocked until a versioned, gitignored historical earnings file has an `available_at` that is the time the information was actually public, and that file passes a timestamp audit. Modeling does not start before that gate.
