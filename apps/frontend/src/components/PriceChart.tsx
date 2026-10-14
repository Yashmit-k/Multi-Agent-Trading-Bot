"use client";

import { useEffect, useRef } from "react";

type Bar = { start: string; end?: string; open: string; high: string; low: string; close: string; volume?: number };

// Daily candlesticks with volume, drawn with lightweight-charts.
export function PriceChart({ bars }: { bars: Bar[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || bars.length === 0) return;
    let disposed = false;
    let cleanup = () => {};
    import("lightweight-charts").then(({ createChart, ColorType }) => {
      if (disposed || !ref.current) return;
      const chart = createChart(ref.current, {
        height: 320,
        layout: { background: { type: ColorType.Solid, color: "#0F141B" }, textColor: "#94A3B8" },
        grid: { vertLines: { color: "#1E2733" }, horzLines: { color: "#1E2733" } },
        rightPriceScale: { borderColor: "#26303C" },
        timeScale: { borderColor: "#26303C" },
        autoSize: true,
      });
      const candles = chart.addCandlestickSeries({
        upColor: "#22C55E",
        downColor: "#EF4444",
        borderVisible: false,
        wickUpColor: "#22C55E",
        wickDownColor: "#EF4444",
      });
      const day = (iso: string) => iso.slice(0, 10);
      const seen = new Set<string>();
      const rows = bars.filter((bar) => {
        const key = day(bar.start);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      candles.setData(
        rows.map((bar) => ({ time: day(bar.start), open: Number(bar.open), high: Number(bar.high), low: Number(bar.low), close: Number(bar.close) })),
      );
      const volume = chart.addHistogramSeries({ priceScaleId: "", priceFormat: { type: "volume" }, color: "#334155" });
      volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      volume.setData(rows.map((bar) => ({ time: day(bar.start), value: Number(bar.volume ?? 0) })));
      chart.timeScale().fitContent();
      cleanup = () => chart.remove();
    });
    return () => {
      disposed = true;
      cleanup();
    };
  }, [bars]);
  if (bars.length === 0) return <p className="text-sm text-[#94A3B8]">No stored daily candles for this symbol.</p>;
  return <div ref={ref} data-testid="price-chart" className="h-[320px] w-full rounded-[12px] border border-[#26303C]" />;
}
