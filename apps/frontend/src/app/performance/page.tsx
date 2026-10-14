import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { BacktestSummary, type BacktestPerformance } from "@/components/BacktestSummary";
import { Empty } from "@/components/ui";

export const metadata = { title: "Performance · StockX" };
export const dynamic = "force-dynamic";

const description = "Backtest results from GET /api/v1/performance. These figures are not paper-account P&L.";

export default async function PerformancePage() {
  try {
    const performance = await fetchApi<BacktestPerformance>("/api/v1/performance");
    return (
      <PageFrame title="Latest stored backtest" description={description}>
        <BacktestSummary performance={performance} />
        <p className="text-xs text-[#64748B]">
          Open Backtests for the run&apos;s period, symbols, and equity curve. Paper-account P&amp;L is on Portfolio.
        </p>
      </PageFrame>
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown";
    if (message === "api_404") {
      return (
        <PageFrame title="Latest stored backtest" description={description}>
          <Empty>No backtests stored yet.</Empty>
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
