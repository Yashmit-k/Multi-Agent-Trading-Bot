"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { EquityChart } from "@/components/dashboard/EquityChart";
import { PnlCalendar } from "@/components/dashboard/PnlCalendar";
import { demoDashboard } from "@/lib/demo/dashboard-fixtures";
import type { DailyPnlDay, DashboardSnapshot } from "@/lib/daily-pnl";
import { loadRealDashboard } from "@/lib/load-real-dashboard";
import { formatInr, formatPct, formatSignedInr, parseDecimal } from "@/lib/money";
import { formatDateKeyLong } from "@/lib/ist";
import { visualState } from "@/lib/cell-state";
import { ErrorState } from "@/components/States";

const REAL_KEY = "dashboard-real";

export function TradingDashboard() {
  const router = useRouter();
  const params = useSearchParams();
  const demo = params.get("demo") === "1";
  const { mutate } = useSWRConfig();
  const { data, error, isLoading, mutate: reload } = useSWR(demo ? null : REAL_KEY, loadRealDashboard);
  const [sessionId, setSessionId] = useState("");
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const snapshot: DashboardSnapshot | undefined = demo ? demoDashboard() : data;

  useEffect(() => {
    setSelectedDay(null);
    setSessionId(snapshot?.sessions[0]?.session_id ?? "");
  }, [demo, snapshot?.sessions[0]?.session_id]);

  const sessionDays = useMemo(() => {
    if (!snapshot) return [];
    const id = sessionId || snapshot.selected_session_id;
    return snapshot.days.filter((day) => day.session_id === id);
  }, [snapshot, sessionId]);

  const endKey = snapshot?.trading_date_ist ?? null;
  const selectedMeta = snapshot?.sessions.find((item) => item.session_id === (sessionId || snapshot.selected_session_id));
  const basisLabel = snapshot?.pnl_basis === "realized_only" ? "Realized P&L" : snapshot?.pnl_basis === "net_equity" ? "Net P&L" : "P&L unavailable";

  function setDemo(next: boolean) {
    setSelectedDay(null);
    if (next) {
      void mutate(REAL_KEY, undefined, { revalidate: false });
      router.replace("/dashboard?demo=1");
      return;
    }
    void mutate(REAL_KEY);
    router.replace("/dashboard");
  }

  const lastRefresh = snapshot?.status.last_refresh;

  return (
    <div className="space-y-4">
      {demo ? (
        <div data-testid="demo-banner" className="rounded-[12px] border border-amber-700 bg-amber-950 px-4 py-2 text-sm text-amber-100">
          DEMO DATA — fixtures for the entire page. Not Core account results. Source: in-repo demo fixtures.
        </div>
      ) : null}

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-[#94A3B8]">Overview</p>
          <h1 className="text-2xl font-semibold text-[#E6EDF3]">Trading Overview</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label className="flex items-center gap-2 text-[#94A3B8]">
            Session
            <select
              data-testid="session-select"
              className="rounded-md border border-[#26303C] bg-[#171F2A] px-2 py-1 text-[#E6EDF3]"
              value={sessionId}
              onChange={(event) => {
                setSessionId(event.target.value);
                setSelectedDay(null);
              }}
              disabled={!snapshot?.sessions.length}
            >
              {snapshot?.sessions.length ? (
                snapshot.sessions.map((item) => (
                  <option key={item.session_id} value={item.session_id}>
                    {item.label}
                  </option>
                ))
              ) : (
                <option value="">Current session only</option>
              )}
            </select>
          </label>
          <button
            type="button"
            className="rounded-md border border-[#26303C] bg-[#171F2A] px-3 py-1 text-[#E6EDF3]"
            onClick={() => {
              if (demo) setDemo(true);
              else void reload();
            }}
          >
            Refresh
          </button>
          <span data-testid="last-updated" className="text-xs text-[#94A3B8]">
            Updated {lastRefresh ? istTime(lastRefresh) : "—"}
          </span>
        </div>
      </header>

      {error && !demo ? <ErrorState message={error.message} /> : null}
      {!demo && !snapshot ? <CalendarSkeleton /> : null}

      {snapshot ? (
        <>
          <SummaryCards
            snapshot={snapshot}
            sessionLabel={selectedMeta?.label ?? "—"}
            endKey={endKey}
            sessionDays={sessionDays}
            sessionBelongsToSeries={snapshot.mode === "real" || sessionDays.length > 0 || snapshot.sessions[0]?.session_id === sessionId}
          />
          {endKey ? (
            <PnlCalendar
              endKey={endKey}
              days={sessionDays}
              selected={selectedDay}
              onSelect={setSelectedDay}
              pnlBasisLabel={basisLabel}
              emptyReason={
                snapshot.daily_endpoint === "missing" || snapshot.daily_endpoint === "unavailable"
                  ? "Daily paper P&L series is unavailable. Cells are missing data, not zero P&L."
                  : sessionDays.length === 0
                    ? "No P&L history recorded for this session. Missing cells are not zeros."
                    : null
              }
              referenceEquity={selectedMeta?.starting_cash_inr ?? snapshot.portfolio.equity}
            />
          ) : (
            <p className="text-sm text-[#94A3B8]">Calendar range unavailable: backend did not provide a trading date.</p>
          )}
          <EquityChart
            mode={snapshot.mode}
            days={sessionDays}
            startingCash={selectedMeta?.starting_cash_inr ?? snapshot.portfolio.equity}
          />
          <DayDetail
            dateKey={selectedDay}
            day={sessionDays.find((item) => item.calendar_date_ist === selectedDay)}
            onClear={() => setSelectedDay(null)}
          />
          <RecentTrades snapshot={snapshot} />
        </>
      ) : null}
    </div>
  );
}

function SummaryCards({
  snapshot,
  sessionLabel,
  endKey,
  sessionDays,
  sessionBelongsToSeries,
}: {
  snapshot: DashboardSnapshot;
  sessionLabel: string;
  endKey: string | null;
  sessionDays: DailyPnlDay[];
  sessionBelongsToSeries: boolean;
}) {
  const start = snapshot.sessions.find((item) => item.label === sessionLabel)?.starting_cash_inr
    ?? snapshot.sessions[0]?.starting_cash_inr
    ?? null;
  const total = sessionBelongsToSeries ? snapshot.portfolio.total_pnl : sessionDays.reduce((sum, day) => sum + (day.net_pnl_inr ?? 0), 0) || null;
  const ret = start && start > 0 && total !== null ? total / start : null;
  const today = endKey ? snapshot.days.find((day) => day.calendar_date_ist === endKey) : undefined;
  const todayState = today ? visualState(today) : undefined;
  const openPositions = snapshot.positions.length;

  const realized = snapshot.portfolio.realized_pnl;
  const unrealized = snapshot.portfolio.unrealized_pnl;
  // During the session Core updates today's figure continuously and marks it provisional (complete = false);
  // the calendar waits for the final close, but this card shows the running number.
  const showToday = today?.net_pnl_inr != null && todayState?.kind !== "market_closed" && today.pnl_basis !== "unavailable";
  const provisional = showToday && today?.complete === false;

  return (
    <div data-testid="kpi-row" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card title="Total P&L">
        <Amount value={total} />
        <p className="text-sm text-[#94A3B8]">
          {formatPct(ret)} of {start === null ? "—" : formatInr(start)}
        </p>
      </Card>
      <Card title="Today’s P&L">
        <Amount value={showToday ? today!.net_pnl_inr! : null} />
        <p className="text-sm text-[#94A3B8]" data-testid="today-label">
          {provisional ? "so far today · provisional" : endKey ? formatDateKeyLong(endKey) : "—"}
        </p>
      </Card>
      <Card title="Realised">
        <Amount value={realized} />
        <p className="text-sm text-[#94A3B8]">from closed trades</p>
      </Card>
      <Card title="Unrealised">
        <Amount value={unrealized} />
        <p className="text-sm text-[#94A3B8]">
          on {openPositions} open position{openPositions === 1 ? "" : "s"}
        </p>
      </Card>
    </div>
  );
}

function Amount({ value }: { value: number | null }) {
  const tone = value === null || value === 0 ? "text-[#E6EDF3]" : value > 0 ? "text-emerald-400" : "text-red-400";
  return <p className={`font-mono text-2xl tabular-nums ${tone}`}>{value === null ? "—" : formatSignedInr(value)}</p>;
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#94A3B8]">{title}</h2>
      {children}
    </section>
  );
}

