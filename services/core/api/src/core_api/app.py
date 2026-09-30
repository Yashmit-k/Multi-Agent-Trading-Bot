"""Core HTTP API. Unfinished product routes return 501."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

from contracts.enums import Timeframe, TradingMode
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.submission import SubmissionResult
from contracts.version import __version__ as contracts_version
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_db.seed import load_seed
from core_db.session import create_schema
from core_ingestion.service import EventPublisher, MemoryEventPublisher, RedisEventPublisher, ingest_signal
from core_market_data import ZerodhaMarketDataProvider

_bearer = HTTPBearer(auto_error=False)

LATER_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/api/v1/market/overview"),
    ("GET", "/api/v1/stocks/{symbol}/signals"),
    ("GET", "/api/v1/stocks/{symbol}/agents"),
    ("GET", "/api/v1/stocks/{symbol}/news"),
    ("GET", "/api/v1/stocks/{symbol}/fundamentals"),
    ("GET", "/api/v1/signals"),
    ("GET", "/api/v1/signals/{symbol}"),
    ("GET", "/api/v1/performance"),
    ("POST", "/api/v1/backtests"),
    ("GET", "/api/v1/backtests/{id}"),
    ("GET", "/api/v1/zerodha/status"),
    ("GET", "/api/v1/zerodha/connect"),
    ("GET", "/api/v1/zerodha/callback"),
    ("GET", "/api/v1/agents"),
    ("GET", "/api/v1/agents/{agent_name}/health"),
)


class ErrorBody(BaseModel):
    detail: str


def create_app(
    settings: Settings | None = None,
    repository: CoreRepository | None = None,
    publisher: EventPublisher | None = None,
    *,
    seed: bool = False,
) -> FastAPI:
    resolved = settings or Settings.from_env()
    if repository is None:
        factory = create_schema(resolved.database_url)
        repository = CoreRepository(factory)
        if seed:
            load_seed(repository)
    if publisher is None:
        publisher = _publisher(resolved.redis_url)
    app = FastAPI(title="Core trading API", version="1.0.0")
    app.state.settings = resolved
    app.state.repository = repository
    app.state.publisher = publisher

    def require_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> None:
        if credentials is None or credentials.credentials != resolved.core_api_token:
            raise HTTPException(status_code=401, detail="unauthorized")

    def require_internal(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> None:
        if credentials is None or credentials.credentials != resolved.internal_signal_token:
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/system/status")
    def status(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        zerodha = ZerodhaMarketDataProvider.from_env(repository)
        return {
            "status": "ok",
            "contract_version": contracts_version,
            "trading_mode": resolved.trading_mode.value,
            "live_enabled": False,
            "exchange_scope": "NSE",
            "zerodha_configured": zerodha.credentials_present(),
        }

    @app.get("/api/v1/market/instruments")
    def instruments(_: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [_instrument_body(item) for item in repository.list_instruments()]

    @app.get("/api/v1/market/candles/{symbol}")
    def candles(
        symbol: str,
        _: Annotated[None, Depends(require_user)],
        timeframe: str = "1d",
        as_of: datetime | None = None,
    ) -> list[dict[str, object]]:
        moment = as_of or datetime.now(timezone.utc)
        bars = repository.candles_until(symbol, Timeframe(timeframe), moment)
        return [bar.model_dump(mode="json") for bar in bars]

    @app.get("/api/v1/stocks")
    def stocks(_: Annotated[None, Depends(require_user)], as_of: datetime | None = None) -> list[dict[str, object]]:
        moment = as_of or datetime.now(timezone.utc)
        return [_instrument_body(item) for item in repository.members_at(moment)]

    @app.get("/api/v1/stocks/{symbol}")
    def stock(symbol: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        instrument = repository.get_by_symbol(symbol)
        if instrument is None:
            raise HTTPException(status_code=404, detail="unknown_symbol")
        return _instrument_body(instrument)

    @app.post("/api/v1/internal/signals", response_model=SubmissionResult)
    def submit_signal(
        body: dict,
        _: Annotated[None, Depends(require_internal)],
        x_trading_mode: Annotated[str | None, Header()] = None,
        x_replay_as_of: Annotated[str | None, Header()] = None,
    ) -> SubmissionResult:
        try:
            signal = AgentSignal.model_validate(body)
        except ValidationError as exc:
            signal_id = str(body.get("signal_id") or "unknown")
            repository.insert_rejection(str(uuid4()), signal_id, "invalid_schema", exc.errors()[0]["type"], datetime.now(timezone.utc))
            raise HTTPException(status_code=422, detail="invalid_schema") from exc
        mode = TradingMode(x_trading_mode) if x_trading_mode else resolved.trading_mode
        return ingest_signal(
            repository,
            publisher,
            signal,
            mode=mode,
            now=datetime.now(timezone.utc),
            replay_as_of=_parse_time(x_replay_as_of),
            skew_seconds=resolved.max_clock_skew_seconds,
        )

    @app.get("/api/v1/decisions")
    def decisions(_: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.list_proposals()]

    @app.get("/api/v1/decisions/{proposal_id}")
    def decision(proposal_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        proposal = repository.get_proposal(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="unknown_proposal")
        return proposal.model_dump(mode="json")

    @app.get("/api/v1/risk/status")
    def risk_status(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        decisions_stored = repository.list_risk_decisions()
        latest = max(decisions_stored, key=lambda item: item.timestamp) if decisions_stored else None
        return {
            "risk_version": "1.0.0",
            "kill_switch": "noop",
            "latest": None if latest is None else latest.model_dump(mode="json"),
        }

    @app.get("/api/v1/portfolio")
    def portfolio(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        snapshot = repository.latest_snapshot()
        return {"snapshot": None if snapshot is None else snapshot.model_dump(mode="json")}

    @app.get("/api/v1/positions")
    def positions(_: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.list_positions()]

    @app.get("/api/v1/orders")
    def orders(_: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.list_orders()]

    @app.get("/api/v1/trades")
    def trades(_: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.list_executions()]

    @app.get("/api/v1/paper/status")
    def paper_status(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return _paper_body(repository, resolved)

    @app.post("/api/v1/paper/start")
    def paper_start(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        repository.set_paper_running(True)
        return _paper_body(repository, resolved)

    @app.post("/api/v1/paper/stop")
    def paper_stop(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        repository.set_paper_running(False)
        return _paper_body(repository, resolved)

    for method, path in LATER_ROUTES:
        app.add_api_route(
            path,
            _not_ready(path),
            methods=[method],
            dependencies=[Depends(require_user)],
            response_model=ErrorBody,
        )

    return app


def _paper_body(repository: CoreRepository, settings: Settings) -> dict[str, object]:
    return {
        "running": repository.paper_running(),
        "trading_mode": settings.trading_mode.value,
        "starting_cash": str(settings.paper_starting_cash),
        "kill_switch": "noop",
    }


def _instrument_body(item: object) -> dict[str, object]:
    return {
        "instrument_id": item.instrument_id,  # type: ignore[attr-defined]
        "exchange": item.exchange,  # type: ignore[attr-defined]
        "symbol": item.symbol,  # type: ignore[attr-defined]
        "trading_symbol": item.trading_symbol,  # type: ignore[attr-defined]
        "instrument_token": item.instrument_token,  # type: ignore[attr-defined]
    }


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _not_ready(path: str):
    def endpoint() -> None:
        raise HTTPException(status_code=501, detail="not_implemented")

    endpoint.__name__ = "later_" + path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return endpoint


def _publisher(redis_url: str) -> EventPublisher:
    try:
        import redis
    except ImportError:
        return MemoryEventPublisher()
    return RedisEventPublisher(redis.Redis.from_url(redis_url))
