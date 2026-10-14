import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EquityChart } from "@/components/dashboard/EquityChart";
import { PnlCalendar } from "@/components/dashboard/PnlCalendar";
import { TradingDashboard } from "@/components/dashboard/TradingDashboard";
import { demoDashboard } from "@/lib/demo/dashboard-fixtures";
import { visualState } from "@/lib/cell-state";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams("demo=1"),
}));

describe("demo fixtures", () => {
  it("never uses Core and includes all six cell states", () => {
    const snap = demoDashboard();
    expect(snap.mode).toBe("demo");
    expect(snap.daily_endpoint).toBe("demo_fixture");
    const kinds = new Set(snap.days.map((day) => visualState(day).kind));
    expect(kinds.has("profit")).toBe(true);
    expect(kinds.has("loss")).toBe(true);
    expect(kinds.has("zero") || kinds.has("no_activity")).toBe(true);
    expect(kinds.has("market_closed")).toBe(true);
    expect(kinds.has("missing")).toBe(true);
    expect(kinds.has("no_activity")).toBe(true);
  });
});

describe("PnlCalendar geometry", () => {
  it("renders a wide grid with 53 week columns", () => {
    const snap = demoDashboard();
    const { container } = render(
      <PnlCalendar
        endKey={snap.trading_date_ist!}
        days={snap.days}
        selected={null}
        onSelect={() => undefined}
        pnlBasisLabel="Net P&L"
        emptyReason={null}
        referenceEquity={1_000_000}
      />,
    );
    const wrap = screen.getByTestId("calendar-grid-wrap");
    const weeks = wrap.querySelectorAll('[role="row"]');
    expect(weeks.length).toBe(53);
    const cell = container.querySelector("[data-date]") as HTMLElement;
    expect(cell.className).toContain("aspect-square");
    if (wrap.scrollWidth > 0 && wrap.clientHeight > 0) {
      expect(wrap.scrollWidth / wrap.clientHeight).toBeGreaterThanOrEqual(5);
    }
  });

  it("keeps a single tab stop until arrows move", () => {
    const snap = demoDashboard();
    render(
      <PnlCalendar
        endKey={snap.trading_date_ist!}
        days={snap.days}
        selected={null}
        onSelect={() => undefined}
        pnlBasisLabel="Net P&L"
        emptyReason={null}
        referenceEquity={1_000_000}
      />,
    );
    const cells = [...document.querySelectorAll("[data-date]")];
    const tabbable = cells.filter((node) => (node as HTMLElement).tabIndex === 0);
    expect(tabbable.length).toBe(1);
    fireEvent.keyDown(tabbable[0], { key: "ArrowLeft" });
  });
});

describe("dashboard isolation", () => {
  it("keeps four desktop KPI columns and never fetches backtest as paper P&L", () => {
    const source = readFileSync("src/components/dashboard/TradingDashboard.tsx", "utf8");
    expect(source).toContain("lg:grid-cols-4");
    expect(source).not.toContain('"/api/v1/performance"');
    const loader = readFileSync("src/lib/load-real-dashboard.ts", "utf8");
    expect(loader).not.toContain("demoDashboard");
    expect(loader).toContain('"/api/v1/paper/daily-performance"');
  });

  it("labels demo data and uses a working demo checkbox", () => {
    render(<TradingDashboard />);
    expect(screen.getByTestId("demo-banner").textContent).toContain("DEMO DATA");
    const toggle = screen.getByTestId("demo-toggle");
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    expect(toggle.getAttribute("role")).toBe("switch");
  });

  it("shows an unavailable equity panel in real mode and a demo series in demo mode", () => {
    const { rerender } = render(<EquityChart mode="real" days={[]} startingCash={null} />);
    expect(screen.getByTestId("equity-graph-empty").textContent).toContain("not stored");
    rerender(<EquityChart mode="demo" days={demoDashboard().days} startingCash={1_000_000} />);
    expect(screen.queryByTestId("equity-graph-empty")).toBeNull();
    expect(screen.getByTestId("equity-chart").textContent).toContain("DEMO fixture");
  });
});
