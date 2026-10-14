"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { DailyPnlDay } from "@/lib/daily-pnl";
import { buildSundayFirstLayout } from "@/lib/calendar-layout";
import { formatDateKeyLong, WEEKDAY_FULL, WEEKDAY_LABELS } from "@/lib/ist";
import { cellClass, stateLabel, visualState } from "@/lib/cell-state";
import { formatSignedInr } from "@/lib/money";
import { inrForThreshold, PNL_HEATMAP_THRESHOLDS } from "@/lib/pnl-heatmap";

type Props = {
  endKey: string;
  days: DailyPnlDay[];
  selected: string | null;
  onSelect: (key: string | null) => void;
  pnlBasisLabel: string;
  emptyReason: string | null;
  referenceEquity: number | null;
};

export function PnlCalendar({ endKey, days, selected, onSelect, pnlBasisLabel, emptyReason, referenceEquity }: Props) {
  const layout = useMemo(() => buildSundayFirstLayout(endKey, 365), [endKey]);
  const byDate = useMemo(() => new Map(days.map((day) => [day.calendar_date_ist, day])), [days]);
  const scroller = useRef<HTMLDivElement>(null);
  const [focusKey, setFocusKey] = useState<string | null>(layout.keys[layout.keys.length - 1] ?? null);
  const [tip, setTip] = useState<{ key: string; x: number; y: number } | null>(null);

  useEffect(() => {
    const node = scroller.current;
    if (node && typeof node.scrollTo === "function") {
      node.scrollTo({ left: node.scrollWidth, behavior: "instant" });
    }
  }, [endKey]);

  function move(deltaWeek: number, deltaDay: number) {
    if (!focusKey) return;
    const next = shift(layout, focusKey, deltaWeek, deltaDay);
    if (!next) return;
    setFocusKey(next);
    const node = scroller.current?.querySelector(`[data-date="${next}"]`) as HTMLElement | null;
    node?.focus();
  }

  const counts = useMemo(() => {
    let profit = 0;
    let loss = 0;
    let active = 0;
    for (const day of days) {
      const state = visualState(day);
      if (state.kind === "profit") {
        profit += 1;
        active += 1;
      } else if (state.kind === "loss") {
        loss += 1;
        active += 1;
      } else if (state.kind === "zero" && day.has_activity) active += 1;
    }
    return { profit, loss, active };
  }, [days]);

  const net = days.reduce((sum, day) => sum + (day.net_pnl_inr ?? 0), 0);
  const refEq = referenceEquity && referenceEquity > 0 ? referenceEquity : null;

  return (
    <section data-testid="pnl-calendar" className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-[#E6EDF3]">Trading Activity</h2>
          <p className="text-sm text-[#94A3B8]">
            Each cell is one IST calendar day. Color is {pnlBasisLabel} as a % of that day’s start-of-day equity
            (fixed thresholds).
          </p>
        </div>
        <dl className="flex flex-wrap gap-4 font-mono text-sm tabular-nums text-[#94A3B8]">
          <div>
            Period {pnlBasisLabel}{" "}
            <span className="text-[#E6EDF3]">{days.length ? formatSignedInr(net) : "—"}</span>
          </div>
          <div>
            Active {counts.active} · Profit {counts.profit} · Loss {counts.loss}
          </div>
        </dl>
      </div>
      {emptyReason ? (
        <p data-testid="pnl-empty" className="mb-3 text-sm text-[#94A3B8]">
          {emptyReason}
        </p>
      ) : null}
      <div ref={scroller} className="overflow-x-auto pb-2" data-testid="calendar-scroll">
        <div className="min-w-[720px] w-full" data-testid="calendar-grid-wrap">
          <div
            className="mb-1 grid w-full"
            style={{ gridTemplateColumns: `28px repeat(${layout.weekStarts.length}, minmax(0, 1fr))`, columnGap: 3 }}
          >
            <span />
            {layout.weekStarts.map((_, weekIndex) => {
              const label = layout.monthLabels.find((item) => item.weekIndex === weekIndex);
              return (
                <span key={weekIndex} className="text-[10px] leading-none text-[#94A3B8]">
                  {label?.label ?? ""}
                </span>
              );
            })}
          </div>
          <div role="grid" aria-label="Trading P&L calendar" className="flex w-full gap-[3px]">
            <div className="flex w-8 shrink-0 flex-col justify-between py-[1px] pr-1 text-[11px] leading-none text-[#94A3B8]" aria-hidden="true">
              {WEEKDAY_LABELS.map((label) => (
                <div key={label} className="flex aspect-square items-center">
                  {label}
                </div>
              ))}
            </div>
            <div className="flex min-w-0 flex-1 gap-[3px]">
              {layout.columns.map((column, weekIndex) => (
                <div key={layout.weekStarts[weekIndex]} className="flex min-w-0 flex-1 flex-col gap-[3px]" role="row">
                  {column.map((dateKey, weekday) => {
                    if (!dateKey) {
                      return <div key={`${weekIndex}-${weekday}`} className="aspect-square w-full min-h-[12px]" />;
                    }
                    const day = byDate.get(dateKey);
                    const state = visualState(day);
                    const tabIndex = focusKey === dateKey ? 0 : -1;
                    return (
                      <button
                        key={dateKey}
                        type="button"
                        role="gridcell"
                        data-date={dateKey}
                        data-testid={`cell-${dateKey}`}
                        aria-label={stateLabel(state, dateKey)}
                        aria-selected={selected === dateKey}
                        aria-pressed={selected === dateKey}
                        tabIndex={tabIndex}
                        className={`aspect-square w-full min-h-[12px] min-w-[12px] rounded-[3px] ${cellClass(state)} focus:outline-none focus:ring-2 focus:ring-cyan-400 ${
                          selected === dateKey ? "ring-2 ring-[#E6EDF3]" : ""
                        }`}
                        onClick={() => onSelect(dateKey)}
                        onFocus={(event) => {
                          setFocusKey(dateKey);
                          const box = event.currentTarget.getBoundingClientRect();
                          setTip({ key: dateKey, x: box.left, y: box.bottom });
                        }}
                        onBlur={() => setTip((current) => (current?.key === dateKey ? null : current))}
                        onMouseEnter={(event) => {
                          const box = event.currentTarget.getBoundingClientRect();
                          setTip({ key: dateKey, x: box.left, y: box.bottom });
                        }}
                        onMouseLeave={() => setTip((current) => (current?.key === dateKey ? null : current))}
                        onKeyDown={(event) => {
                          if (event.key === "ArrowRight") {
                            event.preventDefault();
                            move(1, 0);
                          } else if (event.key === "ArrowLeft") {
                            event.preventDefault();
                            move(-1, 0);
                          } else if (event.key === "ArrowDown") {
                            event.preventDefault();
                            move(0, 1);
                          } else if (event.key === "ArrowUp") {
                            event.preventDefault();
                            move(0, -1);
                          } else if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            onSelect(dateKey);
                          } else if (event.key === "Escape") {
                            onSelect(null);
                          }
                        }}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      {tip ? <Tooltip dateKey={tip.key} day={byDate.get(tip.key)} x={tip.x} y={tip.y} /> : null}
      <Legend referenceEquity={refEq} />
      <p className="sr-only">{WEEKDAY_FULL.join(", ")}</p>
    </section>
  );
}

function shift(layout: ReturnType<typeof buildSundayFirstLayout>, key: string, dWeek: number, dDay: number): string | null {
  for (let w = 0; w < layout.columns.length; w += 1) {
    const d = layout.columns[w].indexOf(key);
    if (d < 0) continue;
    let nw = w + dWeek;
    let nd = d + dDay;
    if (nd > 6) {
      nw += 1;
      nd = 0;
    }
    if (nd < 0) {
      nw -= 1;
      nd = 6;
    }
    const next = layout.columns[nw]?.[nd];
    return next ?? null;
  }
  return null;
}

function Tooltip({ dateKey, day, x, y }: { dateKey: string; day?: DailyPnlDay; x: number; y: number }) {
  const state = visualState(day);
  return (
    <div
      role="tooltip"
      data-testid="cell-tooltip"
      className="pointer-events-none fixed z-50 max-w-xs rounded-lg border border-[#26303C] bg-[#171F2A] px-3 py-2 text-xs text-[#E6EDF3] shadow"
      style={{ left: Math.min(x, window.innerWidth - 280), top: y + 8 }}
    >
      <p className="font-medium">{formatDateKeyLong(dateKey)} (IST)</p>
      <p className="text-[#94A3B8]">{stateLabel(state, dateKey)}</p>
      {state.kind === "market_closed" ? <p>Exchange closed. No P&L.</p> : null}
      {state.kind === "missing" ? <p>Result unavailable or incomplete.</p> : null}
      {state.kind === "no_activity" ? <p>Market was open; no qualifying activity recorded.</p> : null}
      {day && day.net_pnl_inr !== null && state.kind !== "market_closed" && state.kind !== "missing" ? (
        <p className="font-mono tabular-nums">{formatSignedInr(day.net_pnl_inr)}</p>
      ) : null}
      {day?.realized_pnl_inr != null ? <p>Realized {formatSignedInr(day.realized_pnl_inr)}</p> : null}
      {day?.unrealized_change_inr != null ? <p>Unrealized Δ {formatSignedInr(day.unrealized_change_inr)}</p> : null}
      {day?.fees_inr != null ? <p>Fees {formatSignedInr(day.fees_inr)} (already in equity if charged)</p> : null}
      {day?.complete === false ? <p>complete=false</p> : null}
      {day?.session_id ? <p>Session {day.session_id}</p> : null}
      {day?.source_updated_at ? <p>Source {day.source_updated_at}</p> : null}
    </div>
  );
}

function Legend({ referenceEquity }: { referenceEquity: number | null }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-[#94A3B8]" data-testid="calendar-legend">
      <span>Less</span>
      {[1, 2, 3, 4, 5].map((level) => (
        <span key={`l${level}`} className={`inline-block h-3 w-3 rounded-[3px] ${cellClass({ kind: "loss", level: level as 1 | 2 | 3 | 4 | 5 })}`} title={`Loss level ${level}`} />
      ))}
      <span className={`inline-block h-3 w-3 rounded-[3px] ${cellClass({ kind: "zero" })}`} title="Zero P&L" />
      <span className={`inline-block h-3 w-3 rounded-[3px] ${cellClass({ kind: "no_activity" })}`} title="No activity" />
      <span className={`inline-block h-3 w-3 rounded-[3px] ${cellClass({ kind: "market_closed" })}`} title="Market closed" />
      <span className={`inline-block h-3 w-3 rounded-[3px] ${cellClass({ kind: "missing" })}`} title="Missing" />
      {[1, 2, 3, 4, 5].map((level) => (
        <span key={`p${level}`} className={`inline-block h-3 w-3 rounded-[3px] ${cellClass({ kind: "profit", level: level as 1 | 2 | 3 | 4 | 5 })}`} title={`Profit level ${level}`} />
      ))}
      <span>More</span>
      <span>
        Thresholds {PNL_HEATMAP_THRESHOLDS.map((item) => `${item * 100}%`).join(" / ")}
        {referenceEquity
          ? ` of ref equity ${referenceEquity.toLocaleString("en-IN")} → ${PNL_HEATMAP_THRESHOLDS.map((item) =>
              Math.round(inrForThreshold(referenceEquity, item)).toLocaleString("en-IN"),
            ).join(" / ")} INR`
          : " (INR equivalents need start-of-day equity)"}
      </span>
    </div>
  );
}
