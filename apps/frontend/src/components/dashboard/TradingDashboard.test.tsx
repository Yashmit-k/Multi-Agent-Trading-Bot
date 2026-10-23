import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EquityChart } from "@/components/dashboard/EquityChart";
import { PnlCalendar } from "@/components/dashboard/PnlCalendar";
import { TradingDashboard } from "@/components/dashboard/TradingDashboard";
import { demoDashboard } from "@/lib/demo/dashboard-fixtures";
import { visualState } from "@/lib/cell-state";
import type { DailyPnlDay } from "@/lib/daily-pnl";

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
    expect(screen.getByTestId("weekday-labels").textContent).toBe("SunMonTueWedThuFriSat");
    const rows = [...Array(7)].map((_, weekday) => screen.getByTestId(`heatmap-row-${weekday}`));
    expect(rows.length).toBe(7);
    expect(rows[0].children.length).toBe(54);
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
    expect(loader).not.toContain("current-paper");
    expect(loader).toContain('"/api/v1/paper/daily-performance"');
  });

  it("labels demo data and keeps the header minimal", () => {
    render(<TradingDashboard />);
    expect(screen.getByTestId("demo-banner").textContent).toContain("DEMO DATA");
    expect(screen.queryByTestId("demo-toggle")).toBeNull();
    expect(document.body.textContent).not.toContain("live_enabled=");
    expect(document.body.textContent).not.toContain("Last successful refresh");
    expect(screen.getByTestId("last-updated").textContent).toMatch(/Updated \d{2}:\d{2} IST/);
    expect(screen.getByTestId("session-select").textContent).not.toContain("(active) (active)");
  });

  it("shows total, today, realised and unrealised cards and a recent-trades table", () => {
    render(<TradingDashboard />);
    const cards = screen.getByTestId("kpi-row").textContent ?? "";
    for (const title of ["Total P&L", "Today’s P&L", "Realised", "Unrealised"]) expect(cards).toContain(title);
    expect(cards).not.toContain("Win rate");
    const trades = screen.getByTestId("recent-trades").textContent ?? "";
    expect(trades).toContain("INFY");
    expect(trades).toContain("BUY");
    expect(screen.queryByTestId("market-panel")).toBeNull();
    expect(screen.queryByTestId("activity-panel")).toBeNull();
  });

  it("shows an unavailable equity panel in real mode and a demo series in demo mode", () => {
    const { rerender } = render(<EquityChart mode="real" days={[]} startingCash={null} />);
    expect(screen.getByTestId("equity-graph-empty").textContent).toContain("not stored");
    rerender(<EquityChart mode="demo" days={demoDashboard().days} startingCash={1_000_000} />);
    expect(screen.queryByTestId("equity-graph-empty")).toBeNull();
    expect(screen.getByTestId("equity-chart").textContent).toContain("DEMO fixture");
    const equitySource = readFileSync("src/components/dashboard/EquityChart.tsx", "utf8");
    expect(equitySource).toContain("<svg");
    expect(equitySource).not.toContain("lightweight-charts");
    rerender(<EquityChart mode="demo" days={[]} startingCash={1_000_000} />);
    expect(screen.getByTestId("equity-demo-empty").textContent).toContain("No demo equity series");
    expect(screen.queryByRole("img", { name: "Demo cumulative equity" })).toBeNull();
  });

  it("does not mount Arm/Disarm on the dashboard", () => {
    const source = readFileSync("src/components/dashboard/TradingDashboard.tsx", "utf8");
    expect(source).not.toContain("KillSwitchControl");
    render(<TradingDashboard />);
    expect(screen.queryByRole("button", { name: "Arm" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Disarm" })).toBeNull();
    expect(screen.queryByTestId("risk-panel")).toBeNull();
  });
});

describe("calendar missing series", () => {
  const calendarProps = {
    endKey: "2026-10-10",
    selected: null as string | null,
    onSelect: () => undefined,
    pnlBasisLabel: "Net P&L",
    referenceEquity: 1_000_000,
  };

  it("hides the heatmap when the daily series is empty", () => {
    const { rerender } = render(
      <PnlCalendar
        {...calendarProps}
        days={[]}
        emptyReason="Daily paper P&L series is unavailable. Cells are missing data, not zero P&L."
      />,
    );
    expect(screen.getByTestId("pnl-empty").textContent).toContain("unavailable");
    expect(screen.queryByTestId("calendar-grid-wrap")).toBeNull();
    rerender(
      <PnlCalendar {...calendarProps} days={demoDashboard().days} emptyReason={null} />,
    );
    expect(screen.queryByTestId("pnl-empty")).toBeNull();
    expect(screen.getByTestId("calendar-grid-wrap")).toBeTruthy();
    expect(screen.getByLabelText("Trading P&L calendar")).toBeTruthy();
  });

  it("selects a calendar date on click", () => {
    const onSelect = vi.fn();
    const snap = demoDashboard();
    const key = snap.days.find((day) => day.has_activity)?.calendar_date_ist ?? snap.days[5]?.calendar_date_ist;
    render(
      <PnlCalendar
        {...calendarProps}
        days={snap.days}
        emptyReason={null}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByTestId(`cell-${key}`));
    expect(onSelect).toHaveBeenCalledWith(key);
  });

  it("shows signed P&L on hover for a profit or loss day", () => {
    const snap = demoDashboard();
    const day = snap.days.find((item) => {
      const kind = visualState(item).kind;
      return (kind === "profit" || kind === "loss") && item.net_pnl_inr != null;
    });
    expect(day).toBeTruthy();
    render(<PnlCalendar {...calendarProps} days={snap.days} emptyReason={null} />);
    fireEvent.mouseEnter(screen.getByTestId(`cell-${day!.calendar_date_ist}`));
    const tip = screen.getByTestId("cell-tooltip");
    expect(tip.textContent).toContain(day!.calendar_date_ist.slice(0, 4));
    expect(tip.textContent).toMatch(/Daily Net P&L/);
    expect(tip.textContent).not.toMatch(/Daily Net P&L ₹0\.00/);
    fireEvent.focus(screen.getByTestId(`cell-${day!.calendar_date_ist}`));
    expect(screen.getByTestId("cell-tooltip")).toBeTruthy();
  });

  it("does not treat missing days as zero P&L in the tooltip", () => {
    const snap = demoDashboard();
    const missing = snap.days.find((item) => visualState(item).kind === "missing");
    expect(missing).toBeTruthy();
    render(<PnlCalendar {...calendarProps} days={snap.days} emptyReason={null} />);
    fireEvent.mouseEnter(screen.getByTestId(`cell-${missing!.calendar_date_ist}`));
    const tip = screen.getByTestId("cell-tooltip");
    expect(tip.textContent).toContain("Daily P&L data unavailable.");
    expect(tip.textContent).toContain("No data");
    expect(tip.textContent).not.toContain("Daily Net P&L");
    expect(tip.textContent).not.toContain("₹0.00");
  });
});


describe("today's P&L card", () => {
  it("shows the running figure during the session, labelled provisional", async () => {
    const snap = demoDashboard();
    const key = snap.trading_date_ist!;
    const day: DailyPnlDay = { ...(snap.days.find((item) => item.calendar_date_ist === key) ?? snap.days[snap.days.length - 1]), calendar_date_ist: key, complete: false, net_pnl_inr: 1234.5, has_activity: true, trading_calendar_state: "open", pnl_basis: "net_equity" };
    const { SummaryCardsForTest } = await import("@/components/dashboard/TradingDashboard");
    render(<SummaryCardsForTest snapshot={{ ...snap, days: [day] }} endKey={key} />);
    expect(screen.getByTestId("kpi-row").textContent).toContain("1,234.50");
    expect(screen.getByTestId("today-label").textContent).toBe("so far today · provisional");
  });
});
