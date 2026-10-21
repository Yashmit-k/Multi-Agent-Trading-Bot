import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EquityChart } from "@/components/dashboard/EquityChart";
import type { DailyPnlDay } from "@/lib/daily-pnl";

function day(date: string, start: number, pnl: number): DailyPnlDay & { equity_inr: number } {
  return {
    session_id: "s1",
    calendar_date_ist: date,
    snapshot_as_of: null,
    complete: true,
    pnl_basis: "net",
    net_pnl_inr: pnl,
    start_of_day_equity_inr: start,
    realized_pnl_inr: pnl,
    unrealized_change_inr: 0,
    fees_inr: 0,
    has_activity: true,
    trading_calendar_state: "open",
    source_updated_at: null,
    closed_trades: 1,
    equity_inr: start + pnl,
  } as DailyPnlDay & { equity_inr: number };
}

describe("EquityChart (real data)", () => {
  it("draws a marker per day, the start line and the latest equity", () => {
    const days = [day("2026-10-13", 1_000_000, 300), day("2026-10-14", 1_000_300, -500), day("2026-10-15", 999_800, 450)];
    render(<EquityChart mode="real" days={days} startingCash={1_000_000} />);
    expect(screen.getAllByTestId("equity-point")).toHaveLength(3);
    expect(screen.getByTestId("equity-start-line")).toBeTruthy();
    const chart = screen.getByTestId("equity-chart").textContent ?? "";
    expect(chart).toContain("Start ₹10,00,000");
    expect(chart).toContain("Latest ₹10,00,250");
    expect(chart).toContain("15 Oct");
  });

  it("says history starts later when there is only one day", () => {
    render(<EquityChart mode="real" days={[day("2026-10-13", 1_000_000, 300)]} startingCash={1_000_000} />);
    expect(screen.getByTestId("equity-graph-short").textContent).toContain("starts after the first full trading day");
    expect(screen.queryAllByTestId("equity-point")).toHaveLength(0);
  });
});