function DayDetail({ dateKey, day, onClear }: { dateKey: string | null; day?: DailyPnlDay; onClear: () => void }) {
  if (!dateKey) return null;
  const state = visualState(day);
  return (
    <section className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4" data-testid="day-detail">
      <div className="mb-2 flex justify-between">
        <h2 className="font-semibold text-[#E6EDF3]">{formatDateKeyLong(dateKey)}</h2>
        <button type="button" className="text-sm text-cyan-400" onClick={onClear}>
          Clear selection
        </button>
      </div>
      {state.kind === "market_closed" ? <p className="text-sm text-[#94A3B8]">Exchange was closed.</p> : null}
      {state.kind === "missing" ? <p className="text-sm text-[#94A3B8]">Incomplete or missing snapshot. Not a zero-P&L day.</p> : null}
      {state.kind === "no_activity" ? <p className="text-sm text-[#94A3B8]">Market open; no qualifying activity.</p> : null}
      {day?.net_pnl_inr != null && state.kind !== "market_closed" && state.kind !== "missing" ? (
        <p className="font-mono tabular-nums">{formatSignedInr(day.net_pnl_inr)}</p>
      ) : null}
    </section>
  );
}

const REASONS: Record<string, string> = {
  entry: "entry",
  stop: "stop loss",
  target: "target",
  signal: "agents turned bearish",
  kill_switch: "kill switch",
  manual: "manual",
};

