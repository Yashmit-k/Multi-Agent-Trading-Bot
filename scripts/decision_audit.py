"""Decision-engine audit: what happened to every agent proposal, and what the stock did next.

Question (from our mentor): "The rule-based agents compute correctly; is the DECISION step the problem?"
This script answers with numbers. For every agent proposal (strategy_id ``paper-fusion``) since --since it
records the fused signal, the agents that supported it, the portfolio manager's verdict, the risk result
(and which checks failed), whether the order filled, and the stock's return 1 and 5 sessions later. The
return is recorded for EVERY proposal, rejected and vetoed ones included: that is the counterfactual.

Reads only the public read-only API of the live site (GET requests, no token, no writes)::

    /api/v1/trace?event_type=decision.created|risk.approved|risk.rejected|review.completed&limit=1000
    /api/v1/orders, /api/v1/trades, /api/v1/agents/scorecard
    /api/v1/market/candles/{symbol}?timeframe=1d&last=60
    /api/v1/signals/{symbol}   (only to name the agents behind each supporting signal id)

Each URL is fetched once and cached under --cache; --refresh fetches again. Writes docs/decision-audit.md and
docs/decision-audit.json. Usage::

    python scripts/decision_audit.py --api https://13-238-176-73.sslip.io

Return rule (no look-ahead): the base is the proposal's entry price, the price the decision saw. The k-session
return uses the close of the k-th NSE daily bar whose IST session date is AFTER the decision's session date;
nothing from the decision's own session after the decision bar is used. Missing later bars give no return.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
AGENT_STRATEGY = "paper-fusion"
HORIZONS = (1, 5)
THRESHOLDS = (0.25, 0.35, 0.45)
LIVE_THRESHOLD = 0.35
NEUTRAL_BELOW = 0.05  # an agent signal smaller than this supports neither side (the scorecard's rule)
# Risk checks that limit how much the book holds or trades, without judging the trade itself.
CAPACITY_CHECKS = ("max_open_positions", "daily_entry_cap", "exposure_cap", "per_stock_cap", "sector_concentration", "notional_cap")
EVENT_TYPES = ("decision.created", "risk.approved", "risk.rejected", "review.completed")


# --- fetching ----------------------------------------------------------------------------------------


class CachedApi:
    """GET-only JSON client. Every path is fetched at most once and kept on disk."""

    def __init__(self, base: str, cache: Path, *, refresh: bool = False) -> None:
        self.base = base.rstrip("/")
        self.cache = cache
        self.refresh = refresh
        cache.mkdir(parents=True, exist_ok=True)

    def get(self, path: str) -> object:
        name = hashlib.sha256(path.encode()).hexdigest()[:24] + ".json"
        file = self.cache / name
        if file.is_file() and not self.refresh:
            return json.loads(file.read_text(encoding="utf-8"))
        request = urllib.request.Request(self.base + path, headers={"Accept": "application/json", "User-Agent": "stockx-decision-audit"})
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
        file.write_bytes(body)
        return json.loads(body)


def fetch_all(api: CachedApi) -> dict[str, object]:
    payloads: dict[str, object] = {}
    for event_type in EVENT_TYPES:
        # The trace route caps limit at 1000; the response says how many came back.
        payloads[event_type] = api.get(f"/api/v1/trace?{urllib.parse.urlencode({'event_type': event_type, 'limit': 1000})}")
    payloads["orders"] = api.get("/api/v1/orders")
    payloads["trades"] = api.get("/api/v1/trades")
    payloads["scorecard"] = api.get("/api/v1/agents/scorecard")
    return payloads


# --- pure helpers (unit-tested) -----------------------------------------------------------------------


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def session_date(value: str) -> date:
    """IST calendar date of a timestamp: the NSE session it belongs to."""
    return _parse_ts(value).astimezone(IST).date()


def forward_returns(candles: list[dict], decision_ts: str, base_price: float, horizons: tuple[int, ...] = HORIZONS) -> dict[int, float | None]:
    """Return after k sessions from base_price, using only daily closes of sessions after the decision's session."""
    decided = session_date(decision_ts)
    later = sorted((session_date(bar["start"]), float(bar["close"])) for bar in candles if session_date(bar["start"]) > decided)
    out: dict[int, float | None] = {}
    for k in horizons:
        out[k] = (later[k - 1][1] / base_price - 1) if len(later) >= k and base_price > 0 else None
    return out


def _events(payload: object) -> list[dict]:
    return list(payload.get("events", [])) if isinstance(payload, dict) else []


