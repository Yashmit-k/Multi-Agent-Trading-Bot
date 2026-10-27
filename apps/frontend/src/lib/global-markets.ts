// The global-markets agent's view (quant_agents/global_markets.py), read from its signal metadata. Observe-only.

export type GlobalInput = { symbol: string; move_pct: number; z: number };
export type GlobalView = {
  sessionDate: string;
  slot: string;
  expectedGapPct: number;
  rangePct: [number, number];
  riskOff: boolean;
  riskOn: boolean;
  correlation: number;
  inputs: Array<{ name: string } & GlobalInput>;
};

export const INPUT_LABEL: Record<string, string> = {
  asia: "Asia open (Nikkei, Kospi, Hang Seng)",
  sp500: "S&P 500",
  nasdaq: "Nasdaq",
  vix: "US VIX",
  brent: "Brent crude",
  usdinr: "USD/INR",
  dollar: "Dollar index",
  us10y: "US 10-year yield",
};

export function globalView(signal: { agent_name?: string; metadata?: Record<string, unknown> } | undefined | null): GlobalView | null {
  if (!signal || signal.agent_name !== "global_markets") return null;
  const m = signal.metadata ?? {};
  const range = m.expected_gap_range_pct;
  const inputs = (m.inputs ?? {}) as Record<string, GlobalInput>;
  if (typeof m.expected_gap_pct !== "number" || !Array.isArray(range) || typeof m.session_date !== "string") return null;
  return {
    sessionDate: m.session_date,
    slot: typeof m.slot_ist === "string" ? m.slot_ist : "",
    expectedGapPct: m.expected_gap_pct,
    rangePct: [Number(range[0]), Number(range[1])],
    riskOff: m.risk_off === true,
    riskOn: m.risk_on === true,
    correlation: Number((m.fit as Record<string, unknown> | undefined)?.correlation ?? 0),
    inputs: Object.keys(INPUT_LABEL)
      .filter((name) => inputs[name])
      .map((name) => ({ name, ...inputs[name] })),
  };
}

export const signedPct = (value: number, digits = 2) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(digits)}%`;

export function moodLabel(view: GlobalView): string {
  return view.riskOff ? "risk-off night" : view.riskOn ? "risk-on night" : "ordinary night";
}
