import { fetchApi } from "@/lib/api";
import type { ProvisionalMarketOverview, ProvisionalRiskStatus, ProvisionalStock, ProvisionalSystemStatus } from "@/api/generated/provisional";
import { ErrorState } from "@/components/States";
import { HorizonSplit } from "@/components/HorizonSplit";

export default async function DashboardPage() {
  try {
    const [status, overview, stocks, signals, portfolio, positions, risk] = await Promise.all([
      fetchApi<ProvisionalSystemStatus>("/api/v1/system/status"),
      fetchApi<ProvisionalMarketOverview>("/api/v1/market/overview"),
      fetchApi<ProvisionalStock[]>("/api/v1/stocks"),
      fetchApi<Array<{ agent_name: string; horizon: string; signal: number; confidence: number; symbol: string }>>("/api/v1/signals"),
      fetchApi<{ total_pnl: string; equity: string; gross_exposure: string }>("/api/v1/portfolio"),
      fetchApi<Array<{ symbol: string; quantity: number }>>("/api/v1/positions"),
      fetchApi<ProvisionalRiskStatus>("/api/v1/risk/status"),
    ]);
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p>NIFTY proxy last: {overview.nifty_last}</p>
        <p>
          Breadth: {overview.breadth_advancers} advancers / {overview.breadth_decliners} decliners (provisional)
        </p>
        <p>
          Mode {status.trading_mode} · live_enabled {String(status.live_enabled)} · health {status.status}
        </p>
        <p>
          Portfolio PnL {portfolio.total_pnl} · equity {portfolio.equity} · exposure {portfolio.gross_exposure}
        </p>
        <p>
          Risk {risk.status} · {risk.message}
        </p>
        <h2 className="font-semibold">Positions</h2>
        <ul>
          {positions.map((item) => (
            <li key={item.symbol}>
              {item.symbol} qty {item.quantity}
            </li>
          ))}
        </ul>
        <h2 className="font-semibold">Top signals</h2>
        <HorizonSplit signals={signals} />
        <h2 className="font-semibold">Universe</h2>
        <ul>
          {stocks.map((item) => (
            <li key={item.symbol}>
              {item.symbol} {item.last_price}
            </li>
          ))}
        </ul>
        <p>News on this page uses per-stock fixtures, not a global news endpoint.</p>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
