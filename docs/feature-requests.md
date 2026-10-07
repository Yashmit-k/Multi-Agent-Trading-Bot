# Feature Engine requests (quant, target feature_version 1.1.0)

Please emit these as Feature Engine outputs. Agents will not compute them.

## Mean reversion
- bollinger_pct_b
- distance_from_mean
- zscore_20
- reversion_half_life

## Volume
- relative_volume
- volume_acceleration
- volume_imbalance
- price_volume_corr

## Momentum
- roc_10
- trend_strength_adx
- relative_strength_nifty
- volume_confirmation

## Technical
- support_level
- resistance_level
- trend_slope

## Regime
- volatility_percentile (HIGH_VOLATILITY / LOW_VOLATILITY are omitted without it)
- Index FeatureSets for NIFTY50 and INDIAVIX (RISK_ON / RISK_OFF)

## Research-only ratios (Experiment A)

Quant `ml/features.py` derives these from Feature Engine fields for research. They are **not** FeatureSet fields. Production `MlAgent` must not compute them until the engine emits them:

- close_sma_10
- close_sma_20
- close_ema_12
- close_ema_26
- macd_over_close
- macd_signal_over_close
- atr_over_close
- bollinger_position
- close_vwap
- volume_ratio
- momentum_10_over_close

## Fixture names
Contracts fixture `feature_set_for` uses `return_1d` and `volume`. The engine uses `return_1` and `last_volume`. Please align contracts fixtures with the engine.
