"use client";

import { FUNDAMENTAL_AGENTS } from "@/contracts/generated/vocab";

type Signal = {
  agent_name: string;
  horizon: string;
  signal: number;
  confidence: number;
  symbol?: string;
};

export function HorizonSplit({ signals }: { signals: Signal[] }) {
  const warnings = signals.filter(
    (item) => FUNDAMENTAL_AGENTS.includes(item.agent_name as (typeof FUNDAMENTAL_AGENTS)[number]) && item.horizon === "INTRADAY",
  );
  const intra = signals.filter((item) => item.horizon === "INTRADAY");
  const swing = signals.filter((item) => item.horizon === "SWING");
  return (
    <div className="grid md:grid-cols-2 gap-4">
      {warnings.length > 0 ? (
        <p data-testid="horizon-warning" className="md:col-span-2 text-amber-700">
          Contract warning: fundamental/valuation/earnings signal tagged INTRADAY. Horizon was not changed.
        </p>
      ) : null}
      <section>
        <h3 className="font-semibold">INTRADAY</h3>
        <ul>
          {intra.map((item, index) => (
            <li key={index}>
              {item.agent_name} {item.signal} ({item.confidence})
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className="font-semibold">SWING</h3>
        <ul>
          {swing.map((item, index) => (
            <li key={index}>
              {item.agent_name} {item.signal} ({item.confidence})
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
