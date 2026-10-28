import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const fetchApi = vi.fn();
vi.mock("@/lib/api", () => ({ fetchApi: (path: string) => fetchApi(path) }));

import MomentumTrialPage from "@/app/momentum/page";

describe("momentum trial page", () => {
  it("shows the pending picks while waiting for the first open", async () => {
    fetchApi.mockResolvedValueOnce({ status: "waiting for the first open", as_of_session: "2026-10-30", next_decision: "2026-11-30", pending_ranking: [{ rank: 1, symbol: "CUPID" }] });
    render(await MomentumTrialPage());
    expect(screen.getByTestId("trial-status").textContent).toContain("Waiting");
    expect(screen.getByText("CUPID")).toBeTruthy();
    expect(screen.getByText("PAPER ONLY")).toBeTruthy();
  });

  it("shows returns, holdings and months once running", async () => {
    fetchApi.mockResolvedValueOnce({
      status: "running", method: "equal_split_compounding", capital: 100000, hold: 10, equity: 101800, cash: 900, as_of_session: "2026-11-30", return: 0.018, benchmark_return: 0.006, niftybees_return: 0.009,
      holdings: [{ symbol: "ATHERENERG", value: 20410, cost: 20000, return: 0.0205 }],
      months: [{ month_end: "2026-11-30", strategy: 0.018, benchmark: 0.006, niftybees: 0.009 }],
      backtest: { period: "2016-02 to 2026-10", cagr: 0.267, benchmark_cagr: 0.14, max_drawdown: 0.39 },
    });
    render(await MomentumTrialPage());
    expect(screen.getByTestId("trial-status").textContent).toContain("Running");
    expect(screen.getAllByText("+1.8%").length).toBeGreaterThan(0);
    expect(screen.getByText("ATHERENERG")).toBeTruthy();
    expect(screen.getByTestId("trial-value").textContent).toContain("1,01,800");
    expect(screen.getByText(/invested once; every month the whole amount is split equally across the 10/)).toBeTruthy();
    expect(screen.getByText(/worst fall −39.0%/)).toBeTruthy();
  });

  it("shows the delivery book as a second section when present", async () => {
    fetchApi.mockResolvedValueOnce({
      status: "waiting for the first open", hold: 10, pending_ranking: [{ rank: 1, symbol: "CUPID" }],
      delivery_book: { status: "waiting for the first open", hold: 10, pending_ranking: [{ rank: 1, symbol: "LAURUSLABS" }] },
    });
    render(await MomentumTrialPage());
    expect(screen.getByText("Second book: momentum + delivery filter")).toBeTruthy();
    expect(screen.getByTestId("delivery-status").textContent).toContain("Waiting");
    expect(screen.getByText("LAURUSLABS")).toBeTruthy();
  });
});
