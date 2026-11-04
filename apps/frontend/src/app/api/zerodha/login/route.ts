import { coreHeaders, coreUrl } from "@/lib/core-direct";
import { tokenFromCookieHeader, validToken } from "@/lib/operator-session";

export const dynamic = "force-dynamic";

// Starts the Zerodha login: only the signed-in operator is sent on to Zerodha's own login page.
export async function GET(request: Request): Promise<Response> {
  const back = new URL("/settings", request.url);
  if (!validToken(tokenFromCookieHeader(request.headers.get("cookie")))) {
    back.searchParams.set("zerodha", "operator_login_required");
    return Response.redirect(back, 303);
  }
  try {
    const response = await fetch(coreUrl("/api/v1/zerodha/connect"), { headers: coreHeaders(), cache: "no-store", signal: AbortSignal.timeout(15000) });
    const body = (await response.json()) as { login_url?: string; detail?: string };
    if (!response.ok || !body.login_url?.startsWith("https://kite.zerodha.com/")) {
      back.searchParams.set("zerodha", body.detail ?? "zerodha_connect_failed");
      return Response.redirect(back, 303);
    }
    return Response.redirect(body.login_url, 303);
  } catch {
    back.searchParams.set("zerodha", "core_api_unreachable");
    return Response.redirect(back, 303);
  }
}
