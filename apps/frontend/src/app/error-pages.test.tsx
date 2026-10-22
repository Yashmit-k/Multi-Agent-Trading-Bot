import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ErrorPage from "@/app/error";
import NotFound from "@/app/not-found";

describe("fallback pages", () => {
  it("links the 404 page back to the dashboard", () => {
    render(<NotFound />);
    expect(screen.getByRole("link", { name: /back to the dashboard/i }).getAttribute("href")).toBe("/dashboard");
  });

  it("calls reset from Try again, hides the raw error and links to /system", () => {
    const reset = vi.fn();
    render(<ErrorPage error={new Error("secret database detail")} reset={reset} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/secret database detail/)).toBeNull();
    expect(screen.getByRole("link", { name: /system status/i }).getAttribute("href")).toBe("/system");
  });
});
