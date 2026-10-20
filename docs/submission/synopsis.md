# Project synopsis: Multi-Agent NIFTY 50 Paper Trading System (StockX)

**Problem.** A retail trader in Indian equities has to read price action, news and company fundamentals for many stocks at once, and then turn those reads into trades without breaking their own risk rules. By hand this is slow and inconsistent. Automated bots have the opposite problem: they are often opaque, overfit to past data, or let one model place real orders unchecked. Evidence also gets lost: when the chart says buy and the news says sell, a single model averages the two away instead of noticing the conflict. What is missing is a system that watches all 50 NIFTY 50 stocks, collects independent specialist opinions, *argues about them*, and turns them into auditable decisions inside hard risk limits, safely, without risking money.

**Solution.** StockX is a multi-agent platform running on live Zerodha market data with paper money.
- **Nine specialist agents** score every stock independently and publish the same message: a score from −1 to +1, a confidence, and their reasons.
  - Five are deterministic **quant agents** (technical, momentum, mean reversion, volume, market regime).
  - Four are **LLM intelligence agents** (news from 16 live RSS feeds; fundamentals, valuation and earnings from nightly Yahoo data).
- Code fuses the opinions per horizon and proposes a trade when the fused signal is strong enough.
- A tenth agent, the **LLM portfolio manager**, then reviews every proposed BUY before the risk engine sees it:
  - it plans what to check and calls tools (every agent's opinion, news, fundamentals, price features, the market regime, the paper book, and its own past reviews);
  - it names the conflicts between agents;
  - it can ask an intelligence agent to re-check a stock with fresh data and a second model;
  - it approves, shrinks or vetoes the trade.
- Plain code critiques the manager in turn: a verdict that ignores a disagreeing agent, or rests on an opinion the LLM never actually produced, is sent back for revision.
- The risk engine still has the final say: paper mode only, the NIFTY universe, cash, ₹20,000 per order, six entries a day, sector and exposure limits.
- Paper execution fills at the next bar with Zerodha charges.
- Every handoff, including each reasoning step of the manager, is a typed message on a Redis bus. A trace recorder stores it, and the dashboard shows it live.
- Live trading is hard-coded off.

**Target user.** An individual Indian retail trader, or a small research team, who wants to forward-test a systematic multi-signal NIFTY 50 strategy on real market data with fake money. They need to see exactly why every decision was made, including where the agents disagreed, before trusting it with capital. The Strategy Lab serves the same user: they can build any rule-based algorithm, backtest it with the live fill and cost model, and apply it to paper trading, either replacing the agents, trading alongside them, or trading only when the agents agree (a Settings choice).

## Scope relative to the approved CA2 description

The architecture, the specialist agents, the rule "agents give opinions, code decides", separate horizons, point-in-time data and staged modes are as approved. Changes, stated honestly:

| CA2 item | Status now | Why |
|---|---|---|
| Agent coordination | **Added: the LLM portfolio manager** (supervisor/critic) with tools, re-check requests to other agents, critique and revision, and model failover | The first build's agents only published opinions into a fixed pipeline. The manager makes the agents reason about each other's output. It can only approve, shrink or veto, so it adds judgement without adding a way to lose money. |
| ML agent | Implemented, **not loaded** | Three pre-registered ML studies found no robust return edge after costs ([study write-ups](../../services/quant/docs/)). An agent must pass its gate before it gets a vote. |
| Fusion weights | Set by a backtest of every agent ([agent-tuning result](../../services/quant/docs/agent-tuning-result.md)) | No quant agent kept a validated swing edge, so their swing weight is 0. Fundamental, valuation, earnings and ML have weight 0. They still run, and the portfolio manager weighs their arguments. |
| LLM capacity | Free-tier Gemini | When the daily quota runs out, the intelligence agents fall back to a labelled heuristic (`fixture.heuristic`). The manager detects fallback-based opinions and asks for a re-check on a second model. |
| Intraday entries | Off by default | The exit-rules and selective-intraday studies found 5-minute entries lose money to charges. Intraday exits still run. |
| SHADOW / LIVE modes | Disabled | No strategy has passed the acceptance gate. |
| Profitable strategy | Not claimed | 13 pre-registered studies are published with their failures in [`services/quant/docs/`](../../services/quant/docs/). |
