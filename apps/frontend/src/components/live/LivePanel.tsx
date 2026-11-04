"use client";

import { useCallback, useEffect, useState } from "react";
import { errorText, fetchApi, postApi } from "@/lib/api";
import { inr, price } from "@/lib/format";
import { useOperator, OperatorLogin } from "@/components/operator/OperatorGate";
import { Card, Table, Td } from "@/components/ui";

type Settings = { amount: number; stocks: number; mode: string; max_order: number };
type SettingsView = { settings: Settings; modes: string[]; updated_at: string | null; changes: Array<{ at: string; by: string; changed: Record<string, { from: unknown; to: unknown }> }> };
type ZerodhaStatus = { configured: boolean; authenticated: boolean; expires_at?: string | null };
type Account = {
  holdings: Array<{ symbol: string; quantity: number; t1_quantity: number; average_price: number | null; close_price: number | null }>;
  positions: Array<{ symbol: string; product: string; quantity: number; average_price: number | null }>;
  cash: { available: number | null };
  orders: Array<{ order_id: string; symbol: string; side: string; quantity: number; filled_quantity: number; status: string; placed_at: string }>;
  read_at: string;
};

type Plan = {
  mode: string;
  detail?: string;
  decided_at_close?: string;
  trade_at_open_of?: string;
  assumed_account?: boolean;
  book?: number;
  per_stock?: number;
  orders?: Array<{ side: string; symbol: string; quantity: number; close: number; limit: number; value: number; blocked: string | null }>;
  warnings?: string[];
  totals?: { buy?: number; sell?: number; charges?: number };
  digest?: string;
  run_phase?: string | null;
  live_switch?: boolean;
};
type RunOrder = { side: string; symbol: string; quantity: number; filled: number; limit: number; average_price: number | null; status: string; round: string };
type Run = { decided: string; phase: string; deadline: string; orders: RunOrder[]; notes: string[]; summary?: { bought: number; sold: number; unfilled: string[] } };

const PHASE: Record<string, string> = {
  selling: "Selling", buying: "Buying", buying_wait: "Waiting for buys to fill", leftover_wait: "Buying with the leftover cash",
  closing: "Cancelling what is still open", done: "Done", stopped: "Stopped", skipped: "Skipped this month",
};

const MODE_LABEL: Record<string, string> = { off: "Off", dry_run: "Dry run (orders shown, never sent)", live: "Live (orders sent after you approve)" };
const LABEL: Record<string, string> = { amount: "Amount for the strategy", stocks: "Number of stocks", mode: "Mode", max_order: "Largest single order" };
const HINT: Record<string, string> = {
  amount: "The most of your account the strategy may use, in rupees. It never spends beyond this.",
  stocks: "How many of the top-ranked stocks to hold. Takes effect at the next rebalance.",
  max_order: "Any order above this is refused, as a guard against a bug.",
};

