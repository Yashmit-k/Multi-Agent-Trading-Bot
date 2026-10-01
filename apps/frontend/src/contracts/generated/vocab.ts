/* generated — do not edit */
export const SCHEMA_VERSION = "1.0" as const;
export const EVENT_TYPES = [
  "agent.heartbeat",
  "agent.signal",
  "decision.created",
  "feature.updated",
  "fundamental.updated",
  "market.candle",
  "market.tick",
  "news.article",
  "news.signal",
  "order.created",
  "order.filled",
  "order.rejected",
  "order.updated",
  "portfolio.updated",
  "position.updated",
  "risk.approved",
  "risk.rejected",
  "system.alert"
] as const;
export type EventType = (typeof EVENT_TYPES)[number];
export const STREAM_EVENT_TYPES = [
  "market.tick",
  "market.candle",
  "feature.updated",
  "agent.signal",
  "news.article",
  "news.signal",
  "decision.created",
  "risk.approved",
  "risk.rejected",
  "order.updated",
  "order.filled",
  "position.updated",
  "portfolio.updated",
  "system.alert",
] as const;
export const TRADING_MODES = ["BACKTEST", "PAPER", "SHADOW", "LIVE"] as const;
export type TradingMode = (typeof TRADING_MODES)[number];
export const HORIZONS = ["INTRADAY", "SWING", "LONG_TERM"] as const;
export const FUNDAMENTAL_AGENTS = ["fundamental", "valuation", "earnings"] as const;
export const DISCRIMINATOR_MAPPING = {
  "agent.heartbeat": "#/$defs/AgentHeartbeatEnvelope",
  "agent.signal": "#/$defs/AgentSignalEnvelope",
  "decision.created": "#/$defs/DecisionCreatedEnvelope",
  "feature.updated": "#/$defs/FeatureUpdatedEnvelope",
  "fundamental.updated": "#/$defs/FundamentalUpdatedEnvelope",
  "market.candle": "#/$defs/MarketCandleEnvelope",
  "market.tick": "#/$defs/MarketTickEnvelope",
  "news.article": "#/$defs/NewsArticleEnvelope",
  "news.signal": "#/$defs/NewsSignalEnvelope",
  "order.created": "#/$defs/OrderCreatedEnvelope",
  "order.filled": "#/$defs/OrderFilledEnvelope",
  "order.rejected": "#/$defs/OrderRejectedEnvelope",
  "order.updated": "#/$defs/OrderUpdatedEnvelope",
  "portfolio.updated": "#/$defs/PortfolioUpdatedEnvelope",
  "position.updated": "#/$defs/PositionUpdatedEnvelope",
  "risk.approved": "#/$defs/RiskApprovedEnvelope",
  "risk.rejected": "#/$defs/RiskRejectedEnvelope",
  "system.alert": "#/$defs/SystemAlertEnvelope"
} as const;
