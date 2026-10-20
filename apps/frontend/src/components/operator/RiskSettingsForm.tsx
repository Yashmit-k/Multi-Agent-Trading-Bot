"use client";

import { useState } from "react";
import { errorText, postApi } from "@/lib/api";
import { OperatorGate } from "@/components/operator/OperatorGate";

export type Bound = { key: string; label: string; min: string | null; max: string | null; default: string };
export type RiskSettingsView = { settings: Record<string, string | number | boolean>; bounds: Bound[]; updated_at: string | null; updated_by: string | null };

const HINT: Record<string, string> = {
  max_order_notional: "Largest single buy, in rupees. Hard ceiling Rs 1,00,000.",
  daily_entry_limit: "New buy orders the agents may place per IST day. 0 stops new entries.",
  max_open_positions: "Different stocks held at once.",
  max_per_sector: "Stocks from one NIFTY sector at once.",
  max_exposure_fraction: "Money invested as a fraction of starting cash, e.g. 0.30 = 30%.",
  max_per_stock: "Money in any one stock, including queued buys.",
  stop_loss_pct: "Exit if price falls this % below entry.",
  take_profit_pct: "Exit if price rises this % above entry.",
  auto_entries: "Off: agents can still exit holdings, but only you open new positions.",
  manager_review: "On: each agent BUY waits up to 240 s for the LLM portfolio manager, which can approve, shrink or veto it (never enlarge it). Off: the risk engine decides alone.",
  intraday_auto_entries: "Off by default: the exit-rules study found 5-minute entries lose about 0.4% a trade to charges. Swing entries and your manual orders are unaffected.",
};

export function RiskSettingsForm({ initial }: { initial: RiskSettingsView }) {
  const [view, setView] = useState(initial);
  const [draft, setDraft] = useState<Record<string, string | boolean>>(() =>
    Object.fromEntries(Object.entries(initial.settings).map(([key, value]) => [key, typeof value === "boolean" ? value : String(value)])),
  );
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, setPending] = useState(false);

  async function save(values: Record<string, string | boolean>) {
    setPending(true);
    setMessage(null);
    try {
      const next = await postApi<RiskSettingsView>("/api/v1/settings/risk", { values, operator: "web-operator" });
      setView(next);
      setDraft(Object.fromEntries(Object.entries(next.settings).map(([key, value]) => [key, typeof value === "boolean" ? value : String(value)])));
      setMessage({ ok: true, text: "Saved. The worker uses these from its next cycle (within a minute)." });
    } catch (error) {
      setMessage({ ok: false, text: errorText(error) });
    } finally {
      setPending(false);
    }
  }

  return (
    <OperatorGate what="change risk limits">
      {(operator) => (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void save(draft);
          }}
          className="space-y-3"
        >
          <div className="grid gap-3 md:grid-cols-2">
            {view.bounds.map((bound) => (
              <label key={bound.key} className="block rounded border border-[#26303C] bg-[#0F141B] p-3 text-sm">
                <span className="font-medium">{bound.label}</span>
                {bound.min === null ? (
                  <span className="mt-2 flex items-center gap-2">
                    <input
                      type="checkbox"
                      disabled={!operator}
                      checked={Boolean(draft[bound.key])}
                      onChange={(event) => setDraft({ ...draft, [bound.key]: event.target.checked })}
                    />
                    <span className="text-xs text-[#94A3B8]">{draft[bound.key] ? "on" : "off"}</span>
                  </span>
                ) : (
                  <input
                    type="number"
                    step="any"
                    min={bound.min ?? undefined}
                    max={bound.max ?? undefined}
                    disabled={!operator}
                    value={String(draft[bound.key] ?? "")}
                    onChange={(event) => setDraft({ ...draft, [bound.key]: event.target.value })}
                    className="mt-2 w-full rounded border border-[#26303C] bg-[#0B0F14] px-2 py-1 font-mono disabled:opacity-60"
                  />
                )}
                <span className="mt-1 block text-xs text-[#64748B]">
                  {HINT[bound.key]} {bound.min !== null ? `Allowed ${bound.min}–${bound.max}; default ${bound.default}.` : `Default ${bound.default}.`}
                </span>
              </label>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" disabled={!operator || pending} className="rounded bg-[#2563EB] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">
              Save limits
            </button>
            <button
              type="button"
              disabled={!operator || pending}
              onClick={() => void save(Object.fromEntries(view.bounds.map((bound) => [bound.key, bound.min === null ? bound.default === "true" : bound.default])))}
              className="rounded border border-[#26303C] px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Reset to defaults
            </button>
            {message ? <span className={`text-sm ${message.ok ? "text-[#22C55E]" : "text-[#EF4444]"}`}>{message.text}</span> : null}
          </div>
          <p className="text-xs text-[#64748B]">
            {view.updated_at ? `Last changed ${new Date(view.updated_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST by ${view.updated_by}.` : "Never changed: defaults in force."} Paper trading only; these
            limits cannot enable live orders.
          </p>
        </form>
      )}
    </OperatorGate>
  );
}
