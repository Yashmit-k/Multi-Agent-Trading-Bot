/** Typed adapter for the proposed daily P&L contract. Core does not publish this yet. */

export type PnlBasis = "net_equity" | "realized_only" | "unavailable";

export type TradingCalendarState = "open" | "closed" | "unknown";

export type DailyPnlDay = {
  session_id: string;
  calendar_date_ist: string;
  snapshot_as_of: string | null;
  complete: boolean;
  pnl_basis: PnlBasis;
  net_pnl_inr: number | null;
  start_of_day_equity_inr: number | null;
  realized_pnl_inr: number | null;
  unrealized_change_inr: number | null;
  fees_inr: number | null;
  has_activity: boolean | null;
  trading_calendar_state: TradingCalendarState;
  source_updated_at: string | null;
  closed_trades: number | null;
};

export type PaperSession = {
  session_id: string;
  label: string;
  status: "active" | "closed" | "unknown";
  starting_cash_inr: number | null;
  source: string;
};

export type DashboardSnapshot = {
  mode: "real" | "demo";
  trading_date_ist: string | null;
  trading_date_source: string;
  sessions: PaperSession[];
  selected_session_id: string;
  pnl_basis: PnlBasis;
  days: DailyPnlDay[];
  portfolio: {
    equity: number | null;
    cash: number | null;
    total_pnl: number | null;
    realized_pnl: number | null;
    unrealized_pnl: number | null;
    gross_exposure: number | null;
    drawdown: number | null;
    as_of: string | null;
  };
  win_rate: { pct: number | null; sample: number | null; definition: string };
  positions: Array<Record<string, unknown>>;
  orders: Array<Record<string, unknown>>;
  trades: Array<Record<string, unknown>>;
  status: {
    core: string;
    trading_mode: string;
    live_enabled: boolean | null;
    paper_running: boolean | null;
    kill_switch: string | null;
    zerodha_authenticated: boolean | null;
    zerodha_configured: boolean | null;
    worker: string;
    market_as_of: string | null;
    last_refresh: string;
  };
  daily_endpoint: "missing" | "unavailable" | "demo_fixture";
  contract_note: string;
};
