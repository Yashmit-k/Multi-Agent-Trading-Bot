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

export async function postApi<T>(path: string, body: unknown): Promise<T> {
  const headers: HeadersInit = { "Content-Type": "application/json", ...authHeaders() };
  const response = await fetch(apiUrl(path), {
    method: "POST",
    signal: AbortSignal.timeout(15000),
    headers,
    body: JSON.stringify(body),
  });
  if (response.status === 501) {
    throw new Error("not_implemented");
  }
  if (!response.ok) {
    throw new Error(`api_${response.status}`);
  }
  return (await response.json()) as T;
}
