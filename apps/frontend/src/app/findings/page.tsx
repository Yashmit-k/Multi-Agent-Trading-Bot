import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Card, Stat } from "@/components/ui";
import { FINDINGS, REPO_DOCS, type Outcome } from "@/lib/research/findings";

export const metadata = { title: "Research findings · StockX" };

const OUTCOME: Record<Outcome, { label: string; tone: "up" | "down" | "warn" }> = {
  edge: { label: "Edge found", tone: "up" },
  mixed: { label: "Partial: not tradeable", tone: "warn" },
  no_edge: { label: "No edge", tone: "down" },
};

export default function FindingsPage() {
  const tradeable = FINDINGS.filter((f) => f.outcome === "edge").length;
  return (
    <PageFrame
      title="Research findings"
      description="Every study, newest first. Each protocol was committed before its result was computed, and every result is shown, including failures. Exploratory runs are labelled."
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Studies scored" value={FINDINGS.length} />
        <Stat label="Tradeable edges after costs" value={tradeable} tone={tradeable > 0 ? "up" : "down"} hint="long-only, Zerodha charges" />
        <Stat label="Real but untradeable signals" value={FINDINGS.filter((f) => f.outcome === "mixed").length} tone="muted" hint="volatility forecast, intraday ranking, 20-day momentum" />
      </div>
      {FINDINGS.map((f) => (
        <Card
          key={f.slug}
          title={f.title}
          right={
            <span className="flex items-center gap-2">
              {f.exploratory ? <Badge tone="info">Exploratory</Badge> : null}
              <Badge tone={OUTCOME[f.outcome].tone}>{OUTCOME[f.outcome].label}</Badge>
            </span>
          }
        >
          <div className="space-y-2 text-sm">
            <p className="text-[#94A3B8]">{f.question}</p>
            <p className="font-medium">{f.verdict}</p>
            <ul className="list-disc space-y-0.5 pl-5 tabular-nums">
              {f.numbers.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
            <p>
              <span className="text-[#94A3B8]">Consequence: </span>
              {f.consequence}
            </p>
            <p className="flex flex-wrap gap-x-4 text-xs text-[#94A3B8]">
              <span>Scored {f.date}</span>
              {f.protocol ? (
                <a className="underline hover:text-white" href={`${REPO_DOCS}/${f.protocol}`} target="_blank" rel="noreferrer">
                  Protocol
                </a>
              ) : null}
              <a className="underline hover:text-white" href={`${REPO_DOCS}/${f.result}`} target="_blank" rel="noreferrer">
                Result
              </a>
            </p>
          </div>
        </Card>
      ))}
    </PageFrame>
  );
}
