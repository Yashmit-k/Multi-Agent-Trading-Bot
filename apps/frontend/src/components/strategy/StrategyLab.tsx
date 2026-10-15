"use client";

import { useState } from "react";
import { errorText, fetchApi, postApi } from "@/lib/api";
import { Card } from "@/components/ui";
import { useOperator, OperatorLogin } from "@/components/operator/OperatorGate";
import { ConditionList } from "@/components/strategy/ConditionEditor";
import { LabResults } from "@/components/strategy/LabResults";
import { BLANK, withDefaults, type Catalog, type Definition, type LabResult, type Saved } from "@/components/strategy/types";

const box = "rounded border border-[#26303C] bg-[#0B0F14] px-2 py-1 text-sm disabled:opacity-60";
const daysAgo = (days: number) => new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);

function NumberField({ label, value, onChange, hint, step = "any", optional = false }: { label: string; value: number | null; onChange: (next: number | null) => void; hint?: string; step?: string; optional?: boolean }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-xs text-[#94A3B8]">{label}</span>
      <input
        type="number"
        step={step}
        className={`${box} w-36`}
        value={value === null ? "" : String(value)}
        placeholder={optional ? "off" : undefined}
        onChange={(event) => onChange(event.target.value === "" ? (optional ? null : 0) : Number(event.target.value))}
      />
      {hint ? <span className="text-[10px] text-[#64748B]">{hint}</span> : null}
    </label>
  );
}

