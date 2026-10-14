import { fetchApi } from "@/lib/api";
import type { ProvisionalRiskStatus, ProvisionalSystemStatus } from "@/api/generated/provisional";
import { ErrorState } from "@/components/States";
import { KillSwitchControl } from "@/components/KillSwitchControl";
import { PageFrame } from "@/components/shell/PageFrame";
import { parseMode } from "@/lib/mode";

export default async function RiskPage() {
  try {
    const [risk, system] = await Promise.all([
      fetchApi<ProvisionalRiskStatus>("/api/v1/risk/status"),
      fetchApi<ProvisionalSystemStatus>("/api/v1/system/status").catch(() => null),
    ]);
    const mode = system ? parseMode(system.trading_mode) : "UNKNOWN";
    const killSwitch = risk.kill_switch;
    return (
      <PageFrame
        title="Risk"
        description={`${risk.status} at ${risk.as_of}: ${risk.message}`}
      >
        {killSwitch === "armed" || killSwitch === "disarmed" ? (
          <KillSwitchControl killSwitch={killSwitch} live={mode === "LIVE"} />
        ) : (
          <p className="text-sm text-[#94A3B8]">Kill switch controls unavailable (status has no armed/disarmed value).</p>
        )}
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Risk">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
