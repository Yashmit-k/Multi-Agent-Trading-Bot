import { fetchApi } from "@/lib/api";
import { EmptyState, ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

export default async function PositionsPage() {
  try {
    const rows = await fetchApi<Array<{ symbol: string; quantity: number }>>("/api/v1/positions");
    if (rows.length === 0) {
      return (
        <PageFrame title="Positions">
          <EmptyState label="positions" />
        </PageFrame>
      );
    }
    return (
      <PageFrame title="Positions">
        <ul className="space-y-1 text-sm">
          {rows.map((item) => (
            <li key={item.symbol}>
              {item.symbol} {item.quantity}
            </li>
          ))}
        </ul>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Positions">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
