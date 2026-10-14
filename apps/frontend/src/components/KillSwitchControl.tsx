"use client";

import { useState } from "react";
import { postApi } from "@/lib/api";

export function KillSwitchControl({
  killSwitch,
  live,
}: {
  killSwitch: string;
  live: boolean;
}) {
  const [value, setValue] = useState(killSwitch);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const armed = value === "armed";

  async function setArmed(next: boolean) {
    const confirmText = next
      ? "Arm the kill switch? New buys will be rejected and flatten sells will be queued. This does not start or stop paper trading and cannot enable LIVE."
      : "Disarm the kill switch? New entries may resume under paper risk rules. This cannot enable LIVE.";
    if (!window.confirm(confirmText)) return;
    setPending(true);
    setError(null);
    try {
      const result = await postApi<{ kill_switch: string }>("/api/v1/risk/kill-switch", { armed: next });
      setValue(result.kill_switch);
    } catch (err) {
      setError(err instanceof Error ? err.message : "unknown");
    } finally {
      setPending(false);
    }
  }

  return (
    <div data-testid="kill-switch-control">
      <p className="font-mono">
        State: <span data-testid="kill-switch-value">{value}</span>
      </p>
      <p className="mt-1 text-sm text-[#94A3B8]">
        Arming rejects new buys and queues flatten sells. It is not paper start/stop and cannot enable LIVE.
      </p>
      {live ? (
        <p className="mt-2 text-sm text-red-800">Controls are read-only while mode is LIVE.</p>
      ) : (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            className="rounded border border-[#26303C] bg-[#171F2A] px-3 py-1 text-sm text-[#E6EDF3] disabled:opacity-50"
            disabled={pending || armed}
            onClick={() => void setArmed(true)}
          >
            Arm
          </button>
          <button
            type="button"
            className="rounded border border-[#26303C] bg-[#171F2A] px-3 py-1 text-sm text-[#E6EDF3] disabled:opacity-50"
            disabled={pending || !armed}
            onClick={() => void setArmed(false)}
          >
            Disarm
          </button>
        </div>
      )}
      {error ? (
        <p data-testid="kill-switch-error" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}
    </div>
  );
}
