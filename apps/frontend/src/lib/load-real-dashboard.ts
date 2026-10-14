import { fetchApi } from "@/lib/api";
import type { DashboardSnapshot, PaperSession, PnlBasis } from "@/lib/daily-pnl";
import { istDateKeyFromInstant } from "@/lib/ist";
import { parseDecimal } from "@/lib/money";

async function optional<T>(path: string): Promise<{ ok: true; value: T } | { ok: false; error: string }> {
  try {
    const value = await fetchApi<T>(path);
    return { ok: true, value };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "unknown" };
  }
}

export const MISSING_DAILY_PNL_CONTRACT = `Daily paper equity series is not loaded on this page (Core reports that history as unavailable). Requested read-only session daily-pnl fields: session_id, calendar_date_ist (YYYY-MM-DD IST key), snapshot_as_of, complete, pnl_basis, net_pnl_inr, start_of_day_equity_inr, realized_pnl_inr, unrealized_change_inr, fees_inr, has_activity, trading_calendar_state, source_updated_at. Latest stored backtest is not paper session P&L. Also missing: paper session-history list, market holiday calendar, backend trading_date_ist / clock, closed-trade win-rate convention.`;

export type DailyPerformanceResponse = {
  status?: string;
  reason?: string;
};

export function applyDailyPerformance(
  snapshot: DashboardSnapshot,
  result: { ok: true; value: DailyPerformanceResponse } | { ok: false; error: string },
): DashboardSnapshot {
  if (!result.ok) {
    return { ...snapshot, daily_endpoint: "missing", days: [] };
  }
  const status = result.value?.status;
  if (status === "unavailable" || typeof status !== "string" || status !== "available") {
    const reason = typeof result.value?.reason === "string" ? result.value.reason : "unavailable";
    return {
      ...snapshot,
      daily_endpoint: "unavailable",
      days: [],
      contract_note: `${MISSING_DAILY_PNL_CONTRACT} Core daily-performance status=${status ?? "missing"}; reason=${reason}.`,
    };
  }
  return { ...snapshot, daily_endpoint: "unavailable", days: [] };
}

function activePaperSession(paper: Record<string, unknown>): PaperSession[] {
  const sessionId = paper.session_id;
  if (typeof sessionId !== "string" || sessionId.length === 0) {
    return [];
  }
  return [
    {
      session_id: sessionId,
      label: paper.running ? "Current paper account (running)" : "Current paper account",
      status: paper.running ? "active" : "unknown",
      starting_cash_inr: parseDecimal(paper.starting_cash as string | undefined),
      source: "GET /api/v1/paper/status (no session-history API)",
    },
  ];
}

function emptyRealSnapshot(note: string): DashboardSnapshot {
  return {
    mode: "real",
    trading_date_ist: null,
    trading_date_source: "unavailable",
    sessions: [],
    selected_session_id: "",
    pnl_basis: "unavailable",
    days: [],
    portfolio: {
      equity: null,
      cash: null,
      total_pnl: null,
      realized_pnl: null,
      unrealized_pnl: null,
      gross_exposure: null,
      drawdown: null,
      as_of: null,
    },
    win_rate: {
      pct: null,
      sample: null,
      definition: "No Core closed-trade pairing convention is published for paper. Latest stored backtest is not paper session P&L.",
    },
    positions: [],
    orders: [],
    trades: [],
    market: null,
    status: {
      core: "unavailable",
      trading_mode: "UNKNOWN",
      live_enabled: false,
      paper_running: null,
      kill_switch: null,
      zerodha_authenticated: null,
      zerodha_configured: null,
      worker: "Worker status unavailable",
      market_as_of: null,
      last_refresh: new Date().toISOString(),
    },
    daily_endpoint: "missing",
    contract_note: note,
  };
}

