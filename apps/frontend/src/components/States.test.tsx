import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ModeBanner } from "@/components/ModeBanner";
import { HorizonSplit } from "@/components/HorizonSplit";
import { NotAvailableState, EmptyState, ErrorState, LoadingState } from "@/components/States";

describe("ModeBanner", () => {
  it("shows UNKNOWN", () => {
    render(<ModeBanner mode="UNKNOWN" />);
    expect(screen.getByTestId("mode-banner").textContent).toContain("UNKNOWN");
  });
  it("warns on LIVE", () => {
    render(<ModeBanner mode="LIVE" />);
    expect(screen.getByTestId("mode-banner").textContent).toContain("LIVE TRADING");
  });
});

describe("HorizonSplit", () => {
  it("warns without mutating horizon", () => {
    render(
      <HorizonSplit
        signals={[{ agent_name: "fundamental", horizon: "INTRADAY", signal: 0.1, confidence: 0.2 }]}
      />,
    );
    expect(screen.getByTestId("horizon-warning")).toBeTruthy();
  });
});

describe("states", () => {
  it("renders loading error empty and not-available", () => {
    render(<LoadingState />);
    render(<ErrorState message="x" />);
    render(<EmptyState label="rows" />);
    render(<NotAvailableState feature="agents" />);
    expect(screen.getByTestId("not-available").textContent).toContain("agents");
  });
});
