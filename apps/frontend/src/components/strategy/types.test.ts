import { describe, expect, it } from "vitest";
import { higherTimeframes, ruleText, withDefaults, type OperandInfo } from "@/components/strategy/types";
import { allowOperatorWrite, allowPublicWrite } from "@/lib/proxy-policy";

const catalog: OperandInfo[] = [
  { indicator: "ema", label: "EMA", group: "Trend", needs_period: true, default_period: 20, uses_period2: false, uses_param: false },
  { indicator: "close", label: "Close", group: "Price", needs_period: false, default_period: null, uses_period2: false, uses_param: false },
  { indicator: "rsi", label: "RSI", group: "Momentum", needs_period: true, default_period: 14, uses_period2: false, uses_param: false },
];

describe("strategy definitions", () => {
  it("upgrades strategies saved before groups existed", () => {
    const legacy = withDefaults({
      name: "old",
      entry: [{ left: { indicator: "ema", period: 20 }, op: "crosses_above", right: { indicator: "ema", period: 50 } }],
      exit: [],
      stop_loss_pct: 5,
      take_profit_pct: 15,
      position_notional: 25000,
    });
    expect(legacy.entry.logic).toBe("all");
    expect(legacy.exit).toBeNull();
    expect(legacy.stop).toMatchObject({ kind: "percent", value: 5 });
    expect(legacy.targets[0]).toMatchObject({ kind: "percent", value: 15, fraction: 1 });
    expect(legacy.sizing.value).toBe(25000);
  });

  it("describes nested rules the way the confirmation shows them", () => {
    const text = ruleText(
      {
        logic: "all",
        items: [
          { left: { indicator: "close", timeframe: "1d" }, op: ">", right: { indicator: "ema", period: 50, timeframe: "1d" } },
          { logic: "any", items: [{ left: { indicator: "rsi", period: 14 }, op: "<", right: { value: 30 } }, { left: { indicator: "rsi", period: 14, offset: 1 }, op: "crosses_above", right: { value: 30 }, for_bars: 1 }] },
        ],
      },
      catalog,
    );
    expect(text).toBe("1d Close is above 1d EMA(50) AND (RSI(14) is below 30 OR RSI(14) 1 bars ago crosses above 30)");
  });

  it("only offers timeframes above the strategy's", () => {
    expect(higherTimeframes("15m")).toEqual(["1h", "1d"]);
    expect(higherTimeframes("1d")).toEqual([]);
  });
});

describe("apply routes are operator-only", () => {
  it("allows apply and stop for the operator, never for visitors", () => {
    expect(allowOperatorWrite("/api/v1/strategies/strat-abc123/apply")).toBe(true);
    expect(allowOperatorWrite("/api/v1/strategies/active/stop")).toBe(true);
    expect(allowPublicWrite("/api/v1/strategies/strat-abc123/apply")).toBe(false);
    expect(allowPublicWrite("/api/v1/strategies/active/stop")).toBe(false);
  });
});
