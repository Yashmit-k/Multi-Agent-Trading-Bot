import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { StrategyLab } from "@/components/strategy/StrategyLab";
import type { ActiveStrategy, Catalog, Saved } from "@/components/strategy/types";

export const metadata = { title: "Strategy lab · StockX" };
export const dynamic = "force-dynamic";

export default async function StrategiesPage() {
  try {
    const catalog = await fetchApi<Catalog>("/api/v1/strategies/catalog");
    const saved = await fetchApi<Saved[]>("/api/v1/strategies").catch(() => [] as Saved[]);
    const active = await fetchApi<{ active: ActiveStrategy }>("/api/v1/strategies/active").catch(() => ({ active: null as ActiveStrategy }));
    return (
      <PageFrame
        title="Strategy lab"
        description="Build any rule strategy from 70+ indicators, candle patterns, market structure and session values, with AND/OR groups and higher-timeframe filters. Backtest it on stored NSE data with Zerodha charges, then apply it to paper trading."
      >
        <StrategyLab catalog={catalog} saved={saved} active={active.active} />
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Strategy lab">
        <ErrorState message={error instanceof Error ? error.message : "strategy_lab_unavailable"} />
      </PageFrame>
    );
  }
}
