import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Card, Empty, Score, Stat, SymbolLink } from "@/components/ui";
import { AGENT_KIND, inr, istTime, num, price } from "@/lib/format";

export const metadata = { title: "Trade journal · StockX" };
export const dynamic = "force-dynamic";

type Vote = { agent_name: string; horizon: string; signal: number; confidence: number; reason_codes?: string[] };
type Trade = {
  symbol: string;
  status: string;
  horizon: string | null;
  decided_at: string | null;
  decision_bar: string | null;
  fused_signal: number | null;
  fused_confidence: number | null;
  stop_loss: string | null;
  take_profit: string | null;
  votes: Vote[];
  risk: { status: string; checks: Array<{ name: string; passed: boolean; detail: string }> } | null;
  order: { quantity: number; limit_price: string | null; placed_at: string; status: string; note?: string | null };
  entry_fill: { price: string; quantity: number; fees: string; at: string } | null;
  exit: { price: string; fees: string; at: string; reason: string | null } | null;
  mark: string | null;
  pnl: string | null;
};

const STATUS_TONE: Record<string, "up" | "info" | "muted" | "down"> = { closed: "muted", open: "info", cancelled: "muted", expired: "muted", rejected: "down" };
const EXIT_LABEL: Record<string, string> = { stop: "stop-loss hit (−2%)", target: "target hit (+4%)", signal: "agents turned bearish", kill_switch: "kill switch" };

export default async function JournalPage() {
  try {
    const { trades } = await fetchApi<{ trades: Trade[] }>("/api/v1/journal?limit=100");
    const filled = trades.filter((trade) => trade.entry_fill);
    const pnl = filled.reduce((sum, trade) => sum + (trade.pnl ? Number(trade.pnl) : 0), 0);
    const closed = trades.filter((trade) => trade.status === "closed");
    const wins = closed.filter((trade) => Number(trade.pnl) > 0).length;
    return (
      <PageFrame
        title="Trade journal"
        description="Every paper entry as one story: which agents voted, the fused score, each risk check, the order, the fill, the exit, and the P&L after Zerodha charges."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Entries" value={trades.length} hint={`${filled.length} filled`} />
          <Stat label="Open / closed" value={`${filled.length - closed.length} / ${closed.length}`} />
          <Stat label="Win rate (closed)" value={closed.length ? `${Math.round((wins / closed.length) * 100)}%` : "—"} hint={closed.length ? `${wins} of ${closed.length}` : "no closed trades yet"} />
          <Stat label="P&L (filled, after charges)" value={inr(pnl)} tone={pnl >= 0 ? "up" : "down"} hint="open trades at the latest 5-minute close" />
        </div>
        {trades.length === 0 ? (
          <Empty>No entries in this session yet.</Empty>
        ) : (
          <div className="space-y-3">
            {trades.map((trade) => {
              const value = trade.pnl ? Number(trade.pnl) : null;
              return (
                <Card
                  key={trade.order.placed_at + trade.symbol}
                  title={`${trade.horizon ?? ""} · placed ${istTime(trade.order.placed_at)} IST`}
                  right={<Badge tone={STATUS_TONE[trade.status] ?? "muted"}>{trade.status}</Badge>}
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div className="text-lg">
                      <SymbolLink symbol={trade.symbol} />{" "}
                      <span className="text-sm text-[#94A3B8]">
                        BUY {trade.order.quantity} · limit ₹{price(trade.order.limit_price)} · stop ₹{price(trade.stop_loss)} · target ₹{price(trade.take_profit)}
                      </span>
                    </div>
                    <div className={`text-lg font-semibold tabular-nums ${value === null ? "text-[#64748B]" : value >= 0 ? "text-[#22C55E]" : "text-[#EF4444]"}`}>
                      {value === null ? "—" : inr(value)}
                    </div>
                  </div>
                  <ol className="mt-3 grid gap-3 text-xs lg:grid-cols-4">
                    <li className="rounded border border-[#26303C] p-2">
                      <div className="mb-1 font-semibold uppercase text-[#94A3B8]">1 · Agents ({trade.votes.length})</div>
                      {trade.votes.length === 0 ? <span className="text-[#64748B]">no stored votes</span> : null}
                      {trade.votes.map((vote) => (
                        <div key={vote.agent_name} className="flex justify-between gap-2">
                          <span>
                            {vote.agent_name} {AGENT_KIND[vote.agent_name] === "llm" ? <Badge tone="info">LLM</Badge> : null}
                          </span>
                          <span>
                            <Score value={vote.signal} /> <span className="text-[#64748B]">c {num(vote.confidence)}</span>
                          </span>
                        </div>
                      ))}
                    </li>
                    <li className="rounded border border-[#26303C] p-2">
                      <div className="mb-1 font-semibold uppercase text-[#94A3B8]">2 · Fusion & decision</div>
                      <div>
                        fused <Score value={trade.fused_signal} /> · confidence {num(trade.fused_confidence)}
                      </div>
                      <div className="text-[#64748B]">needs ≥ +0.20 and ≥ 0.30</div>
                      <div className="mt-1 text-[#64748B]">decided {trade.decided_at ? istTime(trade.decided_at) : "—"} · bar {istTime(trade.decision_bar)}</div>
                    </li>
                    <li className="rounded border border-[#26303C] p-2">
                      <div className="mb-1 font-semibold uppercase text-[#94A3B8]">3 · Risk ({trade.risk?.checks.length ?? 0} checks)</div>
                      {trade.risk?.checks.map((check) => (
                        <div key={check.name} className={check.passed ? "text-[#94A3B8]" : "text-[#EF4444]"}>
                          {check.passed ? "✓" : "✗"} {check.name}
                        </div>
                      ))}
                    </li>
                    <li className="rounded border border-[#26303C] p-2">
                      <div className="mb-1 font-semibold uppercase text-[#94A3B8]">4 · Execution</div>
                      {trade.entry_fill ? (
                        <div>
                          filled {trade.entry_fill.quantity} @ ₹{price(trade.entry_fill.price)} · {istTime(trade.entry_fill.at)} · charges ₹{price(trade.entry_fill.fees)}
                        </div>
                      ) : (
                        <div className="text-[#64748B]">order {trade.order.status.toLowerCase()}{trade.order.note ? `: ${trade.order.note}` : ""}</div>
                      )}
                      {trade.exit ? (
                        <div className="mt-1">
                          exit @ ₹{price(trade.exit.price)} · {istTime(trade.exit.at)} · {EXIT_LABEL[trade.exit.reason ?? ""] ?? trade.exit.reason}
                        </div>
                      ) : trade.entry_fill ? (
                        <div className="mt-1 text-[#64748B]">open · mark ₹{price(trade.mark)}</div>
                      ) : null}
                    </li>
                  </ol>
                </Card>
              );
            })}
          </div>
        )}
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Trade journal">
        <ErrorState message={error instanceof Error ? error.message : "journal_unavailable"} />
      </PageFrame>
    );
  }
}
