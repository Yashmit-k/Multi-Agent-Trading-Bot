import Link from "next/link";
import { fetchApi } from "@/lib/api";
import type { ProvisionalStock } from "@/api/generated/provisional";
import { EmptyState, ErrorState } from "@/components/States";

export default async function StocksPage() {
  try {
    const stocks = await fetchApi<ProvisionalStock[]>("/api/v1/stocks");
    if (stocks.length === 0) return <EmptyState label="stocks" />;
    return (
      <div>
        <h1 className="text-2xl font-bold">Stocks</h1>
        <ul>
          {stocks.map((item) => (
            <li key={item.symbol}>
              <Link className="underline" href={`/stocks/${item.symbol}`}>
                {item.symbol}
              </Link>{" "}
              {item.last_price}
            </li>
          ))}
        </ul>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
