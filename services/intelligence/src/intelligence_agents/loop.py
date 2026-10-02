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


def run_cycle(settings: IntelligenceSettings, runner, health: RunnerHealth, router) -> None:
    as_of = cycle_as_of(runner.clock.now(), settings.eval_interval_seconds)
    produced = runner.run(list(settings.symbols), as_of)
    health.last_run_at = datetime.now(timezone.utc).isoformat()
    health.signals_emitted_last_run = len(produced)
    health.prompt_tokens = router._tracker.prompt_tokens
    health.completion_tokens = router._tracker.completion_tokens
    health.fallbacks = getattr(router._tier1, "fallbacks", 0)
    duplicates = sum(1 for item in runner.results[-len(produced) :] if item.duplicate)
    logger.info(
        "eval_cycle_complete",
        extra={
            "signals": len(produced),
            "duplicates": duplicates,
            "prompt_tokens": health.prompt_tokens,
            "completion_tokens": health.completion_tokens,
            "estimated_usd": router._tracker.estimate(health.prompt_tokens, health.completion_tokens),
            "fallbacks": health.fallbacks,
        },
    )


async def evaluation_loop(settings: IntelligenceSettings, stop: asyncio.Event, health: RunnerHealth, sink) -> None:
    runner, router = make_runner(settings, sink=sink)
    health.runner_running = True
    try:
        while not stop.is_set():
            try:
                await asyncio.to_thread(run_cycle, settings, runner, health, router)
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
