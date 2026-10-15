// Operator sign-in for the public site. Visitors are read-only; an operator who knows
// OPERATOR_PASSWORD (set on the server, never in the bundle) gets a signed, HTTP-only cookie
// that lets the proxy forward the operator writes (settings, manual orders, strategies).
// Without OPERATOR_PASSWORD, sign-in is disabled and every write stays blocked.
import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export const COOKIE = "stockx_operator";
export const SESSION_SECONDS = 12 * 60 * 60;

function secret(): string {
  const explicit = process.env.OPERATOR_SESSION_SECRET;
  if (explicit) return explicit;
  return createHash("sha256").update(`stockx-operator:${process.env.OPERATOR_PASSWORD ?? ""}:${process.env.CORE_API_TOKEN ?? ""}`).digest("hex");
}

export function loginEnabled(): boolean {
  return Boolean(process.env.OPERATOR_PASSWORD);
}

export function passwordMatches(candidate: string): boolean {
  const expected = process.env.OPERATOR_PASSWORD;
  if (!expected) return false;
  const a = createHash("sha256").update(candidate).digest();
  const b = createHash("sha256").update(expected).digest();
  return timingSafeEqual(a, b);
}

function sign(payload: string): string {
  return createHmac("sha256", secret()).update(payload).digest("hex");
}

export function issueToken(now = Date.now()): string {
  const expires = Math.floor(now / 1000) + SESSION_SECONDS;
  const payload = `operator.${expires}`;
  return `${payload}.${sign(payload)}`;
}

export function validToken(token: string | undefined, now = Date.now()): boolean {
  if (!token || !loginEnabled()) return false;
  const parts = token.split(".");
  if (parts.length !== 3 || parts[0] !== "operator") return false;
  const expires = Number(parts[1]);
  if (!Number.isFinite(expires) || expires * 1000 < now) return false;
  const expected = Buffer.from(sign(`${parts[0]}.${parts[1]}`));
  const given = Buffer.from(parts[2]);
  return expected.length === given.length && timingSafeEqual(expected, given);
}

export function tokenFromCookieHeader(header: string | null): string | undefined {
  if (!header) return undefined;
  for (const part of header.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === COOKIE) return rest.join("=");
  }
  return undefined;
}

// Five wrong passwords from one address lock it out for 15 minutes.
const failures = new Map<string, { count: number; until: number }>();

export function lockedOut(address: string, now = Date.now()): boolean {
  const entry = failures.get(address);
  return Boolean(entry && entry.count >= 5 && entry.until > now);
}

export function recordFailure(address: string, now = Date.now()): void {
  const entry = failures.get(address);
  const fresh = !entry || entry.until <= now;
  failures.set(address, { count: fresh ? 1 : entry.count + 1, until: now + 15 * 60 * 1000 });
}

export function clearFailures(address: string): void {
  failures.delete(address);
}
