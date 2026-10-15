import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { BacktestSummary, type BacktestPerformance } from "@/components/BacktestSummary";
import { EquityLine } from "@/components/EquityLine";
import { Badge, Card, Empty } from "@/components/ui";
import { inr, istTime, shortId } from "@/lib/format";

export const metadata = { title: "Backtests · StockX" };
export const dynamic = "force-dynamic";

type BacktestRun = {
  backtest_id: string;
  snapshot_id: string;
  strategy: string;
  timeframe: string;
  start: string;
  end: string;
  symbols: string[];
  initial_cash: string;
  transaction_cost_bps: string | null;
  slippage_bps: string;
  portfolio_value: string;
  candles_processed?: number;
  signals_generated?: number;
  performance: BacktestPerformance;
  equity_curve: Array<{ timestamp: string; equity: string }>;
};

export default async function BacktestsPage({ searchParams }: { searchParams: Promise<{ id?: string }> }) {
  const params = await searchParams;
  try {
    const runs = await fetchApi<BacktestRun[]>("/api/v1/backtests");
    if (runs.length === 0) {
      return (
        <PageFrame title="Backtests">
          <Empty>No backtests stored yet.</Empty>
        </PageFrame>
      );
    }
    const selected = runs.find((run) => run.backtest_id === params.id) ?? runs[0];
    return (
      <PageFrame
        title="Backtests"
        description="Historical replays of the same fusion → decision → risk → execution path, on frozen Zerodha candles. These are not paper-account results."
      >
        {runs.length > 1 ? (
          <div className="flex flex-wrap gap-2 text-sm">
            {runs.map((run) => (
              <a key={run.backtest_id} href={`/backtests?id=${run.backtest_id}`} className={run.backtest_id === selected.backtest_id ? "text-[#60A5FA]" : "text-[#94A3B8] hover:text-[#E6EDF3]"}>
                {shortId(run.backtest_id)} · {run.strategy}
              </a>
            ))}
          </div>
        ) : null}
        <Card title={`Run ${shortId(selected.backtest_id)}`} right={<Badge tone="info">{selected.strategy}</Badge>}>
          <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-xs text-[#94A3B8]">Period</dt>
              <dd>
                {istTime(selected.start)} → {istTime(selected.end)} IST · {selected.timeframe} bars
              </dd>
            </div>
            <div>
              <dt className="text-xs text-[#94A3B8]">Symbols</dt>
              <dd>{selected.symbols.join(", ")}</dd>
            </div>
            <div>
              <dt className="text-xs text-[#94A3B8]">Snapshot</dt>
              <dd className="font-mono text-xs">{selected.snapshot_id}</dd>
            </div>
            <div>
              <dt className="text-xs text-[#94A3B8]">Starting → ending</dt>
              <dd>
                {inr(selected.initial_cash)} → {inr(selected.portfolio_value)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-[#94A3B8]">Costs</dt>
              <dd>
                {selected.transaction_cost_bps ?? "itemized"} bp per fill + {selected.slippage_bps} bp slippage
              </dd>
            </div>
            <div>
              <dt className="text-xs text-[#94A3B8]">Pipeline activity</dt>
              <dd>
                {selected.candles_processed ?? "—"} bars · {selected.signals_generated ?? "—"} agent signals
              </dd>
            </div>
          </dl>
        </Card>
        <BacktestSummary performance={selected.performance} />
        <Card title="Equity curve">
          {/* Points before the run start are indicator warm-up with no trading; they are left out. */}
          <EquityLine points={selected.equity_curve.filter((point) => point.timestamp >= selected.start)} />
          <p className="mt-2 text-xs text-[#64748B]">
            Ends at {inr(selected.portfolio_value)}, a net P&amp;L of {inr(selected.performance.net_pnl)} after costs.
          </p>
        </Card>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Backtests">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
