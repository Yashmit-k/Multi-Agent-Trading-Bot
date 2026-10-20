"""Exploratory stop/target grid on the selective-intraday entry (see intraday-exits-exploration-protocol.md).

    python -m quant_agents.research.intraday_exits_explore
"""

from __future__ import annotations

import json

from quant_agents.research import agent_tuning as at
from quant_agents.research import exit_rules as er
from quant_agents.research import intraday_selective as sel

STOPS = (0.01, 0.015, 0.02, 0.03)
TARGETS = (None, 0.005, 0.01, 0.015, 0.02)
ENTRY = {"threshold": 0.8, "hold": None, "selection": "top1"}


def run() -> dict[str, object]:
    panel = at.build_panel("5m")
    signal, confidence = at.fused(panel, sel.CONFIGS, sel.WEIGHTS, old_rule=False)

    def sim(period, stop, target):  # type: ignore[no-untyped-def]
        return sel.simulate(panel, signal, confidence, period, ENTRY["threshold"], ENTRY["hold"], ENTRY["selection"], stop_pct=stop, target_pct=target)

    grid = []
    for stop in STOPS:
        for target in TARGETS:
            train = sim(at.TRAIN, stop, target)
            grid.append({"stop": stop, "target": target, "train": train})
            print("train stop", stop, "target", target, train["trades"], round(train["net_per_trade"], 1), round(train["total_net"]), flush=True)
    best = max(grid, key=lambda item: item["train"]["mean_session_net"])
    validate = sim(at.VALIDATE, best["stop"], best["target"])
    seen = sim(at.TEST, best["stop"], best["target"])
    worth = bool(best["train"]["total_net"] > 0 and validate["total_net"] > 0)
    report = {
        "protocol": "services/quant/docs/intraday-exits-exploration-protocol.md",
        "exploratory": True,
        "entry": ENTRY,
        "grid": grid,
        "best": {"stop": best["stop"], "target": best["target"]},
        "train": best["train"],
        "validate": validate,
        "already_seen_2026": seen,
        "worth_a_fresh_test": worth,
    }
    print("best", report["best"], "validate", round(validate["total_net"]), "2026 (seen)", round(seen["total_net"]), "worth a fresh test", worth, flush=True)
    return report


def main() -> None:
    out = er.ROOT / "services/quant/docs/results/intraday-exits-exploration.json"
    out.write_text(json.dumps(run(), indent=2, default=str))


if __name__ == "__main__":
    main()
