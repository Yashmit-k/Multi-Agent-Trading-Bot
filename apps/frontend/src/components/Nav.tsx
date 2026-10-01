import Link from "next/link";

const LINKS = [
  ["/dashboard", "Dashboard"],
  ["/market", "Market"],
  ["/stocks", "Stocks"],
  ["/signals", "Signals"],
  ["/agents", "Agents"],
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
  return (
    <nav className="flex flex-wrap gap-3 p-3 border-b text-sm">
      {LINKS.map(([href, label]) => (
        <Link key={href} href={href} className="underline">
          {label}
        </Link>
      ))}
    </nav>
  );
}
