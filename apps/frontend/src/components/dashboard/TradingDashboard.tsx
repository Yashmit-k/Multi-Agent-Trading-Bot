"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { EquityChart } from "@/components/dashboard/EquityChart";
import { KillSwitchControl } from "@/components/KillSwitchControl";
import { PnlCalendar } from "@/components/dashboard/PnlCalendar";
import { demoDashboard } from "@/lib/demo/dashboard-fixtures";
import type { DailyPnlDay, DashboardSnapshot } from "@/lib/daily-pnl";
import { loadRealDashboard } from "@/lib/load-real-dashboard";
import { formatInr, formatPct, formatSignedInr } from "@/lib/money";
import { formatDateKeyLong, formatIstInstant } from "@/lib/ist";
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
          <p className="text-sm text-[#94A3B8]">
            PAPER TRADING · live_enabled={String(snapshot?.status.live_enabled ?? "—")} · read-only
          </p>
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
                    {item.label} ({item.status})
                  </option>
                ))
              ) : (
                <option value="">No session-history API</option>
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
          <button
            type="button"
            role="switch"
            data-testid="demo-toggle"
            aria-checked={demo}
            aria-label="Show demonstration data"
            className="flex items-center gap-2 rounded-md border border-[#26303C] bg-[#171F2A] px-3 py-1 text-[#E6EDF3]"
            onClick={() => setDemo(!demo)}
          >
            <span className={demo ? "text-amber-200" : "text-[#94A3B8]"}>{demo ? "On" : "Off"}</span>
            Demo data
          </button>
        </div>
      </header>
      <p className="text-xs text-[#94A3B8]">
        Last successful refresh {lastRefresh ? formatIstInstant(lastRefresh) : "—"}. Market as_of{" "}
        {snapshot?.status.market_as_of ? formatIstInstant(snapshot.status.market_as_of) : "unavailable"}. Trading date{" "}
        {endKey ?? "—"} ({snapshot?.trading_date_source ?? "—"}).
      </p>

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
          <div className="grid gap-4 lg:grid-cols-2">
            <StatusPanel snapshot={snapshot} />
            <Tables snapshot={snapshot} />
          </div>
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
  const closedLabel = snapshot.win_rate.sample;

  return (
    <div data-testid="kpi-row" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card title="Total P&L">
        <p className="font-mono text-2xl tabular-nums text-[#E6EDF3]">{total === null ? "—" : formatSignedInr(total)}</p>
        <p className="text-sm text-[#94A3B8]">
          Session return {formatPct(ret)} of starting cash {start === null ? "—" : formatInr(start)}
        </p>
        <p className="text-xs text-[#94A3B8]">{sessionLabel}</p>
        <p className="text-xs text-[#94A3B8]">
          Realized {snapshot.portfolio.realized_pnl === null ? "—" : formatSignedInr(snapshot.portfolio.realized_pnl)} ·
          Unrealized {snapshot.portfolio.unrealized_pnl === null ? "—" : formatSignedInr(snapshot.portfolio.unrealized_pnl)}
        </p>
      </Card>
      <Card title={snapshot.pnl_basis === "realized_only" ? "Today’s realized P&L" : "Today’s P&L"}>
        <p className="font-mono text-2xl tabular-nums text-[#E6EDF3]">
          {today?.net_pnl_inr == null || todayState?.kind === "missing" || todayState?.kind === "market_closed"
            ? "—"
            : formatSignedInr(today.net_pnl_inr)}
        </p>
        <p className="text-xs text-[#94A3B8]">
          Date {endKey ?? "—"} · complete {today ? String(today.complete) : "n/a"} · {snapshot.pnl_basis}
        </p>
        {snapshot.mode === "real" ? (
          <p className="text-xs text-[#94A3B8]">Not inferred from browser time. Cumulative portfolio P&L is not today’s P&L.</p>
        ) : null}
      </Card>
      <Card title="Win rate">
        <p className="font-mono text-2xl tabular-nums text-[#E6EDF3]">
          {!sessionBelongsToSeries || snapshot.win_rate.pct === null ? "—" : formatPct(snapshot.win_rate.pct)}
        </p>
        <p className="text-sm text-[#94A3B8]">n = {sessionBelongsToSeries ? (closedLabel ?? "—") : "—"}</p>
        <p className="text-xs text-[#94A3B8]" title={snapshot.win_rate.definition}>
          {snapshot.win_rate.definition}
        </p>
      </Card>
      <Card title="Trades and positions">
        <p className="font-mono text-2xl tabular-nums text-[#E6EDF3]">{openPositions} open</p>
        <p className="text-sm text-[#94A3B8]">
          Executions listed {snapshot.trades.length} · orders {snapshot.orders.length}. Unfilled orders are not completed trades.
        </p>
        <Link href="/positions" className="text-sm text-cyan-400 hover:underline">
          Positions
        </Link>{" "}
        <Link href="/orders" className="text-sm text-cyan-400 hover:underline">
          Orders
        </Link>
      </Card>
    </div>
  );
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

function StatusPanel({ snapshot }: { snapshot: DashboardSnapshot }) {
  const s = snapshot.status;
  return (
    <section className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4 text-sm">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#94A3B8]">Status</h2>
      <ul className="space-y-1 text-[#E6EDF3]">
        <li>Core API {s.core}</li>
        <li>Mode {s.trading_mode} · live_enabled {String(s.live_enabled)}</li>
        <li>Paper running {s.paper_running === null ? "—" : String(s.paper_running)}</li>
        <li>
          {s.kill_switch ? (
            <KillSwitchControl killSwitch={s.kill_switch} live={s.trading_mode === "LIVE"} />
          ) : (
            <>Kill switch —</>
          )}
        </li>
        <li>Zerodha configured {s.zerodha_configured === null ? "—" : String(s.zerodha_configured)}</li>
        <li>Zerodha authenticated {s.zerodha_authenticated === null ? "—" : String(s.zerodha_authenticated)}</li>
        <li>{s.worker}</li>
        <li className="text-[#94A3B8]">{snapshot.contract_note}</li>
      </ul>
    </section>
  );
}

function Tables({ snapshot }: { snapshot: DashboardSnapshot }) {
  return (
    <section className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4 text-sm">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#94A3B8]">Positions and orders</h2>
      {snapshot.positions.length === 0 ? (
        <p className="text-[#94A3B8]">No open positions.</p>
      ) : (
        <table className="mb-3 w-full font-mono tabular-nums">
          <thead>
            <tr className="text-left text-[#94A3B8]">
              <th>Symbol</th>
              <th>Qty</th>
              <th>Unrealized</th>
            </tr>
          </thead>
          <tbody>
            {snapshot.positions.map((row) => (
              <tr key={String(row.symbol)}>
                <td>{String(row.symbol)}</td>
                <td>{String(row.quantity)}</td>
                <td>{row.unrealized_pnl == null ? "—" : String(row.unrealized_pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {snapshot.orders.length === 0 ? (
        <p className="text-[#94A3B8]">No orders.</p>
      ) : (
        <ul className="space-y-1">
          {snapshot.orders.map((row) => {
            const status = String(row.status ?? "");
            const review = status === "legacy_order_requires_review";
            return (
              <li key={String(row.order_id)}>
                {String(row.symbol)} {status}
                {review ? " — legacy review, not a pending fill" : ""}
                {status === "CANCELLED" ? " (cancelled; not a completed trade)" : ""}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function CalendarSkeleton() {
  return (
    <div data-testid="calendar-skeleton" className="h-40 animate-pulse rounded-[12px] border border-[#26303C] bg-[#121922]" />
  );
}
