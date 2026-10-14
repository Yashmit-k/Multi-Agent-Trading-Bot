import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PaperMetrics } from "@/components/PaperMetrics";

describe("checkpoint 4 page contracts", () => {
  it("builds the news list from scored live headlines, not fixtures", () => {
    const source = readFileSync("src/app/news/page.tsx", "utf8");
    expect(source).toContain('agent: "news"');
    expect(source).toContain("headlines");
    expect(source).not.toContain("fixtures");
  });

  it("keeps performance on the backtest route", () => {
    const source = readFileSync("src/app/performance/page.tsx", "utf8");
    expect(source).toContain("Backtest results");
    expect(source).toContain("Latest stored backtest");
    expect(source).toContain("not paper-account");
    expect(source).toContain('"/api/v1/performance"');
    expect(source).not.toContain("/api/v1/paper/daily-performance");
  });

  it("keeps the interactive kill switch on the Risk page only", () => {
    const risk = readFileSync("src/app/risk/page.tsx", "utf8");
    const dashboard = readFileSync("src/components/dashboard/TradingDashboard.tsx", "utf8");
    expect(risk).toContain("KillSwitchControl");
    expect(dashboard).not.toContain("KillSwitchControl");
  });

  it("does not treat backtest performance as paper P&L", () => {
    const dashboard = readFileSync("src/app/dashboard/page.tsx", "utf8");
    const loader = readFileSync("src/lib/load-real-dashboard.ts", "utf8");
    const overview = readFileSync("src/components/dashboard/TradingDashboard.tsx", "utf8");
    expect(loader).toContain('"/api/v1/portfolio"');
    expect(dashboard).not.toContain('"/api/v1/performance"');
    expect(loader).not.toContain('"/api/v1/performance"');
    expect(overview).not.toContain('"/api/v1/performance"');
    expect(loader).toContain('"/api/v1/paper/daily-performance"');
    expect(dashboard).not.toContain('"/api/v1/paper/daily-performance"');
    expect(overview).not.toContain('"/api/v1/paper/daily-performance"');
    expect(dashboard).not.toContain("News on this page");
    render(
      <PaperMetrics
        portfolio={{ snapshot: null, total_pnl: null, equity: "1000000", gross_exposure: null }}
      />,
    );
    expect(screen.getByTestId("missing-pnl").textContent).toContain("unavailable");
    expect(screen.getByTestId("equity-graph-empty").textContent).toContain("No equity graph");
    expect(screen.queryByText(/P&L 0/)).toBeNull();
  });
});
