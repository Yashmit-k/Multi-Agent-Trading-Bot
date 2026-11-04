"""Momentum live: the paper-trial book with the live order limits, side by side (momentum-gap-check.md).

The same book as the trial (₹1,00,000 once, 10 stocks, equal split, leftover filled, all charges), with buys and sells
as limit orders 1.5% or 3% from the decision close. Missed buys keep their cash; missed sells keep the stock a month.
"At the open" fills only if the opening price is within the limit; "during the day" also fills at the limit if the day's
range reached it. The live orders (cancelled at 10:30) fall between the two.

    python -m quant_agents.research.momentum_band_compare
"""

from __future__ import annotations

import json
from datetime import date

from quant_agents.research import exit_rules as er
from quant_agents.research import momentum_compound as mc
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load

OUT = er.ROOT / "services/quant/docs/results/momentum-band-compare.json"
VARIANTS = {
    "backtest (every order at the open)": (None, False),
    "1.5%, at the open": (0.015, False),
    "1.5%, during the day": (0.015, True),
    "3%, at the open": (0.03, False),
    "3%, during the day": (0.03, True),
}
PERIODS = {"2016-02 to 2026-10": (date(2016, 2, 1), None), "2016-20": (date(2016, 2, 1), date(2020, 12, 31)),
           "2021-23": (date(2021, 1, 1), date(2023, 12, 31)), "2024-26": (date(2024, 1, 1), None)}


def main() -> None:
    m = wm.Market(load())
    report: dict[str, dict[str, dict[str, float]]] = {}
    for period, (start, end) in PERIODS.items():
        report[period] = {}
        for name, (band, intraday) in VARIANTS.items():
            sim = mc.simulate(m, start=start, end=end, fill_leftover=True, band=band, intraday=intraday)
            s = mc.summary(m, sim)
            buys = sum(1 for tr in sim["trades"] if tr["side"] == "BUY" and tr.get("note") != "leftover")
            sells = sum(1 for tr in sim["trades"] if tr["side"] == "SELL")
            report[period][name] = {"final": s["final_value"], "cagr": s["cagr"], "max_drawdown": s["max_drawdown"], "charges": s["charges"],
                                    "buys": buys, "sells": sells, "missed_buys": sim["missed"]["BUY"], "missed_sells": sim["missed"]["SELL"]}
            r = report[period][name]
            print(f"{period:20} {name:36} ₹{r['final']:>11,.0f} {r['cagr']:6.1%} dd {r['max_drawdown']:4.0%} missed buys {r['missed_buys']:3}/{r['buys'] + r['missed_buys']:<4} sells {r['missed_sells']:3}/{r['sells'] + r['missed_sells']:<4} charges ₹{r['charges']:,.0f}", flush=True)
    OUT.write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
