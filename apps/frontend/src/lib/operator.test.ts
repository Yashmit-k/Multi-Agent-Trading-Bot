import { afterEach, describe, expect, it } from "vitest";
import { allowOperatorWrite, allowPublicWrite, allowWrite } from "@/lib/proxy-policy";
import { issueToken, passwordMatches, tokenFromCookieHeader, validToken } from "@/lib/operator-session";

describe("operator write policy", () => {
  it("lists only the operator actions", () => {
    expect(allowOperatorWrite("/api/v1/settings/risk")).toBe(true);
    expect(allowOperatorWrite("/api/v1/paper/orders/manual")).toBe(true);
    expect(allowOperatorWrite("/api/v1/paper/orders/abc123/cancel")).toBe(true);
    expect(allowOperatorWrite("/api/v1/paper/positions/M&M/close")).toBe(true);
    expect(allowOperatorWrite("/api/v1/strategies/strat-1/backtest")).toBe(true);
    expect(allowOperatorWrite("/api/v1/paper/start")).toBe(false);
    expect(allowOperatorWrite("/api/v1/internal/signals")).toBe(false);
    expect(allowOperatorWrite("/api/v1/zerodha/backfill")).toBe(false);
  });
  it("lets visitors preview backtests only", () => {
    expect(allowPublicWrite("/api/v1/strategies/preview/backtest")).toBe(true);
    expect(allowPublicWrite("/api/v1/strategies")).toBe(false);
    expect(allowWrite("/api/v1/settings/risk", "")).toBe(false);
  });
});

describe("operator session", () => {
  const before = { ...process.env };
  afterEach(() => {
    process.env = { ...before };
  });
  it("is disabled without a password", () => {
    delete process.env.OPERATOR_PASSWORD;
    expect(passwordMatches("anything")).toBe(false);
    expect(validToken(issueToken())).toBe(false);
  });
  it("signs, expires and rejects tampering", () => {
    process.env.OPERATOR_PASSWORD = "test-only-password";
    expect(passwordMatches("test-only-password")).toBe(true);
    expect(passwordMatches("wrong")).toBe(false);
    const token = issueToken();
    expect(validToken(token)).toBe(true);
    expect(validToken(token.replace(/.$/, (c) => (c === "a" ? "b" : "a")))).toBe(false);
    expect(validToken(issueToken(Date.now() - 13 * 3600 * 1000))).toBe(false);
    expect(tokenFromCookieHeader(`a=1; stockx_operator=${token}`)).toBe(token);
  });
});
