"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { provenance, sourceLabel } from "@/lib/signal-provenance";

export type TraceEvent = {
  event_id: string;
  event_type: string;
  recorded_at: string;
  timestamp: string | null;
  channel: string | null;
  source: string | null;
  agent: string | null;
  symbol: string | null;
  correlation_id: string;
  payload: Record<string, unknown>;
};

type TraceResponse = { count: number; live_enabled: boolean; events: TraceEvent[] };

export const LANES: Array<{ key: string; label: string; kind: string }> = [
  { key: "technical", label: "Technical", kind: "Quant (rules)" },
  { key: "momentum", label: "Momentum", kind: "Quant (rules)" },
  { key: "mean_reversion", label: "Mean reversion", kind: "Quant (rules)" },
  { key: "volume", label: "Volume", kind: "Quant (rules)" },
  { key: "regime", label: "Regime", kind: "Quant (rules)" },
  { key: "news", label: "News", kind: "Intelligence (LLM)" },
  { key: "fundamental", label: "Fundamental", kind: "Intelligence (LLM)" },
  { key: "valuation", label: "Valuation", kind: "Intelligence (LLM)" },
  { key: "earnings", label: "Earnings", kind: "Intelligence (LLM)" },
  { key: "decision.created", label: "Fusion + Decision", kind: "Core (code)" },
  { key: "risk", label: "Risk engine", kind: "Core (code)" },
  { key: "order", label: "Paper execution", kind: "Core (code)" },
];

export function laneOf(event: TraceEvent): string {
  if (event.event_type === "agent.signal") return event.agent ?? "unknown";
  if (event.event_type === "decision.created") return "decision.created";
  if (event.event_type.startsWith("risk.")) return "risk";
  return "order";
}

export function describe(event: TraceEvent): string {
  const p = event.payload ?? {};
  switch (event.event_type) {
    case "agent.signal":
      return `${p.horizon ?? ""} score ${num(p.signal)} · conf ${num(p.confidence)}`;
    case "decision.created":
      return `${p.side} ${p.quantity} @ ${p.entry_price} · fused ${num(p.aggregated_signal)} from ${(p.supporting_signal_ids as unknown[] | undefined)?.length ?? 0} signals`;
    case "risk.approved":
    case "risk.rejected": {
      const checks = (p.checks as Array<{ name: string; passed: boolean }> | undefined) ?? [];
      const failed = checks.filter((check) => !check.passed).map((check) => check.name);
      return `${p.status}${failed.length ? ` · failed ${failed.join(", ")}` : ` · ${checks.length} checks passed`}`;
    }
    case "order.filled":
      return `filled ${p.quantity} @ ${p.price} · fees ${p.fees}`;
    case "position.updated":
      return `position ${p.quantity} @ ${p.average_price}`;
    default:
      return `${p.side ?? ""} ${p.quantity ?? ""} ${p.status ?? ""}`.trim();
  }
}

function num(value: unknown): string {
  return typeof value === "number" ? value.toFixed(2) : String(value ?? "—");
}

function time(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour12: false });
}

const loadTrace = (key: string) => fetchApi<TraceResponse>(key);

