# Demo script (live demo and the optional 2–3 minute video)

Sign in as the operator first (header → Sign in). If possible, record or present between 09:20 and 15:15 IST on a trading day, when real agent BUYs go through the portfolio manager (Settings → strategy mode must be "alongside" or no strategy applied; in "replace" mode the agents open no new trades). Outside that window, use **Ask the portfolio manager**, which runs the same agent on a hypothetical trade.

| Time | Screen | Say |
|---|---|---|
| 0:00–0:15 | Overview, PAPER banner | "StockX is a multi-agent NIFTY 50 paper trader on live Zerodha data with fake money. Live trading is hard-disabled." |
| 0:15–0:40 | **Agents** page | "Nine specialists each publish a score, a confidence and reasons: five rule-based quant agents and four LLM agents that read live news and fundamentals. A backtest set their fusion weights. Only agents with a validated edge vote, but the others still argue their case." |
| 0:40–1:40 | **Portfolio manager** → pick a stock → **Would you buy this now?** | While it runs (20–60 s): "This is the tenth agent, an LLM supervisor. Watch it plan, choose tools, and find where the agents disagree." Then point at the steps. *Plan*: it decides what to look at. *Tool call* + *why*: each call has a stated purpose. *Sent back for revision*: our code rejected its draft because it ignored a disagreeing agent, or relied on an opinion produced by a fallback heuristic. *Asks news agent*: it requested a re-check, and the News agent pulled fresh headlines and answered with a second model. *Verdict*: approve, shrink or veto, with the conflicts it found. "It can only make a trade smaller or stop it; the risk engine still runs after it." |
| 1:40–2:10 | **Agent trace** | "Every one of those steps is a real message on the Redis bus. Here is the portfolio-manager lane, the agent.request to the News agent, and its reply signal on agent.events. A real trade's chain links signals → proposal → review → risk → order → fill under one id." |
| 2:10–2:30 | **Risk** page or a journal entry | "When the manager vetoes, the risk check 'portfolio_manager' fails with its critique. If it is down or rate-limited, the trade waits up to 240 seconds, is marked UNAVAILABLE, and the normal rules decide. Nothing crashes." |
| 2:30–2:50 | **Strategy lab** + **Settings** | "You can also build your own algorithm, backtest it with the same fill and cost model as paper trading, and apply it. Settings chooses whether it replaces the agents, trades alongside them, or trades only when the agents agree, in which case the portfolio manager reviews it too." |

**Robustness talking points for Q&A:**
- **Bad input.** An unknown symbol returns 422. A non-operator gets 401 and the sign-in box.
- **Partial failures.**
  - A failing tool returns an error to the model, which picks another route.
  - Gemini 429/503/timeout is retried once, then the backup model takes over, then a labelled rule-based review runs.
  - A re-check that fails is reported back, and the manager decides without it.
- **Why several agents.** One model averaging everything hides conflicts. Here independent specialists disagree in the open, and a supervisor must address each disagreement before it may decide.
