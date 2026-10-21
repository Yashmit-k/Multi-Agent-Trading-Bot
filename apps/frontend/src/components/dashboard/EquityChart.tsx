import type { DailyPnlDay } from "@/lib/daily-pnl";
import { formatInr, formatSignedInr } from "@/lib/money";

const PLOT = { width: 560, height: 240, left: 78, right: 12, top: 14, bottom: 30 };
const MAX_X_LABELS = 6;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatAxisInr(value: number): string {
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

// "2025-10-15" -> "15 Oct" (or "15 Oct 2025"); read from the string so time zones cannot shift the day.
function formatDay(iso: string, withYear = false): string {
  const [year, month, day] = iso.split("-");
  const name = MONTHS[Number(month) - 1];
  if (!name) return iso;
  return `${Number(day)} ${name}${withYear ? ` ${year}` : ""}`;
}

// Honest y-scale: pad the data (and the starting cash) by at least 0.5% of the start or ₹5,000,
// so a tiny move cannot fill the whole chart height.
function equityScale(values: number[], base: number): { lo: number; hi: number; ticks: number[] } {
  const pad = Math.max(Math.abs(base) * 0.005, 5000);
  const lo = Math.min(base, ...values) - pad;
  const hi = Math.max(base, ...values) + pad;
  const rough = (hi - lo) / 3;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((candidate) => candidate >= rough) ?? rough;
  const ticks: number[] = [];
  for (let tick = Math.ceil(lo / step) * step; tick <= hi; tick += step) ticks.push(Math.round(tick));
  return { lo, hi, ticks };
}

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
    const series = days.flatMap((day) => {
      const reported = (day as DailyPnlDay & { equity_inr?: number | null }).equity_inr;
      const equity =
        reported ?? (day.start_of_day_equity_inr != null && day.net_pnl_inr != null ? day.start_of_day_equity_inr + day.net_pnl_inr : null);
      // A day without a usable equity figure is skipped rather than drawn as a drop to zero.
      return equity == null || !Number.isFinite(equity)
        ? []
        : [{ key: day.calendar_date_ist, equity, pnl: day.net_pnl_inr, complete: day.complete }];
    });
    if (series.length < 2) {
      return (
        <section className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4" data-testid="equity-chart">
          <h2 className="mb-2 text-lg font-semibold text-[#E6EDF3]">Equity history</h2>
          <p data-testid="equity-graph-short" className="text-sm text-[#94A3B8]">
            Equity history starts after the first full trading day.
          </p>
        </section>
      );
    }
    const base = days[0].start_of_day_equity_inr ?? series[0].equity;
    const last = series[series.length - 1];
    const { lo, hi, ticks } = equityScale(series.map((item) => item.equity), base);
    const x = (index: number) => PLOT.left + (index / (series.length - 1)) * (PLOT.width - PLOT.left - PLOT.right);
    const y = (value: number) => PLOT.top + (1 - (value - lo) / (hi - lo)) * (PLOT.height - PLOT.top - PLOT.bottom);
    const baseY = y(base);
    const line = series.map((item, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)} ${y(item.equity).toFixed(1)}`).join(" ");
    const area = `${line} L${x(series.length - 1).toFixed(1)} ${baseY.toFixed(1)} L${x(0).toFixed(1)} ${baseY.toFixed(1)} Z`;
    const labelStep = Math.ceil(series.length / MAX_X_LABELS);
    const labelled = new Set<number>();
    // Count back from the latest day so the newest date is always shown and labels never crowd together.
    for (let index = series.length - 1; index >= 0; index -= labelStep) labelled.add(index);
    const color = last.equity >= base ? "#22C55E" : "#EF4444";
    const radius = series.length > 60 ? 1.5 : 3;
    return (
      <section className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4" data-testid="equity-chart">
        <h2 className="mb-2 text-lg font-semibold text-[#E6EDF3]">Equity history</h2>
        <p className="mb-2 text-xs text-[#94A3B8]">Paper-account equity at each close (Core end-of-day books){last.complete ? "" : "; the last point is today, provisional"}.</p>
        <svg viewBox={`0 0 ${PLOT.width} ${PLOT.height}`} className="mx-auto h-auto w-full max-w-[720px]" role="img" aria-label="Paper equity by trading day">
          <defs>
            <clipPath id="equity-above-start">
              <rect x="0" y="0" width={PLOT.width} height={baseY} />
            </clipPath>
            <clipPath id="equity-below-start">
              <rect x="0" y={baseY} width={PLOT.width} height={PLOT.height - baseY} />
            </clipPath>
          </defs>
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={PLOT.left} x2={PLOT.width - PLOT.right} y1={y(tick)} y2={y(tick)} stroke="#26303C" strokeOpacity="0.6" />
              <text x={PLOT.left - 6} y={y(tick) + 4} textAnchor="end" fontSize="12" fill="#94A3B8">
                {formatAxisInr(tick)}
              </text>
            </g>
          ))}
          <path d={area} fill="#22C55E" fillOpacity="0.18" clipPath="url(#equity-above-start)" data-testid="equity-area-above" />
          <path d={area} fill="#EF4444" fillOpacity="0.18" clipPath="url(#equity-below-start)" data-testid="equity-area-below" />
          <line x1={PLOT.left} x2={PLOT.width - PLOT.right} y1={baseY} y2={baseY} stroke="#94A3B8" strokeDasharray="5 4" data-testid="equity-start-line" />
          <text x={PLOT.width - PLOT.right} y={baseY - 5} textAnchor="end" fontSize="12" fill="#94A3B8">
            Start {formatAxisInr(base)}
          </text>
          <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
          {series.map((item, index) => (
            <circle
              key={item.key}
              data-testid="equity-point"
              cx={x(index)}
              cy={y(item.equity)}
              r={radius}
              fill={color}
              tabIndex={series.length <= 60 ? 0 : undefined}
              className="outline-none focus:stroke-[#E6EDF3] focus:stroke-2"
            >
              <title>{`${formatDay(item.key, true)} · Equity ${formatInr(item.equity)} · P&L ${item.pnl == null ? "unavailable" : formatSignedInr(item.pnl)}`}</title>
            </circle>
          ))}
          {series.map((item, index) =>
            labelled.has(index) ? (
              <text key={item.key} x={x(index)} y={PLOT.height - 8} textAnchor="middle" fontSize="12" fill="#94A3B8">
                {formatDay(item.key)}
              </text>
            ) : null,
          )}
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
