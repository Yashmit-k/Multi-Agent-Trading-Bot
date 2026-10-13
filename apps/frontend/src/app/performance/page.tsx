import { fetchApi } from "@/lib/api";
import { EmptyState, ErrorState } from "@/components/States";

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

export default async function PerformancePage() {
  try {
    const performance = await fetchApi<Performance>("/api/v1/performance");
    return (
      <div>
        <h1 className="text-2xl font-bold">Backtest results</h1>
        <p>These figures are the latest stored backtest from GET /api/v1/performance. They are not paper-account P&amp;L.</p>
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
      </div>
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown";
    if (message === "api_404") {
      return (
        <div>
          <h1 className="text-2xl font-bold">Backtest results</h1>
          <p>These figures are the latest stored backtest from GET /api/v1/performance. They are not paper-account P&amp;L.</p>
          <EmptyState label="backtests" />
        </div>
      );
    }
    return <ErrorState message={message} />;
  }
}
