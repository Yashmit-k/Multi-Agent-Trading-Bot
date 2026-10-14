import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Card } from "@/components/ui";
import { istTime } from "@/lib/format";

export const metadata = { title: "System · StockX" };
export const dynamic = "force-dynamic";

type Check = { component: string; status: "ok" | "warn" | "down" | "idle"; detail: string; agents?: Record<string, number | null> };
type Health = { as_of: string; live_enabled: boolean; checks: Check[] };

const TONE = { ok: "up", warn: "warn", down: "down", idle: "muted" } as const;
const LABEL = { ok: "OK", warn: "Attention", down: "Down", idle: "Idle" } as const;

const FLOW = [
  "Zerodha Kite",
  "Market-data collector",
  "Quant agents",
  "Intelligence agents",
  "Redis event bus",
  "Paper worker (orchestrator)",
  "Trace recorder",
];

export default async function SystemPage() {
  try {
    const health = await fetchApi<Health>("/api/v1/system/health");
    const counts = health.checks.reduce<Record<string, number>>((acc, item) => ({ ...acc, [item.status]: (acc[item.status] ?? 0) + 1 }), {});
    return (
      <PageFrame
        title="System health"
        description={`Live check of every component in the pipeline, as of ${istTime(health.as_of)} IST. Live trading is ${health.live_enabled ? "ENABLED" : "disabled"}.`}
      >
        <div className="flex flex-wrap gap-2 text-sm">
          <Badge tone="up">{counts.ok ?? 0} OK</Badge>
          <Badge tone="warn">{counts.warn ?? 0} need attention</Badge>
          <Badge tone="down">{counts.down ?? 0} down</Badge>
          <Badge tone="muted">{counts.idle ?? 0} idle</Badge>
        </div>
        <Card title="Pipeline">
          <ol className="flex flex-wrap items-center gap-2 text-xs">
            {FLOW.map((name, index) => {
              const item = health.checks.find((check) => check.component === name);
              return (
                <li key={name} className="flex items-center gap-2">
                  <span className="rounded border border-[#26303C] px-2 py-1">
                    {name} {item ? <Badge tone={TONE[item.status]}>{LABEL[item.status]}</Badge> : null}
                  </span>
                  {index < FLOW.length - 1 ? <span className="text-[#475569]">→</span> : null}
                </li>
              );
            })}
          </ol>
        </Card>
        <div className="grid gap-3 md:grid-cols-2">
          {health.checks.map((item) => (
            <Card key={item.component} title={item.component} right={<Badge tone={TONE[item.status]}>{LABEL[item.status]}</Badge>}>
              <p className="text-sm">{item.detail}</p>
              {item.agents ? (
                <ul className="mt-2 grid grid-cols-2 gap-1 text-xs text-[#94A3B8]">
                  {Object.entries(item.agents).map(([name, age]) => (
                    <li key={name}>
                      {name}: {age === null ? "no signal yet" : `${age} min ago`}
                    </li>
                  ))}
                </ul>
              ) : null}
            </Card>
          ))}
        </div>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="System health">
        <ErrorState message={error instanceof Error ? error.message : "health_unavailable"} />
      </PageFrame>
    );
  }
}
