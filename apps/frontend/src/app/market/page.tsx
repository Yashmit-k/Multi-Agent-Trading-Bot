import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { StockTable } from "@/components/StockTable";
import { Card, Stat } from "@/components/ui";
import { istTime, pct } from "@/lib/format";
import { change, loadStocks } from "@/lib/stocks";

export const metadata = { title: "Market · StockX" };
export const dynamic = "force-dynamic";

type Ingestion = { authenticated?: boolean; last_success_at?: string | null; last_error?: string | null; running?: boolean };

export default async function MarketPage() {
  try {
    const [rows, ingestion] = await Promise.all([
      loadStocks(),
      fetchApi<Ingestion>("/api/v1/market/ingestion").catch(() => null),
    ]);
    const priced = rows.filter((row) => change(row) !== null);
    const sorted = [...priced].sort((a, b) => (change(b) ?? 0) - (change(a) ?? 0));
    const up = priced.filter((row) => (change(row) ?? 0) > 0).length;
    const down = priced.filter((row) => (change(row) ?? 0) < 0).length;
    const mean = priced.length ? priced.reduce((sum, row) => sum + (change(row) ?? 0), 0) / priced.length : null;
    const lastBar = rows.map((row) => row.bar_end).filter(Boolean).sort().at(-1) ?? null;
    return (
      <PageFrame
        title="Market"
        description="NIFTY 50 constituents from stored Zerodha daily candles. Day change compares the last two completed daily bars."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Advancers / decliners" value={`${up} / ${down}`} hint={`${priced.length} of ${rows.length} symbols priced`} />
          <Stat label="Average day change" value={pct(mean)} tone={mean === null ? "muted" : mean >= 0 ? "up" : "down"} hint="Equal-weight mean, not the index" />
          <Stat label="Latest daily bar" value={istTime(lastBar)} hint="IST" />
          <Stat
            label="Zerodha feed"
            value={ingestion?.authenticated ? "Connected" : "Logged out"}
            tone={ingestion?.authenticated ? "up" : "down"}
            hint={ingestion?.last_success_at ? `last poll ${istTime(ingestion.last_success_at)}` : ingestion?.last_error ?? "no successful poll yet"}
          />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <Card title="Top gainers">
            <StockTable rows={sorted.slice(0, 5)} />
          </Card>
          <Card title="Top losers">
            <StockTable rows={sorted.slice(-5).reverse()} />
          </Card>
        </div>
        <Card title="All constituents">
          <StockTable rows={rows} />
        </Card>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Market">
        <ErrorState message={error instanceof Error ? error.message : "market_unavailable"} />
      </PageFrame>
    );
  }
}
