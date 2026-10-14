import { fetchApi } from "@/lib/api";

export type SignalRow = {
  signal_id: string;
  agent_name: string;
  symbol: string;
  horizon: string;
  signal: number;
  confidence: number;
  timestamp: string;
  valid_until?: string;
  reason_codes?: string[];
  metadata?: Record<string, unknown>;
};

export async function loadSignals(params: { limit?: number; symbol?: string; agent?: string } = {}): Promise<SignalRow[]> {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 300));
  if (params.symbol) query.set("symbol", params.symbol);
  if (params.agent) query.set("agent", params.agent);
  return fetchApi<SignalRow[]>(`/api/v1/signals?${query.toString()}`);
}

// Newest signal per (agent, horizon); input is newest first.
export function latestPerAgent(rows: SignalRow[]): SignalRow[] {
  const seen = new Map<string, SignalRow>();
  for (const row of rows) {
    const key = `${row.agent_name}|${row.horizon}`;
    if (!seen.has(key)) seen.set(key, row);
  }
  return [...seen.values()].sort((a, b) => a.agent_name.localeCompare(b.agent_name) || a.horizon.localeCompare(b.horizon));
}
