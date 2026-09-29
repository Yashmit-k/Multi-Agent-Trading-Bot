# contracts 1.0.0

Shared schemas, events, and interfaces for every service in the trading system. This package is the integration boundary. It does not implement strategy, risk rules, brokers, or storage.

```python
from contracts.schemas.agent_signal import AgentSignal
```

## Install

From the repo root:

```bash
python3 -m pip install -e "packages/contracts[dev]"
```

Python 3.12 or newer. Version `1.0.0`.

## Versioning

- Breaking schema changes require a major version.
- Backward-compatible additions require a minor version.
- Bug and documentation fixes require a patch version.

Wire field `schema_version` is `"1.0"`. A breaking schema change bumps that major number and the package major version together.

## What other developers import

Dev 1 and Dev 2 import this package. They do not redefine:

- `AgentSignal`, `NewsArticle`, `NewsSignal`, `FeatureSet`, `TradeProposal`, `RiskDecision`, `Order`, `Execution`, `Position`, `PortfolioSnapshot`, `EventEnvelope`
- agent ids, event names, Redis channels, horizons, trading modes, or order states

A contract change is a pull request to `packages/contracts`.

## Closed vocabulary

| Kind | Values |
| --- | --- |
| Agents | `technical`, `momentum`, `mean_reversion`, `volume`, `regime`, `ml`, `news`, `fundamental`, `valuation`, `earnings` |
| Horizons | `INTRADAY`, `SWING`, `LONG_TERM` |
| Modes | `BACKTEST`, `PAPER`, `SHADOW`, `LIVE` |
| Order states | `CREATED`, `VALIDATED`, `RISK_APPROVED`, `SUBMITTED`, `OPEN`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `REJECTED`, `EXPIRED`, `FAILED` |

Redis channels are `market.events`, `feature.events`, `agent.events`, `news.events`, `decision.events`, `risk.events`, `order.events`, `portfolio.events`, and `system.events`. The event type lives on `EventEnvelope`. There is no per-agent channel. `fundamental.updated` is published on `market.events`.

`order.filled` carries an `Execution`. `order.created` carries an `Order` in `CREATED`. `order.rejected` carries an `Order` in `REJECTED`.

## Point in time

`FundamentalDataPoint.available_at` is the first time a backtest may see the row. Use `contracts.pit.assert_available` or `filter_available` so `available_at <= as_of`. `published_at` on a news article is the source time. `retrieved_at` is when this system stored it.

Agents read `FeatureSet` from `FeatureProvider`. They do not recompute indicators from candles.

## Agents

`TradingAgent.evaluate(symbol, as_of, context)` returns `AgentSignal`. `AgentContext` may hold market, feature, news, and fundamental providers, configuration, and an optional portfolio snapshot. It rejects known execution-credential keys.

Agents publish through `SignalSink.submit`. They do not write PostgreSQL, change positions, place orders, call Zerodha, call the risk engine, or call another agent.

`MarketDataProvider` is the interface for both `ZerodhaMarketDataProvider` and `HistoricalReplayMarketDataProvider`.

## Fakes

`FakeMarketDataProvider`, `FakeFeatureProvider`, `FakeNewsProvider`, `FakeFundamentalProvider`, and `FakeSignalSink` serve a fixed daily series for `RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, and `ICICIBANK`. `FIXTURE_AS_OF` is `2024-06-03T10:00:00+00:00` (15:30 IST). The same call returns the same value. One fundamental row per symbol stays hidden until its `available_at`.

## HTTP contract

- `POST /api/v1/internal/signals` accepts `AgentSignal` and returns `SubmissionResult`. The reference app validates the body and does not persist it.
- `GET /api/v1/system/contracts` returns `contract_version`, `schema_versions`, `event_versions`, `supported_agents`, `supported_horizons`, and `supported_modes`.

## Generated schemas

JSON Schema and OpenAPI are generated from the models into [`docs/contracts`](../../docs/contracts). Regenerate them after a schema change:

```bash
python -m contracts.export_schemas
```

Do not edit those files by hand.

## Tests

```bash
python3 -m pytest
```

Run that from `packages/contracts`.

The import example for other developers is [`examples/dev_import.py`](../../examples/dev_import.py).
