export const metadata = { title: "Agents · StockX" };
import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Card, Table, Td } from "@/components/ui";
import { excludedAgents, provenance, sourceLabel } from "@/lib/signal-provenance";

export const dynamic = "force-dynamic";

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
  reason_codes?: string[];
  metadata?: Record<string, unknown>;
};

type ScoreRow = {
  agent: string;
  horizon: string;
  published: number;
  scored: number;
  directional: number;
  neutral: number;
  hit_rate: number | null;
  hit_rate_95: [number, number] | null;
  mean_signed_return_bps: number | null;
  information_coefficient: number | null;
  beats_coin_flip: boolean;
  proposals_supported: number;
  approved_supported: number;
  in_fusion: boolean;
};
type WeightRow = { agent: string; horizon: string; weight: number; basis: string; graded: number; version?: string | null };
type Scorecard = { as_of: string; window_days: number; agents: ScoreRow[]; fusion_weights?: { computed_at: string; detail: WeightRow[] } };

const BASIS: Record<string, string> = {
  better_than_coin_flip: "proven better than a coin flip",
  backtest_prior: "from the 2024-26 backtest (live record still short)",
  unproven: "unproven (current version)",
  worse_than_coin_flip: "proven worse: votes ignored",
  market_filter: "market filter, not a vote",
  excluded: "excluded from fusion",
};

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

function Verdict({ row }: { row: ScoreRow }) {
  if (row.directional < 30) return <Badge>too few ({row.directional})</Badge>;
  if (row.beats_coin_flip) return <Badge tone="up">beats coin flip</Badge>;
  if (row.hit_rate_95 && row.hit_rate_95[1] < 0.5) return <Badge tone="down">worse than coin flip</Badge>;
  return <Badge tone="warn">not distinguishable</Badge>;
}

function ScorecardTable({ card }: { card: Scorecard }) {
  return (
    <Card title={`Live scorecard · last ${card.window_days} days`}>
      <p className="mb-2 text-xs text-[#94A3B8]">
        Did the direction of each agent's live signals match what the stock did next? Intraday signals are checked against the price 60 minutes later; swing signals against
        the close of the next session. Repeated views on the same bar or session count once, and scores under ±0.05 count as neutral. A hit rate only means something when its
        95% interval clears 50%, and with days, not years, of live data most agents will not get there. Moves within one market day are correlated, so even the interval is
        optimistic.
      </p>
      <Table head={["Agent", "Horizon", "Scored", "Hit rate", "95% interval", "Avg signed move", "IC", "Proposals backed", "Approved", "Verdict", "Fusion weight"]} minWidth={1040}>
        {card.agents.map((row) => (
          <tr key={`${row.agent}-${row.horizon}`} className="border-t border-[#1E2631]">
            <Td>
              {row.agent}
              {row.in_fusion ? null : <span className="ml-1 text-[10px] text-[#F59E0B]">excluded</span>}
            </Td>
            <Td>{row.horizon}</Td>
            <Td>
              {row.directional}
              <span className="text-[#64748B]"> +{row.neutral} neutral</span>
            </Td>
            <Td>{row.hit_rate === null ? "—" : pct(row.hit_rate)}</Td>
            <Td>{row.hit_rate_95 ? `${pct(row.hit_rate_95[0])} – ${pct(row.hit_rate_95[1])}` : "—"}</Td>
            <Td>{row.mean_signed_return_bps === null ? "—" : `${row.mean_signed_return_bps.toFixed(1)} bp`}</Td>
            <Td>{row.information_coefficient === null ? "—" : row.information_coefficient.toFixed(3)}</Td>
            <Td>{row.proposals_supported}</Td>
            <Td>{row.approved_supported}</Td>
            <Td>
              <Verdict row={row} />
            </Td>
            <Td className="text-xs">
              {(() => {
                const weight = card.fusion_weights?.detail.find((item) => item.agent === row.agent && item.horizon === row.horizon);
                if (!weight) return <span className="text-[#64748B]">—</span>;
                return (
                  <span title={BASIS[weight.basis] ?? weight.basis}>
                    <b className={weight.weight === 0 ? "text-[#EF4444]" : weight.weight >= 1 ? "text-[#22C55E]" : "text-[#E6EDF3]"}>{weight.weight.toFixed(2)}</b>{" "}
                    <span className="text-[#64748B]">{BASIS[weight.basis] ?? weight.basis}</span>
                  </span>
                );
              })()}
            </Td>
          </tr>
        ))}
      </Table>
      <p className="mt-2 text-[10px] text-[#64748B]">
        Computed {new Date(card.as_of).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST, refreshed every 10 minutes. Fusion weights are set hourly by the worker from each
        agent&apos;s current version only (20 days, sample size discounted 5× because stocks move together): 0 = proven worse than a coin flip, 0.5 = unproven, 1.0–1.5 = proven better.
      </p>
    </Card>
  );
}

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
    const card = await fetchApi<Scorecard>("/api/v1/agents/scorecard").catch(() => null);
    const excluded = excludedAgents(process.env.FUSION_EXCLUDED_AGENTS);
    return (
      <PageFrame
        title="Agents"
        description="Every agent returns the same shape: a score from -1 to +1, a confidence from 0 to 1, and its reasons. No agent places an order."
      >
        {card ? <ScorecardTable card={card} /> : <p className="text-xs text-[#94A3B8]">Scorecard unavailable.</p>}
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {agents.map((agent) => {
            const last = latest.get(agent.agent_name);
            return (
              <section key={agent.agent_name} className="rounded border border-[#26303C] bg-[#0F141B] p-3 text-sm">
                <div className="flex items-baseline justify-between gap-2">
                  <h2 className="font-semibold">{agent.agent_name}</h2>
                  <span className={agent.enabled ? "text-[#22C55E]" : "text-[#94A3B8]"}>{agent.enabled ? "enabled" : "disabled"}</span>
                </div>
                {excluded.includes(agent.agent_name) ? (
                  <div className="text-xs text-[#F59E0B]">Excluded from fusion: no live data source, so it cannot influence trades.</div>
                ) : null}
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
                    <Detail signal={last} />
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

function Detail({ signal }: { signal: SignalRow }) {
  const p = provenance(signal as unknown as Record<string, unknown>);
  return (
    <div className="mt-1 space-y-0.5 text-[#CBD5E1]">
      {p.reasons.length ? <div>Reasons: {p.reasons.join(", ")}</div> : null}
      <div className="text-[#94A3B8]">Source: {sourceLabel(signal.agent_name, signal as unknown as Record<string, unknown>)}</div>
      {p.insufficient ? <div className="text-[#94A3B8]">Insufficient data for this symbol.</div> : null}
      {p.headlines.slice(0, 3).map((item) => (
        <div key={item.title}>
          “{item.title}” <span className="text-[#64748B]">({item.source})</span>
        </div>
      ))}
    </div>
  );
}