export function AgentTrace({ excluded = [] }: { excluded?: string[] }) {
  const [filter, setFilter] = useState<string>("all");
  const [chain, setChain] = useState<string | null>(null);
  const { data, error, isLoading } = useSWR("/api/v1/trace?limit=300", loadTrace, { refreshInterval: 10000 });
  const chainKey = chain ? `/api/v1/trace/${encodeURIComponent(chain)}` : null;
  const { data: chainData } = useSWR(chainKey, loadTrace);

  const events = useMemo(() => {
    const all = data?.events ?? [];
    return filter === "all" ? all : all.filter((event) => laneOf(event) === filter);
  }, [data, filter]);

  const counts = useMemo(() => {
    const totals = new Map<string, { count: number; last: string | null }>();
    for (const event of data?.events ?? []) {
      const lane = laneOf(event);
      const current = totals.get(lane) ?? { count: 0, last: null };
      totals.set(lane, { count: current.count + 1, last: current.last ?? event.timestamp });
    }
    return totals;
  }, [data]);

  if (error) return <ErrorState message={error instanceof Error ? error.message : "trace_unavailable"} />;
  if (isLoading || !data) return <p data-testid="loading" className="text-sm text-[#94A3B8]">Loading trace…</p>;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {LANES.map((lane) => {
          const stat = counts.get(lane.key);
          const active = filter === lane.key;
          return (
            <button
              key={lane.key}
              type="button"
              onClick={() => setFilter(active ? "all" : lane.key)}
              className={`rounded border px-3 py-2 text-left text-xs ${active ? "border-[#3B82F6] bg-[#13233B]" : "border-[#26303C] bg-[#0F141B]"}`}
            >
              <div className="font-semibold text-[#E6EDF3]">{lane.label}</div>
              <div className="text-[#94A3B8]">{lane.kind}</div>
              <div className="mt-1 text-[#E6EDF3]">{stat ? `${stat.count} msgs` : "no messages"}</div>
              <div className="text-[#64748B]">{stat ? time(stat.last) : "—"}</div>
              {excluded.includes(lane.key) ? <div className="text-[#F59E0B]">excluded from fusion</div> : null}
            </button>
          );
        })}
      </div>

      {chain && chainData ? (
        <section className="rounded border border-[#3B82F6] bg-[#0F141B] p-3">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-semibold">Handoff chain {chain.slice(0, 16)}…</span>
            <button type="button" className="text-xs text-[#94A3B8] underline" onClick={() => setChain(null)}>
              close
            </button>
          </div>
          <ol className="space-y-1 text-xs">
            {chainData.events.map((event) => (
              <li key={event.event_id}>
                <span className="text-[#64748B]">{time(event.timestamp)}</span> · <b>{event.event_type}</b> · {event.source} →{" "}
                <code>{event.channel}</code> · {describe(event)}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {events.length === 0 ? (
        <p data-testid="empty" className="text-sm text-[#94A3B8]">
          No bus messages recorded yet. The trace recorder stores messages as agents publish them.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-xs">
            <thead className="text-[#94A3B8]">
              <tr>
                <th className="py-1 pr-3">Time (IST)</th>
                <th className="pr-3">Event</th>
                <th className="pr-3">Producer</th>
                <th className="pr-3">Channel</th>
                <th className="pr-3">Symbol</th>
                <th className="pr-3">Content</th>
                <th>Chain</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.event_id} className="border-t border-[#26303C] align-top">
                  <td className="py-1 pr-3 whitespace-nowrap text-[#94A3B8]">{time(event.timestamp)}</td>
                  <td className="pr-3 whitespace-nowrap">{event.event_type}</td>
                  <td className="pr-3 whitespace-nowrap">{event.agent ? `${event.agent} agent` : event.source}</td>
                  <td className="pr-3">
                    <code>{event.channel}</code>
                  </td>
                  <td className="pr-3">{event.symbol ?? "—"}</td>
                  <td className="pr-3">
                    {describe(event)}
                    {event.event_type === "agent.signal" ? <SignalDetail event={event} excluded={excluded} /> : null}
                  </td>
                  <td>
                    <button type="button" className="text-[#60A5FA] underline" onClick={() => setChain(event.correlation_id)}>
                      view
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-[#64748B]">
        {data.count} most recent messages · refreshes every 10 s · PAPER only, live trading disabled.
      </p>
    </div>
  );
}

function SignalDetail({ event, excluded }: { event: TraceEvent; excluded: string[] }) {
  const p = provenance(event.payload);
  return (
    <div className="text-[#64748B]">
      {p.reasons.length ? <div>reasons: {p.reasons.join(", ")}</div> : null}
      <div>source: {sourceLabel(event.agent ?? "", event.payload)}</div>
      {p.headlines.slice(0, 2).map((item) => (
        <div key={item.title}>
          “{item.title}” <span className="text-[#475569]">({item.source})</span>
        </div>
      ))}
      {event.agent && excluded.includes(event.agent) ? <div className="text-[#F59E0B]">excluded from fusion: no live data feed, cannot affect trades</div> : null}
    </div>
  );
}
