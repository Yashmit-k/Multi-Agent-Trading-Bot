import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Card, Stat } from "@/components/ui";
import { inr, istTime } from "@/lib/format";

export const metadata = { title: "Portfolio · StockX" };
export const dynamic = "force-dynamic";

type Snapshot = { cash: string; equity: string; market_value: string; realized_pnl: string; unrealized_pnl: string; total_pnl: string; drawdown: string; timestamp: string };
type Portfolio = { snapshot: Snapshot | null; equity: string; total_pnl: string | null; gross_exposure: string | null; session_id: string | null };
type Paper = { running: boolean; session_status: string | null; session_starting_cash: string | null; kill_switch: string };

export default async function PortfolioPage() {
  try {
    const [portfolio, paper] = await Promise.all([fetchApi<Portfolio>("/api/v1/portfolio"), fetchApi<Paper>("/api/v1/paper/status")]);
    const snap = portfolio.snapshot;
    const total = snap ? Number(snap.total_pnl) : null;
    return (
      <PageFrame title="Portfolio" description="The active paper cash book. Values come from the latest stored portfolio snapshot, written after each fill.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Equity" value={inr(portfolio.equity)} hint={snap ? `as of ${istTime(snap.timestamp)} IST` : "no fills yet: equals starting cash"} />
          <Stat label="Cash" value={snap ? inr(snap.cash) : inr(paper.session_starting_cash)} />
          <Stat label="Total P&L" value={snap ? inr(snap.total_pnl) : "—"} tone={total === null ? "muted" : total >= 0 ? "up" : "down"} hint={snap ? undefined : "not shown as ₹0: nothing has traded"} />
          <Stat label="Gross exposure" value={portfolio.gross_exposure ? inr(portfolio.gross_exposure) : "—"} />
        </div>
        <Card title="Session">
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-[#94A3B8]">Session id</dt>
              <dd className="font-mono text-xs">{portfolio.session_id ?? "none"}</dd>
            </div>
            <div>
              <dt className="text-xs text-[#94A3B8]">Status</dt>
              <dd>{paper.session_status ?? "—"} · paper {paper.running ? "running" : "stopped"} · kill switch {paper.kill_switch}</dd>
            </div>
            <div>
              <dt className="text-xs text-[#94A3B8]">Starting cash</dt>
              <dd>{inr(paper.session_starting_cash)}</dd>
            </div>
            <div>
              <dt className="text-xs text-[#94A3B8]">Realized / unrealized</dt>
              <dd>{snap ? `${inr(snap.realized_pnl)} / ${inr(snap.unrealized_pnl)}` : "—"}</dd>
            </div>
          </dl>
        </Card>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Portfolio">
        <ErrorState message={error instanceof Error ? error.message : "portfolio_unavailable"} />
      </PageFrame>
    );
  }
}
