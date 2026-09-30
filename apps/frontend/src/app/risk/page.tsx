import { fetchApi } from "@/lib/api";
import type { ProvisionalRiskStatus } from "@/api/generated/provisional";
import { ErrorState } from "@/components/States";

export default async function RiskPage() {
  try {
    const risk = await fetchApi<ProvisionalRiskStatus>("/api/v1/risk/status");
    return (
      <div>
        <h1 className="text-2xl font-bold">Risk</h1>
        <p>
          {risk.status} at {risk.as_of}: {risk.message}
        </p>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
