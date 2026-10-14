"use client";

import type { TradingMode } from "@/contracts/generated/vocab";

export function ModeBanner({
  mode,
  killSwitch = "UNKNOWN",
}: {
  mode: TradingMode | "UNKNOWN";
  killSwitch?: string;
}) {
  const live = mode === "LIVE";
  return (
    <div
      data-testid="mode-banner"
      className={
        live
          ? "flex items-center justify-between gap-3 bg-red-800 px-4 py-2 text-sm font-semibold text-white"
          : "flex items-center justify-between gap-3 border-b border-[#26303C] bg-[#0F141B] px-4 py-2 text-sm text-[#E6EDF3]"
      }
    >
      <div className="min-w-0 flex-1">
        PAPER TRADING · mode {mode}
        {live ? " — LIVE TRADING IS ACTIVE. This UI cannot enable or disable LIVE." : null}
        <span data-testid="kill-chip" className="ml-3 inline-block rounded bg-[#171F2A] px-2 py-0.5 text-xs font-medium">
          Kill switch: {killSwitch}
        </span>
      </div>
      <p
        data-testid="brand-mark"
        className="shrink-0 text-right text-lg font-semibold tracking-[0.18em] text-[#E6EDF3]"
      >
        StockX
      </p>
    </div>
  );
}
