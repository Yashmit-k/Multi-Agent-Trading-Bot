import { fetchApi } from "@/lib/api";
import { EmptyState, ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

export default async function OrdersPage() {
  try {
    const rows = await fetchApi<Array<{ order_id: string; status: string; symbol: string }>>("/api/v1/orders");
    if (rows.length === 0) {
      return (
        <PageFrame title="Orders">
          <EmptyState label="orders" />
        </PageFrame>
      );
    }
    return (
      <PageFrame title="Orders">
        <ul className="space-y-1 text-sm">
          {rows.map((item) => (
            <li key={item.order_id}>
              {item.order_id} {item.symbol} {item.status}
            </li>
          ))}
        </ul>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Orders">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
