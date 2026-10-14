import { describe, expect, it } from "vitest";
import { excludedAgents, provenance } from "@/lib/signal-provenance";

describe("signal provenance", () => {
  it("labels a real LLM", () => {
    const p = provenance({ reason_codes: ["news.earnings"], metadata: { llm: [{ model: "llama-3.1-8b", fallback: false }], headlines: [{ title: "Infosys beats" }] } });
    expect(p.llm).toBe("LLM llama-3.1-8b");
    expect(p.headlines[0].title).toBe("Infosys beats");
    expect(p.reasons).toEqual(["news.earnings"]);
  });

  it("labels the fixture fallback honestly", () => {
    expect(provenance({ metadata: { llm: [{ model: "llama", fallback: true }] } }).llm).toContain("fixture");
    expect(provenance({ metadata: { llm: [{ model: "fixture" }] } }).llm).toContain("fixture");
  });

  it("accepts a single llm object", () => {
    expect(provenance({ metadata: { llm: { model: "fixture" } } }).llm).toContain("fixture");
  });

  it("deterministic agents have no LLM", () => {
    expect(provenance({ reason_codes: ["momentum.up"], metadata: {} }).llm).toBeNull();
  });

  it("parses the excluded list", () => {
    expect(excludedAgents(" Fundamental,valuation ,")).toEqual(["fundamental", "valuation"]);
    expect(excludedAgents(undefined)).toEqual([]);
  });
});
