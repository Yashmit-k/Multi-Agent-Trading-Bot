import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StrategyGuidePage from "@/app/strategies/guide/page";

describe("Strategy Lab guide", () => {
  it("renders the guide sections as static text", () => {
    render(<StrategyGuidePage />);
    expect(screen.getByRole("heading", { level: 1, name: "How the Strategy Lab works" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /time stop/i })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /how entry orders fill/i })).toBeTruthy();
    expect(document.body.textContent).toContain("signal bar's close plus 0.25%");
    expect(document.body.textContent).toContain("agents_agree");
    expect(screen.getByRole("link", { name: /back to the strategy lab/i }).getAttribute("href")).toBe("/strategies");
  });
});
