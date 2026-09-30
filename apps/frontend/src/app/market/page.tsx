import { fetchApi } from "@/lib/api";
import type { ProvisionalMarketOverview, ProvisionalStock } from "@/api/generated/provisional";
import { ErrorState } from "@/components/States";

export default async function MarketPage() {
  try {
    const overview = await fetchApi<ProvisionalMarketOverview>("/api/v1/market/overview");
    const stocks = await fetchApi<ProvisionalStock[]>("/api/v1/stocks");
    return (
      <div>
        <h1 className="text-2xl font-bold">Market</h1>
        <p>As of {overview.as_of}</p>
        <p>
          NIFTY proxy {overview.nifty_last} · breadth {overview.breadth_advancers}/{overview.breadth_decliners}
        </p>
        <ul>
          {stocks.map((item) => (
            <li key={item.symbol}>
              {item.symbol} {item.last_price}
            </li>
          ))}
        </ul>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
