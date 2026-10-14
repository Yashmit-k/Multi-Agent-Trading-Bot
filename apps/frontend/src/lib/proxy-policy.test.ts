import { describe, expect, it } from "vitest";
import { allowRead, allowWrite } from "@/lib/proxy-policy";

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
});
