import result from "@/lib/research/ml-rank-result.json";
import { PageFrame } from "@/components/shell/PageFrame";
import { Badge, Card, Stat, Table, Td } from "@/components/ui";
import { EnsembleStudy } from "@/components/research/EnsembleStudy";

export const metadata = { title: "Research · StockX" };

type Period = {
  windows: number;
  strategy_mean: number;
  equal_weight_mean: number;
  momentum_mean: number;
  random_mean: number;
  excess_mean: number;
  excess_lower_90: number;
  excess_upper_90: number;
  hit_rate: number;
  trades: number;
  total_cost: number;
  total_net_pnl: number;
  excess_without_best_symbol: number;
  best_symbol: string;
  passed: Record<string, boolean>;
};

const pct = (value: number, digits = 2) => `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
const inr = (value: number) => `₹${Math.round(value).toLocaleString("en-IN")}`;

const GATES: Record<string, string> = {
  excess_positive_with_lower_bound: "Beats equal weight, with the 90% lower bound above zero",
  beats_momentum: "Beats plain 20-day momentum",
  beats_random: "Beats random picks",
  not_one_stock: "Still beats equal weight without its best stock",
};

function Row({ label, period }: { label: string; period: Period }) {
  return (
    <tr>
      <Td>{label}</Td>
      <Td className="tabular-nums">{period.windows}</Td>
      <Td className={`tabular-nums ${period.strategy_mean >= 0 ? "text-[#22C55E]" : "text-[#EF4444]"}`}>{pct(period.strategy_mean)}</Td>
      <Td className="tabular-nums text-[#94A3B8]">{pct(period.equal_weight_mean)}</Td>
      <Td className="tabular-nums text-[#94A3B8]">{pct(period.momentum_mean)}</Td>
      <Td className="tabular-nums text-[#94A3B8]">{pct(period.random_mean)}</Td>
      <Td className="tabular-nums">{pct(period.excess_mean, 3)}</Td>
      <Td className="tabular-nums text-xs text-[#94A3B8]">
        {pct(period.excess_lower_90, 3)} … {pct(period.excess_upper_90, 3)}
      </Td>
      <Td className="tabular-nums">{(period.hit_rate * 100).toFixed(0)}%</Td>
    </tr>
  );
}

export default function ResearchPage() {
  const dev = result.development as unknown as Record<string, Period>;
  const oos = result.out_of_sample as unknown as Period;
  const chosen = result.chosen_model as string;
  return (
    <PageFrame
      title="ML research"
      description="Two pre-registered studies. Rules were fixed and committed before any result existed, and every result is shown, including failures."
    >
      <h2 className="pt-2 text-lg font-semibold">Study 2 · Multi-algorithm ensemble across market conditions</h2>
      <EnsembleStudy />
      <h2 className="pt-6 text-lg font-semibold">Study 1 · Single-model stock ranker, scored once on 2026</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Verdict" value={result.accepted ? "Accepted" : "Not accepted"} tone={result.accepted ? "up" : "down"} hint="MlAgent stays unloaded; no paper orders use it" />
        <Stat label="Out-of-sample edge vs basket" value={pct(oos.excess_mean, 2)} tone="up" hint="per 5-session window, after costs" />
        <Stat label="Windows beating the basket" value={`${(oos.hit_rate * 100).toFixed(0)}%`} hint={`${oos.windows} windows in 2026`} />
        <Stat label="Absolute net P&L (2026)" value={inr(oos.total_net_pnl)} tone={oos.total_net_pnl >= 0 ? "up" : "down"} hint={`${oos.trades} trades, ${inr(oos.total_cost)} in charges`} />
      </div>
      <Card title="How the strategy trades">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>After the close, a model scores all {result.symbols} NIFTY 50 stocks using only past daily candles: returns, volatility, RSI, ATR, moving-average distance, volume, and their cross-sectional ranks.</li>
          <li>Buy the 6 highest-scored at the next open, ₹20,000 each (the paper caps), and sell 5 sessions later.</li>
          <li>Every trade pays Zerodha delivery charges (STT 0.1% each side, stamp, exchange, SEBI, GST, DP) plus 5 bp slippage per fill, about 0.4% per round trip.</li>
          <li>Walk-forward training: refit every 21 sessions on labels that finished at least 5 sessions earlier, so no future data leaks in.</li>
        </ul>
      </Card>
      <Card title="Mean net return per 5-session window">
        <Table head={["Period / model", "Windows", "Model", "Equal weight", "Momentum", "Random", "Excess", "90% interval", "Beat basket"]} minWidth={900}>
          <Row label="Development · A (gradient boosting)" period={dev.A} />
          <Row label="Development · B (ridge)" period={dev.B} />
          <Row label={`Out-of-sample 2026 · ${chosen}`} period={oos} />
        </Table>
        <p className="mt-2 text-xs text-[#64748B]">Model {chosen} was chosen on development data only. 2026 was scored exactly once.</p>
      </Card>
      <Card title="Acceptance gate (out-of-sample)">
        <ul className="space-y-2 text-sm">
          {Object.entries(oos.passed).map(([key, ok]) => (
            <li key={key} className="flex items-center gap-2">
              <Badge tone={ok ? "up" : "down"}>{ok ? "pass" : "fail"}</Badge> {GATES[key] ?? key}
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Conclusion">
        <p className="text-sm">
          The model picks stocks that lose less than the market, and in 2026 that held in two windows out of three. But the evidence is not strong enough to rule out luck,
          and after delivery costs a long-only book still lost money in a falling market. It is a promising stock-picker, not a profitable strategy, so it is not traded.
          The next honest step is a forward test: record its picks from today and score them on data that does not exist yet.
        </p>
      </Card>
    </PageFrame>
  );
}
