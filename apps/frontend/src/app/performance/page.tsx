import { fetchApi } from "@/lib/api";
import type { ProvisionalPerformance } from "@/api/generated/provisional";
import { ErrorState } from "@/components/States";

export default async function PerformancePage() {
  try {
    const perf = await fetchApi<ProvisionalPerformance>("/api/v1/performance");
    return (
      <div>
        <h1 className="text-2xl font-bold">Performance</h1>
        <p>Total PnL {perf.total_pnl}</p>
        <p>Sharpe placeholder {perf.sharpe_placeholder} (not live performance)</p>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
