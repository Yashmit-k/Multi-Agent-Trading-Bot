import { describe, expect, it } from "vitest";
import { globalView, moodLabel, signedPct } from "@/lib/global-markets";

describe("global markets view", () => {
  it("reads the expected open from the agent's metadata", () => {
    const view = globalView({
      agent_name: "global_markets",
      metadata: {
        session_date: "2026-10-27",
        slot_ist: "09:10",
        expected_gap_pct: -0.31,
        expected_gap_range_pct: [-0.89, 0.27],
        risk_off: true,
        fit: { correlation: 0.52 },
        inputs: { sp500: { symbol: "^GSPC", move_pct: -0.8, z: -1.1 }, asia: { symbol: "^N225+^KS11+^HSI", move_pct: -0.6, z: -1.4 } },
      },
    });
    expect(view?.expectedGapPct).toBe(-0.31);
    expect(view?.inputs.map((item) => item.name)).toEqual(["asia", "sp500"]);
    expect(view && moodLabel(view)).toBe("risk-off night");
    expect(signedPct(-0.31)).toBe("−0.31%");
  });

  it("ignores other agents and incomplete metadata", () => {
    expect(globalView({ agent_name: "regime", metadata: {} })).toBeNull();
    expect(globalView({ agent_name: "global_markets", metadata: { session_date: "2026-10-27" } })).toBeNull();
  });
});
