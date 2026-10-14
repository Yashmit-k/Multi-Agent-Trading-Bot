import { describe, expect, it } from "vitest";
import { formatIstInstant, istDateKeyFromInstant } from "@/lib/ist";
import { assertGithubGeometry, buildSundayFirstLayout } from "@/lib/calendar-layout";
import { heatmapLevel, PNL_HEATMAP_THRESHOLDS, signedPnlLevel } from "@/lib/pnl-heatmap";

describe("IST instants", () => {
  it("maps 2026-10-12T18:45:00Z to 13 October 2026", () => {
    expect(istDateKeyFromInstant("2026-10-12T18:45:00Z")).toBe("2026-10-13");
    expect(formatIstInstant("2026-10-12T18:45:00Z")).toBe("00:15 IST on 13 October 2026");
  });
});

describe("GitHub Sunday-first geometry", () => {
  it("has 365 keys and 53 columns", () => {
    const layout = buildSundayFirstLayout("2026-10-10", 365);
    expect(layout.keys).toHaveLength(365);
    expect(layout.weekStarts).toHaveLength(53);
    expect(() => assertGithubGeometry(layout)).not.toThrow();
    const jan = layout.monthLabels.find((item) => item.label === "Jan");
    expect(jan).toBeTruthy();
    const firstJanKey = layout.columns[jan!.weekIndex].find((key) => key?.startsWith("2026-01") || key?.startsWith("2025-01"));
    expect(firstJanKey).toBeTruthy();
  });

  it("places Sunday at row 0", () => {
    const layout = buildSundayFirstLayout("2026-10-10", 365);
    const sunday = layout.keys.find((key) => new Date(`${key}T00:00:00Z`).getUTCDay() === 0);
    expect(sunday).toBeTruthy();
    const week = layout.columns.find((column) => column.includes(sunday!));
    expect(week?.[0]).toBe(sunday);
  });
});

describe("heatmap thresholds", () => {
  it("uses documented fractions", () => {
    expect([...PNL_HEATMAP_THRESHOLDS]).toEqual([0.001, 0.0025, 0.005, 0.01]);
    expect(heatmapLevel(0.0002)).toBe(1);
    expect(heatmapLevel(0.001)).toBe(2);
    expect(heatmapLevel(0.0025)).toBe(3);
    expect(signedPnlLevel(200, 1_000_000)).toEqual({ kind: "profit", level: 1 });
    expect(signedPnlLevel(-200, 1_000_000)).toEqual({ kind: "loss", level: 1 });
    expect(signedPnlLevel(100, null)).toEqual({ kind: "missing" });
    expect(signedPnlLevel(0, 1_000_000)).toEqual({ kind: "zero" });
  });
});
