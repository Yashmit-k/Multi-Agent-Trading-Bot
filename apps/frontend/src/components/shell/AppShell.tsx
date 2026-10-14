"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { TradingMode } from "@/contracts/generated/vocab";
import { ModeBanner } from "@/components/ModeBanner";

const LINKS = [
  ["/dashboard", "Overview"],
  ["/positions", "Positions"],
  ["/orders", "Orders"],
  ["/news", "News"],
  ["/signals", "Signals"],
  ["/agents", "Agents"],
  ["/trace", "Agent trace"],
  ["/market", "Market"],
  ["/stocks", "Stocks"],
  ["/portfolio", "Portfolio"],
  ["/backtests", "Backtests"],
  ["/performance", "Performance"],
  ["/risk", "Risk"],
  ["/system", "System"],
  ["/settings", "Settings"],
] as const;

export function AppShell({
  mode,
  killSwitch = "UNKNOWN",
  children,
}: {
  mode: TradingMode | "UNKNOWN";
  killSwitch?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen bg-[#0B0F14] text-[#E6EDF3]">
      <ModeBanner mode={mode} killSwitch={killSwitch} />
      <div className="flex min-h-[calc(100vh-40px)]">
        <aside className="hidden w-[214px] shrink-0 border-r border-[#26303C] bg-[#0F141B] md:block">
          <nav className="flex flex-col gap-0.5 px-2 py-4 text-sm">
            {LINKS.map(([href, label]) => {
              const active = pathname === href || pathname.startsWith(`${href}/`);
              return (
                <Link prefetch={false}
                  key={href}
                  href={href}
                  className={
                    active
                      ? "rounded-md bg-[#171F2A] px-3 py-1.5 text-[#E6EDF3]"
                      : "rounded-md px-3 py-1.5 text-[#94A3B8] hover:bg-[#171F2A]"
                  }
                >
                  {label}
                </Link>
              );
            })}
          </nav>
        </aside>
        <div className="min-w-0 flex-1">
          <nav className="flex gap-1 overflow-x-auto border-b border-[#26303C] px-3 py-2 text-xs md:hidden">
            {LINKS.map(([href, label]) => {
              const active = pathname === href || pathname.startsWith(`${href}/`);
              return (
                <Link prefetch={false}
                  key={href}
                  href={href}
                  className={`shrink-0 rounded px-2 py-1 ${active ? "bg-[#171F2A] text-[#E6EDF3]" : "text-[#94A3B8]"}`}
                >
                  {label}
                </Link>
              );
            })}
          </nav>
          <main className="w-full max-w-none p-4">{children}</main>
        </div>
      </div>
    </div>
  );
}
