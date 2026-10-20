"""Buy NIFTY after risk-off days, per services/quant/docs/risk-off-nifty-protocol.md.

    python -m quant_agents.research.risk_off_nifty
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np

from quant_agents.research import agent_tuning as at
from quant_agents.research import exit_rules as er

IN_SAMPLE = (date(2024, 4, 1), date(2025, 12, 31))
TEST = (date(2026, 1, 1), date(2026, 10, 5))
NOTIONAL = 100_000.0
SLIP = 0.0002


def etf_costs(buy: float, sell: float) -> float:
    exchange = (buy + sell) * 0.0000307
    sebi = (buy + sell) * 10 / 1e7
    return sell * 0.00001 + buy * 0.00015 + exchange + sebi + 0.18 * (exchange + sebi) + 15.34


def stock_costs(buy: float, sell: float) -> float:
    exchange = (buy + sell) * 0.0000307
    sebi = (buy + sell) * 10 / 1e7
    return (buy + sell) * 0.001 + buy * 0.00015 + exchange + sebi + 0.18 * (exchange + sebi) + 15.34


def risk_off_days() -> tuple[list[date], np.ndarray, np.ndarray, np.ndarray]:
    nifty, vix = at.load("NIFTY50", "1d"), at.load("INDIAVIX", "1d")
    vix_ret = dict(zip(vix["sessions"].tolist(), vix["return_1"].tolist()))
    days = [date.fromordinal(int(d)) for d in nifty["sessions"]]
    flag = np.array([bool(nifty["ema_12"][k] < nifty["ema_26"][k] and vix_ret.get(int(nifty["sessions"][k]), np.nan) > 0) for k in range(len(days))])
    return days, flag, nifty["open"], nifty["close"]


def trades(variant: str, period: tuple[date, date], days, flag, opens, closes, *, costs=etf_costs) -> list[float]:  # type: ignore[no-untyped-def]
    out = []
    for k in range(len(days) - 1):
        if not (period[0] <= days[k] <= period[1]) or not flag[k]:
            continue
        buy_raw = closes[k] if variant == "A" else opens[k + 1]
        sell_raw = closes[k + 1]
        buy, sell = buy_raw * (1 + SLIP), sell_raw * (1 - SLIP)
        units = NOTIONAL / buy
        net = (sell - buy) * units - costs(NOTIONAL, sell * units)
        out.append(net / NOTIONAL)
    return out


def summary(returns: list[float], quantile: float = 0.05) -> dict[str, object]:
    arr = np.array(returns)
    if len(arr) == 0:
        return {"trades": 0}
    rng = np.random.default_rng(0)
    boot = [rng.choice(arr, len(arr), replace=True).mean() for _ in range(2000)]
    return {
        "trades": int(len(arr)),
        "win_rate": float((arr > 0).mean()),
        "mean_net_bp": float(arr.mean() * 10_000),
        "total_net_rupees": float(arr.sum() * NOTIONAL),
        "mean_low_bp": float(np.quantile(boot, quantile) * 10_000),
    }


def run() -> dict[str, object]:
    days, flag, opens, closes = risk_off_days()
    report: dict[str, object] = {"protocol": "services/quant/docs/risk-off-nifty-protocol.md", "variants": {}}
    for variant in ("A", "B"):
        test = summary(trades(variant, TEST, days, flag, opens, closes))
        works = bool(test["trades"] >= 15 and test["mean_net_bp"] > 0 and test["mean_low_bp"] > 0)
        report["variants"][variant] = {  # type: ignore[index]
            "in_sample": summary(trades(variant, IN_SAMPLE, days, flag, opens, closes)),
            "test": test,
            "test_stock_like_costs": summary(trades(variant, TEST, days, flag, opens, closes, costs=stock_costs)),
            "works": works,
        }
    in_test = [k for k in range(len(days) - 1) if TEST[0] <= days[k] <= TEST[1]]
    other = [closes[k + 1] / closes[k] - 1 for k in in_test if not flag[k]]
    first, last = in_test[0], in_test[-1] + 1
    report["comparison"] = {
        "buy_and_hold_test_pct": float((closes[last] / closes[first] - 1) * 100),
        "non_risk_off_next_day_bp": float(np.mean(other) * 10_000),
        "risk_off_share_test": float(np.mean([flag[k] for k in in_test])),
    }
    return report


def main() -> None:
    out = er.ROOT / "services/quant/docs/results/risk-off-nifty-result.json"
    report = run()
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
