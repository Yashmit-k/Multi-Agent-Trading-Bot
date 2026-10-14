import { fetchApi } from "@/lib/api";
import type { ProvisionalMarketOverview, ProvisionalStock } from "@/api/generated/provisional";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

export default async function MarketPage() {
  try {
    const overview = await fetchApi<ProvisionalMarketOverview>("/api/v1/market/overview");
    const stocks = await fetchApi<ProvisionalStock[]>("/api/v1/stocks");
    return (
      <PageFrame title="Market" description={`As of ${overview.as_of}`}>
        <p className="text-sm">
          NIFTY proxy {overview.nifty_last} · breadth {overview.breadth_advancers}/{overview.breadth_decliners}
        </p>
        <ul className="space-y-1 text-sm">
          {stocks.map((item) => (
            <li key={item.symbol}>
              {item.symbol} {item.last_price}
            </li>
          ))}
        </ul>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Market">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
