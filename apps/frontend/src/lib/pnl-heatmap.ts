/**
 * Fixed symmetric daily P&L intensity vs start-of-day equity.
 * Fractions, not whole percents. Do not recompute as quantiles.
 */
export const PNL_HEATMAP_THRESHOLDS = [
  0.001, // 0.10%
  0.0025, // 0.25%
  0.005, // 0.50%
  0.01, // 1.00%
] as const;

export type HeatLevel = 1 | 2 | 3 | 4 | 5;

export type CellVisualState =
  | { kind: "profit"; level: HeatLevel }
  | { kind: "loss"; level: HeatLevel }
  | { kind: "zero" }
  | { kind: "no_activity" }
  | { kind: "market_closed" }
  | { kind: "missing" };

export function heatmapLevel(absFraction: number): HeatLevel {
  if (absFraction >= PNL_HEATMAP_THRESHOLDS[3]) return 5;
  if (absFraction >= PNL_HEATMAP_THRESHOLDS[2]) return 4;
  if (absFraction >= PNL_HEATMAP_THRESHOLDS[1]) return 3;
  if (absFraction >= PNL_HEATMAP_THRESHOLDS[0]) return 2;
  return 1;
}

export function inrForThreshold(equity: number, fraction: number): number {
  return equity * fraction;
}

export function signedPnlLevel(
  netPnl: number,
  startOfDayEquity: number | null,
): { kind: "profit" | "loss" | "zero" | "missing"; level?: HeatLevel } {
  if (netPnl === 0) return { kind: "zero" };
  if (startOfDayEquity === null || !(startOfDayEquity > 0) || !Number.isFinite(startOfDayEquity)) {
    return { kind: "missing" };
  }
  const fraction = Math.abs(netPnl) / startOfDayEquity;
  const level = heatmapLevel(fraction);
  return { kind: netPnl > 0 ? "profit" : "loss", level };
}
