import { beforeEach, describe, expect, it, vi } from "vitest";
import { applyDailyPerformance, loadRealDashboard, type DailyPerformanceResponse } from "@/lib/load-real-dashboard";
import type { DashboardSnapshot } from "@/lib/daily-pnl";
import { demoDashboard } from "@/lib/demo/dashboard-fixtures";
import { fetchApi } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  fetchApi: vi.fn(),
}));

const ACTIVE_SESSION_ID = "c6c7f91fe84f4d48862c4a1b85646f3b";

function paperStatus(sessionId: string | null) {
  return {
    running: true,
    trading_mode: "PAPER",
    starting_cash: "1000000",
    kill_switch: "disarmed",
    session_id: sessionId,
    session_status: "active",
    live_enabled: false,
  };
}

function mockReads(paper: Record<string, unknown> | Error) {
  vi.mocked(fetchApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/paper/status") {
      if (paper instanceof Error) throw paper;
      return paper;
    }
    if (path === "/api/v1/paper/daily-performance") {
      return { status: "unavailable", reason: "no_daily_equity_history" };
    }
    if (path === "/api/v1/positions" || path === "/api/v1/orders" || path === "/api/v1/trades") {
      return [];
    }
    if (path === "/api/v1/system/status") {
      return { status: "ok", trading_mode: "PAPER", live_enabled: false };
    }
    throw new Error("api_503");
  });
}

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

describe("loadRealDashboard session id", () => {
  beforeEach(() => {
    vi.mocked(fetchApi).mockReset();
  });

  it("uses the active paper session id from GET /api/v1/paper/status", async () => {
    mockReads(paperStatus(ACTIVE_SESSION_ID));
    const snapshot = await loadRealDashboard();
    expect(snapshot.mode).toBe("real");
    expect(snapshot.sessions[0]?.session_id).toBe(ACTIVE_SESSION_ID);
    expect(snapshot.selected_session_id).toBe(ACTIVE_SESSION_ID);
    expect(snapshot.selected_session_id).not.toBe("current-paper");
    expect(snapshot.daily_endpoint).toBe("unavailable");
    expect(snapshot.days).toEqual([]);
    const demoIds = demoDashboard().sessions.map((session) => session.session_id);
    expect(demoIds).not.toContain(snapshot.selected_session_id);
    expect(demoDashboard().mode).toBe("demo");
  });

  it("leaves the session empty when paper status has no session id", async () => {
    mockReads(paperStatus(null));
    const snapshot = await loadRealDashboard();
    expect(snapshot.sessions).toEqual([]);
    expect(snapshot.selected_session_id).toBe("");
    expect(snapshot.mode).toBe("real");
  });

  it("leaves the session empty when paper status fails", async () => {
    mockReads(new Error("api_503"));
    const snapshot = await loadRealDashboard();
    expect(snapshot.sessions).toEqual([]);
    expect(snapshot.selected_session_id).toBe("");
    expect(snapshot.status.core).toBe("ok");
    expect(snapshot.daily_endpoint).toBe("unavailable");
  });
});

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
