import { fetchApi } from "@/lib/api";

export type StockRow = {
  symbol: string;
  exchange: string;
  last_price: string;
  prev_close?: string | null;
  change_pct?: string | null;
  bar_end?: string | null;
};

export async function loadStocks(): Promise<StockRow[]> {
  return fetchApi<StockRow[]>("/api/v1/stocks");
}

export function change(row: StockRow): number | null {
  if (row.change_pct === null || row.change_pct === undefined) return null;
  const value = Number(row.change_pct);
  return Number.isFinite(value) ? value : null;
}