function SettingsForm({ view, onSaved }: { view: SettingsView; onSaved: (next: SettingsView) => void }) {
  const [draft, setDraft] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(view.settings).map(([k, v]) => [k, String(v)])));
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, setPending] = useState(false);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    try {
      const next = await postApi<SettingsView>("/api/v1/live/settings", { values: draft, operator: "web-operator" });
      onSaved(next);
      setMessage({ ok: true, text: "Saved. Applies from the next rebalance." });
    } catch (error) {
      setMessage({ ok: false, text: errorText(error) });
    } finally {
      setPending(false);
    }
  }
  const field = "w-40 rounded border border-[#26303C] bg-[#0B0F14] px-2 py-1 text-sm";
  return (
    <form onSubmit={(event) => void save(event)} className="space-y-3 text-sm">
      {(["amount", "stocks", "max_order"] as const).map((key) => (
        <label key={key} className="grid gap-1 sm:grid-cols-[220px_1fr] sm:items-center">
          <span className="text-[#94A3B8]">{LABEL[key]}</span>
          <span>
            <input aria-label={LABEL[key]} inputMode="numeric" className={field} value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
            <span className="mt-0.5 block text-xs text-[#64748B]">{HINT[key]}</span>
          </span>
        </label>
      ))}
      <label className="grid gap-1 sm:grid-cols-[220px_1fr] sm:items-center">
        <span className="text-[#94A3B8]">{LABEL.mode}</span>
        <span>
          <select aria-label={LABEL.mode} className={field} value={draft.mode} onChange={(e) => setDraft({ ...draft, mode: e.target.value })}>
            {view.modes.map((mode) => (
              <option key={mode} value={mode}>{MODE_LABEL[mode] ?? mode}</option>
            ))}
          </select>
          <span className="mt-0.5 block text-xs text-[#64748B]">
            {view.modes.includes("live") ? "Live: nothing is sent until you press Approve on the month's orders." : "Live is off on the server (switch MOMENTUM_LIVE_ENABLED)."}
          </span>
        </span>
      </label>
      <div className="flex items-center gap-3">
        <button type="submit" disabled={pending} className="rounded bg-[#2563EB] px-3 py-1 font-medium text-white disabled:opacity-50">Save</button>
        {message ? <span className={message.ok ? "text-[#22C55E]" : "text-[#EF4444]"}>{message.text}</span> : null}
      </div>
      {view.changes.length ? (
        <details className="text-xs text-[#94A3B8]">
          <summary className="cursor-pointer">Change history ({view.changes.length})</summary>
          <ul className="mt-1 space-y-0.5">
            {view.changes.map((change) => (
              <li key={change.at}>
                {new Date(change.at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}:{" "}
                {Object.entries(change.changed).map(([k, v]) => `${LABEL[k] ?? k} ${String(v.from)} → ${String(v.to)}`).join(", ")}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </form>
  );
}

function AccountView() {
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setError(null);
    fetchApi<Account>("/api/v1/live/account").then(setAccount).catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);
  if (error) return <p className="text-sm text-[#EF4444]">Could not read the account: {error}</p>;
  if (!account) return <p className="text-sm text-[#94A3B8]">Reading your account…</p>;
  return (
    <div className="space-y-3 text-sm">
      <p>
        Cash available: <span className="font-semibold tabular-nums">{inr(account.cash.available)}</span>
        <button type="button" onClick={load} className="ml-3 text-xs text-[#93C5FD] underline">Refresh</button>
      </p>
      {account.holdings.length ? (
        <Table head={["Holding", "Shares", "Avg price", "Last close"]} minWidth={420}>
          {account.holdings.map((row) => (
            <tr key={row.symbol}>
              <Td>{row.symbol}</Td>
              <Td className="tabular-nums">{row.quantity + row.t1_quantity}{row.t1_quantity ? ` (${row.t1_quantity} settling)` : ""}</Td>
              <Td className="tabular-nums">{price(row.average_price)}</Td>
              <Td className="tabular-nums">{price(row.close_price)}</Td>
            </tr>
          ))}
        </Table>
      ) : (
        <p className="text-[#94A3B8]">No holdings.</p>
      )}
      {account.orders.length ? <p className="text-xs text-[#94A3B8]">{account.orders.length} order(s) today in the account.</p> : null}
      <p className="text-xs text-[#64748B]">Read-only. Nothing on this site places orders yet.</p>
    </div>
  );
}

function PlanCard({ mode, onRun }: { mode: string; onRun: () => void }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const load = useCallback(() => {
    setPlan(null);
    setError(null);
    fetchApi<Plan>("/api/v1/live/plan").then(setPlan).catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load, mode]);
  async function act(path: string, body: object, question: string) {
    if (!window.confirm(question)) return;
    setPending(true);
    try {
      await postApi(path, { ...body, operator: "web-operator" });
      onRun();
      load();
    } catch (e) {
      setError(`${errorText(e)}. Reload the orders and try again.`);
    } finally {
      setPending(false);
    }
  }
  if (error) return <p className="text-sm text-[#EF4444]">{error}</p>;
  if (!plan) return <p className="text-sm text-[#94A3B8]">Working out the orders…</p>;
  if (plan.mode === "off") return <p className="text-sm text-[#94A3B8]">Mode is Off. Set it to Dry run to see the orders each rebalance would place.</p>;
  if (plan.detail === "no_proposal_yet") return <p className="text-sm text-[#94A3B8]">No month-end ranking yet.</p>;
  const orders = plan.orders ?? [];
  return (
    <div className="space-y-3 text-sm">
      <p className="text-[#94A3B8]">
        Ranking fixed at the close of {plan.decided_at_close}; orders for the open of {plan.trade_at_open_of}. Book {inr(plan.book)}, about {inr(plan.per_stock)} per stock.{" "}
        {plan.mode === "live" ? (
          <span className="font-semibold text-[#EF4444]">Live: these are sent to Zerodha only when you press Approve.</span>
        ) : (
          <span className="font-semibold text-[#F59E0B]">Dry run: nothing is sent to Zerodha.</span>
        )}
      </p>
      {plan.run_phase ? <p className="text-xs text-[#94A3B8]">This month: {PHASE[plan.run_phase] ?? plan.run_phase}.</p> : null}
      {plan.assumed_account ? <p className="text-xs text-[#F59E0B]">Not logged in to Zerodha, so this assumes an empty account holding the amount in cash.</p> : null}
      {orders.length ? (
        <Table head={["Order", "Stock", "Shares", "Close", "Limit", "Value"]} minWidth={520}>
          {orders.map((o) => (
            <tr key={`${o.side}-${o.symbol}`} className={o.blocked ? "opacity-50" : ""}>
              <Td className={o.side === "BUY" ? "text-[#22C55E]" : "text-[#EF4444]"}>{o.side === "BUY" ? "Buy" : "Sell"}</Td>
              <Td>{o.symbol}</Td>
              <Td className="tabular-nums">{o.quantity}</Td>
              <Td className="tabular-nums">{price(o.close)}</Td>
              <Td className="tabular-nums">{price(o.limit)}</Td>
              <Td className="tabular-nums">{inr(o.value)}{o.blocked ? ` (${o.blocked})` : ""}</Td>
            </tr>
          ))}
        </Table>
      ) : (
        <p className="text-[#94A3B8]">No orders.</p>
      )}
      {plan.totals && orders.length ? (
        <p className="text-xs text-[#94A3B8]">Buys up to {inr(plan.totals.buy)}, sells at least {inr(plan.totals.sell)}, charges about {inr(plan.totals.charges)}. Limits are the worst price accepted; fills are usually at the market price.</p>
      ) : null}
      {(plan.warnings ?? []).map((w) => (
        <p key={w} className="text-xs text-[#F59E0B]">{w}</p>
      ))}
      {plan.mode === "live" && plan.live_switch && !plan.run_phase ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={pending || plan.assumed_account || !orders.some((o) => !o.blocked)}
            onClick={() => void act("/api/v1/live/approve", { digest: plan.digest }, `Send these ${orders.filter((o) => !o.blocked).length} orders to Zerodha now? Buys up to ${inr(plan.totals?.buy)}.`)}
            className="rounded bg-[#DC2626] px-3 py-1 font-medium text-white disabled:opacity-50"
          >
            Approve and send
          </button>
          <button type="button" disabled={pending} onClick={() => void act("/api/v1/live/skip", {}, "Skip this month? No orders will be placed until next month-end.")} className="rounded border border-[#26303C] px-3 py-1 text-[#94A3B8]">
            Skip this month
          </button>
          {plan.assumed_account ? <span className="text-xs text-[#F59E0B]">Log in to Zerodha first.</span> : null}
        </div>
      ) : null}
    </div>
  );
}

function RunCard({ refreshKey }: { refreshKey: number }) {
  const [run, setRun] = useState<Run | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => {
    fetchApi<{ run: Run | null }>("/api/v1/live/run").then((body) => setRun(body.run)).catch(() => setRun(null));
  }, []);
  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [load, refreshKey]);
  async function stop() {
    if (!window.confirm("Cancel the strategy's open orders and switch Mode to Off?")) return;
    try {
      await postApi("/api/v1/live/stop", { operator: "web-operator" });
      setMessage("Stopped. Mode is Off.");
      load();
    } catch (e) {
      setMessage(errorText(e));
    }
  }
  const active = run && !["done", "stopped", "skipped"].includes(run.phase);
  return (
    <div className="space-y-3 text-sm">
      {run ? (
        <>
          <p>
            Rebalance of {run.decided}: <span className="font-semibold">{PHASE[run.phase] ?? run.phase}</span>
            {active ? ` (open orders are cancelled at ${new Date(run.deadline).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" })} IST)` : ""}
          </p>
          {run.orders.length ? (
            <Table head={["Order", "Stock", "Shares", "Filled", "Limit", "Avg price", "Status"]} minWidth={560}>
              {run.orders.map((o, k) => (
                <tr key={`${o.round}-${o.side}-${o.symbol}-${k}`}>
                  <Td>{o.side === "BUY" ? "Buy" : "Sell"}{o.round === "leftover" ? " (leftover)" : ""}</Td>
                  <Td>{o.symbol}</Td>
                  <Td className="tabular-nums">{o.quantity}</Td>
                  <Td className="tabular-nums">{o.filled}</Td>
                  <Td className="tabular-nums">{price(o.limit)}</Td>
                  <Td className="tabular-nums">{price(o.average_price)}</Td>
                  <Td>{o.status.toLowerCase()}</Td>
                </tr>
              ))}
            </Table>
          ) : null}
          {run.notes.map((n) => (
            <p key={n} className="text-xs text-[#94A3B8]">{n}</p>
          ))}
        </>
      ) : (
        <p className="text-[#94A3B8]">No rebalance has been sent yet.</p>
      )}
      <button type="button" onClick={() => void stop()} className="rounded border border-[#DC2626] px-3 py-1 text-[#FCA5A5]">
        Stop: cancel open orders and switch off
      </button>
      {message ? <p className="text-xs text-[#94A3B8]">{message}</p> : null}
    </div>
  );
}

function ZerodhaCard() {
  const [status, setStatus] = useState<ZerodhaStatus | null>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    const result = new URLSearchParams(window.location.search).get("zerodha");
    if (result && result !== "connected") setNote(result.replaceAll("_", " "));
    fetchApi<ZerodhaStatus>("/api/v1/zerodha/status").then(setStatus).catch(() => setStatus({ configured: false, authenticated: false }));
  }, []);
  if (!status) return <p className="text-sm text-[#94A3B8]">Checking Zerodha…</p>;
  if (!status.configured) {
    return <p className="text-sm text-[#94A3B8]">Zerodha is not set up on the server yet (ZERODHA_API_KEY and ZERODHA_API_SECRET of the Kite Personal app).</p>;
  }
  return (
    <div className="space-y-3">
      {note ? <p className="text-sm text-[#EF4444]">Login failed: {note}</p> : null}
      {status.authenticated ? (
        <>
          <p className="text-sm text-[#22C55E]">Logged in to Zerodha. The session ends at Zerodha&apos;s daily cut-off (about 06:00 IST).</p>
          <AccountView />
        </>
      ) : (
        <div className="space-y-2 text-sm">
          <p className="text-[#94A3B8]">Not logged in today. You log in on Zerodha&apos;s own page; this site never sees your password.</p>
          <a href="/api/zerodha/login" className="inline-block rounded bg-[#2563EB] px-3 py-1 font-medium text-white">Log in to Zerodha</a>
        </div>
      )}
    </div>
  );
}

