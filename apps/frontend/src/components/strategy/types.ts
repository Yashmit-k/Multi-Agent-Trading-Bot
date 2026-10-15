export type Operand = { indicator?: string | null; period?: number | null; value?: number | null };
export type Condition = { left: Operand; op: string; right: Operand };
export type Definition = {
  name: string;
  description?: string;
  timeframe: "1d" | "5m";
  symbols: string[];
  entry: Condition[];
  exit: Condition[];
  stop_loss_pct: number | null;
  take_profit_pct: number | null;
  max_hold_bars: number | null;
  square_off_intraday: boolean;
  position_notional: number;
  max_open_positions: number;
  initial_cash: number;
  slippage_bps: number;
};
export type OperandInfo = { indicator: string; label: string; needs_period: boolean };
export type Catalog = { operands: OperandInfo[]; templates: Partial<Definition>[]; universe: string[]; limits: { max_5m_symbols: number; max_5m_days: number } };
export type Saved = { strategy_id: string; name: string; definition: Definition; updated_at: string; runs?: RunSummary[] };
export type Metrics = {
  trades: number;
  win_rate: number | null;
  net_pnl: number;
  charges: number;
  total_return: number;
  cagr: number | null;
  sharpe: number | null;
  max_drawdown: number;
  profit_factor: number | null;
  average_win: number | null;
  average_loss: number | null;
  average_bars_held: number | null;
  exit_reasons: Record<string, number>;
};
export type RunSummary = { backtest_id: string; start: string; end: string; metrics: Metrics; created_at?: string };
export type LabTrade = { symbol: string; entry_at: string; exit_at: string; entry_price: number; exit_price: number; quantity: number; reason: string; charges: number; net_pnl: number; bars_held: number };
export type LabResult = {
  backtest_id?: string;
  start: string;
  end: string;
  rules: { entry: string[]; exit: string[] };
  symbols_tested: number;
  signals_considered: number;
  trades_skipped_by_portfolio: number;
  metrics: Metrics;
  halves: { split_date?: string; first_half?: { trades: number; net_pnl: number }; second_half?: { trades: number; net_pnl: number } };
  benchmark: { symbol: string; total_return: number; curve: Array<{ date: string; equity: number }> } | null;
  equity_curve: Array<{ date: string; equity: number }>;
  trades: LabTrade[];
  trades_listed_limit?: number;
  notes: string[];
};

export const OPS: Array<[string, string]> = [
  [">", "is above"],
  ["<", "is below"],
  [">=", "is at or above"],
  ["<=", "is at or below"],
  ["crosses_above", "crosses above"],
  ["crosses_below", "crosses below"],
];

export const BLANK: Definition = {
  name: "My strategy",
  description: "",
  timeframe: "1d",
  symbols: ["ALL"],
  entry: [{ left: { indicator: "ema", period: 20 }, op: "crosses_above", right: { indicator: "ema", period: 50 } }],
  exit: [{ left: { indicator: "ema", period: 20 }, op: "crosses_below", right: { indicator: "ema", period: 50 } }],
  stop_loss_pct: 5,
  take_profit_pct: 15,
  max_hold_bars: null,
  square_off_intraday: false,
  position_notional: 20000,
  max_open_positions: 10,
  initial_cash: 500000,
  slippage_bps: 5,
};

export function withDefaults(partial: Partial<Definition>): Definition {
  return { ...BLANK, ...partial, entry: partial.entry ?? BLANK.entry, exit: partial.exit ?? [] } as Definition;
}
