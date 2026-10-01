import { fetchApi } from "@/lib/api";
import type { ProvisionalAgentScore, ProvisionalRiskStatus, ProvisionalStock } from "@/api/generated/provisional";
import { CandleChart } from "@/components/CandleChart";
import { HorizonSplit } from "@/components/HorizonSplit";
import { ErrorState } from "@/components/States";

export default async function StockPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  try {
    const [stock, candles, signals, agents, news, fundamentals, risk, orders] = await Promise.all([
      fetchApi<ProvisionalStock>(`/api/v1/stocks/${symbol}`),
      fetchApi<Array<{ start: string; open: string; high: string; low: string; close: string; timeframe: string }>>(
        `/api/v1/market/candles/${symbol}`,
      ),
      fetchApi<Array<{ agent_name: string; horizon: string; signal: number; confidence: number }>>(
        `/api/v1/stocks/${symbol}/signals`,
      ),
      fetchApi<ProvisionalAgentScore[]>(`/api/v1/stocks/${symbol}/agents`),
      fetchApi<Array<{ title: string; published_at: string }>>(`/api/v1/stocks/${symbol}/news`),
      fetchApi<Array<{ metric: string; value: string; period: string }>>(`/api/v1/stocks/${symbol}/fundamentals`),
      fetchApi<ProvisionalRiskStatus>("/api/v1/risk/status"),
      fetchApi<Array<{ order_id: string; status: string; symbol: string }>>("/api/v1/orders"),
    ]);
    const features = signals[0] as { features?: Record<string, string | number> } | undefined;
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">{stock.symbol}</h1>
        <p>
          Price {stock.last_price} · timeframe {candles[0]?.timeframe ?? "1d"}
        </p>
        <CandleChart rows={candles} />
        <h2 className="font-semibold">Technical features (from last signal)</h2>
        <pre className="text-xs bg-white p-2 overflow-auto">{JSON.stringify(features?.features ?? {}, null, 2)}</pre>
        <HorizonSplit signals={signals} />
        <h2 className="font-semibold">Agent scores</h2>
        <ul>
          {agents.map((item) => (
            <li key={item.agent_name}>
              {item.agent_name} score {item.signal} confidence {item.confidence} ({item.horizon})
            </li>
          ))}
        </ul>
        <h2 className="font-semibold">News</h2>
        <ul>
          {news.map((item) => (
            <li key={item.title}>
              {item.title} ({item.published_at})
            </li>
          ))}
        </ul>
        <h2 className="font-semibold">Fundamentals</h2>
        <ul>
          {fundamentals.map((item) => (
            <li key={item.period}>
              {item.metric} {item.value} {item.period}
            </li>
          ))}
        </ul>
        <p>Current decision is owned by Core fusion — not computed here.</p>
        <p>Risk {risk.status}</p>
        <h2 className="font-semibold">Trade history (orders)</h2>
        <ul>
          {orders
            .filter((item) => item.symbol === stock.symbol)
            .map((item) => (
              <li key={item.order_id}>
                {item.order_id} {item.status}
              </li>
            ))}
        </ul>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
