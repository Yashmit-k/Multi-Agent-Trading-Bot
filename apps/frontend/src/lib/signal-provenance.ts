// Where an agent signal's opinion came from, read from its stored metadata.
type Llm = { model?: string; fallback?: boolean };
type Headline = { title?: string; source?: string };

import { AGENT_KIND, decodeEntities } from "@/lib/format";

export type Provenance = {
  reasons: string[];
  llm: string | null;
  headlines: Headline[];
  insufficient: boolean;
};

export function provenance(payload: Record<string, unknown>): Provenance {
  const metadata = (payload.metadata as Record<string, unknown> | undefined) ?? {};
  const raw = metadata.llm;
  const llmItems = Array.isArray(raw) ? (raw as Llm[]) : raw && typeof raw === "object" ? [raw as Llm] : [];
  const first = llmItems[0];
  let llm: string | null = null;
  if (first) {
    if (first.fallback && first.model === "none") llm = "no LLM answer (quota used up): no opinion";
    else if (first.fallback || first.model === "fixture") llm = "fixture heuristic (no live LLM)";
    else llm = `LLM ${first.model}`;
  }
  return {
    reasons: Array.isArray(payload.reason_codes) ? (payload.reason_codes as string[]) : [],
    llm,
    headlines: Array.isArray(metadata.headlines)
      ? (metadata.headlines as Headline[]).map((item) => ({ ...item, title: item.title ? decodeEntities(item.title) : item.title }))
      : [],
    insufficient: metadata.insufficient_data === true,
  };
}

export function excludedAgents(raw: string | undefined): string[] {
  return (raw ?? "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

// One plain-language line on where a signal's opinion came from.
export function sourceLabel(agent: string, payload: Record<string, unknown>): string {
  const p = provenance(payload);
  if (p.llm) return p.llm;
  if (AGENT_KIND[agent] === "llm") {
    if (p.insufficient) return "no LLM call: no input data for this symbol";
    if (agent !== "news") return "sample data, no live feed: not used in trades";
    return "LLM score (model not recorded on this signal)";
  }
  return "deterministic rules on live candles";
}
