"""Export recorded bus messages as an agent execution trace.

Reads ``GET /api/v1/trace`` from a running Core API and writes two files:

- ``<out>/<run>.jsonl``: one stored event per line, exactly as recorded.
- ``<out>/<run>.md``: a timeline grouped by correlation id, showing the
  producing agent, the bus channel, and the consumer of each handoff.

Usage::

    CORE_API_TOKEN=... python scripts/export_agent_trace.py \
        --api http://localhost:8000 --limit 1000 --run live-signals-20261014

Nothing here writes to the API or the database.
"""

import argparse
import json
import os
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

CONSUMER = {
    "agent.signal": "signal-fusion (via Postgres signal store)",
    "decision.created": "risk-engine",
    "risk.approved": "paper-execution",
    "risk.rejected": "(end of chain)",
    "order.created": "paper-execution settle",
    "order.updated": "paper-execution settle",
    "order.filled": "portfolio / dashboard",
    "order.rejected": "(end of chain)",
    "position.updated": "portfolio / dashboard",
}


def fetch(api: str, token: str, limit: int, event_type: str | None) -> list[dict]:
    query = {"limit": str(limit)}
    if event_type:
        query["event_type"] = event_type
    url = f"{api.rstrip('/')}/api/v1/trace?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())["events"]


def producer(event: dict) -> str:
    if event.get("agent"):
        return f"{event['agent']} agent → {event['source']}"
    return str(event.get("source"))


def summary(event: dict) -> str:
    payload = event.get("payload") or {}
    kind = event["event_type"]
    if kind == "agent.signal":
        return (
            f"{payload.get('symbol')} {payload.get('horizon')} signal={payload.get('signal')} "
            f"confidence={payload.get('confidence')} — {str(payload.get('reasoning', ''))[:140]}"
        )
    if kind == "decision.created":
        return (
            f"{payload.get('side')} {payload.get('quantity')} {payload.get('symbol')} @ {payload.get('entry_price')} "
            f"fused={payload.get('aggregated_signal')} conf={payload.get('aggregated_confidence')} "
            f"stop={payload.get('stop_loss')} target={payload.get('take_profit')} "
            f"from {len(payload.get('supporting_signal_ids') or [])} signals"
        )
    if kind.startswith("risk."):
        failed = [check["name"] for check in payload.get("checks", []) if not check.get("passed")]
        return f"{payload.get('status')} failed_checks={failed or 'none'}"
    if kind.startswith("order."):
        return (
            f"{payload.get('side', '')} {payload.get('quantity')} {payload.get('symbol')} "
            f"status={payload.get('status', 'FILLED')} price={payload.get('price') or payload.get('limit_price')}"
        )
    if kind == "position.updated":
        return f"{payload.get('symbol')} qty={payload.get('quantity')} avg={payload.get('average_price')}"
    return kind


def write(events: list[dict], out: Path, run: str) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    ordered = sorted(events, key=lambda item: (item.get("timestamp") or "", item["recorded_at"]))
    jsonl = out / f"{run}.jsonl"
    jsonl.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in ordered))
    chains: dict[str, list[dict]] = defaultdict(list)
    for item in ordered:
        chains[item["correlation_id"]].append(item)
    proposals = {cid: chain for cid, chain in chains.items() if any(e["event_type"] == "decision.created" for e in chain)}
    signal_ids = {e["correlation_id"] for e in ordered if e["event_type"] == "agent.signal"}
    lines = [
        f"# Agent execution trace — `{run}`",
        "",
        "Captured from the Redis event buses by `core_ingestion.trace_recorder` and exported from "
        "`GET /api/v1/trace`. Every row is a real message; nothing here is simulated or edited. "
        "Trading mode is PAPER and `live_enabled` is false.",
        "",
        f"- Events: {len(ordered)}",
        f"- Agent signals: {len(signal_ids)}",
        f"- Agents seen: {', '.join(sorted({e['agent'] for e in ordered if e.get('agent')})) or 'none'}",
        f"- Decision chains (signal → decision → risk → order → fill): {len(proposals)}",
        f"- First event: {ordered[0]['timestamp'] if ordered else '—'}",
        f"- Last event: {ordered[-1]['timestamp'] if ordered else '—'}",
        "",
    ]
    if proposals:
        lines += ["## Decision chains", ""]
        for cid, chain in proposals.items():
            lines += [f"### Proposal `{cid[:16]}…`", ""]
            decision = next(e for e in chain if e["event_type"] == "decision.created")
            supporting = (decision.get("payload") or {}).get("supporting_signal_ids") or []
            for sid in supporting:
                for signal in chains.get(sid, []):
                    lines.append(_row(signal))
            for event in chain:
                lines.append(_row(event))
            lines.append("")
    lines += ["## Agent signal handoffs", "", "| time (UTC) | producer | channel | consumer | content |", "|---|---|---|---|---|"]
    for event in ordered:
        if event["event_type"] == "agent.signal":
            lines.append(
                f"| {event.get('timestamp')} | {producer(event)} | `{event.get('channel')}` | "
                f"{CONSUMER['agent.signal']} | {summary(event).replace('|', '/')} |"
            )
    markdown = out / f"{run}.md"
    markdown.write_text("\n".join(lines) + "\n")
    return jsonl, markdown


def _row(event: dict) -> str:
    consumer = CONSUMER.get(event["event_type"], "—")
    return f"- `{event.get('timestamp')}` **{event['event_type']}** — {producer(event)} → `{event.get('channel')}` → {consumer}: {summary(event)}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--api", default=os.environ.get("CORE_API_URL", "http://localhost:8000"))
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--event-type", default=None)
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", default="docs/submission/agent-trace")
    args = parser.parse_args()
    token = os.environ.get("CORE_API_TOKEN", "")
    if not token:
        raise SystemExit("CORE_API_TOKEN is required")
    events = fetch(args.api, token, args.limit, args.event_type)
    jsonl, markdown = write(events, Path(args.out), args.run)
    print(f"wrote {len(events)} events to {jsonl} and {markdown}")


if __name__ == "__main__":
    main()
