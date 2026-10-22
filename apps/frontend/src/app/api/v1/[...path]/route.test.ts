import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("backtest preview rate limit", () => {
  beforeEach(() => {
    vi.resetModules();
    process.env.OPERATOR_PASSWORD = "secret";
    process.env.OPERATOR_SESSION_SECRET = "test-session-secret";
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } })));
  });
  afterEach(() => vi.unstubAllGlobals());

  async function preview(post: (request: Request, context: { params: Promise<{ path: string[] }> }) => Promise<Response>, cookie?: string, ip = "203.0.113.7") {
    const request = new Request("https://site.test/api/v1/strategies/preview/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-forwarded-for": ip, host: "site.test", ...(cookie ? { cookie } : {}) },
      body: "{}",
    });
    return post(request, { params: Promise.resolve({ path: ["strategies", "preview", "backtest"] }) });
  }

  it("limits a visitor to ten previews in ten minutes", async () => {
    const { POST } = await import("./route");
    const statuses = [];
    for (let i = 0; i < 11; i += 1) statuses.push((await preview(POST)).status);
    expect(statuses.slice(0, 10).every((status) => status === 200)).toBe(true);
    expect(statuses[10]).toBe(429);
  });

  it("never limits a signed-in operator", async () => {
    const { POST } = await import("./route");
    const { COOKIE, issueToken } = await import("@/lib/operator-session");
    const cookie = `${COOKIE}=${issueToken()}`;
    for (let i = 0; i < 15; i += 1) expect((await preview(POST, cookie, "198.51.100.9")).status).toBe(200);
  });
});
