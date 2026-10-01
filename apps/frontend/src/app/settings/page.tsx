import { fetchApi } from "@/lib/api";
import type { ProvisionalSystemStatus } from "@/api/generated/provisional";
import { parseMode } from "@/lib/mode";
import { ErrorState } from "@/components/States";

export default async function SettingsPage() {
  try {
    const status = await fetchApi<ProvisionalSystemStatus>("/api/v1/system/status");
    const mode = parseMode(status.trading_mode);
    return (
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p>Mode is read-only: {mode}</p>
        <p>This UI cannot enable LIVE trading.</p>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
