"""Health-only FastAPI app. Live modes refuse to start without SignalSink."""

from __future__ import annotations

import os

from fastapi import FastAPI

from contracts.enums import TradingMode
from intelligence_agents.logging import configure_logging
from intelligence_agents.settings import LIVE_MODES, IntelligenceSettings


def create_app(settings: IntelligenceSettings | None = None, *, sink: object | None = None) -> FastAPI:
    resolved = settings or IntelligenceSettings.from_env()
    configure_logging(resolved.log_level)
    if resolved.trading_mode in LIVE_MODES and sink is None:
        raise RuntimeError("intelligence service refuses to start in PAPER/SHADOW/LIVE without a Core-owned SignalSink")
    app = FastAPI(title="Intelligence agents", version="1.0.0")
    app.state.settings = resolved
    app.state.sink = sink

    @app.get("/health")
    def health() -> dict[str, str]:
        if app.state.sink is None:
            return {"status": "degraded", "reason": "no_signal_sink"}
        return {"status": "ok"}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = IntelligenceSettings.from_env()
    sink = None
    if settings.trading_mode is not TradingMode.BACKTEST:
        from intelligence_agents.sink.http import HttpSignalSink

        sink = HttpSignalSink(
            settings.core_api_url,
            settings.internal_signal_token,
            settings.trading_mode,
        )
    global app
    app = create_app(settings, sink=sink)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
