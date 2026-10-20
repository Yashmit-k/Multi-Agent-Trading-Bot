// Which browser requests the public proxy forwards to Core. Reads are allowed.
// Writes are refused unless the path is listed in FRONTEND_ALLOW_POST_PATHS, is an operator
// write and the request carries a valid operator session, or is a harmless public write.
// A visitor on the public URL cannot start, stop, or reconfigure paper trading.
const READ_BLOCKED = ["/api/v1/internal/", "/api/v1/zerodha/connect", "/api/v1/zerodha/callback"];

export function allowRead(path: string): boolean {
  return path.startsWith("/api/v1/") && !READ_BLOCKED.some((prefix) => path.startsWith(prefix));
}

export function allowWrite(path: string, allowed: string | undefined): boolean {
  if (!path.startsWith("/api/v1/") || path.startsWith("/api/v1/internal/")) {
    return false;
  }
  const list = (allowed ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return list.includes(path);
}

// Writes an operator who has signed in may make from the browser.
const OPERATOR_WRITES: RegExp[] = [
  /^\/api\/v1\/settings\/risk$/,
  /^\/api\/v1\/paper\/orders\/manual$/,
  /^\/api\/v1\/paper\/orders\/[\w:.-]+\/cancel$/,
  /^\/api\/v1\/paper\/positions\/[\w&.-]+\/close$/,
  /^\/api\/v1\/strategies$/,
  /^\/api\/v1\/strategies\/[\w-]+\/(backtest|delete|apply)$/,
  /^\/api\/v1\/strategies\/active\/stop$/,
  /^\/api\/v1\/risk\/kill-switch$/,
];

// Writes any visitor may make: a backtest preview changes nothing (rate-limited in the route).
const PUBLIC_WRITES: RegExp[] = [/^\/api\/v1\/strategies\/preview\/backtest$/];

export function allowOperatorWrite(path: string): boolean {
  return OPERATOR_WRITES.some((pattern) => pattern.test(path));
}

export function allowPublicWrite(path: string): boolean {
  return PUBLIC_WRITES.some((pattern) => pattern.test(path));
}
