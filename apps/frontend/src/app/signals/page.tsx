import { fetchApi } from "@/lib/api";
import { HorizonSplit } from "@/components/HorizonSplit";
import { EmptyState, ErrorState } from "@/components/States";

export default async function SignalsPage() {
  try {
    const signals = await fetchApi<Array<{ agent_name: string; horizon: string; signal: number; confidence: number; symbol: string }>>(
      "/api/v1/signals",
    );
    if (signals.length === 0) return <EmptyState label="signals" />;
    return (
      <div>
        <h1 className="text-2xl font-bold">Signals</h1>
        <HorizonSplit signals={signals} />
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
