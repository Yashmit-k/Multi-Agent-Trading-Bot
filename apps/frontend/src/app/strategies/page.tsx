import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { StrategyLab } from "@/components/strategy/StrategyLab";
import type { Catalog, Saved } from "@/components/strategy/types";

export const metadata = { title: "Strategy lab · StockX" };
export const dynamic = "force-dynamic";

export default async function StrategiesPage() {
  try {
    const catalog = await fetchApi<Catalog>("/api/v1/strategies/catalog");
    const saved = await fetchApi<Saved[]>("/api/v1/strategies").catch(() => [] as Saved[]);
    return (
      <PageFrame
        title="Strategy lab"
        description="Build your own rule strategy from indicators (EMA, SMA, RSI, MACD, Bollinger, ATR, volume, breakouts), set stops and sizing, and backtest it on stored NSE data with Zerodha charges."
      >
        <StrategyLab catalog={catalog} saved={saved} />
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
