import { coreHeaders, coreUrl } from "@/lib/core-direct";
import { tokenFromCookieHeader, validToken } from "@/lib/operator-session";
import { sameOrigin } from "@/lib/same-origin";

export const dynamic = "force-dynamic";

// Finishes the Zerodha login. Zerodha redirects the browser to /zerodha/callback; that page posts the one-time
// request token here, so the operator's SameSite=Strict cookie is sent and checked before Core exchanges it.
export async function POST(request: Request): Promise<Response> {
  if (!validToken(tokenFromCookieHeader(request.headers.get("cookie"))) || !sameOrigin(request)) {
    return Response.json({ detail: "operator_login_required" }, { status: 403 });
  }
  let token = "";
  try {
    token = String(((await request.json()) as { request_token?: unknown }).request_token ?? "");
  } catch {
    return Response.json({ detail: "bad_request" }, { status: 400 });
  }
  if (!/^[A-Za-z0-9]{8,64}$/.test(token)) {
    return Response.json({ detail: "bad_request_token" }, { status: 400 });
  }
  try {
    const response = await fetch(coreUrl(`/api/v1/zerodha/callback?request_token=${encodeURIComponent(token)}`), {
      headers: coreHeaders(),
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    const body = (await response.json()) as { authenticated?: boolean; detail?: string };
    return Response.json(response.ok ? { authenticated: Boolean(body.authenticated) } : { detail: body.detail ?? "zerodha_session_failed" }, { status: response.ok ? 200 : 502 });
  } catch {
    return Response.json({ detail: "core_api_unreachable" }, { status: 502 });
  }
}
