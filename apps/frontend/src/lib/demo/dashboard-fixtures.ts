import type { DailyPnlDay, DashboardSnapshot } from "@/lib/daily-pnl";
import { addDaysKey, consecutiveDateKeys, weekdaySundayFirst } from "@/lib/ist";

export const DEMO_END_IST = "2026-10-10";
export const DEMO_SESSION_ACTIVE = "demo-paper-2026";
export const DEMO_STARTING_CASH = 1_000_000;

function mix(key: string): number {
  let h = 2166136261;
  for (let i = 0; i < key.length; i += 1) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 2 ** 32;
}

function demoDay(key: string): DailyPnlDay {
  const weekday = weekdaySundayFirst(key);
  const closed = weekday === 0 || weekday === 6;
  const roll = mix(key);
  if (closed) {
    return {
      session_id: DEMO_SESSION_ACTIVE,
      calendar_date_ist: key,
      snapshot_as_of: null,
      complete: true,
      pnl_basis: "net_equity",
      net_pnl_inr: null,
      start_of_day_equity_inr: DEMO_STARTING_CASH,
      realized_pnl_inr: null,
      unrealized_change_inr: null,
      fees_inr: null,
      has_activity: false,
      trading_calendar_state: "closed",
      source_updated_at: `${key}T10:00:00+05:30`,
      closed_trades: 0,
    };
  }
  if (roll > 0.97) {
    return {
      session_id: DEMO_SESSION_ACTIVE,
      calendar_date_ist: key,
      snapshot_as_of: null,
      complete: false,
      pnl_basis: "unavailable",
      net_pnl_inr: null,
      start_of_day_equity_inr: DEMO_STARTING_CASH,
      realized_pnl_inr: null,
      unrealized_change_inr: null,
      fees_inr: null,
      has_activity: null,
      trading_calendar_state: "unknown",
      source_updated_at: null,
      closed_trades: null,
    };
  }
  if (roll > 0.72) {
    return {
      session_id: DEMO_SESSION_ACTIVE,
      calendar_date_ist: key,
      snapshot_as_of: `${key}T10:00:00+05:30`,
      complete: true,
      pnl_basis: "net_equity",
      net_pnl_inr: 0,
      start_of_day_equity_inr: DEMO_STARTING_CASH,
      realized_pnl_inr: 0,
      unrealized_change_inr: 0,
      fees_inr: 0,
      has_activity: false,
      trading_calendar_state: "open",
      source_updated_at: `${key}T10:00:00+05:30`,
      closed_trades: 0,
    };
  }
  const signed = roll > 0.42 ? 1 : -1;
  const magnitude = 180 + mix(`${key}:m`) * 1100;
  const net = Math.round((signed * magnitude) * 100) / 100;
  const fees = Math.round((8 + mix(`${key}:f`) * 24) * 100) / 100;
  return {
    session_id: DEMO_SESSION_ACTIVE,
    calendar_date_ist: key,
    snapshot_as_of: `${key}T10:00:00+05:30`,
    complete: true,
    pnl_basis: "net_equity",
    net_pnl_inr: net,
    start_of_day_equity_inr: DEMO_STARTING_CASH,
    realized_pnl_inr: Math.round(net * 0.7 * 100) / 100,
    unrealized_change_inr: Math.round(net * 0.3 * 100) / 100,
    fees_inr: fees,
    has_activity: true,
    trading_calendar_state: "open",
    source_updated_at: `${key}T10:00:00+05:30`,
    closed_trades: 1 + Math.floor(mix(`${key}:t`) * 3),
  };
}

export function demoDashboard(): DashboardSnapshot {
  const keys = consecutiveDateKeys(DEMO_END_IST, 365);
  const days = keys.map(demoDay);
  const activeDays = days.filter((day) => day.has_activity && day.net_pnl_inr !== null);
  const total = activeDays.reduce((sum, day) => sum + (day.net_pnl_inr ?? 0), 0);
  const wins = activeDays.filter((day) => (day.net_pnl_inr ?? 0) > 0).length;
  return {
    mode: "demo",
    trading_date_ist: DEMO_END_IST,
    trading_date_source: "demo fixture clock (not browser, not Core)",
    sessions: [
      {
        session_id: DEMO_SESSION_ACTIVE,
        label: "Demo paper 2026 (active)",
        status: "active",
        starting_cash_inr: DEMO_STARTING_CASH,
        source: "demo fixture",
      },
      {
        session_id: "demo-paper-2025-closed",
        label: "Demo paper 2025 (closed)",
        status: "closed",
        starting_cash_inr: DEMO_STARTING_CASH,
        source: "demo fixture",
      },
    ],
    selected_session_id: DEMO_SESSION_ACTIVE,
    pnl_basis: "net_equity",
    days,
    portfolio: {
      equity: DEMO_STARTING_CASH + total,
      cash: 880_000,
      total_pnl: total,
      realized_pnl: total * 0.7,
      unrealized_pnl: total * 0.3,
      gross_exposure: 95_000,
      drawdown: 0.012,
      as_of: `${DEMO_END_IST}T10:00:00+05:30`,
    },
    win_rate: {
      pct: activeDays.length ? wins / activeDays.length : null,
      sample: activeDays.length,
      definition: "Demo fixture: day with positive net_pnl counts as a win. Not a Core closed-trade convention.",
    },
    positions: [
      {
        symbol: "RELIANCE",
        quantity: 10,
        average_price: "1380.00",
        market_price: "1394.50",
        unrealized_pnl: "145.00",
        updated_at: `${DEMO_END_IST}T10:00:00+05:30`,
      },
    ],
    orders: [
      {
        order_id: "demo-ord-1",
        symbol: "INFY",
        side: "BUY",
        status: "FILLED",
        quantity: 5,
        created_at: `${addDaysKey(DEMO_END_IST, -3)}T04:00:00Z`,
      },
      {
        order_id: "demo-ord-kotak",
        symbol: "KOTAKBANK",
        side: "BUY",
        status: "CANCELLED",
        quantity: 2,
        metadata: { note: "fixture cancelled, zero executions" },
        created_at: `${addDaysKey(DEMO_END_IST, -10)}T04:00:00Z`,
      },
    ],
    trades: [
      {
        execution_id: "demo-ex-1",
        symbol: "INFY",
        side: "BUY",
        quantity: 5,
        price: "1510.00",
        timestamp: `${addDaysKey(DEMO_END_IST, -3)}T04:01:00Z`,
      },
    ],
    status: {
      core: "demo",
      trading_mode: "PAPER",
      live_enabled: false,
      paper_running: true,
      kill_switch: "disarmed",
      zerodha_authenticated: false,
      zerodha_configured: false,
      worker: "Worker status unavailable",
      market_as_of: `${DEMO_END_IST}T10:00:00+05:30`,
      last_refresh: `${DEMO_END_IST}T10:00:00+05:30`,
    },
    daily_endpoint: "demo_fixture",
    contract_note: "Whole-page demo fixtures. Not submitted to Core. Magnitudes stay near 0.02%–0.12% of ₹10,00,000.",
  };
}
