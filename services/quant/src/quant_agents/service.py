"""Quant HTTP service. PAPER publishes through the Core signal sink."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from contracts.enums import TradingMode
from quant_agents.logging import configure_logging
from quant_agents.settings import QuantSettings

LIVE_MODES = {TradingMode.PAPER, TradingMode.SHADOW, TradingMode.LIVE}
logger = logging.getLogger(__name__)


def _can_publish(settings: QuantSettings) -> bool:
    return bool(
        settings.trading_mode is TradingMode.PAPER
        and settings.core_api_url
        and settings.core_api_token
        and settings.internal_signal_token
        and settings.symbols
    )


def create_app(settings: QuantSettings | None = None, *, sink: object | None = None) -> FastAPI:
    resolved = settings or QuantSettings.from_env()
    configure_logging(resolved.log_level)
    owned_sink = sink
    if owned_sink is None and _can_publish(resolved):
        from quant_agents.sink import CoreSignalSink

        owned_sink = CoreSignalSink(resolved.core_api_url, resolved.internal_signal_token)
    if resolved.trading_mode in LIVE_MODES and owned_sink is None:
        raise RuntimeError("quant service refuses to start in PAPER/SHADOW/LIVE without a Core-owned SignalSink")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks = []
        if _can_publish(resolved) and app.state.sink is not None:
            tasks.append(asyncio.create_task(_publish_loop(resolved, app.state.sink)))
            if resolved.global_markets:
                tasks.append(asyncio.create_task(_global_markets_loop(app.state.sink)))
        yield
        for task in tasks:
            task.cancel()

    app = FastAPI(title="Quant agents", version="1.0.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.sink = owned_sink
    app.state.market_data = None
    if resolved.data_source == "historical":
        from quant_agents.history import replay_from_settings

        app.state.market_data = replay_from_settings(resolved)

    @app.get("/health")
    def health() -> dict[str, str]:
        if app.state.sink is None:
            return {"status": "degraded", "reason": "no_signal_sink"}
        return {"status": "ok"}

    return app


async def _publish_loop(settings: QuantSettings, sink: object) -> None:
    from quant_agents.paper import run_paper_pass

    while True:
        try:
            await asyncio.to_thread(
                run_paper_pass,
                settings.core_api_url,
                settings.core_api_token,
                settings.symbols,
                sink,
                configuration={
                    "horizon": settings.horizon,
                    "timeframe": settings.timeframe,
                    "regime_index_symbols": (),
                },
                ml_demo=settings.ml_demo,
                ml_demo_dir=settings.ml_demo_dir,
                ml_artifact_dir=settings.artifact_dir,
            )
        except Exception:
            logger.exception("quant paper pass failed")
        await asyncio.sleep(settings.eval_interval_seconds)


async def _global_markets_loop(sink: object) -> None:
    """Observe-only world-markets view at 08:45 and 09:10 IST (quant_agents.global_markets). Retries every 5 minutes."""
    from datetime import datetime, timezone

    from quant_agents import global_markets as gm

    done: set = set()
    retry_at = None
    while True:
        now = datetime.now(timezone.utc)
        try:
            slot = gm.due_slot(now, done, gm.trading_day)
            if slot is not None and (retry_at is None or now >= retry_at):
                await asyncio.to_thread(gm.run_once, sink, now, slot)
                done.add((now.astimezone(gm.IST).date(), slot))
                retry_at = None
        except Exception:
            logger.exception("global markets pass failed")
            retry_at = now + gm.RETRY
        await asyncio.sleep(60)


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("quant_agents.service:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
