export type Operand = {
  indicator?: string | null;
  value?: number | null;
  period?: number | null;
  period2?: number | null;
  param?: number | null;
  offset?: number;
  timeframe?: Timeframe | null;
  scale?: number;
  shift?: number;
};
export type Condition = { left: Operand; op: string; right: Operand; for_bars?: number; within_bars?: number };
export type Group = { logic: "all" | "any"; negate?: boolean; items: Array<Group | Condition> };
export type Timeframe = "5m" | "15m" | "1h" | "1d";
export type StopSpec = { kind: "none" | "percent" | "atr" | "level"; value?: number; period?: number; level?: Operand | null; buffer_pct?: number };
export type TargetSpec = { kind: "percent" | "atr" | "r_multiple"; value: number; period?: number; fraction: number };
export type TrailingSpec = { kind: "percent" | "atr"; value: number; period?: number; activate_after_r?: number };
export type EntryOrder = { type: "market" | "limit"; price?: Operand | null; valid_bars?: number };
export type Sizing = { kind: "notional" | "risk_percent"; value: number; max_notional?: number };

export type Definition = {
  name: string;
  description?: string;
  timeframe: Timeframe;
  direction: "long" | "short";
  symbols: string[];
  entry: Group;
  exit: Group | null;
  entry_order: EntryOrder;
  stop: StopSpec;
  targets: TargetSpec[];
  breakeven_after_first_target: boolean;
  trailing: TrailingSpec | null;
  max_hold_bars: number | null;
  square_off_intraday: boolean;
  last_entry_time: string | null;
  sizing: Sizing;
  max_open_positions: number;
  initial_cash: number;
  slippage_bps: number;
};

export type OperandInfo = { indicator: string; label: string; group: string; needs_period: boolean; default_period: number | null; uses_period2: boolean; uses_param: boolean };
export type Catalog = {
  operands: OperandInfo[];
  templates: Array<Record<string, unknown>>;
  universe: string[];
  limits: { max_intraday_symbols: number; max_intraday_days: number; max_5m_symbols?: number; max_5m_days?: number };
};
export type Saved = { strategy_id: string; name: string; definition: Record<string, unknown>; updated_at: string; runs?: RunSummary[] };
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
  expectancy_r: number | null;
  average_bars_held: number | null;
  exit_reasons: Record<string, number>;
};
export type RunSummary = { backtest_id: string; start: string; end: string; metrics: Metrics; created_at?: string };
export type LabLeg = { quantity: number; price: number; reason: string; at: string };
export type LabTrade = {
  symbol: string;
  direction?: string;
  entry_at: string;
  exit_at: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  reason: string;
  legs?: LabLeg[];
  charges: number;
  net_pnl: number;
  bars_held: number;
};
export type LabResult = {
  backtest_id?: string;
  start: string;
  end: string;
  rules: { entry: string | string[]; exit: string | string[] | null };
  symbols_tested: number;
  signals_considered: number;
  trades_skipped_by_portfolio: number;
  metrics: Metrics;
  halves: { split_date?: string; first_half?: { trades: number; net_pnl: number }; second_half?: { trades: number; net_pnl: number } };
  benchmark: { symbol: string; from?: string; to?: string; total_return: number; curve: Array<{ date: string; equity: number }> } | null;
  equity_curve: Array<{ date: string; equity: number }>;
  trades: LabTrade[];
  trades_listed_limit?: number;
  notes: string[];
};
export type ActiveStrategy = {
  strategy_id: string;
  name: string;
  applied_at: string | null;
  applied_by: string | null;
  timeframe: string;
  symbols: string[];
  entry: string;
  exit: string | null;
} | null;

export const OPS: Array<[string, string]> = [
  [">", "is above"],
  ["<", "is below"],
  [">=", "is at or above"],
  ["<=", "is at or below"],
  ["==", "equals"],
  ["crosses_above", "crosses above"],
  ["crosses_below", "crosses below"],
];

export const TIMEFRAMES: Array<[Timeframe, string]> = [
  ["5m", "5-minute"],
  ["15m", "15-minute"],
  ["1h", "1-hour"],
  ["1d", "Daily"],
];

export const INTRADAY: Timeframe[] = ["5m", "15m", "1h"];
const MINUTES: Record<Timeframe, number> = { "5m": 5, "15m": 15, "1h": 60, "1d": 1440 };
export const higherTimeframes = (tf: Timeframe): Timeframe[] => (Object.keys(MINUTES) as Timeframe[]).filter((item) => MINUTES[item] > MINUTES[tf]);

