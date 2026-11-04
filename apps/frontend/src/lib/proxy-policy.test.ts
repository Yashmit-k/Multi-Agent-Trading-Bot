import { describe, expect, it } from "vitest";
import { allowOperatorWrite, allowRead, allowWrite, operatorOnlyRead } from "@/lib/proxy-policy";

describe("public proxy policy", () => {
  it("allows dashboard reads", () => {
    expect(allowRead("/api/v1/trace")).toBe(true);
    expect(allowRead("/api/v1/paper/status")).toBe(true);
  });

  it("blocks internal and broker login routes", () => {
    expect(allowRead("/api/v1/internal/signals")).toBe(false);
    expect(allowRead("/api/v1/zerodha/connect")).toBe(false);
  });

  it("refuses writes by default", () => {
    expect(allowWrite("/api/v1/paper/start", undefined)).toBe(false);
    expect(allowWrite("/api/v1/risk/kill-switch", "")).toBe(false);
  });

  it("allows only listed writes and never internal ones", () => {
    expect(allowWrite("/api/v1/risk/kill-switch", "/api/v1/risk/kill-switch")).toBe(true);
    expect(allowWrite("/api/v1/paper/start", "/api/v1/risk/kill-switch")).toBe(false);
    expect(allowWrite("/api/v1/internal/signals", "/api/v1/internal/signals")).toBe(false);
  });

  it("keeps the live account and settings to the signed-in operator", () => {
    expect(operatorOnlyRead("/api/v1/live/account")).toBe(true);
    expect(operatorOnlyRead("/api/v1/live/settings")).toBe(true);
    expect(operatorOnlyRead("/api/v1/momentum-trial")).toBe(false);
    expect(allowOperatorWrite("/api/v1/live/settings")).toBe(true);
    expect(allowOperatorWrite("/api/v1/live/account")).toBe(false);
  });
});