def build_records(payloads: dict[str, object], candles: dict[str, list[dict]], signals: dict[str, list[dict]], *, since: date) -> list[dict]:
    """One record per agent proposal on or after `since`, joined to its review, risk result, order and returns."""
    reviews = {e["payload"]["proposal_id"]: e["payload"] for e in _events(payloads["review.completed"]) if e["payload"].get("proposal_id")}
    risk: dict[str, dict] = {}
    for event_type in ("risk.approved", "risk.rejected"):
        for event in _events(payloads[event_type]):
            risk[event["payload"]["proposal_id"]] = event["payload"]
    orders: dict[str, list[dict]] = defaultdict(list)
    for order in payloads["orders"] if isinstance(payloads["orders"], list) else []:
        orders[order.get("proposal_id") or ""].append(order)
    agent_of = {item["signal_id"]: item for rows in signals.values() for item in rows}

    records = []
    for event in _events(payloads["decision.created"]):
        proposal = event["payload"]
        if proposal.get("strategy_id") != AGENT_STRATEGY or session_date(proposal["timestamp"]) < since:
            continue
        pid, side = proposal["proposal_id"], proposal["side"]
        direction = 1 if side == "BUY" else -1
        voters = [agent_of[sid] for sid in proposal.get("supporting_signal_ids", []) if sid in agent_of]
        supporters = sorted({v["agent_name"] for v in voters if v["signal"] * direction >= NEUTRAL_BELOW})
        review = reviews.get(pid)
        decision = risk.get(pid)
        failed = [c["name"] for c in (decision or {}).get("checks", []) if not c.get("passed")]
        own_orders = orders.get(pid, [])
        filled = any(order.get("status") == "FILLED" for order in own_orders)
        approved_qty = (decision or {}).get("approved_quantity")
        reduced = bool(review and review.get("verdict") == "REDUCE") or (approved_qty is not None and approved_qty < proposal["quantity"])
        returns = forward_returns(candles.get(proposal["symbol"], []), proposal["timestamp"], float(proposal["entry_price"]))
        records.append(
            {
                "proposal_id": pid,
                "symbol": proposal["symbol"],
                "side": side,
                "horizon": proposal.get("horizon"),
                "decision_bar": proposal["timestamp"],
                "fused_signal": proposal.get("aggregated_signal"),
                "fused_confidence": proposal.get("aggregated_confidence"),
                "entry_price": float(proposal["entry_price"]),
                "voters": sorted(v["agent_name"] for v in voters),
                "supporting_agents": supporters,
                "manager_verdict": None if review is None else review.get("verdict"),
                "risk_status": None if decision is None else decision.get("status"),
                "failed_checks": failed,
                "reduced": reduced,
                "filled": filled,
                "paths": outcome_paths(decision, failed, reduced, filled),
                **{f"return_{k}s": returns[k] for k in HORIZONS},
            }
        )
    return sorted(records, key=lambda item: item["decision_bar"])


def outcome_paths(decision: dict | None, failed: list[str], reduced: bool, filled: bool) -> list[str]:
    """Every outcome bucket a proposal belongs to. A proposal failing two checks is counted under both."""
    if decision is None:
        return ["no risk decision"]
    if decision.get("status") == "APPROVED":
        paths = ["approved and filled" if filled else "approved, not filled"]
        return paths + (["reduced (manager or risk)"] if reduced else [])
    labels = ["vetoed by the manager" if name == "portfolio_manager" else f"rejected: {name}" for name in failed]
    return labels or ["rejected: (no failed check recorded)"]


def _stats(rows: list[dict]) -> dict[str, object]:
    out: dict[str, object] = {"count": len(rows)}
    for k in HORIZONS:
        values = [row[f"return_{k}s"] for row in rows if row[f"return_{k}s"] is not None]
        out[f"n_{k}s"] = len(values)
        out[f"mean_{k}s"] = statistics.fmean(values) if values else None
        out[f"up_share_{k}s"] = (sum(1 for value in values if value > 0) / len(values)) if values else None
    return out


def summarize(records: list[dict]) -> dict[str, object]:
    buys = [row for row in records if row["side"] == "BUY"]
    by_path: dict[str, list[dict]] = defaultdict(list)
    for row in buys:
        for path in row["paths"]:
            by_path[path].append(row)
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for row in buys:
        for agent in row["supporting_agents"]:
            by_agent[agent].append(row)
    approved = [row for row in buys if row["risk_status"] == "APPROVED"]
    rejected = [row for row in buys if row["risk_status"] == "REJECTED"]
    return {
        "proposals": len(records),
        "buys": len(buys),
        "sells": len(records) - len(buys),
        "all_buys": _stats(buys),
        "approved_buys": _stats(approved),
        "rejected_buys": _stats(rejected),
        "capacity_rejections": _stats([row for row in rejected if row["failed_checks"] and set(row["failed_checks"]) <= set(CAPACITY_CHECKS)]),
        "sells_stats": _stats([row for row in records if row["side"] == "SELL"]),
        "by_path": {path: _stats(rows) for path, rows in sorted(by_path.items(), key=lambda item: -len(item[1]))},
        "by_agent": {agent: _stats(rows) for agent, rows in sorted(by_agent.items())},
        "by_threshold": {f"{t:.2f}": _stats([row for row in buys if (row["fused_signal"] or 0) >= t]) for t in THRESHOLDS},
    }


