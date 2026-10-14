// Where an agent signal's opinion came from, read from its stored metadata.
type Llm = { model?: string; fallback?: boolean };
type Headline = { title?: string; source?: string };

export type Provenance = {
  reasons: string[];
  llm: string | null;
  headlines: Headline[];
  insufficient: boolean;
};

export function provenance(payload: Record<string, unknown>): Provenance {
  const metadata = (payload.metadata as Record<string, unknown> | undefined) ?? {};
  const llmItems = Array.isArray(metadata.llm) ? (metadata.llm as Llm[]) : [];
  const first = llmItems[0];
  let llm: string | null = null;
  if (first) {
    if (first.fallback || first.model === "fixture") llm = "fixture heuristic (no live LLM)";
    else llm = `LLM ${first.model}`;
  }
  return {
    reasons: Array.isArray(payload.reason_codes) ? (payload.reason_codes as string[]) : [],
    llm,
    headlines: Array.isArray(metadata.headlines) ? (metadata.headlines as Headline[]) : [],
    insufficient: metadata.insufficient_data === true,
  };
}

export function excludedAgents(raw: string | undefined): string[] {
  return (raw ?? "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}
