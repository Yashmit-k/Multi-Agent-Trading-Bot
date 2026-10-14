import { fetchApi } from "@/lib/api";
import type { ProvisionalAgentScore, ProvisionalRiskStatus, ProvisionalStock } from "@/api/generated/provisional";
import { CandleChart } from "@/components/CandleChart";
import { HorizonSplit } from "@/components/HorizonSplit";
import { ErrorState, EmptyState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

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
      <PageFrame title={stock.symbol} description={`Price ${stock.last_price} · timeframe ${candles[0]?.timeframe ?? "1d"}`}>
        <CandleChart rows={candles} />
        <h2 className="font-semibold">Technical features (from last signal)</h2>
        <pre className="overflow-auto rounded-[12px] border border-[#26303C] bg-[#121922] p-2 text-xs">
          {JSON.stringify(features?.features ?? {}, null, 2)}
        </pre>
        <HorizonSplit signals={signals} />
        <h2 className="font-semibold">Agent scores</h2>
        <ul className="space-y-1 text-sm">
          {agents.map((item) => (
            <li key={item.agent_name}>
              {item.agent_name} score {item.signal} confidence {item.confidence} ({item.horizon})
            </li>
          ))}
        </ul>
        <h2 className="font-semibold">News</h2>
        <p className="text-sm text-[#94A3B8]">Stored per-symbol articles. This is not a live news feed.</p>
        {news.length === 0 ? (
          <EmptyState label="per-symbol news" />
        ) : (
          <ul className="space-y-1 text-sm">
            {news.map((item) => (
              <li key={item.title}>
                {item.title} ({item.published_at})
              </li>
            ))}
          </ul>
        )}
        <h2 className="font-semibold">Fundamentals</h2>
        <ul className="space-y-1 text-sm">
          {fundamentals.map((item) => (
            <li key={item.period}>
              {item.metric} {item.value} {item.period}
            </li>
          ))}
        </ul>
        <p>Current decision is owned by Core fusion — not computed here.</p>
        <p>Risk {risk.status}</p>
        <h2 className="font-semibold">Trade history (orders)</h2>
        <ul className="space-y-1 text-sm">
          {orders
            .filter((item) => item.symbol === stock.symbol)
            .map((item) => (
              <li key={item.order_id}>
                {item.order_id} {item.status}
              </li>
            ))}
        </ul>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title={symbol}>
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
