"use client";

import { useEffect, useState } from "react";
import { errorText, fetchApi, postApi } from "@/lib/api";
import { Badge, Card } from "@/components/ui";
import { OperatorLogin, useOperator } from "@/components/operator/OperatorGate";
import { GroupEditor, OperandPicker } from "@/components/strategy/ConditionEditor";
import { LabResults } from "@/components/strategy/LabResults";
import {
  BLANK,
  INTRADAY,
  TIMEFRAMES,
  operandText,
  ruleText,
  withDefaults,
  type ActiveStrategy,
  type Catalog,
  type Definition,
  type LabResult,
  type Saved,
  type TargetSpec,
  type Timeframe,
} from "@/components/strategy/types";

const box = "rounded border border-[#26303C] bg-[#0B0F14] px-2 py-1 text-sm disabled:opacity-60";
const daysAgo = (days: number) => new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
const label = "text-xs text-[#94A3B8]";

function Num({ text, value, onChange, hint, step = "any", optional = false, width = "w-28" }: { text: string; value: number | null | undefined; onChange: (next: number | null) => void; hint?: string; step?: string; optional?: boolean; width?: string }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className={label}>{text}</span>
      <input type="number" step={step} className={`${box} ${width}`} value={value === null || value === undefined ? "" : String(value)} placeholder={optional ? "off" : undefined} onChange={(event) => onChange(event.target.value === "" ? (optional ? null : 0) : Number(event.target.value))} />
      {hint ? <span className="text-[10px] text-[#64748B]">{hint}</span> : null}
    </label>
  );
}

