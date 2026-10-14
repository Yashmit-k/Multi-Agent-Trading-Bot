import type { DailyPnlDay } from "@/lib/daily-pnl";
import { signedPnlLevel, type CellVisualState, type HeatLevel } from "@/lib/pnl-heatmap";

export function visualState(day: DailyPnlDay | undefined): CellVisualState {
  if (!day) return { kind: "missing" };
  if (day.trading_calendar_state === "closed") return { kind: "market_closed" };
  if (!day.complete || day.pnl_basis === "unavailable") return { kind: "missing" };
  if (day.has_activity === false) return { kind: "no_activity" };
  if (day.net_pnl_inr === null) return { kind: "missing" };
  const signed = signedPnlLevel(day.net_pnl_inr, day.start_of_day_equity_inr);
  if (signed.kind === "missing") return { kind: "missing" };
  if (signed.kind === "zero") return { kind: "zero" };
  return { kind: signed.kind, level: signed.level as HeatLevel };
}

export function stateLabel(state: CellVisualState, dateKey: string): string {
  switch (state.kind) {
    case "profit":
      return `${dateKey} profitable, intensity ${state.level}`;
    case "loss":
      return `${dateKey} loss, intensity ${state.level}`;
    case "zero":
      return `${dateKey} trading day, zero P&L`;
    case "no_activity":
      return `${dateKey} market open, no recorded activity`;
    case "market_closed":
      return `${dateKey} market closed`;
    default:
      return `${dateKey} missing or incomplete data`;
  }
}

export const CELL_CLASS: Record<string, string> = {
  "profit-1": "bg-[#0e4429]",
  "profit-2": "bg-[#006d32]",
  "profit-3": "bg-[#26a641]",
  "profit-4": "bg-[#39d353]",
  "profit-5": "bg-[#56f06a]",
  "loss-1": "bg-[#4a1515]",
  "loss-2": "bg-[#7f1d1d]",
  "loss-3": "bg-[#b91c1c]",
  "loss-4": "bg-[#ef4444]",
  "loss-5": "bg-[#f87171]",
  zero: "bg-[#3d4a5c]",
  no_activity: "bg-[#202833]",
  market_closed: "bg-[#161b22] bg-[repeating-linear-gradient(45deg,transparent,transparent_3px,#26303C_3px,#26303C_4px)]",
  missing: "bg-[#121922] ring-1 ring-inset ring-[#7c6f4a]",
};

export function cellClass(state: CellVisualState): string {
  if (state.kind === "profit" || state.kind === "loss") return CELL_CLASS[`${state.kind}-${state.level}`];
  return CELL_CLASS[state.kind];
}
