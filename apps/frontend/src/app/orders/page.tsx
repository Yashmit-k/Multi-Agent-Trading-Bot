import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Empty, SymbolLink, Table, Td } from "@/components/ui";
import { istTime, price, shortId } from "@/lib/format";

export const metadata = { title: "Orders · StockX" };
export const dynamic = "force-dynamic";

type Order = {
  order_id: string;
  proposal_id: string;
  symbol: string;
  side: string;
  order_type: string;
  quantity: number;
  limit_price: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
};

const TONE: Record<string, "up" | "down" | "warn" | "info" | "muted"> = {
  FILLED: "up",
  REJECTED: "down",
  CANCELLED: "muted",
  EXPIRED: "muted",
  OPEN: "info",
  CREATED: "info",
};

export default async function OrdersPage() {
  try {
    const rows = await fetchApi<Order[]>("/api/v1/orders");
    const sorted = [...rows].sort((a, b) => b.created_at.localeCompare(a.created_at));
    return (
      <PageFrame
        title="Orders"
        description="Simulated paper orders in the active session: CNC limit buys, at most ₹20,000 each and 6 new entries per IST day. No order reaches a broker."
      >
        {sorted.length === 0 ? (
          <Empty>No paper orders in this session yet. Orders appear when an approved proposal is queued in the 09:20–10:30 IST entry window.</Empty>
        ) : (
          <Table head={["Created (IST)", "Symbol", "Side", "Qty", "Type", "Limit (₹)", "Status", "Note", "Order"]} minWidth={900}>
            {sorted.map((row) => {
              const note = String(row.metadata?.cancel_reason ?? row.metadata?.reason ?? "");
              return (
                <tr key={row.order_id}>
                  <Td className="whitespace-nowrap text-xs text-[#94A3B8]">{istTime(row.created_at)}</Td>
                  <Td>
                    <SymbolLink symbol={row.symbol} />
                  </Td>
                  <Td className={row.side === "BUY" ? "text-[#22C55E]" : "text-[#EF4444]"}>{row.side}</Td>
                  <Td className="tabular-nums">{row.quantity}</Td>
                  <Td className="text-xs">{row.order_type}</Td>
                  <Td className="tabular-nums">{price(row.limit_price)}</Td>
                  <Td>
                    <Badge tone={TONE[row.status] ?? "muted"}>{row.status}</Badge>
                  </Td>
                  <Td className="max-w-[280px] text-xs text-[#94A3B8]">{note}</Td>
                  <Td className="font-mono text-xs text-[#64748B]" >
                    <span title={row.order_id}>{shortId(row.order_id)}</span>
                  </Td>
                </tr>
              );
            })}
          </Table>
        )}
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Orders">
        <ErrorState message={error instanceof Error ? error.message : "orders_unavailable"} />
      </PageFrame>
    );
  }
}
