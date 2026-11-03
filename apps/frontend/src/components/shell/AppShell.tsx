"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import type { TradingMode } from "@/contracts/generated/vocab";
import { ModeBanner } from "@/components/ModeBanner";

type NavLink = readonly [string, string];
const ARCHIVED: ReadonlyArray<NavLink> = [
  ["/dashboard", "Overview"],
  ["/portfolio", "Portfolio"],
  ["/positions", "Positions"],
  ["/orders", "Orders"],
  ["/journal", "Journal"],
  ["/risk", "Risk"],
  ["/agents", "Agents"],
  ["/manager", "Portfolio manager"],
  ["/trace", "Agent trace"],
  ["/signals", "Signals"],
  ["/news", "News"],
  ["/market", "Market"],
  ["/stocks", "Stocks"],
  ["/watchlist", "Watchlist"],
  ["/strategies", "Strategy lab"],
];
const GROUPS: ReadonlyArray<readonly [string, ReadonlyArray<NavLink>]> = [
  ["Momentum", [["/momentum", "Momentum trial"]]],
  ["NIFTY 50 system (archived)", ARCHIVED],
  ["System", [["/system", "Health"], ["/settings", "Settings"]]],
];
// The NIFTY 50 paper system stopped when its Zerodha market data ended.
export const ARCHIVED_NOTE = "Archived: Zerodha market data ended on 3 Nov 2026. This page shows the NIFTY 50 paper system as it stood then.";

export function isArchived(pathname: string): boolean {
  return ARCHIVED.some(([href]) => pathname === href || pathname.startsWith(`${href}/`));
}

const LINKS: NavLink[] = GROUPS.flatMap(([, links]) => [...links]);

export function AppShell({
  mode,
  killSwitch = "UNKNOWN",
  market = null,
  children,
}: {
  mode: TradingMode | "UNKNOWN";
  killSwitch?: string;
  market?: { open: boolean; trading_day: boolean } | null;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const activeTab = useRef<HTMLAnchorElement | null>(null);
  useEffect(() => {
    // The phone tab bar scrolls sideways; bring the current page's tab into view.
    activeTab.current?.scrollIntoView?.({ inline: "center", block: "nearest" });
  }, [pathname]);
  return (
    <div className="min-h-screen bg-[#0B0F14] text-[#E6EDF3]">
      <ModeBanner mode={mode} killSwitch={killSwitch} market={market} />
      <div className="flex min-h-[calc(100vh-48px)]">
        <aside className="sticky top-12 hidden h-[calc(100vh-48px)] w-[214px] shrink-0 overflow-y-auto border-r border-[#26303C] bg-[#0F141B] md:block">
          <nav className="flex flex-col gap-4 px-2 py-4 text-sm">
            {GROUPS.map(([group, links]) => (
              <div key={group}>
                <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-[#64748B]">{group}</div>
                <div className="flex flex-col gap-0.5">
                  {links.map(([href, label]) => {
                    const active = pathname === href || pathname.startsWith(`${href}/`);
                    return (
                      <Link
                        prefetch={false}
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
                </div>
              </div>
            ))}
          </nav>
        </aside>
        <div className="min-w-0 flex-1">
          <div className="relative md:hidden">
            <nav className="flex gap-1 overflow-x-auto border-b border-[#26303C] px-3 py-2 text-xs">
              {LINKS.map(([href, label]) => {
                const active = pathname === href || pathname.startsWith(`${href}/`);
                return (
                  <Link prefetch={false}
                    key={href}
                    href={href}
                    ref={active ? activeTab : undefined}
                    className={`shrink-0 rounded px-2 py-1 ${active ? "bg-[#171F2A] text-[#E6EDF3]" : "text-[#94A3B8]"}`}
                  >
                    {label}
                  </Link>
                );
              })}
            </nav>
            {/* Fade on the right edge hints that the tabs scroll; it never blocks taps. */}
            <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-[#0B0F14] to-transparent" />
          </div>
          <main className="w-full max-w-none p-4">
            {isArchived(pathname) ? (
              <div data-testid="archived-note" className="mb-3 rounded-md border border-[#78350F] bg-[#1C1305] px-3 py-1.5 text-xs text-[#F59E0B]">
                {ARCHIVED_NOTE}
              </div>
            ) : null}
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
