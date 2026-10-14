import { fetchApi } from "@/lib/api";
import { HorizonSplit } from "@/components/HorizonSplit";
import { EmptyState, ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

export default async function SignalsPage() {
  try {
    const signals = await fetchApi<Array<{ agent_name: string; horizon: string; signal: number; confidence: number; symbol: string }>>(
      "/api/v1/signals",
    );
    if (signals.length === 0) {
      return (
        <PageFrame title="Signals">
          <EmptyState label="signals" />
        </PageFrame>
      );
    }
    return (
      <PageFrame title="Signals">
        <HorizonSplit signals={signals} />
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Signals">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
