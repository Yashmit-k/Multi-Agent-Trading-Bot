import { afterEach, describe, expect, it, vi } from "vitest";
import { apiUrl, postApi } from "@/lib/api";

describe("apiUrl", () => {
  it("rejects non v1 paths", () => {
    expect(() => apiUrl("/redis")).toThrow();
  });
  it("accepts /api/v1", () => {
    expect(apiUrl("/api/v1/signals")).toContain("/api/v1/signals");
  });
});

describe("postApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("rejects non v1 paths", async () => {
    await expect(postApi("/redis", { armed: true })).rejects.toThrow(/refusing non-versioned/);
  });

  it("POSTs JSON to a v1 path", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ kill_switch: "armed" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(postApi("/api/v1/risk/kill-switch", { armed: true })).resolves.toEqual({ kill_switch: "armed" });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/risk/kill-switch"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ armed: true }),
      }),
    );
  });
});
