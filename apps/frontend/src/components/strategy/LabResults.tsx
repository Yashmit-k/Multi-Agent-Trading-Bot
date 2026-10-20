"use client";

import { useState } from "react";
import { Badge, Card, Stat, Table, Td } from "@/components/ui";
import { LabChart } from "@/components/strategy/LabChart";
import type { LabResult } from "@/components/strategy/types";

const pct = (value: number | null | undefined, digits = 1) => (value === null || value === undefined || !Number.isFinite(value) ? "—" : `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`);
const rupees = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${value < 0 ? "−" : ""}₹${Math.abs(value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const ist = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });

export function LabResults({ result }: { result: LabResult }) {
  const [shown, setShown] = useState(100);
  const m = result.metrics;
  const beat = result.benchmark ? m.total_return - result.benchmark.total_return : null;
  const trades = [...result.trades].reverse();
  return (
    <div className="space-y-3" data-testid="lab-results">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Net P&L" value={rupees(m.net_pnl)} tone={m.net_pnl >= 0 ? "up" : "down"} hint={`after ${rupees(m.charges)} charges`} />
        <Stat label="Total return" value={pct(m.total_return)} tone={m.total_return >= 0 ? "up" : "down"} hint={result.benchmark ? `NIFTY 50 ${pct(result.benchmark.total_return)}` : undefined} />
        <Stat label="Max drawdown" value={pct(-m.max_drawdown)} tone="down" hint={`Sharpe ${m.sharpe === null ? "n/a" : m.sharpe.toFixed(2)}`} />
        <Stat label="Trades" value={m.trades} hint={`win rate ${pct(m.win_rate)} · PF ${m.profit_factor === null ? "n/a" : m.profit_factor.toFixed(2)}${m.expectancy_r === null || m.expectancy_r === undefined ? "" : ` · ${m.expectancy_r.toFixed(2)}R/trade`}`} />
      </div>
      <Card title="Equity vs NIFTY 50 buy-and-hold">
        <LabChart strategy={result.equity_curve} benchmark={result.benchmark?.curve ?? null} />
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-[#94A3B8]">
          {beat !== null ? <Badge tone={beat >= 0 ? "up" : "down"}>{beat >= 0 ? "beat" : "trailed"} NIFTY 50 by {pct(Math.abs(beat))}</Badge> : null}
          <span>
            {result.symbols_tested} stocks · {result.start} to {result.end} · CAGR {pct(m.cagr)} · avg hold {m.average_bars_held?.toFixed(1) ?? "—"} bars
          </span>
          {result.benchmark?.from && result.benchmark.from > result.start ? (
            <span className="text-[#F59E0B]">NIFTY 50 data starts {result.benchmark.from}, so the benchmark covers a shorter period.</span>
          ) : null}
          {result.trades_skipped_by_portfolio ? <span>{result.trades_skipped_by_portfolio} signals skipped (no free slot or cash)</span> : null}
        </div>
      </Card>
      <div className="grid gap-3 md:grid-cols-2">
        <Card title="Does it hold up in both halves?">
          {result.halves.first_half && result.halves.second_half ? (
            <div className="space-y-1 text-sm">
              <p>
                Before {result.halves.split_date}: {result.halves.first_half.trades} trades, <b className={result.halves.first_half.net_pnl >= 0 ? "text-[#22C55E]" : "text-[#EF4444]"}>{rupees(result.halves.first_half.net_pnl)}</b>
              </p>
              <p>
                From {result.halves.split_date}: {result.halves.second_half.trades} trades, <b className={result.halves.second_half.net_pnl >= 0 ? "text-[#22C55E]" : "text-[#EF4444]"}>{rupees(result.halves.second_half.net_pnl)}</b>
              </p>
              <p className="text-xs text-[#64748B]">A rule that only works in one half is probably fitted to that period.</p>
            </div>
          ) : (
            <p className="text-sm text-[#94A3B8]">Not enough data.</p>
          )}
        </Card>
        <Card title="How trades ended">
          <ul className="space-y-1 text-sm">
            {Object.entries(m.exit_reasons).map(([reason, count]) => (
              <li key={reason} className="flex justify-between">
                <span className="text-[#94A3B8]">{reason.replaceAll("_", " ")}</span>
                <span className="tabular-nums">{count}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-[#64748B]">
            Average win {rupees(m.average_win)} · average loss {rupees(m.average_loss)}
          </p>
        </Card>
      </div>
      <Card title={`Trades (newest first${result.trades_listed_limit && m.trades > result.trades_listed_limit ? `, last ${result.trades_listed_limit} listed` : ""})`}>
        <Table head={["Symbol", "Side", "Entry (IST)", "Exit (IST)", "Qty", "Entry ₹", "Avg exit ₹", "Exits", "Charges", "Net P&L"]} minWidth={940}>
          {trades.slice(0, shown).map((trade, index) => (
            <tr key={`${trade.symbol}-${trade.entry_at}-${index}`}>
              <Td>{trade.symbol}</Td>
              <Td className={`text-xs ${trade.direction === "short" ? "text-[#EF4444]" : "text-[#22C55E]"}`}>{trade.direction === "short" ? "SHORT" : "LONG"}</Td>
              <Td className="whitespace-nowrap text-xs">{ist(trade.entry_at)}</Td>
              <Td className="whitespace-nowrap text-xs">{ist(trade.exit_at)}</Td>
              <Td className="tabular-nums">{trade.quantity}</Td>
              <Td className="tabular-nums">{trade.entry_price.toFixed(2)}</Td>
              <Td className="tabular-nums">{trade.exit_price.toFixed(2)}</Td>
              <Td className="text-xs text-[#94A3B8]">
                {trade.legs && trade.legs.length > 1 ? trade.legs.map((leg) => `${leg.quantity}@${leg.price.toFixed(1)} ${leg.reason.replaceAll("_", " ")}`).join(", ") : trade.reason.replaceAll("_", " ")}
              </Td>
              <Td className="tabular-nums text-xs">{trade.charges.toFixed(2)}</Td>
              <Td className={`tabular-nums ${trade.net_pnl >= 0 ? "text-[#22C55E]" : "text-[#EF4444]"}`}>{rupees(trade.net_pnl)}</Td>
            </tr>
          ))}
        </Table>
        {trades.length > shown ? (
          <button type="button" className="mt-2 text-xs text-[#60A5FA]" onClick={() => setShown(shown + 200)}>
            Show more ({trades.length - shown} left)
          </button>
        ) : null}
      </Card>
      <ul className="list-disc space-y-1 pl-5 text-xs text-[#64748B]">
        {result.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </div>
  );
}
