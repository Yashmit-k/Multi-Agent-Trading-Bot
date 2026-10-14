"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/dashboard", "Dashboard"],
  ["/market", "Market"],
  ["/stocks", "Stocks"],
  ["/signals", "Signals"],
  ["/agents", "Agents"],
  ["/trace", "Agent trace"],
  ["/research", "Research"],
  ["/news", "News"],
  ["/portfolio", "Portfolio"],
  ["/positions", "Positions"],
  ["/orders", "Orders"],
  ["/backtests", "Backtests"],
  ["/performance", "Performance"],
  ["/risk", "Risk"],
  ["/system", "System"],
  ["/settings", "Settings"],
] as const;

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-wrap gap-3 border-b p-3 text-sm">
      {LINKS.map(([href, label]) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link prefetch={false}
            key={href}
            href={href}
            className={active ? "font-semibold text-slate-900 no-underline" : "text-slate-600 underline"}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
