"""Background evaluation loop for serve mode."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from intelligence_agents.runtime import RunnerHealth, make_runner
from intelligence_agents.settings import IntelligenceSettings

logger = logging.getLogger(__name__)


def cycle_as_of(now: datetime, interval_seconds: int) -> datetime:
    """Bucket wall time so a rerun with unchanged inputs keeps the same as_of."""
    step = max(1, int(interval_seconds))
    epoch = int(now.astimezone(timezone.utc).timestamp())
    return datetime.fromtimestamp(epoch - (epoch % step), tz=timezone.utc)


def refresh_sources(settings: IntelligenceSettings, runner, puller=None) -> None:
    """Load RSS or CSV into the stores the agents already read. Fixture mode does nothing."""
    if settings.data_source == "fixtures":
        return
    if settings.data_source == "rss":
        if puller is None:
            logger.error("rss_puller_missing")
        else:
            for url in settings.news_rss_urls:
                try:
                    puller.pull(url)
                except Exception:
                    logger.exception("rss_cycle_failed")
        # Live news and a real fundamentals file can run together.
        if settings.fundamentals_csv:
            _load_fundamentals(runner, settings.fundamentals_csv)
        return
    if settings.data_source == "csv-live":
        from intelligence_agents.fundamentals.csv_loader import load_csv

        try:
            load_csv(runner.fund_store, settings.fundamentals_csv)
        except Exception:
            logger.exception("csv_cycle_failed")


def _load_fundamentals(runner, path: str) -> None:
    from pathlib import Path

    from intelligence_agents.fundamentals.csv_loader import load_csv

    if not Path(path).is_file():
        logger.warning("fundamentals_csv_missing", extra={"path": path})
        return
    try:
        inserted = load_csv(runner.fund_store, path)
        if inserted:
            logger.info("fundamentals_csv_loaded", extra={"rows": inserted})
    except Exception:
        logger.exception("csv_cycle_failed")


def run_cycle(settings: IntelligenceSettings, runner, health: RunnerHealth, router, puller=None) -> None:
    refresh_sources(settings, runner, puller)
    as_of = cycle_as_of(runner.clock.now(), settings.eval_interval_seconds)
    produced = runner.run(list(settings.symbols), as_of)
    health.last_run_at = datetime.now(timezone.utc).isoformat()
    health.signals_emitted_last_run = len(produced)
    routers = [router, *([runner.context_router] if getattr(runner, "context_router", router) is not router else [])]
    health.prompt_tokens = sum(item._tracker.prompt_tokens for item in routers)
    health.completion_tokens = sum(item._tracker.completion_tokens for item in routers)
    snapshot = router.health_snapshot()
    health.fallbacks = sum(int(item.health_snapshot()["fallback_count"]) for item in routers)
    health.last_generation = snapshot["last_generation"]  # type: ignore[assignment]
    health.last_failure_type = snapshot["last_failure_type"]  # type: ignore[assignment]
    health.llm_provider = str(snapshot["provider"])
    health.llm_model = str(snapshot["model"])
    health.quota_exhausted = bool(snapshot["quota_exhausted"])
    duplicates = sum(1 for item in runner.results[-len(produced) :] if item.duplicate)
    logger.info(
        "eval_cycle_complete",
        extra={
            "signals": len(produced),
            "duplicates": duplicates,
            "prompt_tokens": health.prompt_tokens,
            "completion_tokens": health.completion_tokens,
            "estimated_usd": snapshot["cost_usd"],
            "pricing_basis": snapshot["pricing_basis"],
            "fallbacks": health.fallbacks,
            "last_generation": health.last_generation,
            "last_failure_type": health.last_failure_type,
        },
    )


async def evaluation_loop(settings: IntelligenceSettings, stop: asyncio.Event, health: RunnerHealth, sink) -> None:
    runner, router = make_runner(settings, sink=sink)
    puller = None
    if settings.data_source == "rss":
        from intelligence_agents.news.rss import RssPuller

        puller = RssPuller(
            runner.news_store,
            runner.clock,
            settings.symbols,
            max_bytes=settings.rss_max_bytes,
            max_items=settings.rss_max_items,
            interval_seconds=settings.rss_interval_seconds,
        )
    health.runner_running = True
    snapshot = router.health_snapshot()
    health.llm_provider = str(snapshot["provider"])
    health.llm_model = str(snapshot["model"])
    try:
        while not stop.is_set():
            try:
                await asyncio.to_thread(run_cycle, settings, runner, health, router, puller)
                health.consecutive_failures = 0
                health.last_error = None
            except Exception as exc:
                health.consecutive_failures += 1
                health.last_error = str(exc)[:500]
                logger.exception("eval_cycle_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.eval_interval_seconds)
            except TimeoutError:
                continue
    finally:
        health.runner_running = False
