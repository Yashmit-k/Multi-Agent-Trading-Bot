import { fetchApi } from "@/lib/api";
import { EmptyState, ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

type EquityPoint = { timestamp: string; equity: string };

type Performance = {
  total_return: number;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown: string;
  win_rate: number;
  profit_factor: string | null;
  trades: number;
  gross_pnl: string;
  transaction_costs: string;
  slippage: string;
  net_pnl: string;
  periods_per_year: number;
};

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
  performance: Performance;
  equity_curve: EquityPoint[];
};

export default async function BacktestsPage({
  searchParams,
}: {
  searchParams: Promise<{ id?: string }>;
}) {
  const params = await searchParams;
  try {
    const runs = await fetchApi<BacktestRun[]>("/api/v1/backtests");
    if (runs.length === 0) {
      return (
        <PageFrame title="Backtests">
          <EmptyState label="backtests" />
        </PageFrame>
      );
    }
    const selected = runs.find((run) => run.backtest_id === params.id) ?? runs[0];
    const performance = selected.performance;
    return (
      <PageFrame title="Backtests">
        <ul className="space-y-1 text-sm">
          {runs.map((run) => (
            <li key={run.backtest_id}>
              <a className="text-cyan-400 hover:underline" href={`/backtests?id=${run.backtest_id}`}>
                {run.backtest_id}
              </a>
            </li>
          ))}
        </ul>
        <h2 className="text-xl font-semibold">Run {selected.backtest_id}</h2>
        <p>Snapshot {selected.snapshot_id}</p>
        <p>Strategy {selected.strategy}</p>
        <p>
          {selected.timeframe} {selected.start} to {selected.end}
        </p>
        <p>Symbols {selected.symbols.join(", ")}</p>
        <p>Initial cash {selected.initial_cash}</p>
        <p>
          Cost {selected.transaction_cost_bps ?? "itemized"} bp, slippage {selected.slippage_bps} bp
        </p>
        <p>Portfolio {selected.portfolio_value}</p>
        <p>Return {performance.total_return}</p>
        <p>
          Sharpe {performance.sharpe ?? "n/a"} over {performance.periods_per_year} periods/year
        </p>
        <p>Sortino {performance.sortino ?? "n/a"}</p>
        <p>Max drawdown {performance.max_drawdown}</p>
        <p>Win rate {performance.win_rate}</p>
        <p>Profit factor {performance.profit_factor ?? "n/a"}</p>
        <p>Trades {performance.trades}</p>
        <p>Gross P&L {performance.gross_pnl}</p>
        <p>Costs {performance.transaction_costs}</p>
        <p>Slippage {performance.slippage}</p>
        <p>Net P&L {performance.net_pnl}</p>
        <h2 className="text-xl font-semibold">Equity curve</h2>
        <ol className="space-y-1 text-sm">
          {selected.equity_curve.slice(-20).map((point) => (
            <li key={point.timestamp}>
              {point.timestamp} {point.equity}
            </li>
          ))}
        </ol>
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
