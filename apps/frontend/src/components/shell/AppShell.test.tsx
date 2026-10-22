import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/shell/AppShell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

describe("StockX branding", () => {
  it("shows StockX in the header and does not show FLEXI", () => {
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
