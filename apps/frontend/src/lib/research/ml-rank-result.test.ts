import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("research result copy", () => {
  it("matches the committed study output exactly", () => {
    const source = readFileSync("../../services/quant/docs/results/ml-rank-result.json", "utf8");
    const copy = readFileSync("src/lib/research/ml-rank-result.json", "utf8");
    expect(JSON.parse(copy)).toEqual(JSON.parse(source));
  });
});
