import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let path = "/momentum";
vi.mock("next/navigation", () => ({ usePathname: () => path }));

import { AppShell } from "@/components/shell/AppShell";

describe("StockX branding", () => {
  it("shows StockX in the header and does not show FLEXI", () => {
    path = "/momentum";
    render(
      <AppShell mode="PAPER">
        <p>child</p>
      </AppShell>,
    );
    const brand = screen.getByTestId("brand-mark");
    expect(brand.textContent).toBe("StockX");
    const logo = screen.getByTestId("brand-logo");
    expect(logo.getAttribute("src")).toBe("/logo.svg");
    expect(logo.getAttribute("alt")).toBe("");
    expect(screen.getByTestId("mode-banner").textContent).toContain("Paper only");
    expect(screen.queryByText(/flexi/i)).toBeNull();
  });
});

describe("app shell after the NIFTY 50 system was removed", () => {
  it("lists only the Momentum and System groups", () => {
    path = "/momentum";
    render(<AppShell mode="PAPER">x</AppShell>);
    expect(screen.queryByText("NIFTY 50 system (archived)")).toBeNull();
    expect(screen.queryByText("Overview")).toBeNull();
    expect(screen.getAllByText("Momentum trial").length).toBeGreaterThan(0);
  });
});
