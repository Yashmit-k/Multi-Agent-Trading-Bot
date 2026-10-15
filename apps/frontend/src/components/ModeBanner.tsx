"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { TradingMode } from "@/contracts/generated/vocab";
import { OperatorChip } from "@/components/operator/OperatorGate";

function useIstClock(): string {
  const [now, setNow] = useState("");
  useEffect(() => {
    const format = () =>
      new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date());
    setNow(format());
    const timer = setInterval(() => setNow(format()), 30000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function marketState(): "open" | "closed" {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(new Date())
    .reduce<Record<string, string>>((acc, part) => ({ ...acc, [part.type]: part.value }), {});
  const minutes = Number(parts.hour) * 60 + Number(parts.minute);
  const weekday = !["Sat", "Sun"].includes(parts.weekday ?? "");
  return weekday && minutes >= 9 * 60 + 15 && minutes < 15 * 60 + 30 ? "open" : "closed";
}

export function ModeBanner({
  mode,
  killSwitch = "UNKNOWN",
}: {
  mode: TradingMode | "UNKNOWN";
  killSwitch?: string;
}) {
  const live = mode === "LIVE";
  const clock = useIstClock();
  const [market, setMarket] = useState<"open" | "closed" | null>(null);
  useEffect(() => {
    setMarket(marketState());
    const timer = setInterval(() => setMarket(marketState()), 60000);
    return () => clearInterval(timer);
  }, []);
  const armed = killSwitch === "armed";
  return (
    <header
      data-testid="mode-banner"
      className={`sticky top-0 z-20 flex h-12 items-center justify-between gap-3 border-b px-4 backdrop-blur ${
        live ? "border-red-700 bg-red-900/90 text-white" : "border-[#26303C] bg-[#0B0F14]/90 text-[#E6EDF3]"
      }`}
    >
      <Link prefetch={false} href="/dashboard" className="flex min-w-0 items-center gap-2.5">
        <span aria-hidden className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-[#22C55E] to-[#3B82F6] text-xs font-bold text-[#0B0F14]">
          SX
        </span>
        <span data-testid="brand-mark" className="text-base font-semibold tracking-[0.14em]">
          StockX
        </span>
        <span className="hidden truncate text-xs text-[#64748B] sm:inline">NIFTY 50 · multi-agent paper trading</span>
      </Link>
      <div className="flex shrink-0 items-center gap-2 text-xs">
        <span className={`rounded px-2 py-0.5 font-semibold ${live ? "bg-white text-red-800" : "bg-[#1E3A8A]/40 text-[#93C5FD]"}`}>
          {live ? "LIVE TRADING IS ACTIVE" : "PAPER TRADING"}
        </span>
        <span className="hidden rounded border border-[#26303C] px-2 py-0.5 text-[#94A3B8] md:inline">mode {mode}</span>
        {market ? (
          <span className="hidden items-center gap-1 rounded border border-[#26303C] px-2 py-0.5 text-[#94A3B8] md:flex">
            <span className={`h-1.5 w-1.5 rounded-full ${market === "open" ? "bg-[#22C55E]" : "bg-[#64748B]"}`} />
            NSE {market}
          </span>
        ) : null}
        <span
          data-testid="kill-chip"
          className={`rounded px-2 py-0.5 font-medium ${armed ? "bg-[#7F1D1D] text-[#FCA5A5]" : "bg-[#171F2A] text-[#94A3B8]"}`}
        >
          Kill switch: {killSwitch}
        </span>
        <OperatorChip />
        {clock ? <span className="hidden tabular-nums text-[#64748B] sm:inline">{clock} IST</span> : null}
      </div>
    </header>
  );
}
