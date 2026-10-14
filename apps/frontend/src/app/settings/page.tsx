import { fetchApi } from "@/lib/api";
import type { ProvisionalSystemStatus } from "@/api/generated/provisional";
import { parseMode } from "@/lib/mode";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

export default async function SettingsPage() {
  try {
    const status = await fetchApi<ProvisionalSystemStatus>("/api/v1/system/status");
    const mode = parseMode(status.trading_mode);
    return (
      <PageFrame title="Settings">
        <p>Mode is read-only: {mode}</p>
        <p>This UI cannot enable LIVE trading.</p>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Settings">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