export async function loadRealDashboard(): Promise<DashboardSnapshot> {
  try {
  const [system, paper, portfolio, positions, orders, trades, overview, zerodha, risk, daily] = await Promise.all([
    optional<Record<string, unknown>>("/api/v1/system/status"),
    optional<Record<string, unknown>>("/api/v1/paper/status"),
    optional<Record<string, unknown>>("/api/v1/portfolio"),
    optional<unknown[]>("/api/v1/positions"),
    optional<unknown[]>("/api/v1/orders"),
    optional<unknown[]>("/api/v1/trades"),
    optional<Record<string, unknown>>("/api/v1/market/overview"),
    optional<Record<string, unknown>>("/api/v1/zerodha/status"),
    optional<Record<string, unknown>>("/api/v1/risk/status"),
    optional<DailyPerformanceResponse>("/api/v1/paper/daily-performance"),
  ]);

  const sys = system.ok ? system.value : {};
  const pap = paper.ok ? paper.value : {};
  const port = portfolio.ok ? portfolio.value : {};
  const nested = port.snapshot;
  const snap =
    nested && typeof nested === "object" ? (nested as Record<string, unknown>) : {};
  const ov = overview.ok ? overview.value : null;
  const marketAsOf = ov && typeof ov.as_of === "string" ? ov.as_of : "";
  const tradingDate = marketAsOf ? istDateKeyFromInstant(marketAsOf) : null;
  const market =
    ov == null
      ? null
      : {
          as_of: marketAsOf || null,
          nifty_last: typeof ov.nifty_last === "string" ? ov.nifty_last : null,
          breadth_advancers: typeof ov.breadth_advancers === "number" ? ov.breadth_advancers : null,
          breadth_decliners: typeof ov.breadth_decliners === "number" ? ov.breadth_decliners : null,
          mode: typeof ov.mode === "string" ? ov.mode : null,
        };

  const sessions: PaperSession[] = paper.ok ? activePaperSession(pap) : [];

  const pnlBasis: PnlBasis = "unavailable";
  const now = new Date().toISOString();

  const base: DashboardSnapshot = {
    mode: "real",
    trading_date_ist: tradingDate,
    trading_date_source: marketAsOf
      ? "GET /api/v1/market/overview as_of → IST calendar date"
      : "unavailable (no backend trading_date_ist)",
    sessions,
    selected_session_id: sessions[0]?.session_id ?? "",
    pnl_basis: pnlBasis,
    days: [],
    portfolio: {
      equity: parseDecimal((snap.equity as string) ?? (port.equity as string)),
      cash: parseDecimal(snap.cash as string),
      total_pnl: parseDecimal((snap.total_pnl as string) ?? (port.total_pnl as string)),
      realized_pnl: parseDecimal(snap.realized_pnl as string),
      unrealized_pnl: parseDecimal(snap.unrealized_pnl as string),
      gross_exposure: parseDecimal((snap.gross_exposure as string) ?? (port.gross_exposure as string)),
      drawdown: parseDecimal(snap.drawdown as string),
      as_of: typeof snap.timestamp === "string" ? snap.timestamp : null,
    },
    win_rate: {
      pct: null,
      sample: null,
      definition:
        "No Core closed-trade pairing convention is published for paper. Latest stored backtest is not paper session P&L.",
    },
    positions: positions.ok ? (positions.value as Array<Record<string, unknown>>) : [],
    orders: orders.ok ? (orders.value as Array<Record<string, unknown>>) : [],
    trades: trades.ok ? (trades.value as Array<Record<string, unknown>>) : [],
    market,
    status: {
      core: system.ok ? String(sys.status ?? "ok") : `unavailable (${system.error})`,
      trading_mode: String(sys.trading_mode ?? pap.trading_mode ?? "UNKNOWN"),
      live_enabled: sys.live_enabled === false || sys.live_enabled === true ? Boolean(sys.live_enabled) : false,
      paper_running: typeof pap.running === "boolean" ? pap.running : null,
      kill_switch:
        typeof pap.kill_switch === "string"
          ? pap.kill_switch
          : risk.ok && typeof (risk.value as { kill_switch?: string }).kill_switch === "string"
            ? (risk.value as { kill_switch?: string }).kill_switch ?? null
            : null,
      zerodha_authenticated: zerodha.ok ? Boolean((zerodha.value as { authenticated?: boolean }).authenticated) : null,
      zerodha_configured: zerodha.ok ? Boolean((zerodha.value as { configured?: boolean }).configured) : null,
      worker: "Worker status unavailable",
      market_as_of: marketAsOf || null,
      last_refresh: now,
    },
    daily_endpoint: "missing",
    contract_note: MISSING_DAILY_PNL_CONTRACT,
  };
  return applyDailyPerformance(base, daily);
  } catch (error) {
    return emptyRealSnapshot(error instanceof Error ? error.message : MISSING_DAILY_PNL_CONTRACT);
  }
}
