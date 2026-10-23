# Output definition

The system produces a chain of typed records, one per pipeline stage. Each record is stored in Postgres, published on a Redis bus as an `EventEnvelope`, and shown in the dashboard. Schemas are in [`docs/contracts/schemas/`](../contracts/schemas/).

Samples are **real rows** from the running database. Their origin is labelled:
- **[bootstrap paper run, 1 Oct 2026]**: the first end-to-end paper cycle, which used a one-share bootstrap sizing rule.
- **[paper cycle, 12 Oct 2026]**: a later session.
- **[live, 14 Oct 2026]**: captured by the trace recorder.
- **[portfolio manager, 20 Oct 2026]**: a real review run on the deployed system (operator question, so nothing was traded).

None of these are backtest results or fabricated examples. The forward paper run on market hours adds new rows of the same shape, exported to [`agent-trace/`](agent-trace/).

## 1. `TradeProposal` — Decision Engine output

- **Specialists mode (live):** created when Technical or Momentum triggers (score ≥ +0.30, confidence ≥ 0.40) and no specialist blocks. `metadata.specialists` holds every agent's verdict (trigger / pass / block / no opinion / ignored fallback / size), and `metadata.size_fraction` is 0.5 when the market is risk-off.
- **Fusion mode:** created when the fused signal has |signal| ≥ 0.2 and confidence ≥ 0.3. An agent BUY must also reach fused signal ≥ 0.35 and confidence ≥ 0.4.
- SELLs keep the lower bar, so exits are not delayed.

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

## 2. `ProposalReview`, `ReviewStep`, `AgentRequest`: Portfolio manager output

For each review the manager produces a stream of `ReviewStep` messages (`review.step`), zero to two `AgentRequest` messages to other agents (`agent.request`), and one `ProposalReview` verdict (`review.completed`). Schemas: [`ProposalReview.json`](../contracts/schemas/ProposalReview.json), [`ReviewStep.json`](../contracts/schemas/ReviewStep.json), [`AgentRequest.json`](../contracts/schemas/AgentRequest.json).

| `ProposalReview` field | Meaning |
|---|---|
| `verdict` | `APPROVE` · `REDUCE` · `VETO` · `UNAVAILABLE` (no answer within 240 s; the risk engine decides alone) |
| `size_fraction` | 1 for APPROVE/UNAVAILABLE, 0.1–0.9 for REDUCE, 0 for VETO. The schema enforces the pairing, so a verdict cannot enlarge a trade. |
| `conflicts` | one entry per disagreement the manager found. The code rejects a verdict that leaves out an agent disagreeing with the fused signal. |
| `critique` | the decisive evidence, in 2–4 sentences |
| `reviewer` | the model that answered, or `rule_fallback`, or `none` |
| `steps`, `metadata.tools_called`, `metadata.rechecks` | what it did |

`ReviewStep.kind` is one of `plan`, `tool_call` (with `tool` and `purpose`), `tool_result`, `agent_reply`, `critique` (a draft verdict the code sent back), `replan` (model switch or forced verdict), or `llm_error`.

**Steps 13–14 and the request in between [portfolio manager, 20 Oct 2026]**: the manager asks the News agent to re-check RELIANCE, and the agent replies (2 of its 5 headlines shown).

```json
{"kind": "tool_call", "step": 13, "tool": "ask_agent_to_recheck", "actor": "portfolio_manager",
 "purpose": "Re-check news sentiment for RELIANCE without fallback heuristics",
 "arguments": {"agent": "news", "symbol": "RELIANCE", "question": "What is the true news sentiment and score for RELIANCE based on recent headlines, without relying on fallback heuristics?"},
 "review_id": "rv-adhoc-da9515777d6742a59fe6958c", "timestamp": "2026-10-20T13:19:15.850469Z"}
```

```json
{"request_id": "req-eee8f606481b48f8b390", "review_id": "rv-adhoc-da9515777d6742a59fe6958c",
 "from_agent": "portfolio_manager", "to_agent": "news", "symbol": "RELIANCE",
 "question": "What is the true news sentiment and score for RELIANCE based on recent headlines, without relying on fallback heuristics?",
 "timestamp": "2026-10-20T13:19:15.870593Z"}
```

```json
{"kind": "agent_reply", "step": 14, "tool": "ask_agent_to_recheck", "actor": "news",
 "summary": "news re-checked RELIANCE: score 0.72 confidence 0.55",
 "metadata": {"signal_id": "sig-news-db4f35d64f6d92daf15c3f98", "model": "gemini-3-flash-preview", "llm_fallback": false,
              "score": 0.72, "confidence": 0.55, "reason_codes": ["capital_raise", "operating_updates", "analyst_view", "price_move"],
              "headlines": ["Rubio says US to discuss Venezuelan oil production with Ambani's Reliance Industries",
                            "Jio IPO opens tomorrow: How can investors maximise allotment chances under Rs 2,500 crore RIL shareholders quota"]},
 "review_id": "rv-adhoc-da9515777d6742a59fe6958c", "timestamp": "2026-10-20T13:19:28.068265Z"}
```

