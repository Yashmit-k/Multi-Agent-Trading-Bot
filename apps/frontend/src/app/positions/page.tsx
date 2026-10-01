import { fetchApi } from "@/lib/api";
import { EmptyState, ErrorState } from "@/components/States";

export default async function PositionsPage() {
  try {
    const rows = await fetchApi<Array<{ symbol: string; quantity: number }>>("/api/v1/positions");
    if (rows.length === 0) return <EmptyState label="positions" />;
    return (
      <div>
        <h1 className="text-2xl font-bold">Positions</h1>
        <ul>
          {rows.map((item) => (
            <li key={item.symbol}>
              {item.symbol} {item.quantity}
            </li>
          ))}
        </ul>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
