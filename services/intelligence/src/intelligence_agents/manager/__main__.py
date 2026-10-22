"""Run the portfolio manager: claim waiting reviews from Core, review each, repeat.

    python -m intelligence_agents.manager
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from intelligence_agents.logging import configure_logging
from intelligence_agents.manager.agent import PortfolioManager
from intelligence_agents.manager.llm import ToolCallingLLM
from intelligence_agents.manager.tools import CoreClient, IntelligenceClient

logger = logging.getLogger("intelligence_agents.manager")


def build() -> tuple[PortfolioManager, float]:
    base_url = os.environ.get("MANAGER_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("MANAGER_LLM_API_KEY") or os.environ.get("LLM_API_KEY", "")
    effort = os.environ.get("MANAGER_REASONING_EFFORT", "low")
    interval = float(os.environ.get("MANAGER_MIN_INTERVAL_SECONDS", "4"))
    primary = ToolCallingLLM(base_url, api_key, os.environ.get("MANAGER_LLM_MODEL", "gemini-3.5-flash-lite"), reasoning_effort=effort, min_interval_seconds=interval)
    backup_model = os.environ.get("MANAGER_FALLBACK_MODEL", "gemini-3.5-flash").strip()
    secondary = ToolCallingLLM(base_url, api_key, backup_model, reasoning_effort=effort, min_interval_seconds=interval) if backup_model else None
    token = os.environ.get("INTERNAL_SIGNAL_TOKEN", "")
    core = CoreClient(os.environ.get("CORE_API_URL", "http://core-api:8000").rstrip("/"), token)
    intel = IntelligenceClient(os.environ.get("INTELLIGENCE_URL", "http://intelligence:8080").rstrip("/"), token)
    return PortfolioManager(core, intel, primary, secondary), float(os.environ.get("MANAGER_POLL_SECONDS", "5"))


def main() -> None:
    configure_logging(os.environ.get("INTELLIGENCE_LOG_LEVEL", "INFO"))
    manager, poll = build()
    logger.info("manager_started", extra={"models": [model.model for model in manager.models]})
    while True:
        try:
            claimed = manager.core.claim(limit=1)
        except httpx.HTTPError:
            logger.warning("manager_claim_failed")
            time.sleep(poll * 3)
            continue
        for review in claimed:
            started = time.monotonic()
            try:
                verdict = manager.review(review)
                logger.info("review_done", extra={"review_id": review["review_id"], "symbol": review["symbol"], "verdict": verdict["verdict"], "reviewer": verdict["reviewer"], "seconds": round(time.monotonic() - started, 1)})
            except Exception:  # noqa: BLE001 - one bad review must not stop the manager
                logger.exception("review_failed", extra={"review_id": review["review_id"]})
        if not claimed:
            time.sleep(poll)


if __name__ == "__main__":
    main()
