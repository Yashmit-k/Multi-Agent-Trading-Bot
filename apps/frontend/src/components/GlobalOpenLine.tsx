import Link from "next/link";
import { fetchApi } from "@/lib/api";
import { Badge } from "@/components/ui";
import { globalView, moodLabel, signedPct } from "@/lib/global-markets";
import { istDateKeyFromInstant } from "@/lib/ist";

// One line on Overview: where world markets point NIFTY's open today. Shown only for today's session.
export async function GlobalOpenLine() {
  const signals = await fetchApi<Array<{ agent_name: string; metadata?: Record<string, unknown> }>>("/api/v1/signals/latest").catch(() => null);
  const view = globalView(signals?.find((item) => item.agent_name === "global_markets"));
  if (!view || view.sessionDate !== istDateKeyFromInstant(new Date().toISOString())) return null;
  return (
    <Link
      prefetch={false}
      href="/agents#global_markets"
      data-testid="global-open"
      className="mb-4 flex flex-wrap items-center gap-2 rounded-[12px] border border-[#26303C] bg-[#0F141B] px-3 py-2 text-xs hover:border-[#334155]"
    >
      <span className="font-semibold uppercase tracking-wide text-[#94A3B8]">Expected open</span>
      <span className="text-sm font-semibold text-[#E6EDF3]">NIFTY {signedPct(view.expectedGapPct)}</span>
      <span className="text-[#64748B]">
        (usually {signedPct(view.rangePct[0])} to {signedPct(view.rangePct[1])})
      </span>
      <Badge tone={view.riskOff ? "down" : view.riskOn ? "up" : "muted"}>{moodLabel(view)}</Badge>
      <span className="text-[#64748B]">from world markets at {view.slot} IST · context only, never used in trades</span>
    </Link>
  );
}
