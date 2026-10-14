import { fetchApi } from "@/lib/api";
import { PriceChart } from "@/components/PriceChart";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Card, Empty, Score, Stat, Table, Td } from "@/components/ui";
import { AGENT_KIND, decodeEntities, istTime, num, pct, price } from "@/lib/format";
import { excludedAgents, sourceLabel } from "@/lib/signal-provenance";
import { latestPerAgent, loadSignals } from "@/lib/signals";
import { loadStocks } from "@/lib/stocks";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return { title: `${decodeURIComponent(symbol).toUpperCase()} · StockX` };
}

type Bar = { start: string; end: string; open: string; high: string; low: string; close: string; volume: number };
type Article = { article_id: string; title: string; url: string; source: string; published_at: string };
type Order = { order_id: string; symbol: string; side: string; quantity: number; status: string; created_at: string };

export default async function StockPage({ params }: { params: Promise<{ symbol: string }> }) {
  const symbol = decodeURIComponent((await params).symbol).toUpperCase();
  try {
    const [stocks, bars, signals, news, orders] = await Promise.all([
      loadStocks(),
      fetchApi<Bar[]>(`/api/v1/market/candles/${encodeURIComponent(symbol)}?timeframe=1d&last=250`),
      loadSignals({ symbol, limit: 200 }).catch(() => []),
      fetchApi<Article[]>(`/api/v1/stocks/${encodeURIComponent(symbol)}/news`).catch(() => null),
      fetchApi<Order[]>("/api/v1/orders").catch(() => []),
    ]);
    const stock = stocks.find((row) => row.symbol === symbol);
    const latest = latestPerAgent(signals);
    const excluded = excludedAgents(process.env.FUSION_EXCLUDED_AGENTS);
    const mine = orders.filter((order) => order.symbol === symbol);
    const changeValue = stock?.change_pct ? Number(stock.change_pct) : null;
    return (
      <PageFrame title={symbol} description="NSE · NIFTY 50 constituent · daily candles from Zerodha">
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Last close" value={`₹${price(stock?.last_price)}`} hint={stock?.bar_end ? `bar ending ${istTime(stock.bar_end)} IST` : undefined} />
          <Stat label="Day change" value={pct(stock?.change_pct)} tone={changeValue === null ? "muted" : changeValue >= 0 ? "up" : "down"} hint={`previous close ₹${price(stock?.prev_close)}`} />
          <Stat label="Paper orders" value={mine.length} hint="in the active paper session" />
        </div>
        <Card title="Daily price (last 250 sessions)">
          <PriceChart bars={bars} />
        </Card>
        <Card title="Latest opinion from each agent">
          {latest.length === 0 ? (
            <Empty>No agent has scored {symbol} yet.</Empty>
          ) : (
            <Table head={["Agent", "Horizon", "Score", "Confidence", "Reasons", "Source", "Time (IST)"]} minWidth={760}>
              {latest.map((row) => (
                <tr key={row.signal_id}>
                  <Td>
                    <div className="font-medium">{row.agent_name}</div>
                    <div className="mt-0.5 flex gap-1">
                      <Badge tone={AGENT_KIND[row.agent_name] === "llm" ? "info" : "muted"}>{AGENT_KIND[row.agent_name] === "llm" ? "LLM" : "rules"}</Badge>
                      {excluded.includes(row.agent_name) ? <Badge tone="warn">excluded</Badge> : null}
                    </div>
                  </Td>
                  <Td>{row.horizon}</Td>
                  <Td>
                    <Score value={row.signal} />
                  </Td>
                  <Td className="tabular-nums">{num(row.confidence)}</Td>
                  <Td className="text-xs text-[#94A3B8]">{(row.reason_codes ?? []).join(", ")}</Td>
                  <Td className="text-xs text-[#94A3B8]">{sourceLabel(row.agent_name, row as unknown as Record<string, unknown>)}</Td>
                  <Td className="whitespace-nowrap text-xs text-[#94A3B8]">{istTime(row.timestamp)}</Td>
                </tr>
              ))}
            </Table>
          )}
          <p className="mt-2 text-xs text-[#64748B]">
            Scores run from −1 (bearish) to +1 (bullish). Agents never place orders: fusion, decision, and risk code decide.
          </p>
        </Card>
        <Card title="Headlines the News agent read">
          {news === null ? (
            <Empty>The intelligence service is unreachable.</Empty>
          ) : news.length === 0 ? (
            <Empty>No live headline mentioned {symbol} yet.</Empty>
          ) : (
            <ul className="space-y-2 text-sm">
              {news.slice(0, 10).map((item) => (
                <li key={item.article_id}>
                  <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-[#60A5FA]">
                    {decodeEntities(item.title)}
                  </a>
                  <div className="text-xs text-[#64748B]">
                    {item.source} · {istTime(item.published_at)} IST
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title={symbol}>
        <ErrorState message={error instanceof Error ? error.message : "stock_unavailable"} />
      </PageFrame>
    );
  }
}
