export const metadata = { title: "Momentum trial · StockX" };
import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Card, Table, Td } from "@/components/ui";
import { formatInr } from "@/lib/money";

export const dynamic = "force-dynamic";

type Holding = { symbol: string; value: number; cost: number; return: number | null; pending_sell?: boolean };
type Month = { month_end: string; strategy: number; benchmark: number; niftybees: number };
type Backtest = { period: string; cagr: number; benchmark_cagr: number; max_drawdown: number };
export type TrialReport = {
  status: string;
  as_of_session?: string;
  next_decision?: string;
  capital?: number;
  hold?: number;
  position?: number;
  return?: number;
  benchmark_return?: number;
  niftybees_return?: number;
  holdings?: Holding[];
  months?: Month[];
  pending_ranking?: Array<{ rank: number; symbol: string }>;
  backtest?: Backtest;
};

const pct = (value: number | null | undefined) =>
  value === null || value === undefined || !Number.isFinite(value) ? "—" : `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value * 100).toFixed(1)}%`;
const tone = (value: number | null | undefined) => (value === null || value === undefined ? "" : value > 0 ? "text-[#22C55E]" : value < 0 ? "text-[#EF4444]" : "");
const day = (iso?: string) => (iso ? new Date(`${iso}T00:00:00+05:30`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: "Asia/Kolkata" }) : "—");
const monthName = (iso: string) => new Date(`${iso}T00:00:00+05:30`).toLocaleDateString("en-IN", { month: "short", year: "numeric", timeZone: "Asia/Kolkata" });

export default async function MomentumTrialPage() {
  let report: TrialReport;
  try {
    report = await fetchApi<TrialReport>("/api/v1/momentum-trial");
  } catch (error) {
    return (
      <PageFrame title="Momentum trial">
        <ErrorState message={error instanceof Error ? error.message : "momentum_trial_unavailable"} />
      </PageFrame>
    );
  }
  const running = report.status === "running";
  const holdings = report.holdings ?? [];
  const hold = report.hold ?? 10;
  return (
    <PageFrame
      title="Momentum trial"
      description={`Top ${hold} of NSE's 500 most liquid stocks by 12-month momentum, rebalanced monthly. ${report.capital ? `${formatInr(report.capital)} of paper money` : "Paper money"}${report.position ? ` (${formatInr(report.position)} a stock)` : ""}: no real orders are placed.`}
    >
      <Card title="Status" right={<Badge tone="info">PAPER ONLY</Badge>}>
        <p data-testid="trial-status" className="text-sm text-[#E6EDF3]">
          {report.status === "not started" ? "Not started yet." : running ? "Running" : "Waiting for the first trade"}
          {report.as_of_session ? <span className="text-[#94A3B8]"> · data to {day(report.as_of_session)}</span> : null}
        </p>
        {report.next_decision ? <p className="text-xs text-[#94A3B8]">Next decision: close of {day(report.next_decision)}</p> : null}
      </Card>

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          ["Trial", report.return],
          ["Benchmark (500 equal-weight)", report.benchmark_return],
          ["NIFTYBEES", report.niftybees_return],
        ].map(([label, value]) => (
          <section key={label as string} className="rounded-[12px] border border-[#26303C] bg-[#0F141B] p-4">
            <div className="text-xs uppercase tracking-wide text-[#94A3B8]">{label as string}</div>
            <div className={`mt-1 text-2xl font-semibold ${tone(value as number | undefined)}`}>{running ? pct(value as number | undefined) : "—"}</div>
          </section>
        ))}
      </div>

      {running ? (
        <Card title={`Holdings (${holdings.length})`}>
          <Table head={["Stock", "Value", "Return"]} minWidth={320}>
            {holdings.map((h) => (
              <tr key={h.symbol} className="border-t border-[#1E2631]">
                <Td>
                  {h.symbol}
                  {h.pending_sell ? <span className="ml-1 text-[10px] text-[#F59E0B]">selling</span> : null}
                </Td>
                <Td>{formatInr(Math.round(h.value))}</Td>
                <Td className={tone(h.return)}>{pct(h.return)}</Td>
              </tr>
            ))}
          </Table>
        </Card>
      ) : report.pending_ranking?.length ? (
        <Card title="To be bought at the next open">
          <p className="text-sm text-[#CBD5E1]">{report.pending_ranking.slice(0, hold).map((r) => r.symbol).join(", ")}</p>
          <p className="mt-1 text-xs text-[#94A3B8]">{`The first ${hold} that can be bought at that open, in this order.`}</p>
        </Card>
      ) : null}

      {running && report.months?.length ? (
        <Card title="By month">
          <Table head={["Month", "Trial", "Benchmark", "NIFTYBEES"]} minWidth={360}>
            {[...report.months].reverse().map((m) => (
              <tr key={m.month_end} className="border-t border-[#1E2631]">
                <Td>{monthName(m.month_end)}</Td>
                <Td className={tone(m.strategy)}>{pct(m.strategy)}</Td>
                <Td>{pct(m.benchmark)}</Td>
                <Td>{pct(m.niftybees)}</Td>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}

      {report.backtest?.cagr !== undefined ? (
        <p className="text-xs text-[#94A3B8]">
          Backtest {report.backtest.period}: {pct(report.backtest.cagr)} a year against {pct(report.backtest.benchmark_cagr)} for the benchmark, worst fall{" "}
          {pct(-report.backtest.max_drawdown)}. Judged after 12 months (Oct 2027).
        </p>
      ) : null}
    </PageFrame>
  );
}
