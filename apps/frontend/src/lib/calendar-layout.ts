import { addDaysKey, consecutiveDateKeys, parseDateKey, weekSundayKey, weekdaySundayFirst } from "@/lib/ist";

export type CalendarLayout = {
  keys: string[];
  weekStarts: string[];
  /** weekStarts.length columns × 7 Sunday-first rows. null = outside the 365-day range. */
  columns: (string | null)[][];
  monthLabels: { weekIndex: number; label: string }[];
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function buildSundayFirstLayout(endKey: string, count = 365): CalendarLayout {
  const keys = consecutiveDateKeys(endKey, count);
  const keySet = new Set(keys);
  const firstWeek = weekSundayKey(keys[0]);
  const lastWeek = weekSundayKey(keys[keys.length - 1]);
  const weekStarts: string[] = [];
  for (let cursor = firstWeek; cursor <= lastWeek; cursor = addDaysKey(cursor, 7)) {
    weekStarts.push(cursor);
  }
  const columns = weekStarts.map((start) =>
    Array.from({ length: 7 }, (_, weekday) => {
      const key = addDaysKey(start, weekday);
      return keySet.has(key) ? key : null;
    }),
  );
  const monthLabels: { weekIndex: number; label: string }[] = [];
  let previous = "";
  columns.forEach((column, weekIndex) => {
    const firstInRange = column.find((key) => key !== null);
    if (!firstInRange) return;
    const monthId = firstInRange.slice(0, 7);
    if (monthId === previous) return;
    const { m } = parseDateKey(firstInRange);
    monthLabels.push({ weekIndex, label: MONTHS[m - 1] });
    previous = monthId;
  });
  return { keys, weekStarts, columns, monthLabels };
}

export function assertGithubGeometry(layout: CalendarLayout): void {
  if (layout.keys.length !== 365) throw new Error(`expected 365 keys, got ${layout.keys.length}`);
  if (new Set(layout.keys).size !== 365) throw new Error("date keys are not unique");
  if (layout.weekStarts.length !== 53) throw new Error(`expected 53 week columns, got ${layout.weekStarts.length}`);
  const seen = new Set<string>();
  layout.columns.forEach((column) => {
    column.forEach((key, weekday) => {
      if (key === null) return;
      if (seen.has(key)) throw new Error(`duplicate cell ${key}`);
      if (weekdaySundayFirst(key) !== weekday) throw new Error(`weekday mismatch ${key}`);
      seen.add(key);
    });
  });
  if (seen.size !== 365) throw new Error("not every date appears in exactly one cell");
}
