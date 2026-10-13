import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NewsPage from "@/app/news/page";

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
    expect(source).toContain('"/api/v1/performance"');
    expect(source).not.toContain("/api/v1/paper/daily-performance");
  });
});
