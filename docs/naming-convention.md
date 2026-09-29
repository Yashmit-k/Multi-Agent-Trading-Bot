============================================================
MULTI-AGENT TRADING SYSTEM — NAMING CONVENTION
============================================================

Repository:
https://github.com/Yashmit-k/Multi-Agent-Trading-Bot.git

Python:
snake_case

Classes:
PascalCase

Functions:
snake_case

Constants:
UPPER_SNAKE_CASE

Environment variables:
UPPER_SNAKE_CASE

API:
 /api/v1/<resource>

WebSocket:
 /ws/v1/stream

Redis channels:
<domain>.events

Event names:
<domain>.<event>

Examples:
market.tick
market.candle
agent.signal
decision.created
risk.approved
order.filled

------------------------------------------------------------
AGENT IDs
------------------------------------------------------------

technical
momentum
mean_reversion
volume
regime
ml
news
fundamental
valuation
earnings

------------------------------------------------------------
HORIZONS
------------------------------------------------------------

INTRADAY
SWING
LONG_TERM

------------------------------------------------------------
TRADING MODES
------------------------------------------------------------

BACKTEST
PAPER
SHADOW
LIVE

------------------------------------------------------------
ORDER STATES
------------------------------------------------------------

CREATED
VALIDATED
RISK_APPROVED
SUBMITTED
OPEN
PARTIALLY_FILLED
FILLED
CANCELLED
REJECTED
EXPIRED
FAILED

------------------------------------------------------------
SIDES
------------------------------------------------------------

BUY
SELL

------------------------------------------------------------
ORDER TYPES
------------------------------------------------------------

These are the only names. packages/contracts defines them.
SL and SL_M are not aliases.

MARKET
LIMIT
STOP_LOSS
STOP_LOSS_MARKET

------------------------------------------------------------
FILES
------------------------------------------------------------

signal_fusion.py
decision_engine.py
risk_engine.py
market_data.py

------------------------------------------------------------
CLASSES
------------------------------------------------------------

AgentSignal
FeatureSet
TradeProposal
RiskDecision
Order
Execution
Position
PortfolioSnapshot

------------------------------------------------------------
DATABASE
------------------------------------------------------------

Tables:
snake_case plural

agent_signals
trade_decisions
risk_decisions
portfolio_snapshots

Instrument identity:
instrument_id

Signal identity:
signal_id

Foreign keys:
<entity>_id

Timestamps:
created_at
updated_at
published_at
retrieved_at
available_at
executed_at

------------------------------------------------------------
JSON
------------------------------------------------------------

Field names are snake_case.

Enum values stay as packages/contracts defines them.
Examples: INTRADAY, BACKTEST, STOP_LOSS, market.tick.
schema_version is the literal "1.0", not 1.0.0.

Example:

{
  "signal_id": "...",
  "agent_name": "technical",
  "agent_version": "1.0.0",
  "as_of": "...",
  "valid_until": "..."
}

------------------------------------------------------------
VERSIONING
------------------------------------------------------------

Package version of packages/contracts:
MAJOR.MINOR.PATCH
Current package version: 1.0.0

Wire schema_version on AgentSignal and EventEnvelope:
"1.0"
This is not semver and is not 1.0.0.

Agents:
MAJOR.MINOR.PATCH

Features:
feature_version

Strategies:
strategy_version

Models:
model_version

Prompts:
prompt_version

------------------------------------------------------------
RULE
------------------------------------------------------------

If a name already exists in packages/contracts,
DO NOT create another name for the same concept.
============================================================