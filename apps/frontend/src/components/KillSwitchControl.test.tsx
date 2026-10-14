import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KillSwitchControl } from "@/components/KillSwitchControl";

describe("KillSwitchControl", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("does not POST when confirm is cancelled", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<KillSwitchControl killSwitch="disarmed" live={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Arm" }));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("POSTs armed true after confirm", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ kill_switch: "armed" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<KillSwitchControl killSwitch="disarmed" live={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Arm" }));
    await waitFor(() => {
      expect(screen.getByTestId("kill-switch-value").textContent).toBe("armed");
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/risk/kill-switch"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ armed: true }),
      }),
    );
  });
});