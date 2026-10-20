import { existsSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { FINDINGS } from "./findings";

describe("research findings", () => {
  it("links only to committed study docs", () => {
    for (const f of FINDINGS) {
      for (const doc of [f.protocol, f.result]) {
        if (doc) expect(existsSync(`../../services/quant/docs/${doc}`), doc).toBe(true);
      }
    }
  });

  it("has unique slugs and is newest first", () => {
    expect(new Set(FINDINGS.map((f) => f.slug)).size).toBe(FINDINGS.length);
    const dates = FINDINGS.map((f) => f.date);
    expect([...dates].sort().reverse()).toEqual(dates);
  });
});
