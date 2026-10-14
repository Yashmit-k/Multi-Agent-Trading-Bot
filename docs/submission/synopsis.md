# Project synopsis — Multi-Agent NIFTY 50 Paper Trading System

**Problem.** Retail traders in Indian equities have to read price action, news, and company fundamentals for many stocks at once. Then they have to turn those reads into trades without breaking their own risk rules. Doing this by hand is slow and inconsistent. Fully automated bots are a different problem: they are often opaque, overfit to past data, or let one model place real orders unchecked. What is missing is a system that watches all 50 NIFTY 50 stocks, collects independent specialist opinions, and turns them into auditable decisions. Every decision should pass hard risk limits, and the system should be safe to evaluate on live markets without risking money.

**Solution.** We built a multi-agent platform. Each specialized agent scores every NIFTY 50 stock independently and publishes the same message: a score from -1 to +1, a confidence from 0 to 1, and reason codes/metadata explaining why.
- **Quant agents** are deterministic rules computed on live Zerodha Kite market data: Technical, Momentum, Mean Reversion, Volume, and Market Regime.
- **Intelligence agents** use an LLM router on unstructured data: News, Fundamental, Valuation, and Earnings.

Agents never place orders. Code makes the decisions:
1. Signal Fusion combines the opinions with separate intraday, swing, and long-term horizons.
2. The Decision Engine proposes a trade only when the fused signal is strong enough.
3. The Risk Engine approves or rejects it. Its limits: paper mode only, NIFTY universe only, enough cash, ₹20,000 per order, at most 6 new entries per day, and no short selling.
4. Paper Execution simulates the fill at the next bar with Zerodha-style charges.

Every handoff between agents is published on a Redis event bus and captured by a trace recorder. The dashboard shows the live trace, signals, orders, positions, and risk state. Every calculation uses only data that existed at that moment, so backtests cannot see the future. The system supports four modes: BACKTEST, PAPER, SHADOW, and LIVE. It runs in PAPER. LIVE is hard-coded off.

**Target user.** An individual Indian retail trader or small research team who wants to forward-test a systematic, multi-signal NIFTY 50 strategy on real market data with fake money. They need to see exactly why every decision was made before they trust it with capital.

## Scope relative to the approved CA2 description

The architecture, the 10 named agents, the "agents give opinions, code decides" rule, the separate horizons, point-in-time data, and the staged modes are all as approved. Differences, stated honestly:

| CA2 item | Status now | Why |
|---|---|---|
| ML agent | Implemented, **not loaded** | A pre-registered ML stock ranker (gradient boosting on daily features) was built and scored once on unseen 2026 data. It beat an equal-weight basket by +0.21% per 5-day window, in 65% of windows, but its 90% interval includes zero and it lost money after delivery costs. It failed the acceptance gate, so it is not traded ([result](../../services/quant/docs/ml-rank-result.md), *Research* page). |
| News agent | **Live**: real RSS headlines from ET Markets, Business Standard, and Mint, mapped to NIFTY symbols and scored through the LLM router | Live with an OpenAI-compatible LLM key. Without a key, the router falls back to a deterministic heuristic, and each signal is labelled `fixture` in its metadata and in the UI. |
| Fundamental, Valuation, Earnings agents | Run on fixture data and are **excluded from fusion** (weight 0) | No verified live fundamentals/earnings feed is configured. They still run and appear in the trace, but they cannot influence a trade. |
| SHADOW / LIVE modes | Disabled | Paper validation is not complete. No strategy has yet passed the acceptance gate (`docs/strategy-acceptance.md`). |
| Profitable strategy | Not claimed | Research results are documented, including negative ones. The live paper run collects honest forward evidence. |

On the reviewers' note: only the four Intelligence agents are agentic in the LLM sense. The five Quant agents and the core pipeline stages are deterministic tools, by design. See [`design.md`](design.md#which-parts-are-agentic).
