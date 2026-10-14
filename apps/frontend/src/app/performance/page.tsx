import { fetchApi } from "@/lib/api";
import { EmptyState, ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

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

const description =
  "Backtest results from GET /api/v1/performance. These figures are not paper-account P&L.";

export default async function PerformancePage() {
  try {
    const performance = await fetchApi<Performance>("/api/v1/performance");
    return (
      <PageFrame title="Latest stored backtest" description={description}>
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
      </PageFrame>
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown";
    if (message === "api_404") {
      return (
        <PageFrame title="Latest stored backtest" description={description}>
          <EmptyState label="backtests" />
        </PageFrame>
      );
    }
    return (
      <PageFrame title="Latest stored backtest" description={description}>
        <ErrorState message={message} />
      </PageFrame>
    );
  }
}
