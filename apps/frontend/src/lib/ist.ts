export const IST = "Asia/Kolkata";

const DATE_KEY = /^(\d{4})-(\d{2})-(\d{2})$/;

export function parseDateKey(key: string): { y: number; m: number; d: number } {
  const match = DATE_KEY.exec(key);
  if (!match) throw new Error(`invalid calendar_date_ist ${key}`);
  return { y: Number(match[1]), m: Number(match[2]), d: Number(match[3]) };
}

/** Treat YYYY-MM-DD as a civil key. Do not parse it as a JS local timestamp. */
export function addDaysKey(key: string, days: number): string {
  const { y, m, d } = parseDateKey(key);
  const utc = new Date(Date.UTC(y, m - 1, d + days));
  const yy = utc.getUTCFullYear();
  const mm = String(utc.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(utc.getUTCDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

export function weekdaySundayFirst(key: string): number {
  const { y, m, d } = parseDateKey(key);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
}

export function weekSundayKey(key: string): string {
  return addDaysKey(key, -weekdaySundayFirst(key));
}

export function consecutiveDateKeys(endKey: string, count = 365): string[] {
  const start = addDaysKey(endKey, -(count - 1));
  return Array.from({ length: count }, (_, index) => addDaysKey(start, index));
}

/** Instant → IST calendar date YYYY-MM-DD. */
export function istDateKeyFromInstant(iso: string): string {
  const formatted = new Intl.DateTimeFormat("en-CA", {
    timeZone: IST,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(iso));
  return formatted;
}

export function formatIstInstant(iso: string): string {
  const date = new Date(iso);
  const datePart = new Intl.DateTimeFormat("en-GB", {
    timeZone: IST,
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
  const timePart = new Intl.DateTimeFormat("en-GB", {
    timeZone: IST,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
  return `${timePart} IST on ${datePart}`;
}

export function formatDateKeyLong(key: string): string {
  const { y, m, d } = parseDateKey(key);
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(Date.UTC(y, m - 1, d)));
}

export const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
export const WEEKDAY_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] as const;
