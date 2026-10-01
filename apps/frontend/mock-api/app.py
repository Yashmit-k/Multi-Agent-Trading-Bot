"""Mock Core API for frontend development. Payloads use packages/contracts models."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from contracts.enums import AgentName, Exchange, Horizon, OrderStatus, OrderType, RiskStatus, Side, TradingMode
from contracts.events import EventType
from contracts.fixtures import (
    FIXTURE_AS_OF,
    FIXTURE_SYMBOLS,
    articles_for,
    candles_for,
    fundamentals_for,
    quote_for,
    sample_agent_signal,
)
from contracts.schemas.event import EventEnvelope
from contracts.schemas.order import Order
from contracts.schemas.portfolio import PortfolioSnapshot
from contracts.schemas.position import Position
from contracts.version import __version__ as contracts_version

app = FastAPI(title="Provisional mock Core API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ALLOWED_PREFIXES = (
    "/health",
    "/api/health",
    "/api/v1/system/status",
    "/api/v1/market/overview",
    "/api/v1/market/candles/",
    "/api/v1/stocks",
    "/api/v1/signals",
    "/api/v1/portfolio",
    "/api/v1/positions",
    "/api/v1/orders",
    "/api/v1/risk/status",
    "/api/v1/performance",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/ws/v1/stream",
)


class ProvisionalSystemStatus(BaseModel):
    status: str
    contract_version: str
    trading_mode: TradingMode
    live_enabled: bool
    exchange_scope: str


class ProvisionalMarketOverview(BaseModel):
    as_of: str
    nifty_last: str
    breadth_advancers: int
    breadth_decliners: int
    mode: TradingMode


class ProvisionalStock(BaseModel):
    symbol: str
    exchange: Exchange
    last_price: str


class ProvisionalRiskStatus(BaseModel):
    status: RiskStatus
    as_of: str
    message: str


class ProvisionalPerformance(BaseModel):
    as_of: str
    total_pnl: str
    sharpe_placeholder: str = Field(description="Not a live metric")


class ProvisionalAgentScore(BaseModel):
    agent_name: AgentName
    signal: float
    confidence: float
    horizon: Horizon


def _allowed(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_PREFIXES)


@app.middleware("http")
async def reject_unknown(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/v1/") and not _allowed(path):
        return JSONResponse({"detail": "not_implemented"}, status_code=501)
    return await call_next(request)


def _portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=FIXTURE_AS_OF,
        cash="1000000.00",
        equity="1050000.00",
        market_value="50000.00",
        gross_exposure="50000.00",
        net_exposure="50000.00",
        realized_pnl="2000.00",
        unrealized_pnl="3000.00",
        total_pnl="5000.00",
        drawdown="0.01",
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/system/status", response_model=ProvisionalSystemStatus)
def system_status() -> ProvisionalSystemStatus:
    return ProvisionalSystemStatus(
        status="ok",
        contract_version=contracts_version,
        trading_mode=TradingMode.PAPER,
        live_enabled=False,
        exchange_scope="NSE",
    )


@app.get("/api/v1/market/overview", response_model=ProvisionalMarketOverview)
def market_overview() -> ProvisionalMarketOverview:
    q = quote_for("RELIANCE", FIXTURE_AS_OF)
    return ProvisionalMarketOverview(
        as_of=FIXTURE_AS_OF.isoformat(),
        nifty_last=str(q.last_price),
        breadth_advancers=3,
        breadth_decliners=2,
        mode=TradingMode.PAPER,
    )


@app.get("/api/v1/stocks", response_model=list[ProvisionalStock])
def stocks() -> list[ProvisionalStock]:
    rows = []
    for symbol in FIXTURE_SYMBOLS:
        q = quote_for(symbol, FIXTURE_AS_OF)
        rows.append(ProvisionalStock(symbol=symbol, exchange=Exchange.NSE, last_price=str(q.last_price)))
    return rows


@app.get("/api/v1/stocks/{symbol}", response_model=ProvisionalStock)
def stock(symbol: str) -> ProvisionalStock:
    try:
        q = quote_for(symbol, FIXTURE_AS_OF)
    except KeyError:
        raise HTTPException(404, "unknown_symbol")
    return ProvisionalStock(symbol=q.symbol, exchange=q.exchange, last_price=str(q.last_price))


@app.get("/api/v1/market/candles/{symbol}")
def candles(symbol: str) -> list[dict]:
    try:
        bars = candles_for(symbol)
    except KeyError:
        raise HTTPException(404, "unknown_symbol")
    return [bar.model_dump(mode="json") for bar in bars]


@app.get("/api/v1/stocks/{symbol}/signals")
def stock_signals(symbol: str) -> list[dict]:
    try:
        return [sample_agent_signal(symbol).model_dump(mode="json")]
    except KeyError:
        raise HTTPException(404, "unknown_symbol")


@app.get("/api/v1/stocks/{symbol}/agents", response_model=list[ProvisionalAgentScore])
def stock_agents(symbol: str) -> list[ProvisionalAgentScore]:
    sig = sample_agent_signal(symbol)
    return [
        ProvisionalAgentScore(
            agent_name=sig.agent_name,
            signal=sig.signal,
            confidence=sig.confidence,
            horizon=sig.horizon,
        )
    ]


@app.get("/api/v1/stocks/{symbol}/news")
def stock_news(symbol: str) -> list[dict]:
    return [item.model_dump(mode="json") for item in articles_for(symbol, FIXTURE_AS_OF)]


@app.get("/api/v1/stocks/{symbol}/fundamentals")
def stock_fundamentals(symbol: str) -> list[dict]:
    return [item.model_dump(mode="json") for item in fundamentals_for(symbol, FIXTURE_AS_OF)]


@app.get("/api/v1/signals")
def signals() -> list[dict]:
    return [sample_agent_signal(symbol).model_dump(mode="json") for symbol in FIXTURE_SYMBOLS]


@app.get("/api/v1/portfolio")
def portfolio() -> dict:
    return _portfolio().model_dump(mode="json")


@app.get("/api/v1/positions")
def positions() -> list[dict]:
    pos = Position(
        symbol="RELIANCE",
        quantity=10,
        average_price="2900.00",
        market_price="2903.00",
        market_value="29030.00",
        unrealized_pnl="30.00",
        realized_pnl="0.00",
        opened_at=FIXTURE_AS_OF,
        updated_at=FIXTURE_AS_OF,
    )
    return [pos.model_dump(mode="json")]


@app.get("/api/v1/orders")
def orders() -> list[dict]:
    order = Order(
        order_id="ord-1",
        client_order_id="c1",
        proposal_id="prop-1",
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        limit_price=None,
        stop_price=None,
        trading_mode=TradingMode.PAPER,
        status=OrderStatus.CREATED,
        created_at=FIXTURE_AS_OF,
        updated_at=FIXTURE_AS_OF,
        metadata={"fixture": True},
    )
    return [order.model_dump(mode="json")]


@app.get("/api/v1/risk/status", response_model=ProvisionalRiskStatus)
def risk_status() -> ProvisionalRiskStatus:
    return ProvisionalRiskStatus(status=RiskStatus.APPROVED, as_of=FIXTURE_AS_OF.isoformat(), message="paper risk idle")


@app.get("/api/v1/performance", response_model=ProvisionalPerformance)
def performance() -> ProvisionalPerformance:
    snap = _portfolio()
    return ProvisionalPerformance(as_of=snap.timestamp.isoformat(), total_pnl=str(snap.total_pnl), sharpe_placeholder="n/a")


@app.websocket("/ws/v1/stream")
async def stream(ws: WebSocket) -> None:
    await ws.accept()
    quote = quote_for("RELIANCE", FIXTURE_AS_OF)
    envelope = EventEnvelope(
        event_id="evt-tick-1",
        event_type=EventType.MARKET_TICK,
        timestamp=FIXTURE_AS_OF,
        source="mock-api",
        correlation_id="corr-1",
        payload=quote,
    )
    EventEnvelope.model_validate(envelope.model_dump(mode="json"))
    await ws.send_text(envelope.model_dump_json())
    await ws.close()
