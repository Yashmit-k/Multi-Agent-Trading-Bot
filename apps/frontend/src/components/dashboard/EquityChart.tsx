import type { DailyPnlDay } from "@/lib/daily-pnl";
import { formatSignedInr } from "@/lib/money";

export function EquityChart({
  mode,
  days,
  startingCash,
}: {
  mode: "demo" | "real";
  days: DailyPnlDay[];
  startingCash: number | null;
}) {
  if (mode !== "demo" && days.length > 0) {
    // Core end-of-day equity per IST trading day; the last point may be today's provisional book.
    const series = days.map((day) => ({
      key: day.calendar_date_ist,
      equity: (day as DailyPnlDay & { equity_inr?: number | null }).equity_inr ?? (day.start_of_day_equity_inr ?? 0) + (day.net_pnl_inr ?? 0),
      complete: day.complete,
    }));
    const base = days[0].start_of_day_equity_inr ?? series[0].equity;
    const all = [{ key: "start", equity: base, complete: true }, ...series];
    const lo = Math.min(...all.map((item) => item.equity));
    const hi = Math.max(...all.map((item) => item.equity));
    const range = hi - lo || 1;
    const path = all
      .map((item, index) => `${index === 0 ? "M" : "L"}${(8 + (index / Math.max(all.length - 1, 1)) * 704).toFixed(1)} ${(8 + (1 - (item.equity - lo) / range) * 124).toFixed(1)}`)
      .join(" ");
    const last = series[series.length - 1];
    return (
      <section className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4" data-testid="equity-chart">
        <h2 className="mb-2 text-lg font-semibold text-[#E6EDF3]">Equity history</h2>
        <p className="mb-2 text-xs text-[#94A3B8]">Paper-account equity at each close (Core end-of-day books){last.complete ? "" : "; the last point is today, provisional"}.</p>
        <svg viewBox="0 0 720 140" className="h-36 w-full" role="img" aria-label="Paper equity by trading day">
          <path d={path} fill="none" stroke={last.equity >= base ? "#22C55E" : "#EF4444"} strokeWidth="2" />
        </svg>
        <p className="mt-2 font-mono text-sm tabular-nums text-[#94A3B8]">
          Start ₹{base.toLocaleString("en-IN", { maximumFractionDigits: 2 })} · Latest ₹{last.equity.toLocaleString("en-IN", { maximumFractionDigits: 2 })} ({formatSignedInr(last.equity - base)})
        </p>
      </section>
    );
  }

  if (mode !== "demo") {
    return (
      <section className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4" data-testid="equity-chart">
        <h2 className="mb-2 text-lg font-semibold text-[#E6EDF3]">Equity history</h2>
        <p data-testid="equity-graph-empty" className="text-sm text-[#94A3B8]">
          Daily equity history is not stored yet. The curve appears once end-of-day snapshots are stored; until then nothing is drawn, rather than a flat zero line.
        </p>
      </section>
    );
  }

  if (days.length === 0) {
    return (
      <section className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4" data-testid="equity-chart">
        <h2 className="mb-2 text-lg font-semibold text-[#E6EDF3]">Equity history</h2>
        <p data-testid="equity-demo-empty" className="text-sm text-[#94A3B8]">
          No demo equity series for this session.
        </p>
      </section>
    );
  }

  const start = startingCash && startingCash > 0 ? startingCash : 1_000_000;
  const points: Array<{ key: string; equity: number }> = [];
  let equity = start;
  for (const day of days) {
    if (day.net_pnl_inr != null && day.trading_calendar_state !== "closed" && day.complete && day.pnl_basis !== "unavailable") {
      equity += day.net_pnl_inr;
    }
    points.push({ key: day.calendar_date_ist, equity });
  }
  const values = points.map((item) => item.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 720;
  const h = 140;
  const pad = 8;
  const d = points
    .map((item, index) => {
      const x = pad + (index / Math.max(points.length - 1, 1)) * (w - pad * 2);
      const y = pad + (1 - (item.equity - min) / span) * (h - pad * 2);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <section className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4" data-testid="equity-chart">
      <h2 className="mb-2 text-lg font-semibold text-[#E6EDF3]">Equity history</h2>
      <p className="mb-2 text-xs text-amber-200">DEMO fixture cumulative series. Not Core paper-account equity. Not backtest performance.</p>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-36 w-full" role="img" aria-label="Demo cumulative equity">
        <path d={d} fill="none" stroke="#39d353" strokeWidth="2" />
      </svg>
      <p className="mt-2 font-mono text-sm tabular-nums text-[#94A3B8]">
        Start {formatSignedInr(start)} · End {formatSignedInr(values[values.length - 1] ?? start)}
      </p>
    </section>
  );
}
