import { fetchApi } from "@/lib/api";
import type { ProvisionalSystemStatus } from "@/api/generated/provisional";
import { parseMode } from "@/lib/mode";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Card } from "@/components/ui";
import { excludedAgents } from "@/lib/signal-provenance";

export const metadata = { title: "Settings · StockX" };
export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  try {
    const status = await fetchApi<ProvisionalSystemStatus>("/api/v1/system/status");
    const mode = parseMode(status.trading_mode);
    const excluded = excludedAgents(process.env.FUSION_EXCLUDED_AGENTS);
    const rows = [
      ["Trading mode", `${mode} (read-only; set by the server, never by this UI)`],
      ["Live trading", "Disabled. live_enabled is hard-coded false and no code path calls a broker order endpoint."],
      ["Exchange scope", status.exchange_scope],
      ["Agents excluded from fusion", excluded.length ? excluded.join(", ") : "none"],
      ["Public site", "Read-only. Write requests (start/stop paper, kill switch) are refused by the server-side proxy."],
      ["Contract version", status.contract_version],
    ];
    return (
      <PageFrame title="Settings">
        <Card title="Configuration">
          <dl className="space-y-2 text-sm">
            {rows.map(([label, value]) => (
              <div key={label} className="grid grid-cols-[200px_1fr] gap-2">
                <dt className="text-[#94A3B8]">{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Settings">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
