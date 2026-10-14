import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

type AgentRow = {
  agent_name: string;
  enabled: boolean;
  mode: string;
  feature_version: string;
  last_signal_at: string | null;
  sink: string;
  service_status?: string;
  reason?: string;
};

type SignalRow = {
  agent_name: string;
  symbol: string;
  horizon: string;
  signal: number;
  confidence: number;
  timestamp: string;
  reasoning?: string;
};

const KIND: Record<string, string> = {
  technical: "Quant · deterministic rules",
  momentum: "Quant · deterministic rules",
  mean_reversion: "Quant · deterministic rules",
  volume: "Quant · deterministic rules",
  regime: "Quant · deterministic rules",
  ml: "Quant · ML model (not loaded)",
  news: "Intelligence · LLM",
  fundamental: "Intelligence · LLM",
  valuation: "Intelligence · LLM",
  earnings: "Intelligence · LLM",
};

function latestByAgent(signals: SignalRow[]): Map<string, SignalRow> {
  const latest = new Map<string, SignalRow>();
  for (const signal of signals) {
    const current = latest.get(signal.agent_name);
    if (!current || signal.timestamp > current.timestamp) latest.set(signal.agent_name, signal);
  }
  return latest;
}

export default async function AgentsPage() {
  try {
    const agents = await fetchApi<AgentRow[]>("/api/v1/agents");
    const signals = await fetchApi<SignalRow[]>("/api/v1/signals/latest").catch(() => [] as SignalRow[]);
    const latest = latestByAgent(signals);
    return (
      <PageFrame
        title="Agents"
        description="Every agent returns the same shape: a score from -1 to +1, a confidence from 0 to 1, and its reasoning. No agent places an order."
      >
        <div className="grid gap-3 md:grid-cols-2">
          {agents.map((agent) => {
            const last = latest.get(agent.agent_name);
            return (
              <section key={agent.agent_name} className="rounded border border-[#26303C] bg-[#0F141B] p-3 text-sm">
                <div className="flex items-baseline justify-between gap-2">
                  <h2 className="font-semibold">{agent.agent_name}</h2>
                  <span className={agent.enabled ? "text-[#22C55E]" : "text-[#94A3B8]"}>{agent.enabled ? "enabled" : "disabled"}</span>
                </div>
                <div className="text-xs text-[#94A3B8]">
                  {KIND[agent.agent_name] ?? "agent"} · {agent.mode} · features {agent.feature_version}
                  {agent.reason ? ` · ${agent.reason}` : ""}
                </div>
                {last ? (
                  <div className="mt-2 text-xs">
                    <div>
                      Latest: <b>{last.symbol}</b> {last.horizon} · score {last.signal.toFixed(2)} · confidence {last.confidence.toFixed(2)}
                    </div>
                    <div className="text-[#64748B]">{last.timestamp}</div>
                    {last.reasoning ? <p className="mt-1 text-[#CBD5E1]">{last.reasoning}</p> : null}
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-[#94A3B8]">No stored signal from this agent.</p>
                )}
              </section>
            );
          })}
        </div>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Agents">
        <ErrorState message={error instanceof Error ? error.message : "agents_unavailable"} />
      </PageFrame>
    );
  }
}
