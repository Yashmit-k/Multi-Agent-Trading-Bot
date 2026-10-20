// Every scored study, newest first. Each entry mirrors its committed result doc in
// services/quant/docs; the test next to this file checks that every linked doc exists.

export type Outcome = "edge" | "no_edge" | "mixed";

export type Finding = {
  slug: string;
  title: string;
  date: string;
  question: string;
  outcome: Outcome;
  verdict: string;
  numbers: string[];
  consequence: string;
  protocol: string | null;
  result: string;
  exploratory?: boolean;
};

export const REPO_DOCS = "https://github.com/Yashmit-k/Multi-Agent-Trading-Bot/blob/main/services/quant/docs";

export const FINDINGS: Finding[] = [
  {
    slug: "risk-off-nifty",
    title: "Buy NIFTY after risk-off days",
    date: "2026-10-20",
    question: "The tuning study found stocks rose more on days after risk-off days. Does buying the index (an ETF) after them pay on 2026?",
    outcome: "no_edge",
    verdict: "Neither variant works on the 2026 test period.",
    numbers: [
      "Close → next close: 51 trades, −8.0 bp per trade, −₹4,073; lower bound −34.4 bp",
      "Next open → close: −7.2 bp per trade, −₹3,692",
      "In-sample the effect was only +7.2 bp per trade, with a lower bound below zero",
    ],
    consequence: "No ETF strategy added. The regime filter stays off for swing buys and on for intraday.",
    protocol: "risk-off-nifty-protocol.md",
    result: "risk-off-nifty-result.md",
  },
  {
    slug: "intraday-exits",
    title: "Intraday stop/target grid",
    date: "2026-10-20",
    question: "Do different stop and target levels make the selective intraday entry profitable?",
    outcome: "no_edge",
    exploratory: true,
    verdict: "No stop/target pair is profitable; all 20 settings lose on train, and targets make it worse.",
    numbers: ["Best setting (3% stop, no target): −₹34.6 per trade on train", "Validate −₹1.01 lakh, 2026 −₹1.53 lakh"],
    consequence: "Intraday auto-entries stay off.",
    protocol: "intraday-exits-exploration-protocol.md",
    result: "intraday-exits-exploration-result.md",
  },
  {
    slug: "intraday-selective",
    title: "Selective intraday trading",
    date: "2026-10-20",
    question: "Does trading only the strongest validated intraday signals, fewer times a day, cover costs?",
    outcome: "no_edge",
    verdict: "Does not work: all 18 settings lose on train, and the chosen one loses on validation and test.",
    numbers: ["Train: −₹35 to −₹40 per trade across settings", "Chosen setting: 5,598 train trades, 39% win rate, −₹1.99 lakh"],
    consequence: "Intraday auto-entries stay off.",
    protocol: "intraday-selective-protocol.md",
    result: "intraday-selective-result.md",
  },
  {
    slug: "agent-tuning",
    title: "Quant-agent backtest and tuning",
    date: "2026-10-20",
    question: "Do the live quant agents predict next-period returns, and can tuning on train make them work?",
    outcome: "mixed",
    verdict: "Swing: no agent keeps a validated edge. Intraday: a small real edge survives to 2026 but is far too small for costs.",
    numbers: [
      "Swing 1.3.0 on 2026: IC −0.026, 605 trades, −₹82,430; momentum and volume were backwards",
      "Intraday fused IC +0.011 (90% low +0.0065) on 2026, but −₹4.72 lakh over 10,618 trades",
    ],
    consequence: "Applied as agents 1.4.0: swing quant weights 0, intraday weights from the study, swing regime filter removed.",
    protocol: "agent-tuning-protocol.md",
    result: "agent-tuning-result.md",
  },
  {
    slug: "structure-breaks",
    title: "Market-structure breaks with two targets",
    date: "2026-10-20",
    question: "Does a 5-minute break of structure with a 1-hour trend filter, entered on the retest, pay with two targets?",
    outcome: "no_edge",
    verdict: "No variant is profitable; all lose about 0.22% per trade in both halves.",
    numbers: ["TP1 1R / TP2 2R: 18,880 trades, −₹7.89 lakh, profit factor 0.36", "Retest fills reach TP1 first 42% of the time, against 50% for a random walk"],
    consequence: "Nothing changes in paper trading.",
    protocol: "structure-breaks-protocol.md",
    result: "structure-breaks-result.md",
  },
  {
    slug: "order-blocks",
    title: "Multi-timeframe order blocks",
    date: "2026-10-19",
    question: "Does buying a return to a higher-timeframe bullish order block, refined on a lower timeframe, pay at 2R?",
    outcome: "no_edge",
    verdict: "Neither book is profitable; the lower-timeframe refinement lowers the win rate.",
    numbers: ["Daily zone, 15m entry: 137 trades, 24% win rate, −1.19 R per trade", "1h zone, 5m entry: 541 trades, 24% win rate, −₹21,323"],
    consequence: "Nothing changes in paper trading.",
    protocol: "order-blocks-protocol.md",
    result: "order-blocks-result.md",
  },
  {
    slug: "exit-rules",
    title: "Exit rules",
    date: "2026-10-15",
    question: "Does a volatility-scaled stop, a max hold, or a 15:15 square-off beat the live −2% / +4% exits?",
    outcome: "no_edge",
    verdict: "No exit rule beats the live one, and no rule is profitable.",
    numbers: ["Intraday live: 20,706 trades, −0.40% per trade", "Swing live: 2,418 trades, −0.54% per trade"],
    consequence: "Live exits unchanged.",
    protocol: "exit-rules-protocol.md",
    result: "exit-rules-result.md",
  },
  {
    slug: "risk-sizing",
    title: "Risk-based sizing",
    date: "2026-10-15",
    question: "Does sizing by the model's predicted volatility improve any book?",
    outcome: "no_edge",
    verdict: "Risk sizing does not help any book, and no book is profitable.",
    numbers: ["Momentum top 6: −4.7% a year equal-weighted, −5.1% risk-weighted", "Weights barely move: probabilities mostly 0.3–0.7"],
    consequence: "Paper engine keeps equal ₹20,000 sizing.",
    protocol: "risk-sizing-protocol.md",
    result: "risk-sizing-result.md",
  },
  {
    slug: "ml-combined",
    title: "Combined ML model: return and risk targets",
    date: "2026-10-15",
    question: "Across every hypothesis family, does one model predict returns or risk?",
    outcome: "mixed",
    verdict: "No robust return edge across 48 tracked trials. A robust risk edge: about 63% accuracy on next-period volatility.",
    numbers: ["Volatility direction: 62.7% accuracy against 59.3% for the naive rule"],
    consequence: "The risk edge was tested for sizing (see risk-based sizing) and did not help.",
    protocol: "ml-combined-protocol.md",
    result: "ml-combined-result.md",
  },
  {
    slug: "ml-ensemble",
    title: "Multi-algorithm ensemble",
    date: "2026-10-15",
    question: "Does any of 45 model, horizon and market-condition variants make money after costs?",
    outcome: "no_edge",
    verdict: "No robust edge: the best of 45 is what chance alone would produce (White's Reality Check p = 0.76).",
    numbers: ["4 of 45 variants made money; the best earned +6.4% a year", "Best variant against the basket: p = 0.22"],
    consequence: "Nothing is traded.",
    protocol: "ml-ensemble-protocol.md",
    result: "ml-ensemble-result.md",
  },
  {
    slug: "ml-rank",
    title: "Single-model stock ranker",
    date: "2026-10-15",
    question: "Does a walk-forward model that buys the top 6 of 49 stocks for 5 sessions beat the basket on 2026?",
    outcome: "no_edge",
    verdict: "Not accepted: a selection signal, but it fails the statistical gate and loses money in absolute terms after costs.",
    numbers: ["2026: −0.41% net per 5-session window, against −0.62% for the basket", "Excess +0.21% per window, but the 90% interval includes zero"],
    consequence: "MlAgent stays unloaded.",
    protocol: "ml-rank-protocol.md",
    result: "ml-rank-result.md",
  },
  {
    slug: "daily-rules",
    title: "Simple daily rules",
    date: "2026-10-13",
    question: "Do 20-day momentum, 12-1 momentum or low volatility beat equal-weight buy-and-hold after delivery costs (2024–2025)?",
    outcome: "mixed",
    verdict: "Only 20-day momentum at 5 sessions passed; the other five rule-horizon pairs did not.",
    numbers: ["momentum_20, 5 sessions: +0.10% excess per window, lower bound +0.004%", "Absolute return only +0.03% per window; on 2026 the same rule lost −0.89% per window (ML ranker study)"],
    consequence: "Kept as the benchmark that later studies had to beat; not traded.",
    protocol: "daily-rules-protocol.md",
    result: "daily-rules-result.md",
  },
  {
    slug: "timesfm",
    title: "TimesFM-3 zero-shot forecast",
    date: "2026-10-13",
    question: "Does a pretrained time-series foundation model forecast the next close better than the last close (2024)?",
    outcome: "no_edge",
    verdict: "No: a 50.4% sign hit rate, and a larger price error than simply repeating the last close.",
    numbers: ["10,633 scored rows; mean absolute error ₹26.9 against ₹25.8 for last close"],
    consequence: "No fine-tuning and no paper signal.",
    protocol: "timesfm3-protocol.md",
    result: "timesfm3-2024-report.md",
  },
];
