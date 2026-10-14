import { describe, expect, it } from "vitest";
import { describe as describeEvent, laneOf, type TraceEvent } from "@/components/trace/AgentTrace";

function event(overrides: Partial<TraceEvent>): TraceEvent {
  return {
    event_id: "e1",
    event_type: "agent.signal",
    recorded_at: "2026-10-14T04:00:00Z",
    timestamp: "2026-10-14T04:00:00Z",
    channel: "agent.events",
    source: "signal-ingestion",
    agent: "momentum",
    symbol: "RELIANCE",
    correlation_id: "sig-1",
    payload: { horizon: "SWING", signal: 0.5, confidence: 0.8 },
    ...overrides,
  };
}

describe("trace lanes", () => {
  it("puts signals in their agent lane", () => {
    expect(laneOf(event({}))).toBe("momentum");
  });

  it("groups core stages", () => {
    expect(laneOf(event({ event_type: "decision.created", agent: null }))).toBe("decision.created");
    expect(laneOf(event({ event_type: "risk.rejected", agent: null }))).toBe("risk");
    expect(laneOf(event({ event_type: "order.filled", agent: null }))).toBe("order");
  });

  it("names failed risk checks", () => {
    const text = describeEvent(
      event({
        event_type: "risk.rejected",
        payload: { status: "REJECTED", checks: [{ name: "notional_cap", passed: false }, { name: "no_short", passed: true }] },
      }),
    );
    expect(text).toContain("notional_cap");
  });
});
