# Project synopsis: StockX, a multi-agent NIFTY 50 paper-trading system

**Live system:** https://13-238-176-73.sslip.io · **Repository:** https://github.com/Yashmit-k/Multi-Agent-Trading-Bot

**Problem.** An Indian retail trader who follows the 50 NIFTY 50 stocks must read price action, news and company fundamentals for every stock, then turn those readings into trades without breaking their own risk rules. Done by hand, this is slow and inconsistent. Automated bots fail in the opposite way:
- they are opaque;
- they are often overfitted to past prices;
- they usually let a single model place orders with nothing checking it.

When the chart says "buy" and the news says "sell", a single model averages the two signals and the disagreement disappears. The trader needs a system that:
- collects independent specialist opinions on every stock;
- makes the disagreements between them visible and argues about them;
- turns them into auditable decisions inside hard risk limits;
- proves itself with fake money before any real money is involved.

**Solution.** StockX is a multi-agent platform that trades on live Zerodha Kite market data with a ₹10,00,000 paper account.
- **Nine specialist agents** score every stock independently. Each publishes the same message (`AgentSignal`): a score from −1 to +1, a confidence from 0 to 1, and its reasons.
  - **Five deterministic quant agents:** technical, momentum, mean reversion, volume and market regime. Each runs twice: on daily bars for swing trades and on 5-minute bars for intraday trades.
  - **Four LLM intelligence agents** using Google Gemini:
    - **News** reads 16 live Indian financial RSS feeds.
    - **Fundamental**, **valuation** and **earnings** read Yahoo Finance data fetched every weekday at 20:30 IST.
- **Fusion and decision.** An orchestrator combines the opinions into a confidence-weighted average for each stock and horizon. Each agent's weight comes from its live track record, which is re-graded every hour. It proposes a BUY when the fused signal is at least 0.35 and the fused confidence at least 0.4.
- **Portfolio manager (tenth agent).** An LLM supervisor reviews every proposed BUY before the risk engine sees it.
  - It writes a plan and calls eight read-only tools: agent opinions, news, fundamentals, price features, market context, the paper book, its own past reviews, and a re-check request.
  - It names each agent that disagrees with the proposal.
  - It can ask an intelligence agent to re-check a stock with fresh data.
  - It then approves the trade, shrinks it (×0.1 to ×0.9) or vetoes it. It can never create or enlarge a trade.
- **Code checks the manager.** A draft verdict is sent back for revision if:
  - it ignores a disagreeing agent; or
  - it rests on an opinion that came from a fallback heuristic when the LLM was unavailable.
- **Risk engine.** It has the final say, with up to 20 checks on every BUY:
  - paper mode only; the stock must be in the NIFTY 50 universe;
  - ₹20,000 per order and ₹40,000 per stock;
  - at most 6 new entries a day, 10 positions and 2 per sector, and 30% of starting cash in total;
  - daily loss and drawdown limits, loss at the stop, reward-to-risk, price drift and a cooldown after a stop-out;
  - evidence quality: no buy that rests only on fallback heuristics.
- **Paper execution.** It places a delivery (CNC) limit order at the last daily close + 0.25%. The order fills on a later 5-minute bar between 09:20 and 15:15 IST, and Zerodha's real charges are applied.
- **Trace.** Every handoff, including each reasoning step of the manager, is a typed message on a Redis bus. A trace recorder stores it, and the website shows it live.
- **Live trading** is hard-coded off.

**Target user.** An individual Indian retail trader or a small research team. They want to forward-test a systematic, multi-signal NIFTY 50 strategy on real market data with fake money, and see exactly why each decision was made, including where the agents disagreed, before trusting it with capital. The same user can open the **Strategy Lab**:
- build their own rule-based algorithm from 75 indicators, candle patterns and market-structure values;
- backtest it with the same fill and cost rules as paper trading;
- apply it to the paper account. In Settings they choose whether it replaces the agents' entries, trades alongside them, or trades only when the agents agree.

## Scope compared with the approved CA2 description

The architecture, the specialist agents, the principle "agents give opinions, code decides", separate horizons, point-in-time data (no look-ahead) and paper-first staging are as approved. The changes are:

| CA2 item | Status now | Why |
|---|---|---|
| Agent coordination | **Added: an LLM portfolio manager** (supervisor and critic) with tools, re-check requests to other agents, code-side critique of its verdicts, and model failover | In the first build the agents only published opinions into a fixed pipeline. The manager makes them reason about each other's output. Because it can only approve, shrink or veto, it adds judgement without adding a way to lose money. |
| ML agent | Implemented, **not loaded** | Three pre-registered machine-learning studies found no return edge that survives costs. An agent must pass its gate before it gets a vote. |
| Fusion weights | Set by each agent's **live track record**, with backtest priors until the record is long enough | The agent backtest found no quant agent with a validated swing edge. Their swing weight is therefore 0, and on the swing book only the News agent votes (weight 0.5). Fundamental, valuation, earnings and ML are excluded from the vote. They all still run, and the portfolio manager weighs their arguments. |
| LLM capacity | Gemini free tier | When a model's daily quota runs out, its agents switch to backup models and then to a labelled heuristic (`fixture.heuristic`). The manager and the risk engine both detect opinions built on that heuristic. |
| Intraday entries | Off by default (Settings) | Two studies (exit rules and selective intraday) found that 5-minute entries lose money to charges. Intraday exits still run. |
| SHADOW and LIVE modes | Disabled | No strategy has passed the acceptance gate. |
| Profitable strategy | Not claimed | 15 pre-registered studies are published, failures included. One rule-based strategy (EMA dip reversion) passed its gates on 2021–2023 and is now in a paper forward test. |