function istTime(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso)) + " IST";
}

function istDayTime(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
}

function RecentTrades({ snapshot }: { snapshot: DashboardSnapshot }) {
  const sideOf = new Map(snapshot.orders.map((order) => [String(order.order_id), String(order.side ?? "")]));
  const rows = snapshot.trades
    .map((row) => {
      const meta = (row.metadata ?? {}) as Record<string, unknown>;
      const when = String(row.executed_at ?? row.timestamp ?? "");
      const reason = String(meta.reason ?? "");
      const side = String(row.side ?? sideOf.get(String(row.order_id)) ?? (reason === "entry" ? "BUY" : reason ? "SELL" : ""));
      return { id: String(row.execution_id), when, symbol: String(row.symbol), side, quantity: row.quantity, price: parseDecimal(row.price as string), reason };
    })
    .sort((a, b) => b.when.localeCompare(a.when))
    .slice(0, 8);
  return (
    <section data-testid="recent-trades" className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-[#94A3B8]">Recent trades</h2>
        <Link prefetch={false} href="/orders" className="text-sm text-cyan-400 hover:underline">
          View all →
        </Link>
      </div>
      {rows.length === 0 ? (
        <p className="text-[#94A3B8]">No trades yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-left">
            <thead className="text-xs text-[#94A3B8]">
              <tr>
                <th className="py-1 pr-3 font-normal">Time</th>
                <th className="py-1 pr-3 font-normal">Stock</th>
                <th className="py-1 pr-3 font-normal">Side</th>
                <th className="py-1 pr-3 text-right font-normal">Qty</th>
                <th className="py-1 pr-3 text-right font-normal">Price</th>
                <th className="py-1 font-normal">Reason</th>
              </tr>
            </thead>
            <tbody className="text-[#E6EDF3]">
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-[#26303C]">
                  <td className="py-1.5 pr-3 tabular-nums text-[#94A3B8]">{row.when ? istDayTime(row.when) : "—"}</td>
                  <td className="py-1.5 pr-3 font-medium">{row.symbol}</td>
                  <td className={`py-1.5 pr-3 ${row.side === "BUY" ? "text-emerald-400" : row.side === "SELL" ? "text-red-400" : ""}`}>{row.side || "—"}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{String(row.quantity ?? "—")}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{row.price === null ? "—" : formatInr(row.price)}</td>
                  <td className="py-1.5 text-[#94A3B8]">{REASONS[row.reason] ?? (row.reason.replaceAll("_", " ") || "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CalendarSkeleton() {
  return (
    <div data-testid="calendar-skeleton" className="h-40 animate-pulse rounded-[12px] border border-[#26303C] bg-[#121922]" />
  );
}

// Test hook: the summary cards on their own, with the real session wiring stubbed out.
export function SummaryCardsForTest({ snapshot, endKey }: { snapshot: DashboardSnapshot; endKey: string }) {
  return <SummaryCards snapshot={snapshot} sessionLabel={snapshot.sessions[0]?.label ?? "—"} endKey={endKey} sessionDays={snapshot.days} sessionBelongsToSeries />;
}