function ApplyDialog({ definition, catalog, onCancel, onConfirm, pending }: { definition: Definition; catalog: Catalog; onCancel: () => void; onConfirm: () => void; pending: boolean }) {
  const [understood, setUnderstood] = useState(false);
  const targets = definition.targets.length
    ? definition.targets.map((t) => `${Math.round(t.fraction * 100)}% at ${t.value}${t.kind === "percent" ? "%" : t.kind === "atr" ? "× ATR" : "R"}`).join(", ")
    : "none";
  const stop =
    definition.stop.kind === "percent"
      ? `${definition.stop.value}% below entry`
      : definition.stop.kind === "atr"
        ? `${definition.stop.value}× ATR(${definition.stop.period})`
        : definition.stop.kind === "level" && definition.stop.level
          ? `at ${operandText(definition.stop.level, catalog.operands)}${definition.stop.buffer_pct ? ` minus ${definition.stop.buffer_pct}%` : ""}`
          : "none";
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="apply-title" className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-[12px] border border-[#26303C] bg-[#0F141B] p-5 text-sm">
        <h2 id="apply-title" className="text-base font-semibold">
          Apply “{definition.name}” to paper trading?
        </h2>
        <dl className="mt-3 grid grid-cols-[120px_1fr] gap-x-3 gap-y-1.5 text-xs">
          <dt className="text-[#94A3B8]">Bars</dt>
          <dd>{TIMEFRAMES.find(([tf]) => tf === definition.timeframe)?.[1]}</dd>
          <dt className="text-[#94A3B8]">Stocks</dt>
          <dd>{definition.symbols.includes("ALL") ? "All NIFTY 50" : definition.symbols.join(", ")}</dd>
          <dt className="text-[#94A3B8]">Buy when</dt>
          <dd>{ruleText(definition.entry, catalog.operands)}</dd>
          <dt className="text-[#94A3B8]">Sell when</dt>
          <dd>{definition.exit ? ruleText(definition.exit, catalog.operands) : "no exit rule"}</dd>
          <dt className="text-[#94A3B8]">Stop</dt>
          <dd>{stop}</dd>
          <dt className="text-[#94A3B8]">Targets</dt>
          <dd>
            {targets}
            {definition.breakeven_after_first_target ? "; stop to breakeven after the first" : ""}
          </dd>
          <dt className="text-[#94A3B8]">Trailing / time</dt>
          <dd>
            {definition.trailing ? `trail ${definition.trailing.value}${definition.trailing.kind === "percent" ? "%" : "× ATR"}` : "no trailing stop"}
            {definition.max_hold_bars ? `; max ${definition.max_hold_bars} bars` : ""}
            {definition.square_off_intraday ? "; squared off at 15:15" : ""}
          </dd>
          <dt className="text-[#94A3B8]">Size</dt>
          <dd>{definition.sizing.kind === "notional" ? `₹${definition.sizing.value.toLocaleString("en-IN")} per trade` : `${definition.sizing.value}% of starting cash at risk per trade`}</dd>
        </dl>
        <div className="mt-4 rounded border border-[#F59E0B]/40 bg-[#F59E0B]/10 p-3 text-xs text-[#FCD34D]">
          <p className="font-semibold">What changes</p>
          <ul className="mt-1 list-disc space-y-1 pl-4">
            <li>The agents stop opening new positions. This strategy opens them instead, when its buy rule is true on a just-completed bar.</li>
            <li>Its positions exit by its own stop, targets, trailing stop, time limits and sell rule. Positions the agents already hold keep exiting as before.</li>
            <li>Your Settings limits still apply to every order (per-order cap, entries per day, positions, sector, exposure). Entries are CNC limit orders at the latest price + 0.25%, so fills can differ from the backtest.</li>
            <li>Paper money only. Nothing is sent to Zerodha. You can stop applying it at any time.</li>
          </ul>
        </div>
        <label className="mt-3 flex items-start gap-2 text-xs">
          <input type="checkbox" checked={understood} onChange={(event) => setUnderstood(event.target.checked)} />I understand this replaces the agents’ entries in my paper account.
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="rounded border border-[#26303C] px-3 py-1.5" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" disabled={!understood || pending} className="rounded bg-[#16A34A] px-3 py-1.5 font-medium text-white disabled:opacity-50" onClick={onConfirm}>
            {pending ? "Applying…" : "Confirm and apply"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function ActiveStrategyBanner({ active, onStopped }: { active: ActiveStrategy; onStopped?: () => void }) {
  const { status } = useOperator();
  const [error, setError] = useState<string | null>(null);
  if (!active) {
    return <p className="rounded border border-[#26303C] bg-[#0F141B] p-3 text-xs text-[#94A3B8]">No strategy applied: the agents open paper positions. Save a strategy below and choose “Apply to paper trading”.</p>;
  }
  return (
    <div className="flex flex-wrap items-center gap-3 rounded border border-[#16A34A]/50 bg-[#16A34A]/10 p-3 text-sm">
      <Badge tone="up">Applied to paper trading</Badge>
      <span className="font-semibold">{active.name}</span>
      <span className="text-xs text-[#94A3B8]">
        {active.timeframe} · {active.symbols.includes("ALL") ? "all NIFTY 50" : active.symbols.join(", ")} · since {active.applied_at ? new Date(active.applied_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) : "—"} IST
      </span>
      <span className="w-full text-xs text-[#CBD5E1]">Buy when: {active.entry}</span>
      {status?.operator ? (
        <button
          type="button"
          className="rounded border border-[#26303C] px-2 py-1 text-xs hover:border-[#EF4444]"
          onClick={() => {
            if (!window.confirm(`Stop applying "${active.name}"? The agents will open new positions again. Positions this strategy opened keep its exits until they close.`)) return;
            postApi("/api/v1/strategies/active/stop", { confirm: true, operator: "web-operator" })
              .then(() => onStopped?.())
              .catch((err) => setError(errorText(err)));
          }}
        >
          Stop applying
        </button>
      ) : null}
      {error ? <span className="text-xs text-[#EF4444]">{error}</span> : null}
    </div>
  );
}

export function StrategyLab({ catalog, saved: initialSaved, active: initialActive }: { catalog: Catalog; saved: Saved[]; active: ActiveStrategy }) {
  const { status } = useOperator();
  const operator = Boolean(status?.operator);
  const [saved, setSaved] = useState(initialSaved);
  const [active, setActive] = useState<ActiveStrategy>(initialActive);
  const [definition, setDefinition] = useState<Definition>(withDefaults((catalog.templates[0] as Record<string, unknown>) ?? BLANK));
  const [strategyId, setStrategyId] = useState<string | null>(null);
  const [runs, setRuns] = useState<Saved["runs"]>([]);
  const [start, setStart] = useState(daysAgo(730));
  const [end, setEnd] = useState(daysAgo(0));
  const [result, setResult] = useState<LabResult | null>(null);
  const [scan, setScan] = useState<{ matches: Array<{ symbol: string; close: number; bar_end: string }>; scanned: number } | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const set = <K extends keyof Definition>(key: K, value: Definition[K]) => setDefinition((current) => ({ ...current, [key]: value }));
  const intraday = INTRADAY.includes(definition.timeframe);
  const allSymbols = definition.symbols.includes("ALL");
  const limits = catalog.limits;
  const maxSymbols = limits.max_intraday_symbols ?? limits.max_5m_symbols ?? 10;

  useEffect(() => {
    if (!intraday && definition.square_off_intraday) set("square_off_intraday", false);
    if (!intraday && definition.direction === "short") set("direction", "long");
  }, [intraday]); // eslint-disable-line react-hooks/exhaustive-deps

  function load(raw: Record<string, unknown>, id: string | null, keptRuns: Saved["runs"] = []) {
    const next = withDefaults(raw);
    setDefinition(next);
    setStrategyId(id);
    setRuns(keptRuns);
    setResult(null);
    setScan(null);
    setStart(INTRADAY.includes(next.timeframe) ? daysAgo(90) : daysAgo(730));
  }

  async function loadSaved(id: string) {
    if (!id) return;
    setPending("load");
    try {
      const found = await fetchApi<Saved>(`/api/v1/strategies/${id}`);
      load(found.definition, found.strategy_id, found.runs ?? []);
    } catch (error) {
      setMessage({ ok: false, text: errorText(error) });
    } finally {
      setPending(null);
    }
  }

  async function act(kind: "preview" | "save" | "save_run" | "scan" | "delete" | "apply") {
    setPending(kind);
    setMessage(null);
    try {
      if (kind === "preview") {
        setResult(await postApi<LabResult>("/api/v1/strategies/preview/backtest", { start, end, definition }, { timeoutMs: 90000 }));
        return;
      }
      if (kind === "delete") {
        if (!strategyId || !window.confirm(`Delete the saved strategy "${definition.name}"?`)) return;
        await postApi(`/api/v1/strategies/${strategyId}/delete`, {});
        setSaved(saved.filter((item) => item.strategy_id !== strategyId));
        setStrategyId(null);
        setRuns([]);
        setMessage({ ok: true, text: "Deleted." });
        return;
      }
      if (kind === "scan") {
        if (!strategyId) return;
        setScan(await fetchApi(`/api/v1/strategies/${strategyId}/scan`));
        return;
      }
      const stored = await postApi<Saved>("/api/v1/strategies", { strategy_id: strategyId, definition });
      setStrategyId(stored.strategy_id);
      setSaved([stored, ...saved.filter((item) => item.strategy_id !== stored.strategy_id)]);
      if (kind === "apply") {
        const view = await postApi<{ active: ActiveStrategy }>(`/api/v1/strategies/${stored.strategy_id}/apply`, { confirm: true, operator: "web-operator" });
        setActive(view.active);
        setConfirming(false);
        setMessage({ ok: true, text: `“${definition.name}” is now applied to paper trading. It opens positions from the next completed bar.` });
        return;
      }
      if (kind === "save_run") {
        setResult(await postApi<LabResult>(`/api/v1/strategies/${stored.strategy_id}/backtest`, { start, end }, { timeoutMs: 90000 }));
        const detail = await fetchApi<Saved>(`/api/v1/strategies/${stored.strategy_id}`);
        setRuns(detail.runs ?? []);
      }
      setMessage({ ok: true, text: kind === "save" ? "Saved." : "Saved and backtested; the run is kept below." });
    } catch (error) {
      setMessage({ ok: false, text: errorText(error) });
      if (kind === "apply") setConfirming(false);
    } finally {
      setPending(null);
    }
  }

  const liveBlockers = [
    definition.direction === "short" ? "short strategies are backtest-only (the paper engine trades long)" : null,
    definition.stop.kind === "none" ? "add a stop before applying it to paper trading" : null,
  ].filter(Boolean) as string[];

  const updateTarget = (index: number, patch: Partial<TargetSpec>) => set("targets", definition.targets.map((t, k) => (k === index ? { ...t, ...patch } : t)));

  return (
    <div className="space-y-3">
      <ActiveStrategyBanner active={active} onStopped={() => setActive(null)} />

      <Card title="1. Start from">
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className={label}>Template</span>
            <select className={box} defaultValue="" onChange={(event) => event.target.value !== "" && load(catalog.templates[Number(event.target.value)] as Record<string, unknown>, null)}>
              <option value="">Choose a template…</option>
              {catalog.templates.map((template, index) => (
                <option key={String(template.name)} value={index}>
                  {String(template.name)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={label}>Or a saved strategy</span>
            <select className={box} value={strategyId ?? ""} onChange={(event) => void loadSaved(event.target.value)}>
              <option value="">{saved.length ? "Choose…" : "None saved yet"}</option>
              {saved.map((item) => (
                <option key={item.strategy_id} value={item.strategy_id}>
                  {item.name}
                  {active?.strategy_id === item.strategy_id ? " (applied)" : ""}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="rounded border border-[#26303C] px-2 py-1 text-xs" onClick={() => load(BLANK as unknown as Record<string, unknown>, null)}>
            Blank strategy
          </button>
          <label className="flex flex-col gap-1">
            <span className={label}>Name</span>
            <input className={`${box} w-56`} value={definition.name} maxLength={120} onChange={(event) => set("name", event.target.value)} />
          </label>
          <label className="flex min-w-[240px] flex-1 flex-col gap-1">
            <span className={label}>Description</span>
            <input className={box} value={definition.description ?? ""} maxLength={2000} onChange={(event) => set("description", event.target.value)} />
          </label>
        </div>
      </Card>

      <Card title="2. What to trade">
        <div className="flex flex-wrap items-start gap-4 text-sm">
          <label className="flex flex-col gap-1">
            <span className={label}>Bars</span>
            <select
              className={box}
              value={definition.timeframe}
              onChange={(event) => {
                const timeframe = event.target.value as Timeframe;
                const toIntraday = INTRADAY.includes(timeframe);
                setDefinition((current) => ({ ...current, timeframe, symbols: toIntraday && current.symbols.includes("ALL") ? catalog.universe.slice(0, 5) : current.symbols, square_off_intraday: toIntraday ? current.square_off_intraday : false }));
                setStart(toIntraday ? daysAgo(90) : daysAgo(730));
              }}
            >
              {TIMEFRAMES.map(([tf, text]) => (
                <option key={tf} value={tf}>
                  {text}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={label}>Direction</span>
            <select className={box} value={definition.direction} onChange={(event) => setDefinition((current) => ({ ...current, direction: event.target.value as "long" | "short", square_off_intraday: event.target.value === "short" ? true : current.square_off_intraday }))}>
              <option value="long">Long (buy)</option>
              <option value="short" disabled={!intraday}>
                Short (sell first){intraday ? "" : " — intraday only"}
              </option>
            </select>
            {definition.direction === "short" ? <span className="text-[10px] text-[#F59E0B]">Backtest only: intraday short, squared off at 15:15.</span> : null}
          </label>
          <div className="flex flex-col gap-1">
            <span className={label}>Stocks</span>
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={allSymbols} disabled={intraday} onChange={(event) => set("symbols", event.target.checked ? ["ALL"] : catalog.universe.slice(0, 5))} />
              All NIFTY 50 {intraday ? `(intraday tests: up to ${maxSymbols} stocks, ${limits.max_intraday_days ?? 400} days)` : ""}
            </label>
            {!allSymbols ? (
              <>
                <select multiple aria-label="Stocks" className={`${box} h-32 w-48`} value={definition.symbols} onChange={(event) => set("symbols", Array.from(event.target.selectedOptions).map((option) => option.value))}>
                  {catalog.universe.map((symbol) => (
                    <option key={symbol} value={symbol}>
                      {symbol}
                    </option>
                  ))}
                </select>
                <span className="text-[10px] text-[#64748B]">{definition.symbols.length} selected · Ctrl/⌘-click to pick several</span>
              </>
            ) : null}
          </div>
        </div>
      </Card>

      <Card title="3. Rules">
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-semibold">{definition.direction === "long" ? "Buy" : "Sell short"} when</h3>
            <p className="mb-1 text-xs text-[#64748B]">Checked at each bar’s close. Use groups for AND/OR logic, “timing…” for “for N bars” or “within N bars”, and “more…” on an operand for a higher timeframe, N bars ago, or math (× and +).</p>
            <GroupEditor group={definition.entry} catalog={catalog.operands} timeframe={definition.timeframe} onChange={(next) => set("entry", next)} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold">Exit rule</h3>
              <label className="flex items-center gap-1 text-xs text-[#94A3B8]">
                <input
                  type="checkbox"
                  checked={definition.exit !== null}
                  onChange={(event) => set("exit", event.target.checked ? { logic: "any", items: [{ left: { indicator: "rsi", period: 14 }, op: ">", right: { value: 70 } }] } : null)}
                />
                use an exit rule (fills at the next bar’s open)
              </label>
            </div>
            {definition.exit ? <GroupEditor group={definition.exit} catalog={catalog.operands} timeframe={definition.timeframe} onChange={(next) => set("exit", next)} /> : null}
          </div>
        </div>
      </Card>

      <Card title="4. Entry order">
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className={label}>Order type</span>
            <select className={box} value={definition.entry_order.type} onChange={(event) => set("entry_order", { ...definition.entry_order, type: event.target.value as "market" | "limit", price: event.target.value === "limit" ? definition.entry_order.price ?? { indicator: "swing_high", period: 2 } : null })}>
              <option value="market">Market: next bar’s open</option>
              <option value="limit">Limit: at a level (e.g. a retest)</option>
            </select>
          </label>
          {definition.entry_order.type === "limit" && definition.entry_order.price ? (
            <>
              <div className="flex flex-col gap-1">
                <span className={label}>Limit price (read at the signal bar)</span>
                <OperandPicker value={definition.entry_order.price} catalog={catalog.operands} timeframe={definition.timeframe} onChange={(price) => set("entry_order", { ...definition.entry_order, price })} />
              </div>
              <Num text="Valid for (bars)" value={definition.entry_order.valid_bars ?? 5} step="1" onChange={(v) => set("entry_order", { ...definition.entry_order, valid_bars: v ?? 5 })} width="w-20" />
            </>
          ) : null}
        </div>
      </Card>

      <Card title="5. Exits and risk">
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className={label}>Stop loss</span>
              <select className={box} value={definition.stop.kind} onChange={(event) => set("stop", { ...definition.stop, kind: event.target.value as Definition["stop"]["kind"], level: event.target.value === "level" ? definition.stop.level ?? { indicator: "swing_low", period: 2 } : definition.stop.level })}>
                <option value="none">None</option>
                <option value="percent">% from entry</option>
                <option value="atr">ATR multiple</option>
                <option value="level">At a level (swing low, lowest low, SuperTrend…)</option>
              </select>
            </label>
            {definition.stop.kind === "percent" || definition.stop.kind === "atr" ? <Num text={definition.stop.kind === "percent" ? "Stop %" : "× ATR"} value={definition.stop.value} onChange={(v) => set("stop", { ...definition.stop, value: v ?? 2 })} width="w-20" /> : null}
            {definition.stop.kind === "atr" ? <Num text="ATR period" value={definition.stop.period} step="1" onChange={(v) => set("stop", { ...definition.stop, period: v ?? 14 })} width="w-20" /> : null}
            {definition.stop.kind === "level" && definition.stop.level ? (
              <div className="flex flex-col gap-1">
                <span className={label}>Stop level (at the signal bar)</span>
                <OperandPicker value={definition.stop.level} catalog={catalog.operands} timeframe={definition.timeframe} allowNumber={false} onChange={(level) => set("stop", { ...definition.stop, level })} />
              </div>
            ) : null}
            {definition.stop.kind !== "none" ? <Num text="Extra buffer %" value={definition.stop.buffer_pct ?? 0} onChange={(v) => set("stop", { ...definition.stop, buffer_pct: v ?? 0 })} width="w-20" /> : null}
          </div>

          <div className="space-y-2">
            <span className={label}>Targets (up to 3; each sells part of the position; the rest exits by stop, trailing, time or rule)</span>
            {definition.targets.map((target, index) => (
              <div key={index} className="flex flex-wrap items-end gap-2">
                <span className="w-14 pb-1 text-xs text-[#64748B]">Target {index + 1}</span>
                <select className={box} value={target.kind} onChange={(event) => updateTarget(index, { kind: event.target.value as TargetSpec["kind"] })}>
                  <option value="r_multiple">R multiple (× stop distance)</option>
                  <option value="percent">% from entry</option>
                  <option value="atr">ATR multiple</option>
                </select>
                <Num text="Value" value={target.value} onChange={(v) => updateTarget(index, { value: v ?? 1 })} width="w-20" />
                <Num text="% of position" value={Math.round(target.fraction * 100)} step="1" onChange={(v) => updateTarget(index, { fraction: Math.max(1, Math.min(100, v ?? 100)) / 100 })} width="w-20" />
                <button type="button" className="pb-1 text-xs text-[#94A3B8] hover:text-[#EF4444]" onClick={() => set("targets", definition.targets.filter((_, k) => k !== index))}>
                  Remove
                </button>
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" disabled={definition.targets.length >= 3} className="rounded border border-dashed border-[#26303C] px-2 py-1 text-xs text-[#94A3B8] disabled:opacity-40" onClick={() => set("targets", [...definition.targets, { kind: "r_multiple", value: definition.targets.length + 1, fraction: 0.5, period: 14 }])}>
                + Target
              </button>
              <label className="flex items-center gap-1 text-xs text-[#94A3B8]">
                <input type="checkbox" checked={definition.breakeven_after_first_target} onChange={(event) => set("breakeven_after_first_target", event.target.checked)} />
                Move the stop to breakeven after the first target
              </label>
              {definition.targets.reduce((sum, t) => sum + t.fraction, 0) > 1.0001 ? <span className="text-xs text-[#EF4444]">Targets add up to more than 100%.</span> : null}
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className={label}>Trailing stop</span>
              <select className={box} value={definition.trailing?.kind ?? "off"} onChange={(event) => set("trailing", event.target.value === "off" ? null : { kind: event.target.value as "percent" | "atr", value: definition.trailing?.value ?? (event.target.value === "atr" ? 3 : 5), period: 14, activate_after_r: definition.trailing?.activate_after_r ?? 0 })}>
                <option value="off">Off</option>
                <option value="percent">% below the best price</option>
                <option value="atr">ATR multiple below the best price</option>
              </select>
            </label>
            {definition.trailing ? (
              <>
                <Num text={definition.trailing.kind === "percent" ? "Trail %" : "× ATR"} value={definition.trailing.value} onChange={(v) => set("trailing", { ...definition.trailing!, value: v ?? 3 })} width="w-20" />
                <Num text="Start after (R in profit)" value={definition.trailing.activate_after_r ?? 0} onChange={(v) => set("trailing", { ...definition.trailing!, activate_after_r: v ?? 0 })} width="w-24" />
              </>
            ) : null}
            <Num text="Max hold (bars)" value={definition.max_hold_bars} optional step="1" onChange={(v) => set("max_hold_bars", v)} hint={definition.timeframe === "1d" ? "trading days" : `${definition.timeframe} bars`} width="w-24" />
            {intraday ? (
              <>
                <label className="flex items-center gap-2 pb-1 text-xs text-[#94A3B8]">
                  <input type="checkbox" checked={definition.square_off_intraday} disabled={definition.direction === "short"} onChange={(event) => set("square_off_intraday", event.target.checked)} />
                  Square off at 15:15 IST (MIS charges)
                </label>
                <label className="flex flex-col gap-1">
                  <span className={label}>No new entries after (IST)</span>
                  <input type="time" className={box} value={definition.last_entry_time ?? ""} onChange={(event) => set("last_entry_time", event.target.value || null)} />
                </label>
              </>
            ) : null}
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className={label}>Position size</span>
              <select className={box} value={definition.sizing.kind} onChange={(event) => set("sizing", { ...definition.sizing, kind: event.target.value as "notional" | "risk_percent", value: event.target.value === "notional" ? 20000 : 1 })}>
                <option value="notional">Fixed rupees per trade</option>
                <option value="risk_percent">Risk % of starting cash (needs a stop)</option>
              </select>
            </label>
            <Num text={definition.sizing.kind === "notional" ? "₹ per trade" : "Risk % per trade"} value={definition.sizing.value} onChange={(v) => set("sizing", { ...definition.sizing, value: v ?? 1 })} hint={definition.sizing.kind === "notional" ? "1,000 – 1,00,000" : "max 5%"} />
            {definition.sizing.kind === "risk_percent" ? <Num text="Max ₹ per trade" value={definition.sizing.max_notional ?? 100000} onChange={(v) => set("sizing", { ...definition.sizing, max_notional: v ?? 100000 })} /> : null}
            <Num text="Max open positions" value={definition.max_open_positions} step="1" onChange={(v) => set("max_open_positions", v ?? 10)} width="w-20" />
            <Num text="Starting cash ₹" value={definition.initial_cash} onChange={(v) => set("initial_cash", v ?? 500000)} />
            <Num text="Slippage (bp per fill)" value={definition.slippage_bps} onChange={(v) => set("slippage_bps", v ?? 5)} width="w-20" />
          </div>
        </div>
      </Card>

      <Card title="6. Backtest, save, apply">
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className={label}>From</span>
            <input type="date" className={box} value={start} min="2024-01-01" onChange={(event) => setStart(event.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={label}>To</span>
            <input type="date" className={box} value={end} onChange={(event) => setEnd(event.target.value)} />
          </label>
          <button type="button" disabled={pending !== null} onClick={() => void act("preview")} className="rounded bg-[#2563EB] px-3 py-1.5 font-medium text-white disabled:opacity-50">
            {pending === "preview" ? "Running…" : "Run backtest"}
          </button>
          <button type="button" disabled={!operator || pending !== null} onClick={() => void act("save")} className="rounded border border-[#26303C] px-3 py-1.5 disabled:opacity-50">
            Save
          </button>
          <button type="button" disabled={!operator || pending !== null} onClick={() => void act("save_run")} className="rounded border border-[#26303C] px-3 py-1.5 disabled:opacity-50">
            {pending === "save_run" ? "Running…" : "Save & keep this run"}
          </button>
          <button type="button" disabled={!strategyId || pending !== null} onClick={() => void act("scan")} className="rounded border border-[#26303C] px-3 py-1.5 disabled:opacity-50">
            Which stocks match now?
          </button>
          <button type="button" disabled={!operator || pending !== null || liveBlockers.length > 0} title={liveBlockers.join("; ")} onClick={() => setConfirming(true)} className="rounded bg-[#16A34A] px-3 py-1.5 font-medium text-white disabled:opacity-40">
            Apply to paper trading…
          </button>
          <button type="button" disabled={!operator || !strategyId || pending !== null} onClick={() => void act("delete")} className="rounded border border-[#26303C] px-3 py-1.5 text-[#EF4444] disabled:opacity-50">
            Delete
          </button>
        </div>
        {liveBlockers.length ? <p className="mt-2 text-xs text-[#F59E0B]">To apply to paper trading: {liveBlockers.join("; ")}.</p> : null}
        <p className="mt-2 text-xs text-[#64748B]">Data: stored Zerodha candles from January 2024. Anyone can run a backtest; saving and applying need the operator sign-in. Backtests never place orders.</p>
        {!operator ? (
          <div className="mt-2">
            <OperatorLogin compact />
          </div>
        ) : null}
        {message ? <p className={`mt-2 text-sm ${message.ok ? "text-[#22C55E]" : "text-[#EF4444]"}`}>{message.text}</p> : null}
        {scan ? (
          <div className="mt-3 text-sm">
            <p className="text-[#94A3B8]">
              {scan.matches.length} of {scan.scanned} stocks meet the buy rule on their latest completed bar:
            </p>
            <p className="mt-1">{scan.matches.length ? scan.matches.map((item) => `${item.symbol} (₹${item.close})`).join(", ") : "none right now"}</p>
          </div>
        ) : null}
      </Card>

      {runs && runs.length ? (
        <Card title="Kept runs of this strategy">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-[#64748B]">
              <tr>
                <th>Period</th>
                <th>Trades</th>
                <th>Net P&L</th>
                <th>Return</th>
                <th>Max DD</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.backtest_id} className="border-t border-[#1E2631]">
                  <td className="py-1">
                    {run.start} → {run.end}
                  </td>
                  <td>{run.metrics.trades}</td>
                  <td className={run.metrics.net_pnl >= 0 ? "text-[#22C55E]" : "text-[#EF4444]"}>₹{Math.round(run.metrics.net_pnl).toLocaleString("en-IN")}</td>
                  <td>{(run.metrics.total_return * 100).toFixed(1)}%</td>
                  <td>{(run.metrics.max_drawdown * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : null}

      {result ? <LabResults result={result} /> : null}
      {confirming ? <ApplyDialog definition={definition} catalog={catalog} pending={pending === "apply"} onCancel={() => setConfirming(false)} onConfirm={() => void act("apply")} /> : null}
    </div>
  );
}
