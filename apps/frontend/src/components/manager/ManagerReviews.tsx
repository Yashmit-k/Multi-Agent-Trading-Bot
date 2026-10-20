"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { errorText, fetchApi, postApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { OperatorGate } from "@/components/operator/OperatorGate";
import { Badge, Card } from "@/components/ui";

export type Verdict = {
  verdict: "APPROVE" | "REDUCE" | "VETO" | "UNAVAILABLE";
  size_fraction: number;
  conflicts: string[];
  critique: string;
  reviewer: string;
  steps: number;
  metadata?: Record<string, unknown>;
};

export type ReviewRow = {
  review_id: string;
  proposal_id: string | null;
  symbol: string;
  kind: "pipeline" | "ad_hoc";
  status: "pending" | "running" | "done";
  created_at: string;
  updated_at: string;
  request: { side: string; quantity: number; entry_price: string; horizon: string; aggregated_signal: number; aggregated_confidence: number; requested_by: string };
  verdict: Verdict | null;
  step_count?: number;
};

export type Step = {
  event: "review.step" | "agent.request";
  step?: number;
  kind?: string;
  actor?: string;
  tool?: string | null;
  purpose?: string | null;
  summary?: string;
  arguments?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  to_agent?: string;
  question?: string;
  timestamp: string;
};

type Detail = ReviewRow & { steps: Step[]; correlation_id: string; chain: { risk: { status: string; rejection_reason: string | null } | null; order: { status: string; quantity: number } | null } | null };

const TONE: Record<string, "up" | "down" | "warn" | "muted" | "info"> = { APPROVE: "up", REDUCE: "warn", VETO: "down", UNAVAILABLE: "muted" };

export function verdictLabel(verdict: Verdict | null, status: string): string {
  if (!verdict) return status === "running" ? "Reviewing…" : "Waiting";
  if (verdict.verdict === "REDUCE") return `Reduce to ${Math.round(verdict.size_fraction * 100)}%`;
  return verdict.verdict.charAt(0) + verdict.verdict.slice(1).toLowerCase();
}

const STEP_LABEL: Record<string, string> = {
  plan: "Plan",
  tool_call: "Tool call",
  tool_result: "Result",
  agent_reply: "Agent replied",
  critique: "Sent back for revision",
  replan: "Replan",
  llm_error: "LLM error",
};

export function stepLabel(step: Step): string {
  if (step.event === "agent.request") return `Asks ${step.to_agent} agent`;
  return STEP_LABEL[step.kind ?? ""] ?? step.kind ?? "step";
}

function when(value: string): string {
  return new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour12: false });
}

function StepItem({ step }: { step: Step }) {
  const label = stepLabel(step);
  const tone = step.kind === "critique" || step.kind === "llm_error" ? "text-[#F59E0B]" : step.event === "agent.request" || step.kind === "agent_reply" ? "text-[#60A5FA]" : "text-[#94A3B8]";
  return (
    <li className="border-l border-[#26303C] pl-3">
      <div className="flex flex-wrap items-baseline gap-2 text-xs">
        <span className={`font-medium ${tone}`}>{label}</span>
        {step.tool && step.kind !== "agent_reply" ? <code className="text-[#E6EDF3]">{step.tool}</code> : null}
        {step.actor && step.actor !== "portfolio_manager" ? <span className="text-[#94A3B8]">from {step.actor}</span> : null}
        <span className="text-[#64748B]">{new Date(step.timestamp).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false })}</span>
      </div>
      {step.purpose ? <p className="text-sm text-[#CBD5E1]">Why: {step.purpose}</p> : null}
      {step.question ? <p className="text-sm text-[#CBD5E1]">“{step.question}”</p> : null}
      {step.summary ? <p className="whitespace-pre-wrap break-words text-sm">{step.summary}</p> : null}
    </li>
  );
}

