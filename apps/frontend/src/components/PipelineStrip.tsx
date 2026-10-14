import Link from "next/link";
import { fetchApi } from "@/lib/api";
import { Badge } from "@/components/ui";

type Check = { component: string; status: "ok" | "warn" | "down" | "idle"; detail: string };

const SHOWN = ["Zerodha Kite", "Market-data collector", "Quant agents", "Intelligence service", "Redis event bus", "Trace recorder", "Paper worker (orchestrator)"];
const SHORT: Record<string, string> = {
  "Zerodha Kite": "Zerodha",
  "Market-data collector": "Market data",
  "Quant agents": "5 quant agents",
  "Intelligence service": "4 LLM agents",
  "Redis event bus": "Event bus",
  "Trace recorder": "Trace",
  "Paper worker (orchestrator)": "Orchestrator",
};
const TONE = { ok: "up", warn: "warn", down: "down", idle: "muted" } as const;

// Server-rendered status of each pipeline stage, linking to the full health page.
export async function PipelineStrip() {
  const health = await fetchApi<{ checks: Check[] }>("/api/v1/system/health").catch(() => null);
  if (!health) return null;
  const checks = SHOWN.map((name) => health.checks.find((item) => item.component === name)).filter(Boolean) as Check[];
  return (
    <Link prefetch={false} href="/system" className="mb-4 flex flex-wrap items-center gap-1.5 rounded-[12px] border border-[#26303C] bg-[#0F141B] px-3 py-2 text-xs hover:border-[#334155]">
      <span className="mr-1 font-semibold uppercase tracking-wide text-[#94A3B8]">Pipeline</span>
      {checks.map((item, index) => (
        <span key={item.component} className="flex items-center gap-1.5" title={item.detail}>
          <Badge tone={TONE[item.status]}>{SHORT[item.component] ?? item.component}</Badge>
          {index < checks.length - 1 ? <span className="text-[#475569]">→</span> : null}
        </span>
      ))}
    </Link>
  );
}
