import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let path = "/momentum";
vi.mock("next/navigation", () => ({ usePathname: () => path }));

import { AppShell, isArchived } from "@/components/shell/AppShell";

describe("StockX branding", () => {
  it("shows StockX in the header and does not show FLEXI", () => {
    path = "/dashboard";
    render(
      <AppShell mode="PAPER" killSwitch="disarmed">
        <p>child</p>
      </AppShell>,
    );
    const brand = screen.getByTestId("brand-mark");
    expect(brand.textContent).toBe("StockX");
    const logo = screen.getByTestId("brand-logo");
    expect(logo.getAttribute("src")).toBe("/logo.svg");
    expect(logo.getAttribute("alt")).toBe("");
    expect(screen.getByTestId("mode-banner").textContent).toContain("PAPER TRADING");
    expect(screen.getByTestId("kill-chip").textContent).toContain("disarmed");
    expect(screen.queryByText(/flexi/i)).toBeNull();
  });
});

describe("app shell after the NIFTY 50 system was archived", () => {
  it("puts Momentum first and groups the old pages as archived", () => {
    path = "/momentum";
    render(<AppShell mode="PAPER">x</AppShell>);
    const groups = screen.getAllByText(/^(Momentum|NIFTY 50 system \(archived\)|System)$/).map((el) => el.textContent);
    expect(groups.slice(0, 3)).toEqual(["Momentum", "NIFTY 50 system (archived)", "System"]);
    expect(screen.queryByTestId("archived-note")).toBeNull();
  });

  it("shows the archived note on old pages only", () => {
    path = "/positions";
    render(<AppShell mode="PAPER">x</AppShell>);
    expect(screen.getByTestId("archived-note").textContent).toContain("Zerodha market data ended on 3 Nov 2026");
    expect(isArchived("/stocks/RELIANCE")).toBe(true);
    expect(isArchived("/momentum")).toBe(false);
    expect(isArchived("/system")).toBe(false);
  });
});
