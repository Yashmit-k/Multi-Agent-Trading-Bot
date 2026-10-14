import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Empty, Score, SymbolLink, Table, Td } from "@/components/ui";
import { AGENT_KIND, istTime, num } from "@/lib/format";
import { excludedAgents, sourceLabel } from "@/lib/signal-provenance";
import { loadSignals } from "@/lib/signals";

export const metadata = { title: "Signals · StockX" };
export const dynamic = "force-dynamic";

const AGENTS = ["technical", "momentum", "mean_reversion", "volume", "regime", "news", "fundamental", "valuation", "earnings"];

export default async function SignalsPage({ searchParams }: { searchParams: Promise<{ agent?: string; symbol?: string; horizon?: string }> }) {
  const { agent = "", symbol = "", horizon = "" } = await searchParams;
  try {
    const rows = await loadSignals({ limit: 300, agent: agent || undefined, symbol: symbol.trim().toUpperCase() || undefined });
    const shown = horizon ? rows.filter((row) => row.horizon === horizon) : rows;
    const excluded = excludedAgents(process.env.FUSION_EXCLUDED_AGENTS);
    return (
      <PageFrame
        title="Signals"
        description="The 300 most recent agent opinions, newest first. Intraday and swing horizons are fused separately."
      >
        <form className="flex flex-wrap gap-2 text-sm" action="/signals">
          <select name="agent" defaultValue={agent} className="rounded border border-[#26303C] bg-[#0F141B] px-2 py-1.5">
            <option value="">All agents</option>
            {AGENTS.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <select name="horizon" defaultValue={horizon} className="rounded border border-[#26303C] bg-[#0F141B] px-2 py-1.5">
            <option value="">All horizons</option>
            <option value="INTRADAY">INTRADAY</option>
            <option value="SWING">SWING</option>
            <option value="LONG_TERM">LONG_TERM</option>
          </select>
          <input
            name="symbol"
            defaultValue={symbol}
            placeholder="Symbol"
            className="w-36 rounded border border-[#26303C] bg-[#0F141B] px-2 py-1.5 placeholder:text-[#64748B]"
          />
          <button className="rounded border border-[#26303C] px-3 py-1.5">Apply</button>
        </form>
        {shown.length === 0 ? (
          <Empty>No signals match these filters.</Empty>
        ) : (
          <Table head={["Time (IST)", "Symbol", "Agent", "Horizon", "Score", "Confidence", "Reasons", "Source"]} minWidth={880}>
            {shown.map((row) => (
              <tr key={row.signal_id}>
                <Td className="whitespace-nowrap text-xs text-[#94A3B8]">{istTime(row.timestamp)}</Td>
                <Td>
                  <SymbolLink symbol={row.symbol} />
                </Td>
                <Td>
                  <span className="mr-1">{row.agent_name}</span>
                  {AGENT_KIND[row.agent_name] === "llm" ? <Badge tone="info">LLM</Badge> : null}{" "}
                  {excluded.includes(row.agent_name) ? <Badge tone="warn">excluded</Badge> : null}
                </Td>
                <Td className="text-xs">{row.horizon}</Td>
                <Td>
                  <Score value={row.signal} />
                </Td>
                <Td className="tabular-nums">{num(row.confidence)}</Td>
                <Td className="text-xs text-[#94A3B8]">{(row.reason_codes ?? []).join(", ")}</Td>
                <Td className="text-xs text-[#94A3B8]">{sourceLabel(row.agent_name, row as unknown as Record<string, unknown>)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Signals">
        <ErrorState message={error instanceof Error ? error.message : "signals_unavailable"} />
      </PageFrame>
    );
  }
}