function ReviewDetail({ reviewId }: { reviewId: string }) {
  const { data, error } = useSWR<Detail>(`/api/v1/reviews/${reviewId}`, (key: string) => fetchApi<Detail>(key), {
    refreshInterval: (latest) => (latest?.status === "done" ? 0 : 2500),
  });
  if (error) return <ErrorState message="Could not load this review." />;
  if (!data) return <p className="text-sm text-[#94A3B8]">Loading…</p>;
  const verdict = data.verdict;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-base font-semibold">{data.symbol}</span>
        <Badge tone={verdict ? TONE[verdict.verdict] : "info"}>{verdictLabel(verdict, data.status)}</Badge>
        <span className="text-[#94A3B8]">
          {data.kind === "pipeline" ? "Real proposal from the decision engine" : "Operator question (nothing is traded)"} · {data.request.side} {data.request.quantity} @ ₹{data.request.entry_price} · fused {data.request.aggregated_signal.toFixed(2)}
        </span>
      </div>
      {verdict ? (
        <div className="rounded border border-[#26303C] bg-[#0F141B] p-3 text-sm">
          <p className="font-medium">{verdict.critique}</p>
          {verdict.conflicts.length ? (
            <ul className="mt-2 list-disc pl-5 text-[#CBD5E1]">
              {verdict.conflicts.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          <p className="mt-2 text-xs text-[#94A3B8]">
            Reviewer: {verdict.reviewer === "rule_fallback" ? "fixed fallback rules (no model answered)" : verdict.reviewer} · {verdict.steps} steps
          </p>
        </div>
      ) : null}
      {data.chain ? (
        <p className="text-xs text-[#94A3B8]">
          Then the risk engine: {data.chain.risk ? `${data.chain.risk.status}${data.chain.risk.rejection_reason ? ` (${data.chain.risk.rejection_reason})` : ""}` : "not yet"} · order: {data.chain.order ? `${data.chain.order.status} ${data.chain.order.quantity}` : "none"}
        </p>
      ) : null}
      <ol className="space-y-2">
        {data.steps.map((step, index) => (
          <StepItem key={`${step.event}-${step.step ?? index}-${index}`} step={step} />
        ))}
        {data.status !== "done" ? <li className="pl-3 text-xs text-[#94A3B8]">The manager is working…</li> : null}
      </ol>
      <p className="text-xs text-[#64748B]">
        Correlation id <code>{data.correlation_id.slice(0, 16)}…</code>: the same messages are on the <a className="underline" href="/trace">Agent trace</a> page.
      </p>
    </div>
  );
}

function AskForm({ symbols, onAsked }: { symbols: string[]; onAsked: (id: string) => void }) {
  const [symbol, setSymbol] = useState(symbols[0] ?? "RELIANCE");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  useEffect(() => {
    if (!symbols.includes(symbol) && symbols[0]) setSymbol(symbols[0]);
  }, [symbols, symbol]);
  async function ask() {
    setPending(true);
    setMessage(null);
    try {
      const result = await postApi<{ review_id: string }>("/api/v1/reviews", { symbol, horizon: "SWING" });
      onAsked(result.review_id);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <OperatorGate what="ask the portfolio manager for a review">
      {(operator) => (
        <form
          className="flex flex-wrap items-end gap-3 text-sm"
          onSubmit={(event) => {
            event.preventDefault();
            void ask();
          }}
        >
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#94A3B8]">Stock</span>
            <select value={symbol} onChange={(event) => setSymbol(event.target.value)} disabled={!operator} className="rounded border border-[#26303C] bg-[#0B0F14] px-2 py-1">
              {symbols.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={!operator || pending} className="rounded bg-[#2563EB] px-3 py-1 font-medium text-white disabled:opacity-50">
            {pending ? "Asking…" : "Would you buy this now?"}
          </button>
          <span className="text-xs text-[#94A3B8]">Takes 20–60 s. Hypothetical: nothing is traded.</span>
          {message ? <span className="text-xs text-[#EF4444]">{message}</span> : null}
        </form>
      )}
    </OperatorGate>
  );
}

export function ManagerReviews() {
  const { data, error } = useSWR<{ reviews: ReviewRow[] }>("/api/v1/reviews?limit=40", (key: string) => fetchApi<{ reviews: ReviewRow[] }>(key), { refreshInterval: 5000 });
  const { data: instruments } = useSWR<Array<{ symbol: string }>>("/api/v1/market/instruments", (key: string) => fetchApi<Array<{ symbol: string }>>(key));
  const [selected, setSelected] = useState<string | null>(null);
  const reviews = data?.reviews ?? [];
  const current = selected ?? reviews[0]?.review_id ?? null;
  const symbols = (instruments ?? []).map((item) => item.symbol).filter((item) => item !== "NIFTY50" && item !== "INDIAVIX").sort();
  return (
    <div className="space-y-4">
      <Card title="Ask the portfolio manager">
        <AskForm symbols={symbols} onAsked={setSelected} />
      </Card>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <Card title="Recent reviews">
          {error ? <ErrorState message="Could not load reviews." /> : null}
          {!error && reviews.length === 0 ? <p className="text-sm text-[#94A3B8]">No reviews yet. Agent BUYs are reviewed during the 09:20–10:30 IST entry window, or ask above.</p> : null}
          <ul className="divide-y divide-[#1E2630]">
            {reviews.map((row) => (
              <li key={row.review_id}>
                <button
                  type="button"
                  onClick={() => setSelected(row.review_id)}
                  className={`flex w-full items-center justify-between gap-2 px-1 py-2 text-left text-sm ${row.review_id === current ? "bg-[#111827]" : ""}`}
                >
                  <span>
                    <span className="font-medium">{row.symbol}</span>{" "}
                    <span className="text-xs text-[#94A3B8]">
                      {row.kind === "pipeline" ? "trade" : "question"} · {when(row.created_at)}
                    </span>
                  </span>
                  <Badge tone={row.verdict ? TONE[row.verdict.verdict] : "info"}>{verdictLabel(row.verdict, row.status)}</Badge>
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Reasoning">{current ? <ReviewDetail reviewId={current} /> : <p className="text-sm text-[#94A3B8]">Select a review.</p>}</Card>
      </div>
    </div>
  );
}
