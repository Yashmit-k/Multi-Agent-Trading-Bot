import { formatInr, parseDecimal } from "@/lib/money";

const IST = "Asia/Kolkata";

export function inr(raw: string | number | null | undefined): string {
  const value = parseDecimal(raw);
  return value === null ? "—" : formatInr(value);
}

export function price(raw: string | number | null | undefined): string {
  const value = parseDecimal(raw);
  return value === null ? "—" : value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function pct(raw: string | number | null | undefined): string {
  const value = parseDecimal(raw);
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function num(raw: number | null | undefined, digits = 2): string {
  return raw === null || raw === undefined || !Number.isFinite(raw) ? "—" : raw.toFixed(digits);
}

export function istTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: IST,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

export function shortId(id: string | null | undefined): string {
  return id ? `${id.slice(0, 8)}…` : "—";
}

export const AGENT_KIND: Record<string, "quant" | "llm" | "ml"> = {
  technical: "quant",
  momentum: "quant",
  mean_reversion: "quant",
  volume: "quant",
  regime: "quant",
  global_markets: "quant",
  ml: "ml",
  news: "llm",
  fundamental: "llm",
  valuation: "llm",
  earnings: "llm",
};

export function decodeEntities(text: string): string {
  return text.replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
}
