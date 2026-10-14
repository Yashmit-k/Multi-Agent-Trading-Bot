"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { DailyPnlDay } from "@/lib/daily-pnl";
import { buildSundayFirstLayout } from "@/lib/calendar-layout";
import { formatDateKeyLong, WEEKDAY_FULL, WEEKDAY_LABELS, weekdaySundayFirst } from "@/lib/ist";
import { cellClass, stateLabel, visualState } from "@/lib/cell-state";
import { formatInr, formatPct, formatSignedInr } from "@/lib/money";
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

type TipState = { key: string; rect: DOMRect };

export function PnlCalendar({ endKey, days, selected, onSelect, pnlBasisLabel, emptyReason, referenceEquity }: Props) {
  const layout = useMemo(() => buildSundayFirstLayout(endKey, 365), [endKey]);
  const byDate = useMemo(() => new Map(days.map((day) => [day.calendar_date_ist, day])), [days]);
  const scroller = useRef<HTMLDivElement>(null);
  const [focusKey, setFocusKey] = useState<string | null>(layout.keys[layout.keys.length - 1] ?? null);
  const [tip, setTip] = useState<TipState | null>(null);

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
  const heatmap = days.length > 0;
  const weekCount = layout.weekStarts.length;
  const columnTemplate = `28px repeat(${weekCount}, minmax(12px, 1fr))`;

  return (
    <section data-testid="pnl-calendar" className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0 flex-1 break-words">
          <h2 className="text-lg font-semibold text-[#E6EDF3]">Trading Activity</h2>
          <p className="text-sm text-[#94A3B8]">
            Each cell is one IST calendar day. Color is {pnlBasisLabel} as a % of that day’s start-of-day equity
            (fixed thresholds).
          </p>
        </div>
        {heatmap ? (
          <dl className="flex shrink-0 flex-wrap gap-4 font-mono text-sm tabular-nums text-[#94A3B8]">
            <div>
              Period {pnlBasisLabel}{" "}
              <span className="text-[#E6EDF3]">{formatSignedInr(net)}</span>
            </div>
            <div>
              Active {counts.active} · Profit {counts.profit} · Loss {counts.loss}
            </div>
          </dl>
        ) : null}
      </div>
      {emptyReason ? (
        <p data-testid="pnl-empty" className="mb-3 text-sm text-[#94A3B8]">
          {emptyReason}
        </p>
      ) : null}
      {!heatmap ? (
        <p className="text-sm text-[#94A3B8]">
          No daily series is shown. Missing data is not a grey zero heatmap.
        </p>
      ) : (
        <>
          <div ref={scroller} className="overflow-x-auto pb-2" data-testid="calendar-scroll">
            <div className="min-w-[720px] w-full" data-testid="calendar-grid-wrap">
              <div className="mb-1 grid w-full" style={{ gridTemplateColumns: columnTemplate, columnGap: 3 }}>
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
              <div
                role="grid"
                aria-label="Trading P&L calendar"
                className="grid w-full"
                style={{ gridTemplateColumns: columnTemplate, columnGap: 3, rowGap: 3 }}
              >
                <div data-testid="weekday-labels" className="contents">
                  {WEEKDAY_LABELS.map((label, weekday) => (
                    <div key={label} role="row" className="contents" data-testid={`heatmap-row-${weekday}`}>
                      <div className="flex items-center text-[11px] leading-none text-[#94A3B8]" aria-hidden="true">
                        {label}
                      </div>
                      {layout.columns.map((column, weekIndex) => {
                        const dateKey = column[weekday];
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
                              setTip({ key: dateKey, rect: event.currentTarget.getBoundingClientRect() });
                            }}
                            onBlur={() => setTip((current) => (current?.key === dateKey ? null : current))}
                            onMouseEnter={(event) => {
                              setTip({ key: dateKey, rect: event.currentTarget.getBoundingClientRect() });
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
          {tip ? <Tooltip dateKey={tip.key} day={byDate.get(tip.key)} rect={tip.rect} /> : null}
          <Legend referenceEquity={refEq} />
          <p className="sr-only">{WEEKDAY_FULL.join(", ")}</p>
        </>
      )}
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

function statusCopy(kind: ReturnType<typeof visualState>["kind"]): string {
  if (kind === "profit") return "Profit";
  if (kind === "loss") return "Loss";
  if (kind === "zero") return "Break-even";
  return "No data";
}

function Tooltip({ dateKey, day, rect }: { dateKey: string; day?: DailyPnlDay; rect: DOMRect }) {
  const node = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: rect.left, top: rect.bottom + 8 });
  const state = visualState(day);
  const showPnl = state.kind === "profit" || state.kind === "loss" || state.kind === "zero";
  const showReturn = day?.net_pnl_inr != null && day.start_of_day_equity_inr != null && day.start_of_day_equity_inr > 0;

  useLayoutEffect(() => {
    const el = node.current;
    if (!el) return;
    const width = el.offsetWidth;
    const height = el.offsetHeight;
    const margin = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = rect.left;
    if (left + width + margin > vw) left = vw - width - margin;
    if (left < margin) left = margin;
    let top = rect.bottom + 8;
    if (top + height + margin > vh) top = rect.top - height - 8;
    if (top < margin) top = margin;
    if (top + height + margin > vh) top = Math.max(margin, vh - height - margin);
    setPos({ left, top });
  }, [dateKey, rect, day, state.kind]);

  return (
    <div
      ref={node}
      role="tooltip"
      data-testid="cell-tooltip"
      className="pointer-events-none fixed z-50 w-max max-w-xs rounded-lg border border-[#26303C] bg-[#171F2A] px-3 py-2 text-xs text-[#E6EDF3] shadow"
      style={{ left: pos.left, top: pos.top }}
    >
      <p className="font-medium">
        {formatDateKeyLong(dateKey)}, {WEEKDAY_FULL[weekdaySundayFirst(dateKey)]}
      </p>
      {state.kind === "missing" || state.kind === "no_activity" ? (
        <p>Daily P&L data unavailable.</p>
      ) : null}
      {state.kind === "market_closed" ? <p>Exchange closed</p> : null}
      {showPnl && day?.net_pnl_inr != null ? (
        <p className="font-mono tabular-nums">Daily Net P&L {formatSignedInr(day.net_pnl_inr)}</p>
      ) : null}
      {showReturn && day ? (
        <p className="font-mono tabular-nums">
          Daily Return {formatPct(day.net_pnl_inr! / day.start_of_day_equity_inr!)}
        </p>
      ) : null}
      <p>Status {statusCopy(state.kind)}</p>
      {day?.start_of_day_equity_inr != null ? (
        <p className="font-mono tabular-nums">Starting equity {formatInr(day.start_of_day_equity_inr)}</p>
      ) : null}
      {day?.closed_trades != null ? <p>Trades {day.closed_trades}</p> : null}
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
