"""Health-only FastAPI app. No production SignalSink is owned by this package."""

from __future__ import annotations

import os

from fastapi import FastAPI

from contracts.enums import TradingMode
from quant_agents.logging import configure_logging
from quant_agents.settings import QuantSettings

LIVE_MODES = {TradingMode.PAPER, TradingMode.SHADOW, TradingMode.LIVE}


def create_app(settings: QuantSettings | None = None, *, sink: object | None = None) -> FastAPI:
    resolved = settings or QuantSettings.from_env()
    configure_logging(resolved.log_level)
    if resolved.trading_mode in LIVE_MODES and sink is None:
        raise RuntimeError("quant service refuses to start in PAPER/SHADOW/LIVE without a Core-owned SignalSink")
    app = FastAPI(title="Quant agents", version="1.0.0")
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

    uvicorn.run("quant_agents.service:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
