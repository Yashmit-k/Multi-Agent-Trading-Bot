# Quant agents

Python package `quant_agents` under `services/quant`. Agents consume `FeatureSet` via `FeatureProvider` and return `AgentSignal`. They do not recompute indicators, own a `SignalSink`, or call Core HTTP.

## Timestamp vs as_of

`as_of` is the knowledge cutoff. `timestamp` is production time from the injected `Clock`. In replay, `ReplayClock` makes `timestamp == as_of`. Agents never call the wall clock.

`horizons.yaml` is local configuration, not a contract.

## Snapshot dataset

`t+h` is the h-th **later bar that exists** on the same symbol and timeframe (holidays and missing 5m bars skip empty slots). Overnight 5m labels (session date in IST changes) are dropped. Build one parquet per `--timeframe`. Real snapshots require `QUANT_TRAINING_DATA_CUTOFF`. Install `[train]` for pyarrow.

```bash
python -m pip install -e "services/quant[train]"
python -m quant_agents.dataset --snapshot snapshots/nifty50 --timeframe 1d --out datasets/nifty50-1d.parquet
python -m quant_agents.dataset --snapshot snapshots/nifty50 --timeframe 5m --out datasets/nifty50-5m.parquet
```

Do not mix 1d and 5m in one parquet or one model. Train two baselines:

```bash
python -m quant_agents.ml.experiment --parquet datasets/nifty50-1d.parquet --output-dir artifacts/baseline-1d --log experiments/log.jsonl
python -m quant_agents.ml.experiment --parquet datasets/nifty50-5m.parquet --output-dir artifacts/baseline-5m --log experiments/log.jsonl
```

This writes sklearn logistic artifacts and appends to `experiments/log.jsonl`. It does not change production `MlAgent`. PnL needs Core's backtester. `datasets/`, `snapshots/`, `artifacts/`, and `experiments/` are gitignored.

Research Experiment A (relative features, timestamp splits):

```bash
python -m quant_agents.ml.experiment_a --parquet datasets/nifty50-1d.parquet --out experiments/experiment-a/1d
python -m quant_agents.ml.experiment_a --parquet datasets/nifty50-5m.parquet --out experiments/experiment-a/5m
```


## Run

```bash
python -m pip install -e "packages/contracts" -e "services/quant[dev]"
python -m pytest services/quant/tests/unit -q
python -m pytest services/quant/tests/integration -m integration -q
uvicorn quant_agents.service:app --port 8080
```

`/health` is `degraded` until Core injects a `SignalSink`. PAPER/SHADOW/LIVE refuse to start without a sink.

Docker build context is the **repository root**:

```bash
docker build -f services/quant/Dockerfile .
```
