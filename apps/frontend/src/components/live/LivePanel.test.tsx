import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LivePanel } from "@/components/live/LivePanel";

function mockFetch(operator: boolean) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      const body: Record<string, unknown> = {
        "/api/auth/status": { operator, login_enabled: true },
        "/api/v1/live/settings": { settings: { amount: 0, stocks: 10, mode: "off", max_order: 25000 }, modes: ["off", "dry_run"], updated_at: null, changes: [] },
        "/api/v1/zerodha/status": { configured: true, authenticated: false },
        "/api/v1/live/plan": {
          mode: "dry_run", decided_at_close: "2026-11-30", trade_at_open_of: "2026-12-01", assumed_account: true, book: 100000, per_stock: 10000,
          orders: [{ side: "BUY", symbol: "AAA", quantity: 99, close: 100, limit: 101.5, value: 10048.5, blocked: null }], warnings: [], totals: { buy: 10048.5, sell: 0, charges: 12 },
        },
      };
      return new Response(JSON.stringify(body[url] ?? {}), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("settings for momentum live", () => {
  it("shows visitors only the sign-in and never asks for the private settings", async () => {
    const calls = mockFetch(false);
    render(<LivePanel />);
    expect(await screen.findByText(/only for the owner/)).toBeTruthy();
    expect(calls).not.toContain("/api/v1/live/settings");
  });

  it("shows the operator the settings, with live mode not offered yet, and the Zerodha login", async () => {
    mockFetch(true);
    render(<LivePanel />);
    await waitFor(() => expect(screen.getByLabelText("Number of stocks")).toBeTruthy());
    expect((screen.getByLabelText("Number of stocks") as HTMLInputElement).value).toBe("10");
    const modes = Array.from((screen.getByLabelText("Mode") as HTMLSelectElement).options).map((o) => o.value);
    expect(modes).toEqual(["off", "dry_run"]);
    expect((await screen.findByText("Log in to Zerodha")).getAttribute("href")).toBe("/api/zerodha/login");
  });

  it("shows this month's dry-run orders and says nothing is sent", async () => {
    mockFetch(true);
    render(<LivePanel />);
    expect(await screen.findByText("AAA")).toBeTruthy();
    expect(screen.getByText(/Dry run: nothing is sent to Zerodha/)).toBeTruthy();
    expect(screen.getByText(/assumes an empty account/)).toBeTruthy();
  });
});
