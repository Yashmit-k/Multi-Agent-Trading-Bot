import { describe, expect, it } from "vitest";
import { parseMode } from "@/lib/mode";

describe("parseMode", () => {
  it("does not default to PAPER", () => {
    expect(parseMode(undefined)).toBe("UNKNOWN");
    expect(parseMode("nope")).toBe("UNKNOWN");
    expect(parseMode("PAPER")).toBe("PAPER");
  });
});
