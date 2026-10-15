import { loginEnabled, tokenFromCookieHeader, validToken } from "@/lib/operator-session";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  return Response.json(
    { operator: validToken(tokenFromCookieHeader(request.headers.get("cookie"))), login_enabled: loginEnabled() },
    { headers: { "Cache-Control": "no-store" } },
  );
}