export function StrategyLab({ catalog, saved: initialSaved }: { catalog: Catalog; saved: Saved[] }) {
  const { status } = useOperator();
  const operator = Boolean(status?.operator);
  const [saved, setSaved] = useState(initialSaved);
  const [definition, setDefinition] = useState<Definition>(withDefaults(catalog.templates[0] ?? BLANK));
  const [strategyId, setStrategyId] = useState<string | null>(null);
  const [runs, setRuns] = useState<Saved["runs"]>([]);
  const [start, setStart] = useState(daysAgo(730));
  const [end, setEnd] = useState(daysAgo(0));
  const [result, setResult] = useState<LabResult | null>(null);
  const [scan, setScan] = useState<{ matches: Array<{ symbol: string; close: number; bar_end: string }>; scanned: number } | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  const set = <K extends keyof Definition>(key: K, value: Definition[K]) => setDefinition({ ...definition, [key]: value });
  const allSymbols = definition.symbols.includes("ALL");

  function loadTemplate(index: number) {
    const template = catalog.templates[index];
    if (!template) return;
    setDefinition(withDefaults(template));
    setStrategyId(null);
    setRuns([]);
    setResult(null);
    setScan(null);
    if (template.timeframe === "5m") setStart(daysAgo(90));
    else setStart(daysAgo(730));
  }

  async function loadSaved(id: string) {
    if (!id) return;
    setPending("load");
    try {
      const found = await fetchApi<Saved>(`/api/v1/strategies/${id}`);
      setDefinition(withDefaults(found.definition));
      setStrategyId(found.strategy_id);
      setRuns(found.runs ?? []);
      setResult(null);
      setScan(null);
    } catch (error) {
      setMessage({ ok: false, text: errorText(error) });
    } finally {
      setPending(null);
    }
  }

  async function act(kind: "preview" | "save" | "save_run" | "scan" | "delete") {
    setPending(kind);
    setMessage(null);
    try {
      if (kind === "preview") {
        setResult(await postApi<LabResult>("/api/v1/strategies/preview/backtest", { start, end, definition }, { timeoutMs: 60000 }));
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
      if (kind === "save_run") {
        const run = await postApi<LabResult>(`/api/v1/strategies/${stored.strategy_id}/backtest`, { start, end }, { timeoutMs: 60000 });
        setResult(run);
        const detail = await fetchApi<Saved>(`/api/v1/strategies/${stored.strategy_id}`);
        setRuns(detail.runs ?? []);
      }
      setMessage({ ok: true, text: kind === "save" ? "Saved." : "Saved and backtested; the run is kept below." });
    } catch (error) {
      setMessage({ ok: false, text: errorText(error) });
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="space-y-3">
      <Card title="1. Start from">
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Template</span>
            <select className={box} defaultValue="0" onChange={(event) => loadTemplate(Number(event.target.value))}>
              {catalog.templates.map((template, index) => (
                <option key={String(template.name)} value={index}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Or a saved strategy</span>
            <select className={box} value={strategyId ?? ""} onChange={(event) => void loadSaved(event.target.value)}>
              <option value="">{saved.length ? "Choose…" : "None saved yet"}</option>
              {saved.map((item) => (
                <option key={item.strategy_id} value={item.strategy_id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Name</span>
            <input className={`${box} w-56`} value={definition.name} maxLength={120} onChange={(event) => set("name", event.target.value)} />
          </label>
          <label className="flex min-w-[240px] flex-1 flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Description</span>
            <input className={box} value={definition.description ?? ""} maxLength={1000} onChange={(event) => set("description", event.target.value)} />
          </label>
        </div>
      </Card>

      <Card title="2. What to trade">
        <div className="flex flex-wrap items-start gap-4 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Bars</span>
            <select
              className={box}
              value={definition.timeframe}
              onChange={(event) => {
                const timeframe = event.target.value as "1d" | "5m";
                setDefinition({ ...definition, timeframe, symbols: timeframe === "5m" && allSymbols ? catalog.universe.slice(0, 5) : definition.symbols, square_off_intraday: timeframe === "5m" });
                if (timeframe === "5m") setStart(daysAgo(90));
              }}
            >
              <option value="1d">Daily (swing)</option>
              <option value="5m">5-minute (intraday)</option>
            </select>
          </label>
          <div className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Stocks</span>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={allSymbols}
                disabled={definition.timeframe === "5m"}
                onChange={(event) => set("symbols", event.target.checked ? ["ALL"] : catalog.universe.slice(0, 5))}
              />
              All NIFTY 50 {definition.timeframe === "5m" ? `(5-minute tests: up to ${catalog.limits.max_5m_symbols} stocks, ${catalog.limits.max_5m_days} days)` : ""}
            </label>
            {!allSymbols ? (
              <select
                multiple
                aria-label="Stocks"
                className={`${box} h-32 w-48`}
                value={definition.symbols}
                onChange={(event) => set("symbols", Array.from(event.target.selectedOptions).map((option) => option.value))}
              >
                {catalog.universe.map((symbol) => (
                  <option key={symbol} value={symbol}>
                    {symbol}
                  </option>
                ))}
              </select>
            ) : null}
            {!allSymbols ? <span className="text-[10px] text-[#64748B]">{definition.symbols.length} selected · Ctrl/⌘-click to pick several</span> : null}
          </div>
        </div>
      </Card>

      <Card title="3. Rules">
        <div className="space-y-4">
          <ConditionList title="Entry: buy when ALL of these are true" hint="Checked on each bar's close; the buy fills at the next bar's open." conditions={definition.entry} onChange={(next) => set("entry", next)} catalog={catalog.operands} minimum={1} />
          <ConditionList title="Exit: sell when ANY of these is true" hint="Optional. Stops, targets and time limits below also exit." conditions={definition.exit} onChange={(next) => set("exit", next)} catalog={catalog.operands} minimum={0} />
        </div>
      </Card>

      <Card title="4. Risk and sizing">
        <div className="flex flex-wrap gap-4">
          <NumberField label="Stop loss %" value={definition.stop_loss_pct} optional onChange={(value) => set("stop_loss_pct", value)} hint="blank = no stop" />
          <NumberField label="Take profit %" value={definition.take_profit_pct} optional onChange={(value) => set("take_profit_pct", value)} hint="blank = no target" />
          <NumberField label="Max hold (bars)" value={definition.max_hold_bars} optional step="1" onChange={(value) => set("max_hold_bars", value)} hint={definition.timeframe === "1d" ? "days" : "5-minute bars"} />
          <NumberField label="Money per trade ₹" value={definition.position_notional} onChange={(value) => set("position_notional", value ?? 20000)} hint="1,000 – 1,00,000" />
          <NumberField label="Max open positions" value={definition.max_open_positions} step="1" onChange={(value) => set("max_open_positions", value ?? 10)} />
          <NumberField label="Starting cash ₹" value={definition.initial_cash} onChange={(value) => set("initial_cash", value ?? 500000)} />
          <NumberField label="Slippage (bp per fill)" value={definition.slippage_bps} onChange={(value) => set("slippage_bps", value ?? 5)} />
          {definition.timeframe === "5m" ? (
            <label className="flex items-center gap-2 self-center text-xs text-[#94A3B8]">
              <input type="checkbox" checked={definition.square_off_intraday} onChange={(event) => set("square_off_intraday", event.target.checked)} />
              Square off at 15:15 IST
            </label>
          ) : null}
        </div>
      </Card>

      <Card title="5. Backtest">
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">From</span>
            <input type="date" className={box} value={start} min="2024-01-01" onChange={(event) => setStart(event.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">To</span>
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
            Which stocks match today?
          </button>
          <button type="button" disabled={!operator || !strategyId || pending !== null} onClick={() => void act("delete")} className="rounded border border-[#26303C] px-3 py-1.5 text-[#EF4444] disabled:opacity-50">
            Delete
          </button>
        </div>
        <p className="mt-2 text-xs text-[#64748B]">
          Data: stored Zerodha candles from January 2024. Anyone can run a backtest; saving needs the operator sign-in. Backtests never place orders.
        </p>
        {!operator ? (
          <div className="mt-2">
            <OperatorLogin compact />
          </div>
        ) : null}
        {message ? <p className={`mt-2 text-sm ${message.ok ? "text-[#22C55E]" : "text-[#EF4444]"}`}>{message.text}</p> : null}
        {scan ? (
          <div className="mt-3 text-sm">
            <p className="text-[#94A3B8]">
              {scan.matches.length} of {scan.scanned} stocks meet every entry rule on their latest bar:
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
    </div>
  );
}
