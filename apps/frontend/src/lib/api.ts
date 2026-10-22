const PREFIX = "/api/v1/";

function onServer(): boolean {
  return typeof window === "undefined";
}

// Server components call Core directly (API_INTERNAL_BASE_URL, e.g. http://core-api:8000).
// The browser calls same-origin /api/v1/*, which the Next proxy route forwards with the
// server-side token, unless NEXT_PUBLIC_API_BASE_URL points it somewhere else (mock API).
export function apiUrl(path: string): string {
  if (!path.startsWith(PREFIX) && path !== "/api/health") {
    throw new Error(`refusing non-versioned API path: ${path}`);
  }
  const base = onServer()
    ? process.env.API_INTERNAL_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? ""
    : process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  return `${base}${path}`;
}

function authHeaders(): Record<string, string> {
  const token = onServer() ? process.env.CORE_API_TOKEN ?? process.env.NEXT_PUBLIC_CORE_API_TOKEN : process.env.NEXT_PUBLIC_CORE_API_TOKEN;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchApi<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), { signal: AbortSignal.timeout(15000), headers: authHeaders(), cache: "no-store" });
  if (response.status === 501) {
    throw new Error("not_implemented");
  }
  if (!response.ok) {
    throw new Error(`api_${response.status}`);
  }
  return (await response.json()) as T;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `api_${status}`);
  }
}

// A readable message from a failed write: the server's detail, joined field errors, or the status.
export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.detail as { errors?: unknown } | string | null;
    if (typeof detail === "string") return detail.replaceAll("_", " ");
    if (detail && typeof detail === "object" && "errors" in detail) {
      const errors = detail.errors;
      if (Array.isArray(errors)) return errors.join("; ");
      if (errors && typeof errors === "object") return Object.entries(errors).map(([key, value]) => `${key}: ${value}`).join("; ");
    }
    return `request failed (${error.status})`;
  }
  return error instanceof Error ? error.message : "unknown error";
}

export async function postApi<T>(path: string, body: unknown, options: { timeoutMs?: number } = {}): Promise<T> {
  const headers: HeadersInit = { "Content-Type": "application/json", ...authHeaders() };
  const response = await fetch(apiUrl(path), {
    method: "POST",
    signal: AbortSignal.timeout(options.timeoutMs ?? 15000),
    headers,
    body: JSON.stringify(body),
  });
  if (response.status === 501) {
    throw new Error("not_implemented");
  }
  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail ?? null;
    } catch {
      detail = null;
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}
