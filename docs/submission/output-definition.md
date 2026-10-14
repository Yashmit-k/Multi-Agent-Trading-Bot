# Output definition

The system produces a chain of typed records, one per pipeline stage. Each record is stored in Postgres, published on a Redis bus as an `EventEnvelope`, and shown in the dashboard. Schemas are in [`docs/contracts/schemas/`](../contracts/schemas/).

Samples are **real rows** from the running database. Their origin is labelled:
- **[bootstrap paper run, 1 Oct 2026]**: the first end-to-end paper cycle, which used a one-share bootstrap sizing rule.
- **[paper cycle, 12 Oct 2026]**: a later session.
- **[live, 14 Oct 2026]**: captured by the trace recorder.

None of these are backtest results or fabricated examples. The forward paper run on market hours adds new rows of the same shape, exported to [`agent-trace/`](agent-trace/).

## 1. `TradeProposal` — Decision Engine output

Created when the fused signal for a symbol and horizon has |signal| ≥ 0.2 and confidence ≥ 0.3.

| Field | Meaning |
|---|---|
| `proposal_id` | SHA-256 of (symbol, horizon, as_of, strategy, version, session); one decision per key |
| `strategy_id`, `strategy_version` | `paper-fusion` / `1.0.0` |
| `side`, `quantity`, `entry_price` | sized to fit cash and the ₹20,000 cap |
| `stop_loss`, `take_profit` | −2 % / +4 % |
| `aggregated_signal`, `aggregated_confidence` | fusion result |
| `supporting_signal_ids` | the exact agent opinions that produced it |

**[bootstrap paper run, 1 Oct 2026]**

```json
{"proposal_id": "292b6674195da71d8a19353d03f70824f3854aa38010bdd01eceb6bd75a138ca",
 "strategy_id": "paper-fusion", "strategy_version": "1.0.0",
 "symbol": "KOTAKBANK", "horizon": "SWING", "side": "BUY", "quantity": 1,
 "entry_price": "418.3500", "stop_loss": "409.98", "take_profit": "435.08",
 "aggregated_signal": 0.3965, "aggregated_confidence": 0.47,
 "supporting_signal_ids": ["7dc8cc2d…11f3ac", "7f96084c…7ebf75", "42aac0f3…0c32", "4a7c1a8e…5202", "1c6cc012…cca7"],
 "timestamp": "2026-10-01T10:00:00Z",
 "metadata": {"quantity_model": "bootstrap_one_share", "stops_monitored": false}}
```

## 2. `RiskDecision` — Risk Engine output

Six named checks. Any failure rejects the proposal.

**Approved [bootstrap paper run, 1 Oct 2026]**

```json
{"risk_decision_id": "795a97d6e43ae55e4ae224b66fa1e97f099b8b4a1958492d8d446e717b7e502a",
 "proposal_id": "292b6674195da71d8a19353d03f70824f3854aa38010bdd01eceb6bd75a138ca",
 "status": "APPROVED", "approved_quantity": 1, "approved_price": "418.3500", "rejection_reason": null,
 "checks": [{"name": "mode_is_paper", "passed": true}, {"name": "universe_member", "passed": true},
            {"name": "sufficient_cash", "passed": true}, {"name": "notional_cap", "passed": true},
            {"name": "no_short", "passed": true}, {"name": "stop_and_target_side", "passed": true}],
 "risk_version": "1.0.0", "timestamp": "2026-10-01T10:00:00Z"}
```

**Rejected [paper cycle, 12 Oct 2026]**: a bearish fused signal on a stock that is not held. The engine refuses to short.

```json
{"risk_decision_id": "ca1d1c03fd98354657631f15b9300e212a1b1ed762224b1a4e99d0a0eb054ced",
 "proposal_id": "815a762a6c16ab46340cce4a4bbd4a4c1d6ea1764557299242359268d11178f5",
 "status": "REJECTED", "approved_quantity": 0, "rejection_reason": "sell quantity exceeds held quantity",
 "checks": [{"name": "no_short", "passed": false, "detail": "sell quantity exceeds held quantity"}, "…5 passed…"],
 "timestamp": "2026-10-12T10:00:00Z"}
```

