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
});
