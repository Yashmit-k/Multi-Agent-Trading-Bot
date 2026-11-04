// A signed-in operator's writes must come from this site's own pages.
export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true; // same-origin fetches from older browsers may omit it; the cookie is SameSite=Strict
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

// Behind Caddy, request.url names the container (localhost:3000); the browser needs the public address.
export function publicUrl(request: Request, path: string): URL {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  const proto = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  return host ? new URL(path, `${proto ?? new URL(request.url).protocol.replace(":", "")}://${host}`) : new URL(path, request.url);
}
