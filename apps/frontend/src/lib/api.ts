const PREFIX = "/api/v1/";

export function apiUrl(path: string): string {
  if (!path.startsWith(PREFIX) && path !== "/api/health") {
    throw new Error(`refusing non-versioned API path: ${path}`);
  }
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  return `${base}${path}`;
}

export async function fetchApi<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path));
  if (response.status === 501) {
    throw new Error("not_implemented");
  }
  if (!response.ok) {
    throw new Error(`api_${response.status}`);
  }
  return (await response.json()) as T;
}