**The verdict [portfolio manager, 20 Oct 2026]**

```json
{"review_id": "rv-adhoc-da9515777d6742a59fe6958c", "kind": "ad_hoc", "proposal_id": null, "symbol": "RELIANCE",
 "verdict": "VETO", "size_fraction": 0.0, "reviewer": "gemini-3.5-flash", "steps": 31,
 "conflicts": ["regime: risk-off (-1.0) vs positive fused news signal (+0.72)",
               "momentum: strongly bearish (-1.0) on return, 10-day momentum, and MACD vs positive fused news signal (+0.72)",
               "earnings: bearish (-0.30) due to EPS/margin pressures vs positive fused news signal (+0.72)",
               "valuation: disagrees with fused buy signal",
               "volume: disagrees with fused buy signal",
               "fundamental: bearish (-0.291) relying on fallback heuristic (llm_fallback true) vs positive fused news signal"],
 "critique": "The BUY proposal relies entirely on temporary positive news headlines (+0.72), which strongly conflicts with a severe risk-off market regime (-1.0) and negative technical momentum (-1.0 across 1-day return, 10-day momentum, and MACD). Earnings (-0.30), fundamental (-0.291), valuation, and volume agents all disagree with the bullish signal as well. Buying into a broad market downtrend with elevated VIX (+29.6% over 20 days) and opposing technical/fundamental signals carries poor risk-reward.",
 "metadata": {"manager_version": "1.0.0", "rechecks": 1,
              "tools_called": ["get_agent_opinions", "get_market_context", "get_price_features", "get_fundamentals", "ask_agent_to_recheck",
                               "get_agent_opinions", "get_price_features", "get_market_context", "get_portfolio"]},
 "timestamp": "2026-10-20T13:22:51.712033Z"}
```

How a pipeline verdict changes the trade: VETO fails the risk check `portfolio_manager`, so the decision is REJECTED with `"portfolio manager vetoed: <critique>"`. REDUCE lowers `approved_quantity` and the order quantity. Pipeline reviews run in the 09:20–15:15 IST entry window, and their chains appear on the Agent trace and Portfolio manager pages. A complete real chain (REDUCE 16 → 8 shares, then the fill) is in [`agent-trace/20261021-jswsteel-trade.md`](agent-trace/20261021-jswsteel-trade.md).

## 3. `RiskDecision` — Risk Engine output

Six order checks always. Every new BUY (agent or applied strategy) also gets:
- 5 portfolio checks: `max_open_positions`, `sector_concentration`, `exposure_cap`, `per_stock_cap`, `daily_entry_cap`;
- 7 trade checks (risk 1.3.0): `daily_loss_limit`, `drawdown_limit`, `risk_per_trade`, `reward_to_risk`, `price_drift`, `stop_out_cooldown`, `evidence_quality`;
- `market_regime` on intraday buys;
- `portfolio_manager` when the manager reviewed it.

Any failure rejects the proposal, and `rejection_reason` names every failed check. The samples below predate risk 1.3.0, so they show only the six order checks.

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

## 4. `Order` and `Execution` — Paper Execution output

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
- entries only from 09:20 to 15:15 IST (`PAPER_ENTRY_END=15:15` in the deployment; the code default is 10:30).

## 5. Portfolio — `GET /api/v1/portfolio`

**[live, 14 Oct 2026]**: the active session before the forward run.

```json
{"session_id": "c6c7f91fe84f4d48862c4a1b85646f3b", "equity": "1000000.0000",
 "snapshot": null, "total_pnl": null, "gross_exposure": null, "live_enabled": false}
```

`null` means "no fills in this session yet". It is not shown as zero P&L. `GET /api/v1/paper/daily-performance` returns `{"status": "unavailable", "reason": "no_daily_equity_history"}`. The dashboard shows that state instead of drawing an equity curve.

## 6. Agent execution trace — `GET /api/v1/trace`

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
- `review.requested`, `review.step` (one per reasoning step), `agent.request`, `review.completed`
- `risk.approved` / `risk.rejected`
- `order.created` / `order.updated`
- `order.filled`
- `position.updated`

`GET /api/v1/trace/{proposal_id}` returns one trade's whole chain. `scripts/export_agent_trace.py` writes the trace as JSONL plus a readable timeline.

## 7. Dashboard

The public URL renders the same outputs:
- **Portfolio manager**: every review with its plan, tool calls, critiques, agent requests and replies, verdict, and the risk decision that followed. A signed-in operator can ask it about any stock.
- **Agent trace**: live bus messages, agent lanes (including the portfolio manager), and the chain per correlation id.
- **Agents**: each agent's latest score, confidence, reasons, LLM model or fixture label, and headlines.
- **Signals, Orders, Positions, Portfolio, Risk, Market.**

Demo fixtures appear only behind `?demo=1`, under a "DEMO DATA" banner.
