import { fetchApi } from "@/lib/api";
import { EmptyState, ErrorState } from "@/components/States";

export default async function OrdersPage() {
  try {
    const rows = await fetchApi<Array<{ order_id: string; status: string; symbol: string }>>("/api/v1/orders");
    if (rows.length === 0) return <EmptyState label="orders" />;
    return (
      <div>
        <h1 className="text-2xl font-bold">Orders</h1>
        <ul>
          {rows.map((item) => (
            <li key={item.order_id}>
              {item.order_id} {item.symbol} {item.status}
            </li>
          ))}
        </ul>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
