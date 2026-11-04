"use client";

import Link from "next/link";
import type { TradingMode } from "@/contracts/generated/vocab";

// Since the NIFTY 50 system was removed (4 Nov 2026) the bar shows only the brand and that this is paper money.
// The red LIVE warning stays as a safeguard, though nothing on this site trades live.
export function ModeBanner({ mode }: { mode: TradingMode | "UNKNOWN" }) {
  const live = mode === "LIVE";
  return (
    <header
      data-testid="mode-banner"
      className={`sticky top-0 z-20 flex h-12 items-center justify-between gap-3 border-b px-4 backdrop-blur ${
        live ? "border-red-700 bg-red-900/90 text-white" : "border-[#26303C] bg-[#0B0F14]/90 text-[#E6EDF3]"
      }`}
    >
      <Link prefetch={false} href="/momentum" className="flex min-w-0 items-center gap-2.5">
        {/* Decorative: the brand text beside it carries the name, so alt stays empty. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.svg" alt="" data-testid="brand-logo" width={28} height={28} className="h-7 w-7 shrink-0" />
        <span data-testid="brand-mark" className="shrink-0 whitespace-nowrap text-base font-semibold tracking-[0.14em]">
          StockX
        </span>
      </Link>
      <span className={`whitespace-nowrap rounded px-2 py-0.5 text-xs font-semibold ${live ? "bg-white text-red-800" : "bg-[#1E3A8A]/40 text-[#93C5FD]"}`}>
        {live ? "LIVE TRADING IS ACTIVE" : "Paper only"}
      </span>
    </header>
  );
}