export const isGroup = (item: Group | Condition): item is Group => (item as Group).logic !== undefined;

export const BLANK: Definition = {
  name: "My strategy",
  description: "",
  timeframe: "1d",
  direction: "long",
  symbols: ["ALL"],
  entry: { logic: "all", items: [{ left: { indicator: "ema", period: 20 }, op: "crosses_above", right: { indicator: "ema", period: 50 } }] },
  exit: { logic: "any", items: [{ left: { indicator: "ema", period: 20 }, op: "crosses_below", right: { indicator: "ema", period: 50 } }] },
  entry_order: { type: "market", valid_bars: 5 },
  stop: { kind: "percent", value: 5, period: 14, buffer_pct: 0 },
  targets: [{ kind: "percent", value: 15, fraction: 1, period: 14 }],
  breakeven_after_first_target: false,
  trailing: null,
  max_hold_bars: null,
  square_off_intraday: false,
  last_entry_time: null,
  sizing: { kind: "notional", value: 20000, max_notional: 100000 },
  max_open_positions: 10,
  initial_cash: 500000,
  slippage_bps: 5,
};

// Accept templates, saved strategies and strategies saved before groups existed.
export function withDefaults(raw: Record<string, unknown>): Definition {
  const data = { ...raw } as Record<string, unknown>;
  if (Array.isArray(data.entry)) data.entry = { logic: "all", items: data.entry };
  if (Array.isArray(data.exit)) data.exit = data.exit.length ? { logic: "any", items: data.exit } : null;
  if (data.stop_loss_pct !== undefined && data.stop === undefined) data.stop = data.stop_loss_pct ? { kind: "percent", value: data.stop_loss_pct } : { kind: "none" };
  if (data.take_profit_pct !== undefined && data.targets === undefined) data.targets = data.take_profit_pct ? [{ kind: "percent", value: data.take_profit_pct, fraction: 1 }] : [];
  if (data.position_notional !== undefined && data.sizing === undefined) data.sizing = { kind: "notional", value: data.position_notional };
  delete data.stop_loss_pct;
  delete data.take_profit_pct;
  delete data.position_notional;
  const merged = { ...BLANK, ...data } as Definition;
  merged.stop = { ...BLANK.stop, ...(merged.stop ?? {}) };
  merged.entry_order = { ...BLANK.entry_order, ...(merged.entry_order ?? {}) };
  merged.sizing = { ...BLANK.sizing, ...(merged.sizing ?? {}) };
  merged.targets = (merged.targets ?? []).map((target) => ({ ...target, period: target.period ?? 14, fraction: target.fraction ?? 1 }));
  if (merged.exit === undefined) merged.exit = null;
  return merged;
}

// Human-readable rule text, mirroring the server's labels.
export function operandText(operand: Operand, catalog: OperandInfo[]): string {
  if (operand.value !== undefined && operand.value !== null) return String(operand.value);
  const info = catalog.find((item) => item.indicator === operand.indicator);
  const args = [operand.period, operand.period2, operand.param].filter((item) => item !== undefined && item !== null);
  let text = `${info?.label ?? operand.indicator}${args.length ? `(${args.join(", ")})` : ""}`;
  if (operand.timeframe) text = `${operand.timeframe} ${text}`;
  if (operand.offset) text += ` ${operand.offset} bars ago`;
  if (operand.scale !== undefined && operand.scale !== 1) text = `${operand.scale} × ${text}`;
  if (operand.shift) text += ` ${operand.shift > 0 ? "+" : "−"} ${Math.abs(operand.shift)}`;
  return text;
}

export function ruleText(group: Group | null, catalog: OperandInfo[]): string {
  if (!group) return "none";
  const joined = group.items
    .map((item) => {
      if (isGroup(item)) return `(${ruleText(item, catalog)})`;
      const op = OPS.find(([key]) => key === item.op)?.[1] ?? item.op;
      let text = `${operandText(item.left, catalog)} ${op} ${operandText(item.right, catalog)}`;
      if (item.for_bars && item.for_bars > 1) text += ` for ${item.for_bars} bars`;
      if (item.within_bars && item.within_bars > 1) text += ` within ${item.within_bars} bars`;
      return text;
    })
    .join(group.logic === "all" ? " AND " : " OR ");
  return group.negate ? `NOT (${joined})` : joined;
}
