import { describe, expect, it } from "vitest";
import { applyDailyPerformance, type DailyPerformanceResponse } from "@/lib/load-real-dashboard";
import type { DashboardSnapshot } from "@/lib/daily-pnl";

function stub(): DashboardSnapshot {
  return {
    mode: "real",
    trading_date_ist: "2026-10-10",
    trading_date_source: "test",
    sessions: [],
    selected_session_id: "",
    pnl_basis: "unavailable",
    days: [{ session_id: "x", calendar_date_ist: "2026-10-10", snapshot_as_of: null, complete: true, pnl_basis: "net_equity", net_pnl_inr: 99, start_of_day_equity_inr: 1, realized_pnl_inr: 99, unrealized_change_inr: 0, fees_inr: 0, has_activity: true, trading_calendar_state: "open", source_updated_at: null, closed_trades: 1 }],
    portfolio: { equity: null, cash: null, total_pnl: null, realized_pnl: null, unrealized_pnl: null, gross_exposure: null, drawdown: null, as_of: null },
    win_rate: { pct: null, sample: null, definition: "test" },
    positions: [],
    orders: [],
    trades: [],
    status: {
      core: "ok",
      trading_mode: "PAPER",
      live_enabled: false,
      paper_running: null,
      kill_switch: null,
      zerodha_authenticated: null,
      zerodha_configured: null,
      worker: "n/a",
      market_as_of: null,
      last_refresh: "2026-10-10T00:00:00Z",
    },
    daily_endpoint: "missing",
    contract_note: "test",
  };
}

describe("applyDailyPerformance", () => {
  it("maps Core unavailable to empty days, not fabricated P&L", () => {
    const next = applyDailyPerformance(stub(), {
      ok: true,
      value: { status: "unavailable", reason: "no_daily_equity_history" } satisfies DailyPerformanceResponse,
    });
    expect(next.daily_endpoint).toBe("unavailable");
    expect(next.days).toEqual([]);
    expect(next.days.some((day) => day.net_pnl_inr === 0)).toBe(false);
  });

  it("keeps missing when the GET fails", () => {
    const next = applyDailyPerformance(stub(), { ok: false, error: "not_implemented" });
    expect(next.daily_endpoint).toBe("missing");
    expect(next.days).toEqual([]);
  });
});
