import result from "@/lib/research/ml-ensemble-result.json";
import { Badge, Card, Stat, Table, Td } from "@/components/ui";

type Regime = { windows: number; mean_net: number };
type Variant = {
  variant: string;
  horizon: number;
  selector: string;
  exposure: string;
  windows: number;
  mean_net: number;
  annualized_net: number;
  sharpe: number;
  max_drawdown: number;
  exposure_share: number;
  excess_vs_equal_weight: number;
  regimes: Record<string, Regime>;
};

const pct = (value: number, digits = 1) => `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
const tone = (value: number) => (value > 0 ? "text-[#22C55E]" : value < 0 ? "text-[#EF4444]" : "text-[#94A3B8]");
const EXPOSURE: Record<string, string> = { always: "always invested", trend: "NIFTY trend filter", timing: "ML market timing" };

export function EnsembleStudy() {
  const variants = [...(result.variants as unknown as Variant[])].sort((a, b) => b.annualized_net - a.annualized_net);
  const check = result.reality_check as { net_return_p_value: number; best_net_variant: string; excess_p_value: number };
  const best = variants.find((item) => item.variant === check.best_net_variant) ?? variants[0];
  const profitable = variants.filter((item) => item.mean_net > 0).length;
  const baselines = result.baselines as Record<string, { mean_net: number; annualized_net: number }>;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Verdict" value="No robust edge" tone="down" hint="nothing is traded" />
        <Stat label="Variants that made money" value={`${profitable} / ${variants.length}`} hint="net of Zerodha delivery costs" />
        <Stat label="Best variant, annualised" value={pct(best.annualized_net)} tone={best.annualized_net > 0 ? "up" : "down"} hint={`${best.variant} · Sharpe ${best.sharpe.toFixed(2)}`} />
        <Stat label="Reality Check p-value" value={check.net_return_p_value.toFixed(2)} tone="down" hint="chance the best of 45 looks this good by luck alone" />
      </div>
      <Card title="What was tried">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>45 features: momentum, volatility, RSI, ATR, 52-week-high distance, volume, beta and relative strength against NIFTY and the stock&apos;s sector index, plus NIFTY trend, India VIX level and change, market breadth and dispersion.</li>
          <li>Four algorithms (ridge, gradient boosting, random forest, extra trees) and an ensemble that averages their rankings.</li>
          <li>Three exposure rules for different market conditions: always invested, a NIFTY 50-day trend filter, or an ML market-timing model that can hold cash.</li>
          <li>5-, 10- and 20-session holds; walk-forward training only; Zerodha delivery costs and slippage on every trade.</li>
        </ul>
      </Card>
      <Card title="Top 10 of 45 variants (all are in the result file)">
        <Table head={["Variant", "Hold", "Selector", "Exposure", "Annualised", "Sharpe", "Max DD", "Invested", "Excess / window"]} minWidth={900}>
          {variants.slice(0, 10).map((item) => (
            <tr key={item.variant}>
              <Td className="font-mono text-xs">{item.variant}</Td>
              <Td>{item.horizon}d</Td>
              <Td>{item.selector}</Td>
              <Td className="text-xs">{EXPOSURE[item.exposure] ?? item.exposure}</Td>
              <Td className={`tabular-nums ${tone(item.annualized_net)}`}>{pct(item.annualized_net)}</Td>
              <Td className="tabular-nums">{item.sharpe.toFixed(2)}</Td>
              <Td className="tabular-nums text-[#94A3B8]">{pct(-item.max_drawdown)}</Td>
              <Td className="tabular-nums text-[#94A3B8]">{(item.exposure_share * 100).toFixed(0)}%</Td>
              <Td className={`tabular-nums ${tone(item.excess_vs_equal_weight)}`}>{pct(item.excess_vs_equal_weight, 2)}</Td>
            </tr>
          ))}
        </Table>
        <p className="mt-2 text-xs text-[#64748B]">
          Equal-weight basket, same windows and costs: {pct(baselines["H5-equal-weight"].annualized_net)} (5d), {pct(baselines["H10-equal-weight"].annualized_net)} (10d),{" "}
          {pct(baselines["H20-equal-weight"].annualized_net)} (20d) annualised.
        </p>
      </Card>
      <Card title={`Best variant by market condition: ${best.variant}`}>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(best.regimes).map(([name, regime]) => (
            <div key={name} className="rounded border border-[#26303C] p-3 text-sm">
              <div className="text-xs text-[#94A3B8]">{name.replace("/", " · ")}</div>
              <div className={`text-lg font-semibold tabular-nums ${tone(regime.mean_net)}`}>{pct(regime.mean_net, 2)}</div>
              <div className="text-xs text-[#64748B]">{regime.windows} windows</div>
            </div>
          ))}
        </div>
      </Card>
      <Card title="What we learned">
        <ul className="space-y-2 text-sm">
          <li><Badge tone="info">costs</Badge> About 0.4% per delivery round trip is about 20% a year at a 5-day hold but about 5% at 20 days. Every always-invested 5-day variant lost money.</li>
          <li><Badge tone="info">cash</Badge> The profitable variants sat in cash roughly half the time. In this falling period, avoiding exposure mattered more than stock picking.</li>
          <li><Badge tone="info">simplicity</Badge> Ridge regression beat the tree models and the ensemble, which is consistent with complex models fitting noise.</li>
          <li><Badge tone="down">robustness</Badge> With 45 tries and few windows, the best result is within luck (p = {check.net_return_p_value.toFixed(2)}), and it still lost money in up-trend, high-volatility windows.</li>
        </ul>
        <p className="mt-3 text-xs text-[#64748B]">Next: forward-test the leading variant by recording its picks daily, with no orders, and scoring them on data that does not exist yet.</p>
      </Card>
    </>
  );
}
