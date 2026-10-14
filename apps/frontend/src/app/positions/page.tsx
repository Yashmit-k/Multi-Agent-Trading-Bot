import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Empty, SymbolLink, Table, Td } from "@/components/ui";
import { inr, istTime, price } from "@/lib/format";

export const metadata = { title: "Positions · StockX" };
export const dynamic = "force-dynamic";

type Position = {
  symbol: string;
  quantity: number;
  average_price: string;
  market_price: string;
  market_value: string;
  realized_pnl: string;
  unrealized_pnl: string;
  opened_at: string;
};

export default async function PositionsPage() {
  try {
    const rows = await fetchApi<Position[]>("/api/v1/positions");
    return (
      <PageFrame title="Positions" description="Open paper positions in the active session. Long only: the risk engine rejects short sales.">
        {rows.length === 0 ? (
          <Empty>No open positions. A position opens when a paper BUY order fills on a later 5-minute bar.</Empty>
        ) : (
          <Table head={["Symbol", "Qty", "Avg price (₹)", "Mark (₹)", "Value", "Unrealized", "Realized", "Opened (IST)"]} minWidth={820}>
            {rows.map((row) => {
              const unrealized = Number(row.unrealized_pnl);
              return (
                <tr key={row.symbol}>
                  <Td>
                    <SymbolLink symbol={row.symbol} />
                  </Td>
                  <Td className="tabular-nums">{row.quantity}</Td>
                  <Td className="tabular-nums">{price(row.average_price)}</Td>
                  <Td className="tabular-nums">{price(row.market_price)}</Td>
                  <Td className="tabular-nums">{inr(row.market_value)}</Td>
                  <Td className={`tabular-nums ${unrealized >= 0 ? "text-[#22C55E]" : "text-[#EF4444]"}`}>{inr(row.unrealized_pnl)}</Td>
                  <Td className="tabular-nums">{inr(row.realized_pnl)}</Td>
                  <Td className="whitespace-nowrap text-xs text-[#94A3B8]">{istTime(row.opened_at)}</Td>
                </tr>
              );
            })}
          </Table>
        )}
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Positions">
        <ErrorState message={error instanceof Error ? error.message : "positions_unavailable"} />
      </PageFrame>
    );
  }
}