export function LivePanel() {
  const { status } = useOperator();
  const [view, setView] = useState<SettingsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runKey, setRunKey] = useState(0);
  const operator = Boolean(status?.operator);
  useEffect(() => {
    if (!operator) return;
    fetchApi<SettingsView>("/api/v1/live/settings").then(setView).catch((e) => setError(errorText(e)));
  }, [operator]);
  if (!status) return null;
  if (!operator) {
    return (
      <Card title="Sign in">
        <p className="mb-2 text-sm text-[#94A3B8]">Settings and the Zerodha account are only for the owner.</p>
        <OperatorLogin />
      </Card>
    );
  }
  return (
    <>
      <Card title="Momentum live">
        {error ? <p className="text-sm text-[#EF4444]">{error}</p> : view ? <SettingsForm view={view} onSaved={setView} /> : <p className="text-sm text-[#94A3B8]">Loading…</p>}
      </Card>
      <Card title="Zerodha account">
        <ZerodhaCard />
      </Card>
      {view ? (
        <Card title="This month's orders">
          <PlanCard mode={`${view.settings.mode}-${view.updated_at ?? ""}`} onRun={() => setRunKey((k) => k + 1)} />
        </Card>
      ) : null}
      {view && view.settings.mode !== "off" ? (
        <Card title="Rebalance status">
          <RunCard refreshKey={runKey} />
        </Card>
      ) : null}
      <OperatorLogin />
    </>
  );
}
