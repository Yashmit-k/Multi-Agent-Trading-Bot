import { fetchApi } from "@/lib/api";
import type { ProvisionalSystemStatus } from "@/api/generated/provisional";
import { ErrorState } from "@/components/States";

export default async function SystemPage() {
  try {
    const status = await fetchApi<ProvisionalSystemStatus>("/api/v1/system/status");
    return (
      <div>
        <h1 className="text-2xl font-bold">System</h1>
        <pre className="text-sm">{JSON.stringify(status, null, 2)}</pre>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
