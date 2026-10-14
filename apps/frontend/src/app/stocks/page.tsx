import Link from "next/link";
import { fetchApi } from "@/lib/api";
import type { ProvisionalStock } from "@/api/generated/provisional";
import { EmptyState, ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

export default async function StocksPage() {
  try {
    const stocks = await fetchApi<ProvisionalStock[]>("/api/v1/stocks");
    if (stocks.length === 0) {
      return (
        <PageFrame title="Stocks">
          <EmptyState label="stocks" />
        </PageFrame>
      );
    }
    return (
      <PageFrame title="Stocks">
        <ul className="space-y-1 text-sm">
          {stocks.map((item) => (
            <li key={item.symbol}>
              <Link className="text-cyan-400 hover:underline" href={`/stocks/${item.symbol}`}>
                {item.symbol}
              </Link>{" "}
              {item.last_price}
            </li>
          ))}
        </ul>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Stocks">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
