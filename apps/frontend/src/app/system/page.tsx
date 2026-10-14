import { fetchApi } from "@/lib/api";
import type { ProvisionalSystemStatus } from "@/api/generated/provisional";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

export default async function SystemPage() {
  try {
    const status = await fetchApi<ProvisionalSystemStatus>("/api/v1/system/status");
    return (
      <PageFrame title="System">
        <pre className="overflow-auto rounded-[12px] border border-[#26303C] bg-[#121922] p-3 text-sm">{JSON.stringify(status, null, 2)}</pre>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="System">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
