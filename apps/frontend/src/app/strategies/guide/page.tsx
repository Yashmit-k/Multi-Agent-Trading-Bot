import Link from "next/link";
import { PageFrame } from "@/components/shell/PageFrame";

export const metadata = { title: "Strategy Lab guide · StockX" };

const SECTIONS: ReadonlyArray<{ id: string; title: string; body: string[] }> = [
  {
    id: "conditions",
    title: "Entry and exit conditions",
    body: [
      "A strategy buys when its entry rule is true. The rule is a list of conditions combined with AND (all must hold) or OR (any may hold); groups can be nested. Each condition compares two values, such as RSI below 30 or the close above an EMA.",
      "Rules are read on a bar that has just completed, never on one still forming, so the backtest cannot peek at the future. The order itself is placed afterwards and fills on a later bar.",
      "An exit rule is optional. When it turns true the position is sold at the next bar's open. Without one, a position leaves through its stop, targets, trailing stop or time limit.",
    ],
  },
  {
    id: "stop-and-targets",
    title: "Stop loss and targets",
    body: [
      "The stop is the price where a losing position is sold. It can be a percentage, a multiple of ATR, or a level such as a recent swing low. You can add a small extra buffer.",
      "Percent and ATR stops, and percent, ATR and R-multiple targets, are measured from the price actually paid for the shares (the fill price), not from the signal price. A 10% stop therefore means 10% of the money spent. Fixed levels, such as a swing low, stay where they are.",
      "A strategy may have up to three targets. Each one sells a share of the position (for example 50% at +5%); the remainder leaves through the stop, trailing stop, time limit or exit rule. You can move the stop to breakeven after the first target is hit.",
    ],
  },
  {
    id: "level-target",
    title: "The \"level\" target",
    body: [
      "A level target sells at a price taken from an indicator, such as the 20-day EMA, optionally plus a percentage above it. The level is read once, at the signal, and then frozen: it does not move while the trade is open.",
    ],
  },
  {
    id: "add-on",
    title: "The add-on (second tranche)",
    body: [
      "An add-on buys more of the same stock once, when its own rule becomes true, as long as no target has been hit yet. You choose the rupee amount to add.",
      "The extra shares can sell at the last target or at a target of their own. By default the stop is recalculated from the average price of both buys.",
    ],
  },
  {
    id: "time-stop",
    title: "Time stop (max_hold_bars)",
    body: [
      "Max hold is the number of bars a position may stay open. On daily bars that means trading days. When the limit is reached the position is sold, even if neither stop nor target was hit. Leave it empty for no time limit.",
    ],
  },
  {
    id: "entry-limit",
    title: "How entry orders fill",
    body: [
      "Entries are limit orders at the signal bar's close plus 0.25%. On the next bar the order fills at the open if the stock opens at or below that price; otherwise it fills at the limit if the bar trades down to it.",
      "With daily bars the order lives for the next session only. A stock that gaps up past the limit, or never trades down to it, is simply not bought. Because of this, real fills can differ from a plain buy-at-the-close assumption.",
    ],
  },
  {
    id: "modes",
    title: "Strategy modes",
    body: [
      "replace: the agents stop opening new positions, and the strategy opens them instead.",
      "alongside: the strategy and the agents both open positions, sharing the same cash and limits.",
      "agents_agree: only the strategy opens positions, and only when the agents' combined view of that stock is not bearish; the portfolio manager then reviews each entry.",
      "The mode is chosen in Settings. Your limits (per-order cap, entries per day, positions, sector and exposure) apply in every mode.",
    ],
  },
  {
    id: "paper-only",
    title: "Paper trading only",
    body: [
      "Applying a strategy only affects the paper account. No order is sent to a broker, and you can stop applying it at any time. Backtests use past data and charges, so they look better than live results usually do.",
    ],
  },
];

export default function StrategyGuidePage() {
  return (
    <PageFrame title="How the Strategy Lab works" description="A plain-language guide to the rules, exits and fills behind a Lab strategy.">
      <Link prefetch={false} href="/strategies" className="inline-block text-sm text-[#93C5FD] hover:underline">
        ← Back to the Strategy Lab
      </Link>
      <div className="space-y-3">
        {SECTIONS.map((section) => (
          <section key={section.id} id={section.id} className="rounded-[12px] border border-[#26303C] bg-[#121922] p-4">
            <h2 className="mb-2 text-lg font-semibold text-[#E6EDF3]">{section.title}</h2>
            <div className="space-y-2 text-sm text-[#94A3B8]">
              {section.body.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>
          </section>
        ))}
      </div>
    </PageFrame>
  );
}
