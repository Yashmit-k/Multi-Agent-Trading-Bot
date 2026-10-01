import { describe, expect, it } from "vitest";
import { apiUrl } from "@/lib/api";

describe("apiUrl", () => {
  it("rejects non v1 paths", () => {
    expect(() => apiUrl("/redis")).toThrow();
  });
  it("accepts /api/v1", () => {
    expect(apiUrl("/api/v1/signals")).toContain("/api/v1/signals");
  });
});
