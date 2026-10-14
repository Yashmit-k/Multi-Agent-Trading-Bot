const PREFIX = "/api/v1/";

export function apiUrl(path: string): string {
  if (!path.startsWith(PREFIX) && path !== "/api/health") {
    throw new Error(`refusing non-versioned API path: ${path}`);
  }
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  return `${base}${path}`;
}

export async function fetchApi<T>(path: string): Promise<T> {
  const token = process.env.NEXT_PUBLIC_CORE_API_TOKEN;
  const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(apiUrl(path), { signal: AbortSignal.timeout(15000), headers });
  if (response.status === 501) {
    throw new Error("not_implemented");
  }
  if (!response.ok) {
    throw new Error(`api_${response.status}`);
  }
  return (await response.json()) as T;
}

export async function postApi<T>(path: string, body: unknown): Promise<T> {
  const token = process.env.NEXT_PUBLIC_CORE_API_TOKEN;
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
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