# --- report -------------------------------------------------------------------------------------------


def _pct(value: object) -> str:
    return "n/a" if value is None else f"{float(value) * 100:+.2f}%"


def _share(value: object) -> str:
    return "n/a" if value is None else f"{float(value) * 100:.0f}%"


def _row(label: str, stats: dict) -> str:
    return (
        f"| {label} | {stats['count']} | {_pct(stats['mean_1s'])} ({stats['n_1s']}) | {_share(stats['up_share_1s'])} "
        f"| {_pct(stats['mean_5s'])} ({stats['n_5s']}) | {_share(stats['up_share_5s'])} |"
    )


HEADER = "| | Proposals | Mean 1-session return (n) | Up after 1 | Mean 5-session return (n) | Up after 5 |\n|---|---:|---:|---:|---:|---:|"


def answer(summary: dict) -> list[str]:
    """Plain-English reading of the numbers. Sentences are chosen from the data, then the caveat always follows."""
    approved, rejected = summary["approved_buys"], summary["rejected_buys"]
    lines = []
    a1, r1 = approved["mean_1s"], rejected["mean_1s"]
    if a1 is not None and r1 is not None:
        better = "approved" if a1 > r1 else "rejected"
        lines.append(
            f"After one session, the BUYs risk approved moved {_pct(a1)} on average and the ones it rejected {_pct(r1)}: "
            f"the {better} group did better, so on this sample the filters {'kept the better trades' if better == 'approved' else 'removed trades that would have done better'}."
        )
    capacity = summary["capacity_rejections"]
    if rejected["count"]:
        lines.append(
            f"{capacity['count']} of the {rejected['count']} rejected BUYs failed only capacity limits ({', '.join(CAPACITY_CHECKS)}): those checks "
            "say the book was full, not that the trade was bad, so their returns mostly reflect which day the proposals came on."
        )
    vetoed = summary["by_path"].get("vetoed by the manager")
    if vetoed and vetoed["mean_1s"] is not None:
        lines.append(
            f"The portfolio manager vetoed {vetoed['count']} BUYs; after one session they were up {_share(vetoed['up_share_1s'])} of the time "
            f"(mean {_pct(vetoed['mean_1s'])})."
        )
    a5, r5 = approved["mean_5s"], rejected["mean_5s"]
    if a5 is not None and r5 is not None:
        lines.append(f"After five sessions: approved {_pct(a5)} (n={approved['n_5s']}), rejected {_pct(r5)} (n={rejected['n_5s']}).")
    elif summary["all_buys"]["n_5s"] == 0:
        lines.append("No proposal is five sessions old yet, so the 5-session columns are empty; rerun with --refresh once they are.")
    every = summary["all_buys"]
    if every["mean_1s"] is not None:
        lines.append(
            f"Across all {every['count']} agent BUY proposals, the stock was up after one session {_share(every['up_share_1s'])} of the time "
            f"(mean {_pct(every['mean_1s'])}). That is the quality of what the agents and the fusion step proposed, before any filter."
        )
    live, strict = summary["by_threshold"][f"{LIVE_THRESHOLD:.2f}"], summary["by_threshold"]["0.45"]
    if live["mean_1s"] is not None and strict["mean_1s"] is not None:
        lines.append(
            f"Raising the BUY bar from 0.35 to 0.45 would keep {strict['count']} of {live['count']} proposals; their mean 1-session return is "
            f"{_pct(strict['mean_1s'])} against {_pct(live['mean_1s'])}."
        )
    lines.append(
        "Caveat: this covers days, not months, and a few dozen proposals in one market regime. Nothing here was tested for "
        "statistical significance, and with samples this small differences of this size can easily be chance; proposals made on "
        "the same day move together, so they are not independent either. Read it as a first look that says where to measure "
        "next, not as a verdict."
    )
    return lines


