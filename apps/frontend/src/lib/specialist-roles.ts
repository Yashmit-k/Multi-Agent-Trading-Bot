// Each agent's job when Settings → "How agent buys are decided" is "Specialists" (core_decision/specialists.py).
export const ROLE: Record<string, string> = {
  technical: "Trigger: proposes a swing buy when its score is +0.30 or more (confidence 0.40+)",
  momentum: "Trigger: proposes a swing buy when its score is +0.30 or more (confidence 0.40+)",
  volume: "Confirm: blocks a buy on heavy selling (score −0.30 or lower)",
  mean_reversion: "Not overstretched: blocks a buy above the upper band (score −0.50 or lower)",
  news: "Event check: blocks a buy on bad news (score −0.30 or lower, confidence 0.30+); keyword-fallback opinions are ignored",
  earnings: "Event check: blocks a buy on bad results (score −0.30 or lower, confidence 0.30+); keyword-fallback opinions are ignored",
  fundamental: "Quality check: blocks a buy only together with valuation (both −0.50 or lower)",
  valuation: "Quality check: blocks a buy only together with fundamental (both −0.50 or lower)",
  regime: "Market: halves the size of a buy when NIFTY is in a downtrend and India VIX is rising; never blocks",
  ml: "No role: not loaded",
};
