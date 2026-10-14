// Small shared building blocks for the read-only pages.
import Link from "next/link";

export function Card({ title, children, right }: { title?: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="rounded-[12px] border border-[#26303C] bg-[#0F141B] p-4">
      {title ? (
        <div className="mb-3 flex items-baseline justify-between gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-[#94A3B8]">{title}</h2>
          {right}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: "up" | "down" | "muted" }) {
  const color = tone === "up" ? "text-[#22C55E]" : tone === "down" ? "text-[#EF4444]" : tone === "muted" ? "text-[#94A3B8]" : "text-[#E6EDF3]";
  return (
    <div className="rounded-[12px] border border-[#26303C] bg-[#0F141B] p-4">
      <div className="text-xs uppercase tracking-wide text-[#94A3B8]">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      {hint ? <div className="mt-1 text-xs text-[#64748B]">{hint}</div> : null}
    </div>
  );
}

export function Table({ head, children, minWidth = 640 }: { head: string[]; children: React.ReactNode; minWidth?: number }) {
  return (
    <div className="overflow-x-auto rounded-[12px] border border-[#26303C]">
      <table className="w-full text-left text-sm" style={{ minWidth }}>
        <thead className="bg-[#121922] text-xs uppercase tracking-wide text-[#94A3B8]">
          <tr>
            {head.map((label) => (
              <th key={label} className="px-3 py-2 font-medium">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[#1E2733]">{children}</tbody>
      </table>
    </div>
  );
}

export function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-3 py-2 align-top ${className}`}>{children}</td>;
}

export function Score({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined || !Number.isFinite(value)) return <span className="text-[#64748B]">—</span>;
  const color = value > 0.05 ? "text-[#22C55E]" : value < -0.05 ? "text-[#EF4444]" : "text-[#94A3B8]";
  return <span className={`tabular-nums ${color}`}>{value > 0 ? "+" : ""}{value.toFixed(2)}</span>;
}

export function Badge({ children, tone = "muted" }: { children: React.ReactNode; tone?: "muted" | "up" | "down" | "warn" | "info" }) {
  const styles = {
    muted: "border-[#334155] text-[#94A3B8]",
    up: "border-[#166534] text-[#22C55E]",
    down: "border-[#7F1D1D] text-[#EF4444]",
    warn: "border-[#78350F] text-[#F59E0B]",
    info: "border-[#1E3A8A] text-[#60A5FA]",
  }[tone];
  return <span className={`inline-block rounded border px-1.5 py-0.5 text-[11px] leading-none ${styles}`}>{children}</span>;
}

export function SymbolLink({ symbol }: { symbol: string }) {
  return (
    <Link prefetch={false} href={`/stocks/${encodeURIComponent(symbol)}`} className="font-medium text-[#E6EDF3] hover:text-[#60A5FA]">
      {symbol}
    </Link>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p data-testid="empty" className="rounded-[12px] border border-dashed border-[#26303C] p-4 text-sm text-[#94A3B8]">
      {children}
    </p>
  );
}
