"""Fusion weights from each agent's live track record (the Agents-page scorecard).

Refreshed hourly. Only signals from an agent's *current* version are graded, so a rewritten agent
starts as unproven. Proven worse than a coin flip -> 0 (its votes stop counting); unproven -> 0.5;
proven better -> 1.0 to 1.5. Regime is a market filter, not a per-stock vote (weight 0). Agents in
FUSION_EXCLUDED_AGENTS stay at 0. The table is saved in user_settings["agent_weights"].
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from contracts.enums import AgentName, Horizon
from core_db.repository import CoreRepository

logger = logging.getLogger(__name__)
REFRESH = timedelta(hours=1)
WINDOW_DAYS = 20
MARKET_FILTER_AGENTS = frozenset({"regime"})
_cache: dict[str, object] = {"at": None, "table": None}


def compute_weights(repository: CoreRepository, now: datetime, excluded: set[str]) -> tuple[dict[Horizon, dict[str, float]], list[dict]]:
    from core_api.scorecard import UNPROVEN_WEIGHT, compute, reliability_weight

    versions = {str(row.get("agent_name")): str(row.get("agent_version")) for row in repository.latest_signal_per_agent()}
    report = compute(repository, now, WINDOW_DAYS, versions=versions)
    table: dict[Horizon, dict[str, float]] = {horizon: {agent.value: UNPROVEN_WEIGHT for agent in AgentName} for horizon in Horizon}
    detail: list[dict] = []
    for row in report["agents"]:  # type: ignore[union-attr]
        agent, horizon = str(row["agent"]), Horizon(str(row["horizon"]))
        weight, why = reliability_weight(row)
        table[horizon][agent] = weight
        detail.append({"agent": agent, "horizon": horizon.value, "weight": weight, "basis": why, "graded": row["directional"], "hit_rate": row["hit_rate"], "version": versions.get(agent)})
    for horizon in Horizon:
        for agent in MARKET_FILTER_AGENTS:
            table[horizon][agent] = 0.0
        for agent in excluded:
            table[horizon][agent] = 0.0
    for item in detail:
        if item["agent"] in MARKET_FILTER_AGENTS:
            item["weight"], item["basis"] = 0.0, "market_filter"
        elif item["agent"] in excluded:
            item["weight"], item["basis"] = 0.0, "excluded"
    return table, detail


def current_weights(repository: CoreRepository, now: datetime, excluded: set[str]) -> dict[Horizon, dict[str, float]] | None:
    """Cached for REFRESH; on failure keeps the last table (or None: fusion then uses its defaults)."""
    at = _cache["at"]
    if isinstance(at, datetime) and now - at < REFRESH and _cache["table"] is not None:
        return _cache["table"]  # type: ignore[return-value]
    try:
        table, detail = compute_weights(repository, now, excluded)
    except Exception:  # noqa: BLE001 - weights are an input, not a reason to stop trading
        logger.exception("agent_weights_failed")
        return _cache["table"]  # type: ignore[return-value]
    repository.save_setting(
        "agent_weights",
        {"computed_at": now.isoformat(), "window_days": WINDOW_DAYS, "weights": {h.value: v for h, v in table.items()}, "detail": detail},
        updated_by="worker",
        now=now,
    )
    _cache["at"], _cache["table"] = now, table
    return table
