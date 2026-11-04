import { describe, expect, it } from "vitest";
import { GET } from "@/app/api/zerodha/login/route";
import { publicUrl } from "@/lib/same-origin";

describe("Zerodha login start", () => {
  it("sends a visitor back to the public Settings page, not the container address", async () => {
    const request = new Request("http://localhost:3000/api/zerodha/login", { headers: { "x-forwarded-host": "stockx.example", "x-forwarded-proto": "https" } });
    const response = await GET(request);
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("https://stockx.example/settings?zerodha=operator_login_required");
  });

  it("falls back to the request address when no proxy headers are present", () => {
    expect(publicUrl(new Request("http://localhost:3000/x"), "/settings").toString()).toBe("http://localhost:3000/settings");
  });
});
