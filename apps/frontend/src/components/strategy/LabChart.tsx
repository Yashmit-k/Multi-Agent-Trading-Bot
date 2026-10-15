"use client";

import { useEffect, useRef } from "react";

type Point = { date: string; equity: number };

// Strategy equity (green/red) against NIFTY 50 buy-and-hold scaled to the same starting cash (grey).
export function LabChart({ strategy, benchmark }: { strategy: Point[]; benchmark: Point[] | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || strategy.length === 0) return;
    let disposed = false;
    let cleanup = () => {};
    import("lightweight-charts").then(({ createChart, ColorType }) => {
      if (disposed || !ref.current) return;
      const chart = createChart(ref.current, {
        height: 280,
        layout: { background: { type: ColorType.Solid, color: "#0F141B" }, textColor: "#94A3B8" },
        grid: { vertLines: { color: "#1E2733" }, horzLines: { color: "#1E2733" } },
        rightPriceScale: { borderColor: "#26303C" },
        timeScale: { borderColor: "#26303C" },
        autoSize: true,
      });
      const toData = (points: Point[]) => {
        const seen = new Set<string>();
        return points.filter((point) => (seen.has(point.date) ? false : (seen.add(point.date), true))).map((point) => ({ time: point.date, value: point.equity }));
      };
      if (benchmark?.length) {
        chart.addLineSeries({ color: "#64748B", lineWidth: 1, title: "NIFTY 50" }).setData(toData(benchmark) as never);
      }
      const up = strategy[strategy.length - 1].equity >= strategy[0].equity;
      chart.addLineSeries({ color: up ? "#22C55E" : "#EF4444", lineWidth: 2, title: "Strategy" }).setData(toData(strategy) as never);
      chart.timeScale().fitContent();
      cleanup = () => chart.remove();
    });
    return () => {
      disposed = true;
      cleanup();
    };
  }, [strategy, benchmark]);
  if (strategy.length === 0) return <p className="text-sm text-[#94A3B8]">No equity points.</p>;
  return <div ref={ref} data-testid="lab-chart" className="h-[280px] w-full rounded-[12px] border border-[#26303C]" />;
}
