# Quant agents

Python package `quant_agents` under `services/quant`. Agents consume `FeatureSet` via `FeatureProvider` and return `AgentSignal`. They do not recompute indicators, own a `SignalSink`, or call Core HTTP.

## Timestamp vs as_of

`as_of` is the knowledge cutoff. `timestamp` is production time from the injected `Clock`. In replay, `ReplayClock` makes `timestamp == as_of`. Agents never call the wall clock.

`horizons.yaml` is local configuration, not a contract.

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
