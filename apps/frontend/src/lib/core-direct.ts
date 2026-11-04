// Server-side calls from this site's own route handlers to Core, with the server-held token.
export function coreUrl(path: string): string {
  return `${process.env.API_INTERNAL_BASE_URL ?? "http://127.0.0.1:8000"}${path}`;
}

export function coreHeaders(): HeadersInit {
  const token = process.env.CORE_API_TOKEN;
  return token ? { Authorization: `Bearer ${token}` } : {};
}
