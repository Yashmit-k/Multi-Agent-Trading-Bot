import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NewsPage from "@/app/news/page";
import { PaperMetrics } from "@/components/PaperMetrics";

describe("checkpoint 4 page contracts", () => {
  it("keeps the global news list unavailable", () => {
    render(<NewsPage />);
    expect(screen.getByTestId("not-available").textContent).toContain("Global news list");
    const source = readFileSync("src/app/news/page.tsx", "utf8");
    expect(source).toContain("/api/v1/stocks/");
    expect(source).not.toContain("NEWS_RSS");
  });

  it("keeps performance on the backtest route", () => {
    const source = readFileSync("src/app/performance/page.tsx", "utf8");
    expect(source).toContain("Backtest results");
    expect(source).toContain("not paper-account");
    expect(source).toContain('"/api/v1/performance"');
    expect(source).not.toContain("/api/v1/paper/daily-performance");
  });

  it("does not treat backtest performance as paper P&L", () => {
    const dashboard = readFileSync("src/app/dashboard/page.tsx", "utf8");
    expect(dashboard).toContain('"/api/v1/portfolio"');
    expect(dashboard).not.toContain("/api/v1/performance");
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
