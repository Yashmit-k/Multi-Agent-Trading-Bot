import { describe, expect, it } from "vitest";
import { ROLE } from "@/lib/specialist-roles";

describe("specialist roles", () => {
  it("gives every live agent a role line that names its job", () => {
    const agents = ["technical", "momentum", "volume", "mean_reversion", "news", "earnings", "fundamental", "valuation", "regime"];
    for (const agent of agents) expect(ROLE[agent]).toBeTruthy();
    expect(ROLE.technical).toMatch(/^Trigger/);
    expect(ROLE.regime).toMatch(/never blocks/);
    expect(ROLE.news).toMatch(/fallback/);
  });
});
