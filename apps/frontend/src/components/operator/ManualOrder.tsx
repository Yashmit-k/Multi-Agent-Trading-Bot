"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { errorText, postApi } from "@/lib/api";
import { OperatorGate, useOperator } from "@/components/operator/OperatorGate";

type Result = { risk: { status: string; rejection_reason: string | null }; order: { status: string; quantity: number; limit_price: string | null; metadata?: Record<string, unknown> } | null };

export function ManualOrderForm({ symbols, held }: { symbols: string[]; held: Record<string, number> }) {
  const router = useRouter();
  const [symbol, setSymbol] = useState(symbols[0] ?? "");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [quantity, setQuantity] = useState("");
  const [limit, setLimit] = useState("");
  const [override, setOverride] = useState(false);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, setPending] = useState(false);

  async function submit() {
    const summary = `${side} ${quantity || (side === "SELL" ? "all" : "max")} ${symbol}${limit ? ` limit ₹${limit}` : ""}${override ? " (overriding portfolio limits)" : ""}`;
    if (!window.confirm(`Place this PAPER order?\n\n${summary}\n\nNo order is sent to a broker.`)) return;
    setPending(true);
    setMessage(null);
    try {
      const result = await postApi<Result>("/api/v1/paper/orders/manual", {
        symbol,
        side,
        quantity: quantity ? Number(quantity) : null,
        limit_price: side === "BUY" && limit ? limit : null,
        override_limits: override,
        note,
        operator: "web-operator",
      });
      if (result.risk.status !== "APPROVED") {
        setMessage({ ok: false, text: `Risk rejected: ${result.risk.rejection_reason}` });
      } else if (!result.order || result.order.status === "REJECTED") {
        setMessage({ ok: false, text: `Order rejected: ${String(result.order?.metadata?.reason ?? "daily cap reached")}` });
      } else {
        setMessage({ ok: true, text: `Queued ${result.order.quantity} × ${symbol}${result.order.limit_price ? ` at ₹${result.order.limit_price}` : " at next open"}. It fills on the next 5-minute bars while paper trading runs.` });
        router.refresh();
      }
    } catch (error) {
      setMessage({ ok: false, text: errorText(error) });
    } finally {
      setPending(false);
    }
  }

  const input = "rounded border border-[#26303C] bg-[#0B0F14] px-2 py-1 text-sm disabled:opacity-60";
  return (
    <OperatorGate what="place or cancel paper orders">
      {(operator) => (
        <form
          className="flex flex-wrap items-end gap-3 text-sm"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Stock</span>
            <select className={input} value={symbol} disabled={!operator} onChange={(event) => setSymbol(event.target.value)}>
              {symbols.map((item) => (
                <option key={item} value={item}>
                  {item}
                  {held[item] ? ` (held ${held[item]})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Side</span>
            <select className={input} value={side} disabled={!operator} onChange={(event) => setSide(event.target.value as "BUY" | "SELL")}>
              <option value="BUY">BUY</option>
              <option value="SELL">SELL (held only)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Quantity {side === "BUY" ? "(blank = up to your per-order limit)" : "(blank = all)"}</span>
            <input className={`${input} w-32`} type="number" min={1} value={quantity} disabled={!operator} onChange={(event) => setQuantity(event.target.value)} />
          </label>
          {side === "BUY" ? (
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[#94A3B8]">Limit ₹ (blank = last price +0.25%)</span>
              <input className={`${input} w-32`} type="number" step="0.05" min={0} value={limit} disabled={!operator} onChange={(event) => setLimit(event.target.value)} />
            </label>
          ) : null}
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Note</span>
            <input className={`${input} w-48`} value={note} maxLength={200} disabled={!operator} onChange={(event) => setNote(event.target.value)} />
          </label>
          <label className="flex items-center gap-2 pb-1 text-xs text-[#94A3B8]">
            <input type="checkbox" checked={override} disabled={!operator} onChange={(event) => setOverride(event.target.checked)} />
            Override portfolio limits
          </label>
          <button type="submit" disabled={!operator || pending || !symbol} className="rounded bg-[#2563EB] px-3 py-1.5 font-medium text-white disabled:opacity-50">
            Place paper order
          </button>
          {message ? <p className={`w-full text-sm ${message.ok ? "text-[#22C55E]" : "text-[#EF4444]"}`}>{message.text}</p> : null}
          <p className="w-full text-xs text-[#64748B]">
            Override skips position, sector, exposure, per-stock and daily-entry limits only. Cash, the per-order cap, PAPER mode and no-shorting always apply.
          </p>
        </form>
      )}
    </OperatorGate>
  );
}

export function RowAction({ path, label, confirmText, body = {} }: { path: string; label: string; confirmText: string; body?: Record<string, unknown> }) {
  const router = useRouter();
  const { status } = useOperator();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  if (!status?.operator) return null;
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        disabled={pending}
        className="rounded border border-[#26303C] px-2 py-0.5 text-xs text-[#E6EDF3] hover:border-[#EF4444] disabled:opacity-50"
        onClick={() => {
          if (!window.confirm(confirmText)) return;
          setPending(true);
          setError(null);
          postApi(path, { operator: "web-operator", ...body })
            .then(() => router.refresh())
            .catch((err) => setError(errorText(err)))
            .finally(() => setPending(false));
        }}
      >
        {label}
      </button>
      {error ? <span className="text-xs text-[#EF4444]">{error}</span> : null}
    </span>
  );
}
