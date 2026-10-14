"use client";

import { useEffect, useRef } from "react";

// Equity curve of a stored backtest. Points are (ISO time, equity in rupees).
export function EquityLine({ points }: { points: Array<{ timestamp: string; equity: string }> }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || points.length === 0) return;
    let disposed = false;
    let cleanup = () => {};
    import("lightweight-charts").then(({ createChart, ColorType }) => {
      if (disposed || !ref.current) return;
      const chart = createChart(ref.current, {
        height: 260,
        layout: { background: { type: ColorType.Solid, color: "#0F141B" }, textColor: "#94A3B8" },
        grid: { vertLines: { color: "#1E2733" }, horzLines: { color: "#1E2733" } },
        rightPriceScale: { borderColor: "#26303C" },
        timeScale: { borderColor: "#26303C", timeVisible: true },
        autoSize: true,
      });
      const first = Number(points[0].equity);
      const last = Number(points[points.length - 1].equity);
      const series = chart.addAreaSeries({
        lineColor: last >= first ? "#22C55E" : "#EF4444",
        topColor: last >= first ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)",
        bottomColor: "rgba(0,0,0,0)",
        lineWidth: 2,
      });
      const seen = new Set<number>();
      const data = points
        .map((point) => ({ time: Math.floor(new Date(point.timestamp).getTime() / 1000), value: Number(point.equity) }))
        .filter((point) => (seen.has(point.time) ? false : (seen.add(point.time), true)))
        .sort((a, b) => a.time - b.time);
      // lightweight-charts wants UTCTimestamp; the cast keeps the bundle free of its type import.
      series.setData(data as never);
      chart.timeScale().fitContent();
      cleanup = () => chart.remove();
    });
    return () => {
      disposed = true;
      cleanup();
    };
  }, [points]);
  if (points.length === 0) return <p className="text-sm text-[#94A3B8]">No equity points stored for this run.</p>;
  return <div ref={ref} data-testid="equity-line" className="h-[260px] w-full rounded-[12px] border border-[#26303C]" />;
}
