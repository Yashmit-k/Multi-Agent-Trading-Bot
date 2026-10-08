# Label version 1.0

`QUANT_LABELER=quant_agents.labelers:next_close_direction`

## Prediction horizon

`h = QUANT_LABEL_HORIZON` (default `label_horizon` in `horizons.yaml`, must be an integer >= 1). `t+h` is the **h-th later bar that exists** on the same symbol and timeframe. Holidays and missing 5m bars are not empty slots.

## Target

Binary classification from candle **close** (not Feature Engine formulas):

- `1` if `close[t+h] > close[t]`
- `0` if `close[t+h] < close[t]`
- **Dropped** if the two closes are equal (neutral / flat is not labeled 0)

No ratio `close[t+h]/close[t]-1`. Future close is never written as a feature.

## Required future bars

A row is dropped when there is no t+h bar, when `future.end` is after `QUANT_TRAINING_DATA_CUTOFF`, or when a **5m** label would cross an IST session date (overnight gap).

## Why this target

It is a directional paper-trading signal: whether the next available bar closes higher than the current knowable close (`Candle.end`). It is not a PnL backtest.

PnL / execution metrics require Core’s backtester and are out of this phase.
