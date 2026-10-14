/** Provisional mock-API types. Generated conceptually from mock-api/openapi.json. */

export interface ProvisionalSystemStatus {
  status: string;
  contract_version: string;
  trading_mode: string;
  live_enabled: boolean;
  exchange_scope: string;
}

export interface ProvisionalMarketOverview {
  as_of: string;
  nifty_last: string;
  breadth_advancers: number;
  breadth_decliners: number;
  mode: string;
}

export interface ProvisionalStock {
  symbol: string;
  exchange: string;
  last_price: string;
}

export interface ProvisionalRiskStatus {
  status: string;
  as_of: string;
  message: string;
  kill_switch?: string;
}

export interface ProvisionalPerformance {
  as_of: string;
  total_pnl: string;
  sharpe_placeholder: string;
}

export interface ProvisionalAgentScore {
  agent_name: string;
  signal: number;
  confidence: number;
  horizon: string;
}