In the stored history, 83 of 85 risk decisions are rejections. Risk is the stage that actually stops trades.

## 3. `Order` and `Execution` — Paper Execution output

**[bootstrap paper run, 1 Oct 2026]**

```json
{"order_id": "63e73ae0a73b3d6977c69fd27ac3d9b443b2d7d337fa6dd4da25e8e66ca1ca2e",
 "proposal_id": "292b6674195da71d8a19353d03f70824f3854aa38010bdd01eceb6bd75a138ca",
 "symbol": "KOTAKBANK", "exchange": "NSE", "side": "BUY", "order_type": "MARKET", "quantity": 1,
 "status": "FILLED", "trading_mode": "PAPER", "created_at": "2026-10-01T10:00:00Z"}
```

```json
{"execution_id": "b1c5bce3d0823585fa3d8508733d6f5e923d313b5cc1b91372742b6dd631930d",
 "order_id": "63e73ae0a73b3d6977c69fd27ac3d9b443b2d7d337fa6dd4da25e8e66ca1ca2e",
 "symbol": "KOTAKBANK", "quantity": 1, "price": "418.3500", "fees": "0", "slippage": "0",
 "venue": "PAPER", "executed_at": "2026-10-01T10:00:00Z"}
```

Since migration 0006, orders follow the current policy:
- CNC limit buys at reference + 25 bp;
- filled only on a later 5-minute bar;
- Zerodha equity-delivery charges applied;
- at most 6 new entries per IST day;
- entries only from 09:20 to 10:30 IST.

## 4. Portfolio — `GET /api/v1/portfolio`

**[live, 14 Oct 2026]**: the active session before the forward run.

```json
{"session_id": "c6c7f91fe84f4d48862c4a1b85646f3b", "equity": "1000000.0000",
 "snapshot": null, "total_pnl": null, "gross_exposure": null, "live_enabled": false}
```

`null` means "no fills in this session yet". It is not shown as zero P&L. `GET /api/v1/paper/daily-performance` returns `{"status": "unavailable", "reason": "no_daily_equity_history"}`. The dashboard shows that state instead of drawing an equity curve.

## 5. Agent execution trace — `GET /api/v1/trace`

Every message on the Redis buses, recorded by `core_ingestion.trace_recorder`. **[live, 14 Oct 2026]**

```json
{"event_id": "agent.signal:sig-news-8cb463b3d9fe52c6de174365",
 "event_type": "agent.signal", "channel": "agent.events", "source": "signal-ingestion",
 "correlation_id": "sig-news-8cb463b3d9fe52c6de174365",
 "timestamp": "2026-10-14T18:43:56.476111Z", "schema_version": "1.0",
 "payload": {"agent_name": "news", "symbol": "WIPRO", "horizon": "SWING",
             "signal": 0.208, "confidence": 0.48, "reason_codes": ["fixture.heuristic"], "…": "full AgentSignal"}}
```

Downstream events carry the proposal id as `correlation_id`:
- `decision.created`
- `risk.approved` / `risk.rejected`
- `order.created` / `order.updated`
- `order.filled`
- `position.updated`

`GET /api/v1/trace/{proposal_id}` returns one trade's whole chain. `scripts/export_agent_trace.py` writes the trace as JSONL plus a readable timeline.

## 6. Dashboard

The public URL renders the same outputs:
- **Agent trace**: live bus messages, agent lanes, and the chain per correlation id.
- **Agents**: each agent's latest score, confidence, reasons, LLM model or fixture label, and headlines.
- **Signals, Orders, Positions, Portfolio, Risk, Market.**

Demo fixtures appear only behind `?demo=1`, under a "DEMO DATA" banner.
