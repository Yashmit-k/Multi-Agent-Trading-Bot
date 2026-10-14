const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const inrFine = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});

export function formatInr(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value !== 0 && Math.abs(value) < 0.01) return inrFine.format(value);
  return inr.format(value);
}

export function formatSignedInr(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const formatted = formatInr(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `−${formatted}`;
  return formatted;
}

export function formatPct(fraction: number | null): string {
  if (fraction === null || !Number.isFinite(fraction)) return "—";
  const pct = fraction * 100;
  const digits = Math.abs(pct) < 0.01 && pct !== 0 ? 4 : 2;
  const body = pct.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  if (pct > 0) return `+${body}%`;
  if (pct < 0) return `${body}%`;
  return `${body}%`;
}

export function parseDecimal(raw: string | number | null | undefined): number | null {
  if (raw === null || raw === undefined || raw === "") return null;
  const n = typeof raw === "number" ? raw : Number(raw);
  return Number.isFinite(n) ? n : null;
}
