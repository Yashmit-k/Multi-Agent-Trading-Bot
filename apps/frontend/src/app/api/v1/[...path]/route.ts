import { allowRead, allowWrite } from "@/lib/proxy-policy";

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
  if (!allowWrite(pathname, process.env.FRONTEND_ALLOW_POST_PATHS)) {
    return Response.json({ detail: "write_blocked_by_public_proxy" }, { status: 403 });
  }
  const url = new URL(request.url);
  try {
    return await forward(
      await fetch(target(path, url.search), {
        method: "POST",
        headers: headers(request.headers.get("Content-Type")),
        body: await request.text(),
        signal: AbortSignal.timeout(15000),
      }),
    );
  } catch {
    return Response.json({ detail: "core_api_unreachable" }, { status: 502 });
  }
}
