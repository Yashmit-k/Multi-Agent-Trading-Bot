import result from "@/lib/research/ml-combined-result.json";
import { Badge, Card, Stat, Table, Td } from "@/components/ui";

const pct = (value: number, digits = 1) => `${(value * 100).toFixed(digits)}%`;
const signed = (value: number, digits = 1) => `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;

type Trading = {
  windows: number;
  annualized_net: number;
  sharpe: number;
  max_drawdown: number;
  exposure_share: number;
  deflated: { deflated_sharpe: number };
};

export function CombinedStudy() {
  const a = result.target_a_direction as unknown as {
    accuracy: number;
    accuracy_90: [number, number];
    auc: number;
    top6_accuracy: number;
    verdict: string;
    trading: Record<string, Trading>;
  };
  const b = result.target_b_volatility as unknown as {
    accuracy: number;
    accuracy_90: [number, number];
    persistence_accuracy: number;
    improvement_90: [number, number];
    auc: number;
    persistence_auc: number;
    verdict: string;
    low_vol_half: { annualized_net: number; annualized_vol: number; max_drawdown: number };
    all_stocks: { annualized_net: number; annualized_vol: number; max_drawdown: number };
  };
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Return direction accuracy" value={pct(a.accuracy)} tone="muted" hint={`coin flip is 50% · AUC ${a.auc.toFixed(3)}`} />
        <Stat label="Return edge" value="None" tone="down" hint={`Deflated Sharpe ${a.trading.always.deflated.deflated_sharpe.toFixed(2)} (needs > 0.95)`} />
        <Stat label="Volatility accuracy" value={pct(b.accuracy)} tone="up" hint={`naive rule ${pct(b.persistence_accuracy)} · AUC ${b.auc.toFixed(3)}`} />
        <Stat label="Risk edge" value="Robust" tone="up" hint={`+${(b.improvement_90[0] * 100).toFixed(1)} to +${(b.improvement_90[1] * 100).toFixed(1)} pts over naive (90%)`} />
      </div>
      <Card title="One model, every hypothesis family">
        <div className="flex flex-wrap gap-1.5 text-xs">
          {["trend & momentum", "short-term reversal", "risk & beta", "volume & liquidity", "intraday microstructure (2.5M five-minute bars)", "sector-relative strength", "NIFTY & India VIX regime", "calendar"].map((name) => (
            <Badge key={name} tone="info">
              {name}
            </Badge>
          ))}
        </div>
        <p className="mt-2 text-sm text-[#94A3B8]">
          {result.features.length} features, one regularised logistic model per target, walk-forward with a 10-session embargo. There is no historical news outside the protected H001 dataset, so news is not a feature yet; live RSS scores are now accumulating for a future test.
        </p>
      </Card>
      <div className="grid gap-3 lg:grid-cols-2">
        <Card title="A · Will the stock beat the median over 10 sessions?" right={<Badge tone="down">{a.verdict}</Badge>}>
          <Table head={["Exposure", "Annualised", "Sharpe", "Max DD", "Deflated Sharpe"]} minWidth={420}>
            {Object.entries(a.trading).map(([name, row]) => (
              <tr key={name}>
                <Td>{name === "always" ? "always invested" : "NIFTY trend filter"}</Td>
                <Td className={`tabular-nums ${row.annualized_net >= 0 ? "text-[#22C55E]" : "text-[#EF4444]"}`}>{signed(row.annualized_net)}</Td>
                <Td className="tabular-nums">{row.sharpe.toFixed(2)}</Td>
                <Td className="tabular-nums text-[#94A3B8]">{pct(row.max_drawdown)}</Td>
                <Td className="tabular-nums">{row.deflated.deflated_sharpe.toFixed(3)}</Td>
              </tr>
            ))}
          </Table>
          <p className="mt-2 text-xs text-[#64748B]">
            Accuracy {pct(a.accuracy)} (90%: {pct(a.accuracy_90[0])}–{pct(a.accuracy_90[1])}); top-6 picks correct {pct(a.top6_accuracy)}. More features did not help: large-cap NIFTY returns are close to unpredictable at this horizon after costs.
          </p>
        </Card>
        <Card title="B · Will the stock be more volatile than the median?" right={<Badge tone="up">{b.verdict}</Badge>}>
          <Table head={["Predictor", "Accuracy", "AUC"]} minWidth={360}>
            <tr>
              <Td>Combined model</Td>
              <Td className="tabular-nums text-[#22C55E]">{pct(b.accuracy)}</Td>
              <Td className="tabular-nums">{b.auc.toFixed(3)}</Td>
            </tr>
            <tr>
              <Td>Naive: last 20-day volatility</Td>
              <Td className="tabular-nums">{pct(b.persistence_accuracy)}</Td>
              <Td className="tabular-nums">{b.persistence_auc.toFixed(3)}</Td>
            </tr>
          </Table>
          <p className="mt-2 text-xs text-[#64748B]">
            Practical test: holding the predicted calm half gave {signed(b.low_vol_half.annualized_net)} a year at {pct(b.low_vol_half.annualized_vol)} volatility vs {signed(b.all_stocks.annualized_net)} at{" "}
            {pct(b.all_stocks.annualized_vol)} for all stocks. Accurate per stock, but it did not lower portfolio risk by itself; its use is position sizing, which needs its own test.
          </p>
        </Card>
      </div>
    </>
  );
}
