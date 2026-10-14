import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { StockTable } from "@/components/StockTable";
import { loadStocks } from "@/lib/stocks";

export const metadata = { title: "Stocks · StockX" };
export const dynamic = "force-dynamic";

export default async function StocksPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = "" } = await searchParams;
  try {
    const rows = await loadStocks();
    const query = q.trim().toUpperCase();
    const shown = query ? rows.filter((row) => row.symbol.includes(query)) : rows;
    return (
      <PageFrame title="Stocks" description="Open a stock to see its chart, every agent's latest opinion, and the headlines the News agent read.">
        <form className="flex gap-2" action="/stocks">
          <input
            name="q"
            defaultValue={q}
            placeholder="Filter symbol, e.g. INFY"
            className="w-64 rounded border border-[#26303C] bg-[#0F141B] px-3 py-1.5 text-sm text-[#E6EDF3] placeholder:text-[#64748B]"
          />
          <button className="rounded border border-[#26303C] px-3 py-1.5 text-sm">Filter</button>
        </form>
        <StockTable rows={shown} />
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Stocks">
        <ErrorState message={error instanceof Error ? error.message : "stocks_unavailable"} />
      </PageFrame>
    );
  }
}
