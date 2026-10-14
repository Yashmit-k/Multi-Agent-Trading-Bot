import { Card, Stat } from "@/components/ui";
import { inr } from "@/lib/format";

export type BacktestPerformance = {
  total_return: number;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown: string;
  win_rate: number;
  profit_factor: string | null;
  trades: number;
  gross_pnl: string;
  transaction_costs: string;
  slippage: string;
  net_pnl: string;
  periods_per_year: number;
};

function percent(value: number | string | null | undefined, digits = 2): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${(n * 100).toFixed(digits)}%`;
}

function ratio(value: number | string | null | undefined): string {
  const n = typeof value === "string" ? Number(value) : value;
  return n === null || n === undefined || !Number.isFinite(n) ? "n/a" : n.toFixed(2);
}

export function BacktestSummary({ performance }: { performance: BacktestPerformance }) {
  const net = Number(performance.net_pnl);
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total return" value={percent(performance.total_return)} tone={performance.total_return >= 0 ? "up" : "down"} />
        <Stat label="Net P&L" value={inr(performance.net_pnl)} tone={net >= 0 ? "up" : "down"} hint={`gross ${inr(performance.gross_pnl)}`} />
        <Stat label="Max drawdown" value={percent(-Math.abs(Number(performance.max_drawdown)))} tone="down" />
        <Stat label="Trades" value={performance.trades} hint={`win rate ${percent(performance.win_rate, 1)}`} />
      </div>
      <Card title="Risk-adjusted and costs">
        <dl className="grid gap-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-[#94A3B8]">Sharpe (annualised)</dt>
            <dd className="tabular-nums">{ratio(performance.sharpe)}</dd>
          </div>
          <div>
            <dt className="text-xs text-[#94A3B8]">Sortino</dt>
            <dd className="tabular-nums">{ratio(performance.sortino)}</dd>
          </div>
          <div>
            <dt className="text-xs text-[#94A3B8]">Profit factor</dt>
            <dd className="tabular-nums">{ratio(performance.profit_factor)}</dd>
          </div>
          <div>
            <dt className="text-xs text-[#94A3B8]">Transaction costs</dt>
            <dd className="tabular-nums">{inr(performance.transaction_costs)}</dd>
          </div>
          <div>
            <dt className="text-xs text-[#94A3B8]">Slippage</dt>
            <dd className="tabular-nums">{inr(performance.slippage)}</dd>
          </div>
          <div>
            <dt className="text-xs text-[#94A3B8]">Bars per year</dt>
            <dd className="tabular-nums">{performance.periods_per_year}</dd>
          </div>
        </dl>
      </Card>
    </>
  );
}
