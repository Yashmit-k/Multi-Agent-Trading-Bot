"use client";

import type { TradingMode } from "@/contracts/generated/vocab";

export function ModeBanner({ mode }: { mode: TradingMode | "UNKNOWN" }) {
  const live = mode === "LIVE";
  return (
    <div
      data-testid="mode-banner"
      className={live ? "bg-red-700 text-white px-4 py-2 font-bold" : "bg-slate-800 text-white px-4 py-2"}
    >
      Trading mode: {mode}
      {live ? " — LIVE TRADING IS ACTIVE. This UI cannot enable or disable LIVE." : null}
    </div>
  );
}
