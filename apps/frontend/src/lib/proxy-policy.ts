// Which browser requests the public proxy forwards to Core. Reads are allowed.
// Writes are refused unless the path is listed in FRONTEND_ALLOW_POST_PATHS, so a
// visitor on the public URL cannot start, stop, or reconfigure paper trading.
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
