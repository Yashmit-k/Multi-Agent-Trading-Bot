import { fetchApi } from "@/lib/api";
import type { ProvisionalRiskStatus, ProvisionalSystemStatus } from "@/api/generated/provisional";
import { ErrorState } from "@/components/States";
import { KillSwitchControl } from "@/components/KillSwitchControl";
import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Card, Empty, Score, Stat, SymbolLink, Table, Td } from "@/components/ui";
import { istTime, num, price } from "@/lib/format";
import { parseMode } from "@/lib/mode";

export const metadata = { title: "Risk · StockX" };
export const dynamic = "force-dynamic";

type Check = { name: string; passed: boolean; detail: string };
type ChainRow = {
  proposal: { proposal_id: string; symbol: string; side: string; quantity: number; entry_price: string; horizon: string; aggregated_signal: number; aggregated_confidence: number; timestamp: string; supporting_signal_ids: string[] };
  risk: { status: string; checks: Check[]; rejection_reason: string | null } | null;
  order: { status: string } | null;
};

const LIMITS = [
  ["Trading mode", "PAPER only — LIVE, SHADOW and BACKTEST are rejected inside the risk engine"],
  ["Per-order cap", "₹20,000 notional per BUY, fees reserved on top"],
  ["Daily entries", "At most 6 new entry orders per IST calendar day"],
  ["Entry window", "09:20–10:30 IST, with fresh 5-minute data for all 50 constituents"],
  ["Short selling", "Rejected — a SELL may not exceed shares held"],
  ["Brackets", "Stop −2 %, target +4 %; if both hit in one bar, the stop wins"],
  ["Universe", "NIFTY 50 members on the decision date"],
] as const;

export default async function RiskPage() {
  try {
    const [risk, system, chain] = await Promise.all([
      fetchApi<ProvisionalRiskStatus>("/api/v1/risk/status"),
      fetchApi<ProvisionalSystemStatus>("/api/v1/system/status").catch(() => null),
      fetchApi<ChainRow[]>("/api/v1/decisions/chain?limit=50").catch(() => [] as ChainRow[]),
    ]);
    const mode = system ? parseMode(system.trading_mode) : "UNKNOWN";
    const killSwitch = risk.kill_switch;
    const approved = chain.filter((row) => row.risk?.status === "APPROVED").length;
    const rejected = chain.filter((row) => row.risk?.status === "REJECTED").length;
    return (
      <PageFrame title="Risk" description="The risk engine is the gate every proposal must pass. Agents' opinions never skip it.">
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Kill switch" value={killSwitch} tone={killSwitch === "armed" ? "down" : "up"} hint="arming blocks new buys and flattens positions" />
          <Stat label="Approved" value={approved} tone="up" hint="in this session's proposals" />
          <Stat label="Rejected" value={rejected} tone={rejected ? "down" : "muted"} hint="each rejection names the failed check" />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <Card title="Limits enforced in code">
            <dl className="space-y-2 text-sm">
              {LIMITS.map(([label, value]) => (
                <div key={label} className="grid grid-cols-[120px_1fr] gap-2">
                  <dt className="text-[#94A3B8]">{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <Card title="Kill switch">
            {killSwitch === "armed" || killSwitch === "disarmed" ? (
              <KillSwitchControl killSwitch={killSwitch} live={mode === "LIVE"} />
            ) : (
              <p className="text-sm text-[#94A3B8]">Kill switch controls unavailable (status has no armed/disarmed value).</p>
            )}
            <p className="mt-2 text-xs text-[#64748B]">{risk.message}. On the public site this control is read-only.</p>
          </Card>
        </div>
        <Card title="Recent decisions: proposal → risk → order">
          {chain.length === 0 ? (
            <Empty>No proposals in this session yet. The decision engine proposes when the fused signal is at least ±0.2 with confidence at least 0.3.</Empty>
          ) : (
            <Table head={["Time (IST)", "Symbol", "Proposal", "Fused signal", "Risk", "Failed checks", "Order"]} minWidth={900}>
              {chain.map((row) => {
                const failed = (row.risk?.checks ?? []).filter((check) => !check.passed);
                return (
                  <tr key={row.proposal.proposal_id}>
                    <Td className="whitespace-nowrap text-xs text-[#94A3B8]">{istTime(row.proposal.timestamp)}</Td>
                    <Td>
                      <SymbolLink symbol={row.proposal.symbol} />
                    </Td>
                    <Td className="text-xs">
                      <span className={row.proposal.side === "BUY" ? "text-[#22C55E]" : "text-[#EF4444]"}>{row.proposal.side}</span> {row.proposal.quantity} @ ₹
                      {price(row.proposal.entry_price)} · {row.proposal.horizon}
                    </Td>
                    <Td className="text-xs">
                      <Score value={row.proposal.aggregated_signal} /> · conf {num(row.proposal.aggregated_confidence)} · {row.proposal.supporting_signal_ids.length} signals
                    </Td>
                    <Td>{row.risk ? <Badge tone={row.risk.status === "APPROVED" ? "up" : "down"}>{row.risk.status}</Badge> : <Badge>pending</Badge>}</Td>
                    <Td className="text-xs text-[#94A3B8]">{failed.length ? failed.map((check) => `${check.name}: ${check.detail}`).join("; ") : "—"}</Td>
                    <Td className="text-xs">{row.order ? row.order.status : "—"}</Td>
                  </tr>
                );
              })}
            </Table>
          )}
        </Card>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Risk">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
