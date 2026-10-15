"use client";

import { useCallback, useEffect, useState } from "react";

type Status = { operator: boolean; login_enabled: boolean };

export function useOperator(): { status: Status | null; refresh: () => void } {
  const [status, setStatus] = useState<Status | null>(null);
  const refresh = useCallback(() => {
    fetch("/api/auth/status", { cache: "no-store" })
      .then((response) => response.json() as Promise<Status>)
      .then(setStatus)
      .catch(() => setStatus({ operator: false, login_enabled: false }));
  }, []);
  useEffect(() => {
    refresh();
    const onChange = () => refresh();
    window.addEventListener("stockx-operator", onChange);
    return () => window.removeEventListener("stockx-operator", onChange);
  }, [refresh]);
  return { status, refresh };
}

export function OperatorLogin({ compact = false }: { compact?: boolean }) {
  const { status } = useOperator();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  if (status === null) return null;
  if (status.operator) {
    return (
      <button
        type="button"
        className="rounded border border-[#26303C] px-2 py-1 text-xs text-[#94A3B8] hover:text-[#E6EDF3]"
        onClick={() => void fetch("/api/auth/logout", { method: "POST" }).then(() => window.dispatchEvent(new Event("stockx-operator")))}
      >
        Operator · sign out
      </button>
    );
  }
  if (!status.login_enabled) {
    return compact ? null : <p className="text-xs text-[#94A3B8]">Operator sign-in is disabled on this server (OPERATOR_PASSWORD is not set), so changes are read-only.</p>;
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
    setPending(false);
    if (response.ok) {
      setPassword("");
      window.dispatchEvent(new Event("stockx-operator"));
    } else {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      setError((body.detail ?? "sign-in failed").replaceAll("_", " "));
    }
  }
  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-wrap items-center gap-2 text-xs">
      <input
        type="password"
        autoComplete="current-password"
        aria-label="Operator password"
        placeholder="Operator password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        className="w-40 rounded border border-[#26303C] bg-[#0B0F14] px-2 py-1"
      />
      <button type="submit" disabled={pending || !password} className="rounded bg-[#2563EB] px-2 py-1 font-medium text-white disabled:opacity-50">
        Sign in
      </button>
      {error ? <span className="text-[#EF4444]">{error}</span> : null}
    </form>
  );
}

// Children get operator=true only after sign-in; otherwise they render read-only with a sign-in box above.
export function OperatorGate({ children, what }: { children: (operator: boolean) => React.ReactNode; what: string }) {
  const { status } = useOperator();
  const operator = Boolean(status?.operator);
  return (
    <div>
      {!operator ? (
        <div className="mb-3 rounded border border-[#26303C] bg-[#0F141B] p-3">
          <p className="mb-2 text-xs text-[#94A3B8]">Sign in as the operator to {what}. Visitors can look but not change anything.</p>
          <OperatorLogin />
        </div>
      ) : null}
      {children(operator)}
    </div>
  );
}

// Header chip: shows the operator session and a sign-out, and nothing for visitors.
export function OperatorChip() {
  const { status } = useOperator();
  if (!status?.operator) return null;
  return (
    <button
      type="button"
      title="Signed in as operator. Click to sign out."
      className="rounded bg-[#713F12]/60 px-2 py-0.5 font-medium text-[#FCD34D]"
      onClick={() => void fetch("/api/auth/logout", { method: "POST" }).then(() => window.dispatchEvent(new Event("stockx-operator")))}
    >
      Operator ✕
    </button>
  );
}
