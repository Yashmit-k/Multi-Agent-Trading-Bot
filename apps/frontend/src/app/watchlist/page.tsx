import Link from "next/link";
import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Card, Empty, SymbolLink, Table, Td } from "@/components/ui";

export const metadata = { title: "Watchlist · StockX" };
export const dynamic = "force-dynamic";

type Row = {
  symbol: string;
  as_of: string;
  close: number;
  score: number;
  checks_known: number;
  checks: Record<string, boolean | null>;
  rsi: number | null;
  return_20d: number | null;
  atr_pct: number | null;
  agent_view: number | null;
};
type Report = {
  checks: Array<{ key: string; label: string }>;
  min_score: number;
  watchlist: Row[];
  all: Row[];
  history: { forward_sessions: number; by_price_score: Array<{ price_score: number; samples: number; mean_forward_return_pct: number; share_positive: number }> };
};

const SHORT: Record<string, string> = {
  trend_200: "200d",
  ema_stack: "EMA",
  momentum_20: "RS",
  rsi_zone: "RSI",
  macd_up: "MACD",
  volume_up: "Vol",
  near_high: "High",
  calm: "Calm",
  agents_bullish: "Agents",
  market_up: "Mkt",
};

function Mark({ value }: { value: boolean | null }) {
  if (value === null) return <span className="text-[#475569]">·</span>;
  return value ? <span className="text-[#22C55E]">✓</span> : <span className="text-[#EF4444]">✗</span>;
}

export default async function WatchlistPage({ searchParams }: { searchParams: Promise<{ min?: string; all?: string }> }) {
  const params = await searchParams;
  const minimum = Math.max(0, Math.min(10, Number(params.min ?? 7) || 7));
  try {
    const report = await fetchApi<Report>(`/api/v1/watchlist?min_score=${minimum}`);
    const rows = params.all ? report.all : report.watchlist;
    return (
      <PageFrame
        title="Watchlist"
        description="NIFTY 50 stocks scored on a 10-point checklist of conditions traders commonly read as bullish. A screen to research from, not a buy list."
      >
        <Card title="Checklist">
          <ol className="grid gap-1 text-sm md:grid-cols-2">
            {report.checks.map((check, index) => (
              <li key={check.key}>
                <span className="mr-2 inline-block w-14 font-mono text-xs text-[#60A5FA]">{SHORT[check.key]}</span>
                {index + 1}. {check.label}
              </li>
            ))}
          </ol>
        </Card>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-[#94A3B8]">Minimum score:</span>
          {[6, 7, 8, 9].map((value) => (
            <Link prefetch={false} key={value} href={`/watchlist?min=${value}`} className={`rounded border px-2 py-0.5 ${!params.all && value === minimum ? "border-[#2563EB] text-[#E6EDF3]" : "border-[#26303C] text-[#94A3B8]"}`}>
              {value}+
            </Link>
          ))}
          <Link prefetch={false} href={`/watchlist?all=1&min=${minimum}`} className={`rounded border px-2 py-0.5 ${params.all ? "border-[#2563EB]" : "border-[#26303C] text-[#94A3B8]"}`}>
            all 50
          </Link>
        </div>
        {rows.length === 0 ? (
          <Empty>No stock scores {minimum} or more today. Try a lower minimum.</Empty>
        ) : (
          <Table head={["Stock", "Score", ...report.checks.map((check) => SHORT[check.key]), "Close ₹", "RSI", "20d %", "ATR %", "Agents"]} minWidth={1100}>
            {rows.map((row) => (
              <tr key={row.symbol}>
                <Td>
                  <SymbolLink symbol={row.symbol} />
                </Td>
                <Td>
                  <Badge tone={row.score >= 8 ? "up" : row.score >= 6 ? "info" : "muted"}>
                    {row.score}/{row.checks_known}
                  </Badge>
                </Td>
                {report.checks.map((check) => (
                  <Td key={check.key} className="text-center">
                    <Mark value={row.checks[check.key]} />
                  </Td>
                ))}
                <Td className="tabular-nums">{row.close.toFixed(2)}</Td>
                <Td className="tabular-nums">{row.rsi ?? "—"}</Td>
                <Td className={`tabular-nums ${(row.return_20d ?? 0) >= 0 ? "text-[#22C55E]" : "text-[#EF4444]"}`}>{row.return_20d ?? "—"}</Td>
                <Td className="tabular-nums">{row.atr_pct ?? "—"}</Td>
                <Td className="tabular-nums">{row.agent_view === null ? "—" : row.agent_view.toFixed(2)}</Td>
              </tr>
            ))}
          </Table>
        )}
        <Card title={`Has this checklist worked? Past scores vs the next ${report.history.forward_sessions} sessions`}>
          <p className="mb-2 text-xs text-[#94A3B8]">
            Every stock-day since 2024 scored on the eight price checks (the agents' views were not stored that far back), then the stock's return over the next {report.history.forward_sessions}{" "}
            sessions, before costs. Windows overlap and stocks move together, so treat small differences as noise.
          </p>
          <Table head={["Price checks passed (of 8)", "Stock-days", "Average next-10-session return", "Share that rose"]} minWidth={560}>
            {report.history.by_price_score.map((row) => (
              <tr key={row.price_score}>
                <Td>{row.price_score}</Td>
                <Td className="tabular-nums">{row.samples.toLocaleString("en-IN")}</Td>
                <Td className={`tabular-nums ${row.mean_forward_return_pct >= 0 ? "text-[#22C55E]" : "text-[#EF4444]"}`}>{row.mean_forward_return_pct.toFixed(2)}%</Td>
                <Td className="tabular-nums">{(row.share_positive * 100).toFixed(1)}%</Td>
              </tr>
            ))}
          </Table>
        </Card>
        <p className="text-xs text-[#64748B]">
          Daily bars through the last completed session, refreshed every 10 minutes. “·” means not enough history for that check. To trade a screen like this, build it in the Strategy lab and
          backtest it first.
        </p>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Watchlist">
        <ErrorState message={error instanceof Error ? error.message : "watchlist_unavailable"} />
      </PageFrame>
    );
  }
}
