# Demo video script (2–3 minutes)

Record during market hours (09:20–10:30 IST) if possible, so decisions happen live. Screen-record the public URL.

| Time | Screen | Say |
|---|---|---|
| 0:00–0:15 | Dashboard, PAPER banner | "This is our multi-agent NIFTY 50 paper trader. It runs on live Zerodha market data with fake money. Live trading is hard-disabled." |
| 0:15–0:45 | **Agents** page | "Ten agents. Five quant agents are deterministic rules on live candles. Four intelligence agents read unstructured data through an LLM. ML is built but not loaded. Each agent returns the same thing: a score, a confidence, and its reasons. Here the News agent read this live headline…" (point at a headline and its score). "Fundamental, valuation, and earnings have no live feed yet, so they are excluded from fusion and can't affect trades." |
| 0:45–1:30 | **Agent trace** page | "This is a real trace of messages between agents on the Redis bus." Click a lane, then click **view** on a decision chain. "Here the agents' signals were fused into a proposal. Risk ran six checks and approved it, then paper execution queued an order and filled it." If nothing traded, show a rejection: "Risk rejected this one because it would have been a short sale." |
| 1:30–2:00 | **Orders / Positions / Risk** | "Orders are CNC limit orders: at most ₹20,000 each and at most six new entries a day, with Zerodha charges applied. The kill switch blocks new buys and flattens positions." |
| 2:00–2:30 | `docs/submission/design.md` diagram | "Orchestration is a blackboard plus an orchestrator-worker. Agents publish opinions on their own schedules. The core worker runs fusion → decision → risk → execution in a fixed order, so no LLM output can skip risk. Agents give opinions; code decides." |
| 2:30–2:50 | Terminal: `deploy/smoke.sh <url>` | "Smoke test: live trading is off, the trace endpoint is live, and the public proxy refuses write requests." |