def render(summary: dict, records: list[dict], scorecard: object, *, since: date, generated: datetime, api: str) -> str:
    out = [
        "# Decision-engine audit",
        "",
        f"Generated {generated.astimezone(IST):%Y-%m-%d %H:%M} IST from the read-only API of {api}, by `scripts/decision_audit.py`. "
        f"Agent proposals (strategy `{AGENT_STRATEGY}`) since {since:%d %b %Y}: {summary['proposals']} "
        f"({summary['buys']} BUY, {summary['sells']} SELL). Manual and Strategy-lab proposals are left out.",
        "",
        "Return = close of the k-th NSE session after the decision's session ÷ the proposal's entry price − 1. Every proposal gets one, "
        "including rejected and vetoed ones: that is the counterfactual. Proposals too recent to have k later sessions are left out of that column (n shows how many count).",
        "",
        "## 1. BUY proposals by outcome path",
        "",
        "A proposal that failed two risk checks appears under both.",
        "",
        HEADER,
        _row("**All agent BUYs**", summary["all_buys"]),
        _row("Risk approved", summary["approved_buys"]),
        _row("Risk rejected (any reason)", summary["rejected_buys"]),
    ]
    out += [_row(path, stats) for path, stats in summary["by_path"].items()]
    out += ["", f"SELL proposals (exits): {summary['sells_stats']['count']}, mean 1-session return of the stock {_pct(summary['sells_stats']['mean_1s'])} (a negative number means the exit avoided a fall).", ""]
    out += ["## 2. By supporting agent", "", "An agent supports a BUY when its signal in the fused set is at least +0.05.", "", HEADER]
    out += [_row(agent, stats) for agent, stats in summary["by_agent"].items()]
    out += [
        "",
        "## 3. Decision threshold",
        "",
        "BUY proposals whose stored fused signal is at least the bar. The decision engine only proposes from a lower bar, so 0.25 shows what a looser bar would let through among proposals that exist; nothing below the engine's own bar can be judged here.",
        "",
        HEADER.replace("| |", "| Fused signal ≥ |"),
    ]
    out += [_row(f"{t}{' (live)' if float(t) == LIVE_THRESHOLD else ''}", stats) for t, stats in summary["by_threshold"].items()]
    out += ["", "## 4. Answer to the mentor's question", ""] + [f"- {line}" for line in answer(summary)]
    if isinstance(scorecard, dict) and scorecard.get("agents"):
        out += ["", "## Context: agent scorecard (live, last %s days)" % scorecard.get("window_days", "?"), "", "| Agent | Horizon | Directional samples | Hit rate | In fusion |", "|---|---|---:|---:|---|"]
        for row in scorecard["agents"]:
            out.append(f"| {row['agent']} | {row['horizon']} | {row.get('directional', 0)} | {_share(row.get('hit_rate'))} | {'yes' if row.get('in_fusion') else 'no'} |")
    out += ["", "## Every proposal", "", "| Decision bar (IST) | Symbol | Side | Fused | Supporting agents | Manager | Risk | Failed checks | Filled | 1-session | 5-session |", "|---|---|---|---:|---|---|---|---|---|---:|---:|"]
    for row in records:
        bar = _parse_ts(row["decision_bar"]).astimezone(IST)
        out.append(
            f"| {bar:%d %b %H:%M} | {row['symbol']} | {row['side']} | {row['fused_signal']:+.2f} | {', '.join(row['supporting_agents']) or '-'} "
            f"| {row['manager_verdict'] or '-'} | {row['risk_status'] or '-'} | {', '.join(row['failed_checks']) or '-'} | {'yes' if row['filled'] else 'no'} "
            f"| {_pct(row['return_1s'])} | {_pct(row['return_5s'])} |"
        )
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="https://13-238-176-73.sslip.io")
    parser.add_argument("--since", type=date.fromisoformat, default=date(2026, 10, 15))
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "stockx-decision-audit")
    parser.add_argument("--refresh", action="store_true", help="fetch every URL again instead of using the cache")
    parser.add_argument("--out", type=Path, default=Path("docs"))
    args = parser.parse_args()

    api = CachedApi(args.api, args.cache, refresh=args.refresh)
    payloads = fetch_all(api)
    symbols = sorted({e["payload"]["symbol"] for e in _events(payloads["decision.created"]) if e["payload"].get("strategy_id") == AGENT_STRATEGY})
    candles = {s: api.get(f"/api/v1/market/candles/{urllib.parse.quote(s)}?timeframe=1d&last=60") for s in symbols}
    signals = {s: api.get(f"/api/v1/signals/{urllib.parse.quote(s)}") for s in symbols}
    records = build_records(payloads, candles, signals, since=args.since)  # type: ignore[arg-type]
    summary = summarize(records)
    generated = datetime.now(timezone.utc)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "decision-audit.md").write_text(render(summary, records, payloads["scorecard"], since=args.since, generated=generated, api=args.api), encoding="utf-8")
    (args.out / "decision-audit.json").write_text(
        json.dumps({"generated_at": generated.isoformat(), "api": args.api, "since": args.since.isoformat(), "summary": summary, "records": records}, indent=2),
        encoding="utf-8",
    )
    print(f"{len(records)} proposals -> {args.out / 'decision-audit.md'}")


if __name__ == "__main__":
    main()
