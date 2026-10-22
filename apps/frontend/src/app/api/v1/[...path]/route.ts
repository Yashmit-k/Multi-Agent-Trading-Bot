import { allowOperatorWrite, allowPublicWrite, allowRead, allowWrite } from "@/lib/proxy-policy";
import { tokenFromCookieHeader, validToken } from "@/lib/operator-session";

export const dynamic = "force-dynamic";

function target(path: string[], search: string): string {
  const base = process.env.API_INTERNAL_BASE_URL ?? "http://127.0.0.1:8000";
  return `${base}/api/v1/${path.map(encodeURIComponent).join("/")}${search}`;
}

function headers(contentType?: string | null): HeadersInit {
  const token = process.env.CORE_API_TOKEN;
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(contentType ? { "Content-Type": contentType } : {}),
  };
}

async function forward(response: Response): Promise<Response> {
  const body = await response.arrayBuffer();
  return new Response(body, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json", "Cache-Control": "no-store" },
  });
}

type Context = { params: Promise<{ path: string[] }> };

// A signed-in operator's writes must come from this site's own pages.
function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true; // same-origin fetches from older browsers may omit it; the cookie is SameSite=Strict
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

// Ten public backtest previews per address per ten minutes, so visitors cannot tie up the server.
const previews = new Map<string, number[]>();
function rateLimited(request: Request, now = Date.now()): boolean {
  const who = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "local";
  const recent = (previews.get(who) ?? []).filter((stamp) => now - stamp < 10 * 60 * 1000);
  if (recent.length >= 10) return true;
  previews.set(who, [...recent, now]);
  return false;
}

export async function GET(request: Request, context: Context): Promise<Response> {
  const { path } = await context.params;
  const pathname = `/api/v1/${path.join("/")}`;
  if (!allowRead(pathname)) {
    return Response.json({ detail: "blocked_by_public_proxy" }, { status: 403 });
  }
  const url = new URL(request.url);
  try {
    return await forward(await fetch(target(path, url.search), { headers: headers(), cache: "no-store", signal: AbortSignal.timeout(15000) }));
  } catch {
    return Response.json({ detail: "core_api_unreachable" }, { status: 502 });
  }
}

export async function POST(request: Request, context: Context): Promise<Response> {
  const { path } = await context.params;
  const pathname = `/api/v1/${path.join("/")}`;
  const listed = allowWrite(pathname, process.env.FRONTEND_ALLOW_POST_PATHS);
  const signedIn = validToken(tokenFromCookieHeader(request.headers.get("cookie"))) && sameOrigin(request);
  const operator = allowOperatorWrite(pathname) && signedIn;
  const visitor = allowPublicWrite(pathname);
  if (!listed && !operator && !visitor) {
    const detail = allowOperatorWrite(pathname) ? "operator_login_required" : "write_blocked_by_public_proxy";
    return Response.json({ detail }, { status: 403 });
  }
  // The preview limit protects the server from visitors; a signed-in operator is never limited.
  if (visitor && !signedIn && rateLimited(request)) {
    return Response.json({ detail: "too_many_backtests_try_again_shortly" }, { status: 429 });
  }
  const url = new URL(request.url);
  try {
    return await forward(
      await fetch(target(path, url.search), {
        method: "POST",
        headers: headers(request.headers.get("Content-Type")),
        body: await request.text(),
        signal: AbortSignal.timeout(pathname.includes("/backtest") ? 60000 : 15000),
      }),
    );
  } catch {
    return Response.json({ detail: "core_api_unreachable" }, { status: 502 });
  }
}
