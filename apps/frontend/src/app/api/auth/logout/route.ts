import { COOKIE } from "@/lib/operator-session";

export const dynamic = "force-dynamic";

export async function POST(): Promise<Response> {
  return new Response(JSON.stringify({ operator: false }), {
    status: 200,
    headers: { "Content-Type": "application/json", "Set-Cookie": `${COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0` },
  });
}
