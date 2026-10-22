import { describe, expect, it } from "vitest";
import { latestPerAgent, type SignalRow } from "@/lib/signals";

const row = (agent: string, horizon: string, ts: string, signal = 0): SignalRow => ({
  signal_id: `${agent}-${ts}`, agent_name: agent, symbol: "INFY", horizon, signal, confidence: 0.5, timestamp: ts,
});

describe("latestPerAgent", () => {
  it("keeps the first (newest) row per agent and horizon", () => {
    const rows = [row("news", "SWING", "2026-10-15T02:00:00Z", 0.3), row("news", "SWING", "2026-10-14T02:00:00Z", -1), row("momentum", "SWING", "2026-10-14T10:00:00Z")];
    const latest = latestPerAgent(rows);
    expect(latest).toHaveLength(2);
    expect(latest.find((item) => item.agent_name === "news")?.signal).toBe(0.3);
  });
});
