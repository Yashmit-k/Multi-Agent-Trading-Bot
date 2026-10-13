"""FastAPI app. Serve mode runs the evaluation loop; oneshot does not."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from contracts.enums import TradingMode
from intelligence_agents.clock import SystemClock
from intelligence_agents.logging import configure_logging
from intelligence_agents.loop import evaluation_loop
from intelligence_agents.news.ingest import NewsIngestHealth, news_ingest_loop
from intelligence_agents.news.interpret import interpret_text
from intelligence_agents.news.rss import RssPuller
from intelligence_agents.runtime import RunnerHealth, make_stores
from intelligence_agents.settings import LIVE_MODES, IntelligenceSettings
from intelligence_agents.sink.http import HttpSignalSink

logger = logging.getLogger(__name__)


def _require_live_sink(settings: IntelligenceSettings, sink: object | None) -> object:
    if settings.service_mode != "serve":
        return sink
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
    news_health = NewsIngestHealth(interval_seconds=resolved.rss_interval_seconds)
    news_health.interpretation = (
        "available" if resolved.news_interpret and resolved.llm_mode() == "openai" else "unavailable"
    )
    stop = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        eval_task = None
        ingest_task = None
        if resolved.news_ingest and resolved.data_source == "rss":
            interpreter = None
            if resolved.news_interpret:

                def interpreter(**kwargs):
                    return interpret_text(settings=resolved, **kwargs)

            puller = RssPuller(
                app.state.news_store,
                SystemClock(),
                resolved.symbols,
                max_bytes=resolved.rss_max_bytes,
                max_items=resolved.rss_max_items,
                interval_seconds=0,
                interpreter=interpreter,
            )
            ingest_task = asyncio.create_task(
                news_ingest_loop(
                    resolved,
                    stop,
                    news_health,
                    puller,
                    app.state.news_store.latest_published_at,
                    app.state.news_store.graduate_quarantine,
                )
            )
            logger.info(
                "news_ingest_starting",
                extra={
                    "interval_seconds": resolved.rss_interval_seconds,
                    "feeds": len(resolved.news_rss_urls),
                    "symbols": len(resolved.symbols),
                    "service_mode": resolved.service_mode,
                },
            )
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
            eval_task = asyncio.create_task(evaluation_loop(resolved, stop, health, resolved_sink))
        yield
        stop.set()
        for task in (ingest_task, eval_task):
            if task is None:
                continue
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=180)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()

    news_store, fund_store = make_stores(resolved)
    app = FastAPI(title="Intelligence agents", version="1.0.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.sink = resolved_sink
    app.state.health = health
    app.state.news_health = news_health
    app.state.news_store = news_store
    app.state.fund_store = fund_store

    @app.get("/news/{symbol}")
    def news_rows(symbol: str, as_of: str | None = None, limit: int | None = None) -> list[dict[str, object]]:
        moment = _parse_as_of(as_of)
        origin = _data_origin(resolved)
        take = _news_limit(limit)
        rows = []
        for article in news_store.articles_for(symbol, moment)[:take]:
            payload = article.model_dump(mode="json")
            payload["metadata"] = _origin_metadata(payload.get("metadata"), origin)
            rows.append(payload)
        return rows

    @app.get("/fundamentals/{symbol}")
    def fund_rows(symbol: str, as_of: str | None = None) -> list[dict[str, object]]:
        moment = _parse_as_of(as_of)
        origin = _data_origin(resolved)
        rows = []
        for point in fund_store.points_for(symbol, moment):
            payload = point.model_dump(mode="json")
            payload["metadata"] = _origin_metadata(payload.get("metadata"), origin)
            rows.append(payload)
        return rows

    @app.get("/health/news")
    def news_health_view() -> dict[str, object]:
        news_health.stale = _news_stale(news_health, resolved)
        payload = news_health.as_dict()
        payload["data_source"] = resolved.data_source
        payload["data_origin"] = _data_origin(resolved)
        payload["symbols"] = list(resolved.symbols)
        payload["paper_eval_running"] = health.runner_running
        payload["status"] = _news_status(news_health, resolved)
        coverage = _symbol_coverage(news_store, resolved.symbols)
        payload.update(coverage)
        return payload

    @app.get("/health")
    def health_view() -> dict[str, object]:
        reachable = _sink_reachable(resolved, resolved_sink)
        health.sink_reachable = reachable
        news_health.stale = _news_stale(news_health, resolved)
        degraded = False
        reason = None
        if resolved.service_mode == "serve" and resolved.trading_mode in LIVE_MODES and resolved_sink is None:
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
        elif resolved.news_ingest and news_health.consecutive_failures > 0:
            degraded = True
            reason = "news_ingest_failures"
        elif resolved.news_ingest and news_health.stale and news_health.polls > 0:
            degraded = True
            reason = "news_stale"
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
            "data_source": resolved.data_source,
            "data_origin": _data_origin(resolved),
            "news_ingest": news_health.as_dict(),
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


def _parse_as_of(as_of: str | None):
    from datetime import datetime, timezone

    from fastapi import HTTPException

    if as_of is None:
        return datetime.now(timezone.utc)
    try:
        moment = datetime.fromisoformat(as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_as_of") from exc
    if moment.tzinfo is None:
        raise HTTPException(status_code=400, detail="as_of_must_be_timezone_aware")
    return moment


def _data_origin(settings: IntelligenceSettings) -> str:
    if settings.data_source == "fixtures":
        return "demo_fixture"
    if settings.data_source == "rss":
        return "live_rss"
    if settings.data_source == "csv-live":
        return "csv_live_unverified_pit"
    return settings.data_source


def _origin_metadata(metadata: object, origin: str) -> dict[str, object]:
    payload = dict(metadata) if isinstance(metadata, dict) else {}
    payload["data_origin"] = origin
    payload["fixture"] = origin == "demo_fixture"
    payload["live"] = origin == "live_rss"
    if origin == "demo_fixture":
        payload["not_historical_nse_vintage"] = True
        payload["availability"] = "fixture_point_in_time"
    elif origin == "csv_live_unverified_pit":
        payload["not_historical_nse_vintage"] = True
        payload["availability"] = "csv_live_unverified_pit"
    return payload


def _news_limit(limit: int | None) -> int:
    from fastapi import HTTPException

    cap = 100
    if limit is None:
        return cap
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit_must_be_positive")
    return min(limit, cap)


def _symbol_coverage(store, symbols: tuple[str, ...]) -> dict[str, object]:
    from datetime import datetime, timezone

    as_of = datetime.now(timezone.utc)
    counts: dict[str, int] = {}
    with_articles: list[str] = []
    without_articles: list[str] = []
    for symbol in symbols:
        n = len(store.articles_for(symbol, as_of))
        counts[symbol] = n
        if n:
            with_articles.append(symbol)
        else:
            without_articles.append(symbol)
    return {
        "symbols_with_articles": with_articles,
        "symbols_without_articles": without_articles,
        "article_counts": counts,
    }


def _news_stale(news_health: NewsIngestHealth, settings: IntelligenceSettings) -> bool:
    if not settings.news_ingest:
        return False
    if news_health.last_successful_poll is None:
        return news_health.polls > 0
    from datetime import datetime, timezone

    last = datetime.fromisoformat(news_health.last_successful_poll)
    now = datetime.now(timezone.utc)
    return (now - last).total_seconds() > max(60, settings.rss_interval_seconds * 2)


def _news_status(news_health: NewsIngestHealth, settings: IntelligenceSettings) -> str:
    if settings.data_source != "rss":
        return "disabled"
    if news_health.consecutive_failures > 0 or news_health.stale:
        return "degraded"
    if news_health.ingest_running or news_health.polls > 0:
        return "ok"
    return "starting"


def _sink_reachable(settings: IntelligenceSettings, sink: object | None) -> bool | None:
    if settings.service_mode != "serve":
        return None if sink is None else True
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
