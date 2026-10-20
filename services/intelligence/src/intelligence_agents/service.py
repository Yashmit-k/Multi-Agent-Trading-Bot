"""FastAPI app. Serve mode runs the evaluation loop; oneshot does not."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from contracts.enums import TradingMode
from intelligence_agents.logging import configure_logging
from intelligence_agents.loop import evaluation_loop
from intelligence_agents.runtime import RunnerHealth
from intelligence_agents.settings import LIVE_MODES, IntelligenceSettings
from intelligence_agents.sink.http import HttpSignalSink

logger = logging.getLogger(__name__)


class ReassessBody(BaseModel):
    agent: str
    symbol: str
    horizon: str = "SWING"
    request_id: str
    review_id: str


def _require_live_sink(settings: IntelligenceSettings, sink: object | None) -> object:
    if settings.trading_mode not in LIVE_MODES:
        return sink
    if sink is not None:
        return sink
    if not settings.internal_signal_token:
        raise RuntimeError("intelligence service refuses to start in PAPER/SHADOW/LIVE without a Core-owned SignalSink")
    return HttpSignalSink(settings.core_api_url, settings.internal_signal_token, settings.trading_mode)


def create_app(settings: IntelligenceSettings | None = None, *, sink: object | None = None) -> FastAPI:
    resolved = settings or IntelligenceSettings.from_env()
    configure_logging(resolved.log_level)
    resolved_sink = _require_live_sink(resolved, sink)
    health = RunnerHealth()
    health.llm_provider = resolved.llm_provider()
    health.llm_model = resolved.llm_tier1_model
    stop = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if resolved.service_mode == "serve":
            if resolved.trading_mode not in LIVE_MODES or resolved_sink is None:
                raise RuntimeError("serve mode requires PAPER/SHADOW/LIVE and a SignalSink")
            logger.info(
                "serve_starting",
                extra={
                    "mode": resolved.trading_mode.value,
                    "llm_mode": resolved.llm_mode(),
                    "llm_host": resolved.llm_host(),
                    "symbols": ",".join(resolved.symbols),
                },
            )
            task = asyncio.create_task(evaluation_loop(resolved, stop, health, resolved_sink))
        yield
        stop.set()
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=180)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()

    from datetime import datetime, timezone

    from intelligence_agents.runtime import make_stores

    news_store, fund_store = make_stores(resolved)
    app = FastAPI(title="Intelligence agents", version="1.0.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.sink = resolved_sink
    app.state.health = health
    app.state.news_store = news_store
    app.state.fund_store = fund_store

    @app.get("/news/{symbol}")
    def news_rows(symbol: str, as_of: str | None = None) -> list[dict[str, object]]:
        moment = datetime.now(timezone.utc) if as_of is None else datetime.fromisoformat(as_of)
        return [item.model_dump(mode="json") for item in news_store.articles_for(symbol, moment)]

    @app.get("/fundamentals/{symbol}")
    def fundamental_rows(symbol: str, as_of: str | None = None) -> list[dict[str, object]]:
        moment = datetime.now(timezone.utc) if as_of is None else datetime.fromisoformat(as_of)
        return [item.model_dump(mode="json") for item in fund_store.points_for(symbol, moment)]

    @app.post("/reassess")
    def reassess(body: ReassessBody, authorization: str | None = Header(default=None)) -> dict[str, object]:
        """The portfolio manager asks one agent to look at one stock again, now."""
        if not resolved.internal_signal_token or authorization != f"Bearer {resolved.internal_signal_token}":
            raise HTTPException(status_code=401, detail="unauthorized")
        from contracts.enums import Horizon

        from intelligence_agents.reassess import AGENTS, Reassessor

        symbol = body.symbol.strip().upper()
        if body.agent not in AGENTS:
            raise HTTPException(status_code=422, detail="unknown_agent")
        if symbol not in resolved.symbols:
            raise HTTPException(status_code=422, detail="unknown_symbol")
        if resolved_sink is None or resolved.trading_mode not in LIVE_MODES:
            raise HTTPException(status_code=409, detail="no_signal_sink")
        if getattr(app.state, "reassessor", None) is None:
            app.state.reassessor = Reassessor(resolved, resolved_sink)
        try:
            horizon = Horizon(body.horizon.upper())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_horizon") from exc
        return app.state.reassessor.run(agent=body.agent, symbol=symbol, horizon=horizon, request_id=body.request_id, review_id=body.review_id)

    @app.get("/health")
    def health_view() -> dict[str, object]:
        reachable = _sink_reachable(resolved, resolved_sink)
        health.sink_reachable = reachable
        degraded = False
        reason = None
        if resolved.trading_mode in LIVE_MODES and resolved_sink is None:
            degraded = True
            reason = "no_signal_sink"
        elif resolved.trading_mode is TradingMode.BACKTEST and resolved_sink is None:
            degraded = True
            reason = "no_signal_sink"
        elif health.consecutive_failures > 0:
            degraded = True
            reason = "eval_failures"
        elif reachable is False and resolved.service_mode == "serve":
            degraded = True
            reason = "sink_unreachable"
        payload: dict[str, object] = {
            "status": "degraded" if degraded else "ok",
            "runner_running": health.runner_running,
            "last_run_at": health.last_run_at,
            "signals_emitted_last_run": health.signals_emitted_last_run,
            "last_error": health.last_error,
            "consecutive_failures": health.consecutive_failures,
            "sink_reachable": reachable,
            "llm_mode": resolved.llm_mode(),
            "llm_host": resolved.llm_host(),
            "prompt_tokens": health.prompt_tokens,
            "completion_tokens": health.completion_tokens,
            "fallbacks": health.fallbacks,
            "llm_status": {
                "provider": resolved.llm_provider(),
                "model": resolved.llm_tier1_model,
                "host": resolved.llm_host(),
                "last_generation": health.last_generation,
                "fallback_count": health.fallbacks,
                "last_failure_type": health.last_failure_type,
                "quota_exhausted": health.quota_exhausted,
                "prompt_tokens": health.prompt_tokens,
                "completion_tokens": health.completion_tokens,
            },
        }
        if reason:
            payload["reason"] = reason
        return payload

    return app


def _sink_reachable(settings: IntelligenceSettings, sink: object | None) -> bool | None:
    if settings.trading_mode is TradingMode.BACKTEST:
        return None if sink is None else True
    if sink is None:
        return False
    try:
        import httpx

        response = httpx.get(f"{settings.core_api_url}/health", timeout=2.0)
        return response.status_code < 500
    except Exception:
        return False


def main() -> None:
    import uvicorn

    uvicorn.run("intelligence_agents.service:create_app", factory=True, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
