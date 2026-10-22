import { describe, expect, it } from "vitest";
import { stepLabel, verdictLabel } from "./ManagerReviews";
import { allowOperatorWrite, allowRead } from "@/lib/proxy-policy";

describe("portfolio manager view", () => {
  it("labels verdicts, including reduce size and pending states", () => {
    expect(verdictLabel(null, "pending")).toBe("Waiting");
    expect(verdictLabel(null, "running")).toBe("Reviewing…");
    expect(verdictLabel({ verdict: "REDUCE", size_fraction: 0.5, conflicts: [], critique: "", reviewer: "m", steps: 1 }, "done")).toBe("Reduce to 50%");
    expect(verdictLabel({ verdict: "VETO", size_fraction: 0, conflicts: [], critique: "", reviewer: "m", steps: 1 }, "done")).toBe("Veto");
  });

  it("labels agent requests and critiques", () => {
    expect(stepLabel({ event: "agent.request", to_agent: "news", timestamp: "2026-10-20T04:00:00Z" })).toBe("Asks news agent");
    expect(stepLabel({ event: "review.step", kind: "critique", timestamp: "2026-10-20T04:00:00Z" })).toBe("Sent back for revision");
  });

  it("lets only a signed-in operator ask, and never exposes the manager's internal routes", () => {
    expect(allowOperatorWrite("/api/v1/reviews")).toBe(true);
    expect(allowOperatorWrite("/api/v1/internal/reviews/claim")).toBe(false);
    expect(allowRead("/api/v1/reviews/rv-1")).toBe(true);
    expect(allowRead("/api/v1/internal/tools/opinions")).toBe(false);
  });
});
