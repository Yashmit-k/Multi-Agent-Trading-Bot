import { COOKIE, SESSION_SECONDS, clearFailures, issueToken, lockedOut, loginEnabled, passwordMatches, recordFailure } from "@/lib/operator-session";

export const dynamic = "force-dynamic";

function address(request: Request): string {
  return request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "local";
}

export async function POST(request: Request): Promise<Response> {
  if (!loginEnabled()) return Response.json({ detail: "operator_login_disabled" }, { status: 503 });
  const who = address(request);
  if (lockedOut(who)) return Response.json({ detail: "too_many_attempts" }, { status: 429 });
  let password = "";
  try {
    password = String(((await request.json()) as { password?: unknown }).password ?? "");
  } catch {
    return Response.json({ detail: "bad_request" }, { status: 400 });
  }
  if (!passwordMatches(password)) {
    recordFailure(who);
    return Response.json({ detail: "wrong_password" }, { status: 401 });
  }
  clearFailures(who);
  const secure = new URL(request.url).protocol === "https:" || request.headers.get("x-forwarded-proto") === "https";
  const cookie = `${COOKIE}=${issueToken()}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${SESSION_SECONDS}${secure ? "; Secure" : ""}`;
  return new Response(JSON.stringify({ operator: true }), { status: 200, headers: { "Content-Type": "application/json", "Set-Cookie": cookie } });
}
