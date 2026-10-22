import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AgreeAgentsField } from "@/components/operator/AgreeAgentsField";
import { RiskSettingsForm, type RiskSettingsView } from "@/components/operator/RiskSettingsForm";

vi.mock("@/components/operator/OperatorGate", () => ({
  OperatorGate: ({ children }: { children: (operator: boolean) => React.ReactNode }) => <div>{children(true)}</div>,
}));

const CHOICES = [
  { value: "momentum", label: "Momentum" },
  { value: "news", label: "News" },
  { value: "earnings", label: "Earnings" },
];

function view(mode: string): RiskSettingsView {
  return {
    settings: { strategy_mode: mode, agree_agents: "news,earnings" },
    bounds: [
      { key: "strategy_mode", label: "Applied strategy and the agents", min: null, max: null, default: "replace", choices: [{ value: "replace", label: "Replace" }, { value: "agents_agree", label: "Agents agree" }] },
      { key: "agree_agents", label: "Agents a strategy must agree with", min: null, max: null, default: "news,earnings", multiple: true, choices: CHOICES },
    ],
    updated_at: null,
    updated_by: null,
  };
}

describe("agree_agents setting", () => {
  it("ticks the chosen agents and reports the new list in a stable order", () => {
    const onChange = vi.fn();
    render(<AgreeAgentsField label="Agents" value="news,earnings" choices={CHOICES} disabled={false} onChange={onChange} />);
    expect(screen.getByText("A strategy entry is blocked only when these agents are bearish.")).toBeTruthy();
    expect((screen.getByRole("checkbox", { name: "News" }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("checkbox", { name: "Momentum" }) as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("checkbox", { name: "Momentum" }));
    expect(onChange).toHaveBeenLastCalledWith("momentum,news,earnings");
    fireEvent.click(screen.getByRole("checkbox", { name: "News" }));
    expect(onChange).toHaveBeenLastCalledWith("earnings");
  });

  it("appears on the Settings form only in agents_agree mode", () => {
    const { unmount } = render(<RiskSettingsForm initial={view("replace")} />);
    expect(screen.queryByTestId("agree-agents")).toBeNull();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "agents_agree" } });
    expect(screen.getByTestId("agree-agents")).toBeTruthy();
    unmount();
    render(<RiskSettingsForm initial={view("agents_agree")} />);
    expect((screen.getByRole("checkbox", { name: "Earnings" }) as HTMLInputElement).checked).toBe(true);
  });
});
