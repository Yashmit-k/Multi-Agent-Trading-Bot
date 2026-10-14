"""Core HTTP API. Unfinished product routes return 501."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

from contracts.enums import Timeframe, TradingMode
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.submission import SubmissionResult
from contracts.version import __version__ as contracts_version
from core_api.settings import Settings
from core_db.paper_sessions import ActivePaperSessionError, ClosedPaperSessionError
from core_db.repository import CoreRepository
from core_db.seed import load_seed
from core_worker.heartbeat import DEFAULT_WORKER_INTERVAL_SECONDS, heartbeat_view
from core_db.session import create_schema
from core_features.engine import build_feature_set
from core_ingestion.service import EventPublisher, MemoryEventPublisher, RedisEventPublisher, ingest_signal
from core_market_data import ZerodhaMarketDataProvider
from core_market_data.zerodha import SEED_HISTORY_DAYS, ZerodhaAuthError, format_ingestion_report
from core_paper.operator import OperatorRejected, cancel_order, replace_order

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

LATER_ROUTES: tuple[tuple[str, str], ...] = ()


class ErrorBody(BaseModel):
    detail: str


def create_app(
    settings: Settings | None = None,
    repository: CoreRepository | None = None,
    publisher: EventPublisher | None = None,
    *,
    seed: bool = False,
    kite_client: Any | None = None,
) -> FastAPI:
    resolved = settings or Settings.from_env()
    if repository is None:
        factory = create_schema(resolved.database_url)
        repository = CoreRepository(factory)
        if seed:
            load_seed(repository)
    if publisher is None:
        publisher = _publisher(resolved.redis_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = None
        if resolved.market_data_collector:
            task = asyncio.create_task(_collector_loop(_app, repository, resolved.market_data_poll_seconds))
        yield
        if task is not None:
            task.cancel()

    app = FastAPI(title="Core trading API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.state.settings = resolved
    app.state.repository = repository
    app.state.publisher = publisher
    app.state.kite_client = kite_client
    app.state.zerodha_access_token = None
    from core_market_data.collector import HistoricalGate, IngestionState

    app.state.ingestion = IngestionState()
    app.state.historical_gate = HistoricalGate()
    app.state.kite_pace = app.state.historical_gate.pace
    app.state.worker_heartbeat_at = None
    app.state.worker_heartbeat_interval_seconds = DEFAULT_WORKER_INTERVAL_SECONDS

    def require_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> None:
        if credentials is None or credentials.credentials != resolved.core_api_token:
            raise HTTPException(status_code=401, detail="unauthorized")

    def require_internal(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> None:
        if credentials is None or credentials.credentials != resolved.internal_signal_token:
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/api/v1/market/ingestion")
    def market_ingestion(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        state = app.state.ingestion
        body = state.snapshot()
        body["collector_enabled"] = resolved.market_data_collector
        body["live_enabled"] = False
        return body

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
            # Same meaning as /zerodha/status: a Kite client exists (API key and secret set).
            "zerodha_configured": app.state.kite_client is not None or zerodha.credentials_present(),
        }

    @app.get("/api/v1/system/health")
    def system_health(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        """One check per component of the pipeline, for the System page."""
        now = datetime.now(timezone.utc)
        return {"as_of": now.isoformat(), "live_enabled": False, "checks": _health_checks(app, repository, resolved, now)}

    @app.get("/api/v1/market/instruments")
    def instruments(_: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [_instrument_body(item) for item in repository.list_instruments()]

    @app.get("/api/v1/market/candles/{symbol}")
    def candles(
        symbol: str,
        _: Annotated[None, Depends(require_user)],
        timeframe: str = "1d",
        as_of: datetime | None = None,
        last: int | None = None,
    ) -> list[dict[str, object]]:
        """Completed bars, oldest first. ``last`` keeps the newest N (at most 5000)."""
        moment = as_of or datetime.now(timezone.utc)
        bounded = None if last is None else max(1, min(last, 5000))
        bars = repository.candles_until(symbol, Timeframe(timeframe), moment, last=bounded)
        return [bar.model_dump(mode="json") for bar in bars]

    @app.get("/api/v1/market/overview")
    def market_overview(_: Annotated[None, Depends(require_user)], as_of: datetime | None = None) -> dict[str, object]:
        moment = as_of or datetime.now(timezone.utc)
        return _overview_body(repository, moment, resolved.trading_mode)

    @app.get("/api/v1/features/{symbol}")
    def features(
        symbol: str,
        _: Annotated[None, Depends(require_user)],
        timeframe: str = "1d",
        as_of: datetime | None = None,
    ) -> dict[str, object]:
        try:
            parsed = Timeframe(timeframe)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_timeframe") from exc
        latest = repository.latest_candle(symbol, parsed)
        if latest is None:
            raise HTTPException(status_code=404, detail="no_features")
        moment = as_of or latest.end
        bars = repository.candles_until(symbol, parsed, moment)
        built = build_feature_set(symbol, parsed, bars, moment)
        if built is None:
            raise HTTPException(status_code=404, detail="no_features")
        return built.model_dump(mode="json")

    @app.get("/api/v1/signals")
    def signals(
        _: Annotated[None, Depends(require_user)],
        limit: int = 500,
        symbol: str | None = None,
        agent: str | None = None,
    ) -> list[dict]:
        """Newest signals first, capped at 2000 per request."""
        return repository.recent_signal_payloads(max(1, min(limit, 2000)), symbol=symbol, agent_name=agent)

    @app.get("/api/v1/signals/latest")
    def latest_signals(_: Annotated[None, Depends(require_user)]) -> list[dict]:
        return repository.latest_signal_per_agent()

    @app.get("/api/v1/signals/{symbol}")
    def signals_for_symbol(symbol: str, _: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.signals_for(symbol)]

    @app.get("/api/v1/stocks")
    def stocks(_: Annotated[None, Depends(require_user)], as_of: datetime | None = None) -> list[dict[str, object]]:
        moment = as_of or datetime.now(timezone.utc)
        rows = []
        for item in repository.members_at(moment):
            body = _instrument_body(item)
            bars = repository.candles_until(item.symbol, Timeframe.D1, moment, last=2)
            last = bars[-1] if bars else None
            previous = bars[-2] if len(bars) >= 2 else None
            body["last_price"] = "" if last is None else str(last.close)
            body["prev_close"] = None if previous is None else str(previous.close)
            body["change_pct"] = (
                None
                if last is None or previous is None or previous.close == 0
                else format(((last.close / previous.close) - 1) * 100, ".4f")
            )
            body["bar_end"] = None if last is None else last.end.isoformat()
            rows.append(body)
        return rows

    @app.get("/api/v1/stocks/{symbol}")
    def stock(symbol: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        instrument = repository.get_by_symbol(symbol)
        if instrument is None:
            raise HTTPException(status_code=404, detail="unknown_symbol")
        body = _instrument_body(instrument)
        candle = repository.latest_candle(instrument.symbol, Timeframe.D1)
        body["last_price"] = "" if candle is None else str(candle.close)
        return body

    @app.get("/api/v1/stocks/{symbol}/signals")
    def stock_signals(symbol: str, _: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.signals_for(symbol)]

    @app.get("/api/v1/stocks/{symbol}/agents")
    def stock_agents(symbol: str, _: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [
            {
                "agent_name": item.agent_name.value,
                "signal": item.signal,
                "confidence": item.confidence,
                "horizon": item.horizon.value,
            }
            for item in repository.signals_for(symbol)
        ]

    @app.get("/api/v1/stocks/{symbol}/news")
    def stock_news(symbol: str, _: Annotated[None, Depends(require_user)], as_of: str | None = None) -> list[dict[str, object]]:
        return _intelligence_rows(app, "news", symbol, as_of)

    @app.get("/api/v1/stocks/{symbol}/fundamentals")
    def stock_fundamentals(symbol: str, _: Annotated[None, Depends(require_user)], as_of: str | None = None) -> list[dict[str, object]]:
        return _intelligence_rows(app, "fundamentals", symbol, as_of)

    @app.get("/api/v1/agents")
    def agents(_: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        latest = {item["agent_name"]: item for item in repository.latest_signal_per_agent()}
        return [_agent_row(name, enabled, latest.get(name)) for name, enabled in _AGENT_ROWS]

    @app.get("/api/v1/agents/{agent_name}/health")
    def agent_health(agent_name: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        known = {name: enabled for name, enabled in _AGENT_ROWS}
        if agent_name not in known:
            raise HTTPException(status_code=404, detail="unknown_agent")
        latest = {item["agent_name"]: item for item in repository.latest_signal_per_agent()}
        row = _agent_row(agent_name, known[agent_name], latest.get(agent_name))
        intel = _intelligence_health(app)
        if agent_name in {"news", "fundamental", "valuation", "earnings"}:
            row["enabled"] = intel.get("status") == "ok"
            row["service_status"] = intel.get("status", "unknown")
            if "reason" in intel:
                row["reason"] = intel["reason"]
        return row

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
    def decisions(
        _: Annotated[None, Depends(require_user)],
        session_id: str | None = None,
    ) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.list_proposals(_session_argument(repository, session_id))]

    @app.get("/api/v1/decisions/chain")
    def decision_chain(
        _: Annotated[None, Depends(require_user)],
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        """Each proposal with its risk decision and order, newest first."""
        proposals = sorted(
            repository.list_proposals(_session_argument(repository, session_id)), key=lambda item: item.timestamp, reverse=True
        )[: max(1, min(limit, 500))]
        rows = []
        for proposal in proposals:
            risk = repository.risk_for_proposal(proposal.proposal_id)
            order = repository.order_for_proposal(proposal.proposal_id)
            rows.append(
                {
                    "proposal": proposal.model_dump(mode="json"),
                    "risk": None if risk is None else risk.model_dump(mode="json"),
                    "order": None if order is None else order.model_dump(mode="json"),
                }
            )
        return rows

    @app.get("/api/v1/decisions/{proposal_id}")
    def decision(proposal_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        proposal = repository.get_proposal(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="unknown_proposal")
        return proposal.model_dump(mode="json")

    @app.get("/api/v1/trace")
    def trace(
        _: Annotated[None, Depends(require_user)],
        correlation_id: str | None = None,
        event_type: str | None = None,
        source: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
        bounded = max(1, min(limit, 1000))
        events = repository.list_system_events(correlation_id=correlation_id, event_type=event_type, source=source, limit=bounded)
        return {"count": len(events), "live_enabled": False, "events": [_trace_item(item) for item in events]}

    @app.get("/api/v1/trace/{correlation_id}")
    def trace_chain(correlation_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        events = repository.list_system_events(correlation_id=correlation_id, limit=1000)
        if not events:
            raise HTTPException(status_code=404, detail="unknown_correlation_id")
        ordered = sorted(events, key=lambda item: (item["envelope"].get("timestamp", ""), item["recorded_at"]))
        return {"correlation_id": correlation_id, "count": len(ordered), "events": [_trace_item(item) for item in ordered]}

    @app.get("/api/v1/risk/status")
    def risk_status(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        decisions_stored = repository.list_risk_decisions()
        latest = max(decisions_stored, key=lambda item: item.timestamp) if decisions_stored else None
        armed = repository.kill_switch_armed()
        return {
            "risk_version": "1.0.0",
            "kill_switch": "armed" if armed else "disarmed",
            "status": "ok",
            "message": "kill switch flattens open positions when armed",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "latest": None if latest is None else latest.model_dump(mode="json"),
        }

    class KillBody(BaseModel):
        armed: bool

    @app.post("/api/v1/risk/kill-switch")
    def arm_kill_switch(body: KillBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        repository.set_kill_switch(body.armed)
        return {"kill_switch": "armed" if body.armed else "disarmed"}

    @app.get("/api/v1/portfolio")
    def portfolio(
        _: Annotated[None, Depends(require_user)],
        session_id: str | None = None,
    ) -> dict[str, object]:
        argument = _session_argument(repository, session_id)
        book = repository.active_paper_session() if session_id is None else repository.paper_session(session_id)
        base = book.starting_cash if book is not None and book.starting_cash is not None else resolved.paper_starting_cash
        body = _portfolio_body(repository.latest_snapshot(argument), base)
        body["session_id"] = None if book is None else book.session_id
        body["live_enabled"] = False
        return body

    @app.get("/api/v1/positions")
    def positions(
        _: Annotated[None, Depends(require_user)],
        session_id: str | None = None,
    ) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.list_positions(_session_argument(repository, session_id))]

    @app.get("/api/v1/orders")
    def orders(
        _: Annotated[None, Depends(require_user)],
        session_id: str | None = None,
    ) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.list_orders(_session_argument(repository, session_id))]

    @app.get("/api/v1/trades")
    def trades(
        _: Annotated[None, Depends(require_user)],
        session_id: str | None = None,
    ) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.list_executions(_session_argument(repository, session_id))]

    @app.get("/api/v1/paper/status")
    def paper_status(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return _paper_body(repository, resolved)

    @app.get("/api/v1/paper/daily-performance")
    def paper_daily_performance(_: Annotated[None, Depends(require_user)]) -> dict[str, str]:
        """No daily equity series exists. Closed positions are removed, so open-position P&L is not the book."""
        return {"status": "unavailable", "reason": "no_daily_equity_history"}

    @app.get("/api/v1/worker/heartbeat")
    def worker_heartbeat(_: Annotated[None, Depends(require_user)]) -> dict[str, str]:
        return heartbeat_view(
            app.state.worker_heartbeat_at,
            datetime.now(timezone.utc),
            int(app.state.worker_heartbeat_interval_seconds),
        )

    class HeartbeatBody(BaseModel):
        heartbeat_at: datetime
        interval_seconds: int = DEFAULT_WORKER_INTERVAL_SECONDS

    @app.post("/api/v1/worker/heartbeat")
    def record_worker_heartbeat(body: HeartbeatBody, _: Annotated[None, Depends(require_user)]) -> dict[str, str]:
        app.state.worker_heartbeat_at = body.heartbeat_at
        app.state.worker_heartbeat_interval_seconds = body.interval_seconds
        return heartbeat_view(body.heartbeat_at, body.heartbeat_at, body.interval_seconds)

    @app.post("/api/v1/paper/start")
    def paper_start(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        repository.set_paper_running(True)
        return _paper_body(repository, resolved)

    @app.post("/api/v1/paper/stop")
    def paper_stop(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        repository.set_paper_running(False)
        return _paper_body(repository, resolved)

    @app.get("/api/v1/paper/sessions")
    def paper_sessions(_: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [_session_body(item) for item in repository.list_paper_sessions()]

    @app.get("/api/v1/paper/unassigned")
    def paper_unassigned(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return {
            "session_id": None,
            "orders": [item.model_dump(mode="json") for item in repository.list_orders(None)],
            "positions": [item.model_dump(mode="json") for item in repository.list_positions(None)],
            "trades": [item.model_dump(mode="json") for item in repository.list_executions(None)],
            "live_enabled": False,
        }

    @app.post("/api/v1/paper/sessions")
    def open_session(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        try:
            opened = repository.open_paper_session(resolved.paper_starting_cash)
        except ActivePaperSessionError as exc:
            raise HTTPException(status_code=409, detail="active_session_exists") from exc
        logger.info("paper_session_opened session_id=%s", opened.session_id)
        body = _session_body(opened)
        body["live_enabled"] = False
        return body

    @app.get("/api/v1/paper/sessions/{session_id}")
    def paper_session(session_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        book = repository.paper_session(session_id)
        if book is None:
            raise HTTPException(status_code=404, detail="unknown_session")
        body = _session_body(book)
        body["orders"] = [item.model_dump(mode="json") for item in repository.list_orders(session_id)]
        body["positions"] = [item.model_dump(mode="json") for item in repository.list_positions(session_id)]
        body["trades"] = [item.model_dump(mode="json") for item in repository.list_executions(session_id)]
        body["decisions"] = [item.model_dump(mode="json") for item in repository.list_proposals(session_id)]
        snapshot = repository.latest_snapshot(session_id)
        body["snapshot"] = None if snapshot is None else snapshot.model_dump(mode="json")
        body["live_enabled"] = False
        return body

    @app.post("/api/v1/paper/sessions/{session_id}/close")
    def close_session(session_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        try:
            closed = repository.close_paper_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown_session") from exc
        except ClosedPaperSessionError as exc:
            raise HTTPException(status_code=409, detail="session_already_closed") from exc
        logger.info("paper_session_closed session_id=%s", closed.session_id)
        body = _session_body(closed)
        body["live_enabled"] = False
        return body

    @app.post("/api/v1/paper/sessions/{session_id}/activate")
    def activate_session(session_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        book = repository.paper_session(session_id)
        if book is None:
            raise HTTPException(status_code=404, detail="unknown_session")
        if book.status == "closed":
            raise HTTPException(status_code=409, detail="closed_session_stays_closed")
        active = repository.active_paper_session()
        if active is not None and active.session_id != book.session_id:
            raise HTTPException(status_code=409, detail="active_session_exists")
        logger.info("paper_session_active session_id=%s", book.session_id)
        body = _session_body(book)
        body["live_enabled"] = False
        return body

    class OrderAction(BaseModel):
        operator_id: str
        reason: str
        expected_status: str

    class ReplaceAction(OrderAction):
        decision_at: datetime

    @app.post("/api/v1/paper/sessions/{session_id}/orders/{order_id}/cancel")
    def cancel_paper_order(session_id: str, order_id: str, body: OrderAction, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        try:
            return cancel_order(
                repository,
                session_id=session_id,
                order_id=order_id,
                operator_id=body.operator_id,
                reason=body.reason,
                expected_status=body.expected_status,
            )
        except OperatorRejected as exc:
            raise HTTPException(status_code=409, detail=exc.code) from exc

    @app.post("/api/v1/paper/sessions/{session_id}/orders/{order_id}/replace")
    def replace_paper_order(
        session_id: str,
        order_id: str,
        body: ReplaceAction,
        _: Annotated[None, Depends(require_user)],
    ) -> dict[str, object]:
        try:
            return replace_order(
                repository,
                session_id=session_id,
                order_id=order_id,
                operator_id=body.operator_id,
                reason=body.reason,
                expected_status=body.expected_status,
                decision_at=body.decision_at,
            )
        except OperatorRejected as exc:
            raise HTTPException(status_code=409, detail=exc.code) from exc

    @app.get("/api/v1/zerodha/status")
    def zerodha_status(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return {
            "configured": app.state.kite_client is not None,
            "authenticated": bool(app.state.zerodha_access_token),
            "live_enabled": False,
        }

    @app.get("/api/v1/zerodha/connect")
    def zerodha_connect(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        client = app.state.kite_client
        if client is None:
            raise HTTPException(status_code=503, detail="zerodha_not_configured")
        return {"login_url": client.login_url(), "live_enabled": False}

    @app.get("/api/v1/zerodha/callback")
    def zerodha_callback(request_token: str, background: BackgroundTasks) -> dict[str, object]:
        client = app.state.kite_client
        if client is None:
            raise HTTPException(status_code=503, detail="zerodha_not_configured")
        try:
            data = client.generate_session(request_token)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="zerodha_session_failed") from exc
        token = data.get("access_token")
        if not token:
            raise HTTPException(status_code=502, detail="zerodha_session_failed")
        app.state.zerodha_access_token = str(token)
        state = app.state.ingestion
        state.credentials_rejected = False
        state.authenticated = True
        state.last_error = None
        gate = app.state.historical_gate
        if gate.mark_queued():
            state.seed_status = "queued"
            logger.info("seed_queued")
            logging.getLogger("uvicorn.error").info("seed_queued")
            background.add_task(_ingest_seed_history, repository, client, app.state.kite_pace, state, gate)
        else:
            logger.info("seed_duplicate_skipped")
            logging.getLogger("uvicorn.error").info("seed_duplicate_skipped")
        return {"authenticated": True, "live_enabled": False}

    class BacktestBody(BaseModel):
        strategy: str = "paper-fusion"
        symbols: list[str]
        timeframe: str
        start: str
        end: str
        snapshot_id: str
        initial_cash: str = "100000"
        transaction_cost_bps: str = "2"
        slippage_bps: str = "1"

    @app.post("/api/v1/backtests")
    def create_backtest(body: BacktestBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        report = _execute_backtest(body)
        repository.insert_backtest(str(report["backtest_id"]), body.snapshot_id, report)
        return report

    @app.get("/api/v1/backtests")
    def list_backtests(_: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return repository.list_backtests()

    @app.get("/api/v1/backtests/{backtest_id}")
    def get_backtest(backtest_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        report = repository.get_backtest(backtest_id)
        if report is None:
            raise HTTPException(status_code=404, detail="backtest_not_found")
        return report

    @app.get("/api/v1/backtests/{backtest_id}/performance")
    def backtest_performance(backtest_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        report = repository.get_backtest(backtest_id)
        if report is None:
            raise HTTPException(status_code=404, detail="backtest_not_found")
        return report["performance"]

    @app.get("/api/v1/backtests/{backtest_id}/trades")
    def backtest_trades(backtest_id: str, _: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        report = repository.get_backtest(backtest_id)
        if report is None:
            raise HTTPException(status_code=404, detail="backtest_not_found")
        return report["trades"]

    @app.get("/api/v1/performance")
    def latest_performance(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        runs = repository.list_backtests()
        if not runs:
            raise HTTPException(status_code=404, detail="no_backtest")
        return runs[0]["performance"]

    class BackfillBody(BaseModel):
        jobs: list[dict[str, Any]]

    @app.post("/api/v1/zerodha/backfill")
    def zerodha_backfill(body: BackfillBody, background: BackgroundTasks, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        client = app.state.kite_client
        if client is None or not app.state.zerodha_access_token:
            raise HTTPException(status_code=503, detail="zerodha_not_authenticated")
        if getattr(app.state, "backfill_running", False):
            raise HTTPException(status_code=409, detail="backfill_running")
        app.state.backfill_running = True
        app.state.backfill_report = {"running": True, "appended": 0, "unresolved": []}
        background.add_task(_run_backfill, repository, client, body.jobs, app)
        return {"started": True, "jobs": len(body.jobs)}

    @app.get("/api/v1/zerodha/backfill")
    def zerodha_backfill_status(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        report = getattr(app.state, "backfill_report", None)
        if report is None:
            return {"running": False, "appended": 0, "unresolved": []}
        return report

    @app.post("/api/v1/zerodha/context-gate")
    def zerodha_context_gate(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        client = app.state.kite_client
        if client is None or not app.state.zerodha_access_token:
            raise HTTPException(status_code=503, detail="zerodha_not_authenticated")
        from core_market_data.context_pull import prove_nifty_gate
        from core_market_data.zerodha import RequestPace

        report = prove_nifty_gate(client, getattr(app.state, "kite_pace", None) or RequestPace())
        app.state.context_gate = report
        return report

    @app.post("/api/v1/zerodha/context")
    def zerodha_context(background: BackgroundTasks, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        client = app.state.kite_client
        if client is None or not app.state.zerodha_access_token:
            raise HTTPException(status_code=503, detail="zerodha_not_authenticated")
        gate = getattr(app.state, "context_gate", None)
        if not gate or not gate.get("passed"):
            raise HTTPException(status_code=409, detail="nifty_gate_not_passed")
        if getattr(app.state, "context_running", False):
            raise HTTPException(status_code=409, detail="context_running")
        app.state.context_running = True
        app.state.context_report = {"running": True}
        background.add_task(_run_context, client, gate, app)
        return {"started": True}

    @app.get("/api/v1/zerodha/context")
    def zerodha_context_status(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        report = getattr(app.state, "context_report", None)
        if report is None:
            return {"running": False}
        return report

    for method, path in LATER_ROUTES:
        app.add_api_route(
            path,
            _not_ready(path),
            methods=[method],
            dependencies=[Depends(require_user)],
            response_model=ErrorBody,
        )

    return app


def _run_backfill(repository: CoreRepository, client: Any, jobs: list[dict[str, Any]], app: FastAPI) -> None:
    """Use the already authenticated Kite client. The report never includes the access token."""
    from core_market_data.hole_backfill import collect_bars
    from core_market_data.snapshot import _line
    from core_market_data.zerodha import RequestPace

    try:
        bars, unresolved = collect_bars(client, jobs, getattr(app.state, "kite_pace", None) or RequestPace())
        grouped: dict[tuple[str, str], list[Any]] = {}
        for bar in bars:
            grouped.setdefault((bar.symbol, str(bar.timeframe.value)), []).append(bar)
        fresh: list[Any] = []
        for (symbol, _timeframe), items in grouped.items():
            try:
                have = {item.start.astimezone(timezone.utc) for item in repository.stored_candles(symbol, items[0].timeframe)}
            except Exception:
                have = set()
            fresh.extend(bar for bar in items if bar.start.astimezone(timezone.utc) not in have)
        saved: list[Any] = []
        for bar in fresh:
            try:
                repository.upsert_candles([bar])
                saved.append(bar)
            except KeyError:
                saved.append(bar)
        path = Path("/tmp/kite-added.jsonl")
        path.write_text("".join(_line(bar) for bar in saved), encoding="utf-8")
        app.state.backfill_report = {
            "running": False,
            "appended": len(saved),
            "unresolved": unresolved,
            "file": str(path),
        }
    except Exception as exc:
        logger.exception("hole backfill failed")
        app.state.backfill_report = {"running": False, "appended": 0, "unresolved": [], "error": type(exc).__name__}
    finally:
        app.state.backfill_running = False


def _run_context(client: Any, gate: dict[str, object], app: FastAPI) -> None:
    """Pull verified index history. The report keeps the chosen instrument row and never the access token."""
    from core_market_data.context_pull import pull_verified_context
    from core_market_data.zerodha import RequestPace

    try:
        pulled = pull_verified_context(client, gate, getattr(app.state, "kite_pace", None) or RequestPace())
        candles = pulled.pop("candles")
        for timeframe, filename in (("5m", "/tmp/context-5m.jsonl"), ("1d", "/tmp/context-1d.jsonl")):
            body = "".join(line for line in candles if f'"timeframe":"{timeframe}"' in line)
            Path(filename).write_text(body, encoding="utf-8")
        pulled["running"] = False
        pulled["bars"] = len(candles)
        app.state.context_report = pulled
    except Exception as exc:
        logger.exception("context pull failed")
        app.state.context_report = {"running": False, "error": type(exc).__name__}
    finally:
        app.state.context_running = False


def _ingest_seed_history(
    repository: CoreRepository,
    client: Any,
    pace: Any | None = None,
    state: Any | None = None,
    gate: Any | None = None,
) -> None:
    """One 100-day seed. The gate keeps it from overlapping an incremental poll."""
    ops = logging.getLogger("uvicorn.error")
    if gate is not None and pace is not None:
        gate.pace = pace
    acquired = False
    provider = ZerodhaMarketDataProvider(repository, client, pace=pace if pace is not None else (gate.pace if gate is not None else None))
    try:
        if gate is not None:
            gate.begin_seed()
            acquired = True
        if state is not None:
            state.seed_status = "running"
        ops.info("seed_running")
        logger.info("seed_running")
        end = datetime.now(timezone.utc)
        days = int(os.environ.get("SEED_HISTORY_DAYS", str(SEED_HISTORY_DAYS)))

        def _progress(row: Any) -> None:
            if state is None:
                return
            failed = row.status.value != "OK"
            state.seed_symbols_completed += 0 if failed else 1
            state.seed_symbols_failed += 1 if failed else 0
            state.seed_retries = provider.retry_count
            state.seed_timeouts = provider.timeout_count
            state.seed_results = [
                *state.seed_results,
                {"symbol": row.symbol, "status": row.status.value, "detail": row.detail or ""},
            ]
            ops.info("seed_symbol symbol=%s status=%s detail=%s", row.symbol, row.status.value, row.detail or "-")

        report = provider.ingest_seed_history(end - timedelta(days=days), end, on_symbol=_progress)
        failed = sum(1 for row in report.rows if row.status.value != "OK")
        status = "authentication_failed" if any((row.detail or "").endswith("authentication_failed") for row in report.rows) else ("partial" if failed else "completed")
        if state is not None:
            state.seed_status = status
            state.seed_retries = provider.retry_count
            state.seed_timeouts = provider.timeout_count
            if status == "authentication_failed":
                state.credentials_rejected = True
                state.authenticated = False
                state.last_error = "authentication_failed"
        ops.info(
            "seed_finished status=%s symbols=%s failed=%s retries=%s timeouts=%s",
            status,
            len(report.rows),
            failed,
            provider.retry_count,
            provider.timeout_count,
        )
        logger.info("%s", format_ingestion_report(report))
    except Exception as exc:
        if state is not None:
            if isinstance(exc, ZerodhaAuthError):
                state.seed_status = "authentication_failed"
                state.credentials_rejected = True
                state.authenticated = False
                state.last_error = "authentication_failed"
            else:
                state.seed_status = "failed"
                state.last_error = type(exc).__name__
        ops.error("seed_failed error_type=%s", type(exc).__name__)
        logger.error("seed_failed error_type=%s", type(exc).__name__)
    finally:
        if acquired and gate is not None:
            gate.finish_seed()


async def _collector_loop(app: FastAPI, repository: CoreRepository, poll_seconds: int) -> None:
    """Incremental candles only. A missing or rejected session does not call Zerodha."""
    from core_market_data.collector import run_incremental_once

    ops = logging.getLogger("uvicorn.error")
    while True:
        client = app.state.kite_client
        state = app.state.ingestion
        if client is None or not app.state.zerodha_access_token:
            state.mark_unauthenticated()
        elif state.credentials_rejected:
            state.authenticated = False
            state.last_error = "authentication_failed"
        else:
            gate = app.state.historical_gate
            if app.state.kite_pace is not None:
                gate.pace = app.state.kite_pace
            try:
                started = state.skipped_for_seed
                await asyncio.to_thread(
                    run_incremental_once,
                    repository,
                    client,
                    state,
                    pace=gate.pace,
                    gate=gate,
                )
                if state.skipped_for_seed > started:
                    ops.info("incremental_skipped reason=seed_active")
            except Exception as exc:
                state.last_error = type(exc).__name__
                ops.error("market_data_collector_failed error_type=%s", type(exc).__name__)
        await asyncio.sleep(max(1, poll_seconds))


def _overview_body(repository: CoreRepository, moment: datetime, mode: TradingMode) -> dict[str, object]:
    closes: list[Decimal] = []
    advancers = 0
    decliners = 0
    for item in repository.members_at(moment):
        bars = repository.candles_until(item.symbol, Timeframe.D1, moment, last=2)
        if not bars:
            continue
        closes.append(bars[-1].close)
        if len(bars) >= 2 and bars[-1].close > bars[-2].close:
            advancers += 1
        elif len(bars) >= 2 and bars[-1].close < bars[-2].close:
            decliners += 1
    last = (sum(closes, Decimal("0")) / Decimal(len(closes))) if closes else Decimal("0")
    return {
        "as_of": moment.astimezone(timezone.utc).isoformat(),
        "nifty_last": format(last, "f"),
        "breadth_advancers": advancers,
        "breadth_decliners": decliners,
        "mode": mode.value,
    }


def _portfolio_body(snapshot: object, starting_cash: Decimal) -> dict[str, object]:
    if snapshot is None:
        return {
            "snapshot": None,
            "total_pnl": None,
            "equity": str(starting_cash),
            "gross_exposure": None,
        }
    return {
        "snapshot": snapshot.model_dump(mode="json"),  # type: ignore[attr-defined]
        "total_pnl": str(snapshot.total_pnl),  # type: ignore[attr-defined]
        "equity": str(snapshot.equity),  # type: ignore[attr-defined]
        "gross_exposure": str(snapshot.gross_exposure),  # type: ignore[attr-defined]
    }


def _paper_body(repository: CoreRepository, settings: Settings) -> dict[str, object]:
    book = repository.active_paper_session()
    return {
        "running": repository.paper_running(),
        "trading_mode": settings.trading_mode.value,
        "starting_cash": str(settings.paper_starting_cash),
        "kill_switch": "armed" if repository.kill_switch_armed() else "disarmed",
        "session_id": None if book is None else book.session_id,
        "session_status": None if book is None else book.status,
        "session_starting_cash": None if book is None or book.starting_cash is None else str(book.starting_cash),
        "live_enabled": False,
    }


def _session_argument(repository: CoreRepository, session_id: str | None) -> str | None | object:
    if session_id is None:
        from core_db.repository import _ACTIVE

        return _ACTIVE
    if repository.paper_session(session_id) is None:
        raise HTTPException(status_code=404, detail="unknown_session")
    return session_id


def _session_body(book: object) -> dict[str, object]:
    return {
        "session_id": book.session_id,  # type: ignore[attr-defined]
        "status": book.status,  # type: ignore[attr-defined]
        "created_at": book.created_at.isoformat(),  # type: ignore[attr-defined]
        "closed_at": None if book.closed_at is None else book.closed_at.isoformat(),  # type: ignore[attr-defined]
        "starting_cash": None if book.starting_cash is None else str(book.starting_cash),  # type: ignore[attr-defined]
        "live_enabled": False,
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


_AGENT_ROWS = (
    ("technical", True),
    ("momentum", True),
    ("mean_reversion", True),
    ("volume", True),
    ("regime", True),
    ("ml", False),
    ("news", True),
    ("fundamental", True),
    ("valuation", True),
    ("earnings", True),
)


def _agent_row(name: str, enabled: bool, last: dict | None) -> dict[str, object]:
    from core_features.engine import FEATURE_VERSION

    stamp = None if last is None else AgentSignal.model_validate(last).timestamp.isoformat()
    return {
        "agent_name": name,
        "enabled": enabled,
        "mode": "PAPER",
        "feature_version": FEATURE_VERSION,
        "last_signal_at": stamp,
        "sink": "core_ingestion",
    }


def _intelligence_rows(app: FastAPI, kind: str, symbol: str, as_of: str | None) -> list[dict[str, object]]:
    client = getattr(app.state, "intelligence_client", None)
    if client is None:
        client = _HttpIntelligence(os.environ.get("INTELLIGENCE_URL", "http://intelligence:8080"))
    try:
        return client.rows(kind, symbol, as_of)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="intelligence_unavailable") from exc


QUANT_AGENTS = ("technical", "momentum", "mean_reversion", "volume", "regime")
INTEL_AGENTS = ("news", "fundamental", "valuation", "earnings")


def _check(component: str, status: str, detail: str, **extra: object) -> dict[str, object]:
    return {"component": component, "status": status, "detail": detail, **extra}


def _age_minutes(stamp: object, now: datetime) -> float | None:
    if stamp is None:
        return None
    moment = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    return round((now - moment.astimezone(timezone.utc)).total_seconds() / 60, 1)


def _health_checks(app: FastAPI, repository: CoreRepository, settings: Settings, now: datetime) -> list[dict[str, object]]:
    checks = [_check("Core API", "ok", f"mode {settings.trading_mode.value}, live trading disabled")]
    try:
        repository.paper_running()
        checks.append(_check("PostgreSQL", "ok", "store reachable"))
    except Exception as exc:
        checks.append(_check("PostgreSQL", "down", type(exc).__name__))
    client = getattr(app.state.publisher, "_client", None)
    if client is None:
        checks.append(_check("Redis event bus", "warn", "in-memory publisher (no Redis configured)"))
    else:
        try:
            client.ping()
            checks.append(_check("Redis event bus", "ok", "publishing EventEnvelopes on domain channels"))
        except Exception as exc:
            checks.append(_check("Redis event bus", "down", type(exc).__name__))
    if app.state.kite_client is None:
        checks.append(_check("Zerodha Kite", "down", "API key/secret not configured"))
    elif not app.state.zerodha_access_token:
        checks.append(_check("Zerodha Kite", "warn", "configured but logged out; log in before 09:15 IST"))
    else:
        checks.append(_check("Zerodha Kite", "ok", "authenticated (market data only; orders never sent)"))
    ingestion = app.state.ingestion.snapshot()
    age = _age_minutes(ingestion.get("last_success_at"), now)
    if ingestion.get("last_error"):
        checks.append(_check("Market-data collector", "warn", f"last error: {ingestion['last_error']}", last_success_at=ingestion.get("last_success_at")))
    elif age is None:
        checks.append(_check("Market-data collector", "warn", "no successful poll since start"))
    else:
        checks.append(_check("Market-data collector", "ok", f"last poll {age} min ago", last_success_at=ingestion.get("last_success_at")))
    latest = {item["agent_name"]: item for item in repository.latest_signal_per_agent()}
    for group, names, label in (("Quant agents", QUANT_AGENTS, "deterministic rules"), ("Intelligence agents", INTEL_AGENTS, "LLM")):
        ages = {name: _age_minutes(latest.get(name, {}).get("timestamp"), now) for name in names}
        missing = [name for name, value in ages.items() if value is None]
        newest = min((value for value in ages.values() if value is not None), default=None)
        status = "ok" if not missing else "warn"
        detail = f"{len(names) - len(missing)}/{len(names)} {label} agents have published"
        if newest is not None:
            detail += f"; newest signal {newest} min ago"
        if missing:
            detail += f"; silent: {', '.join(missing)}"
        checks.append(_check(group, status, detail, agents=ages))
    intel = _intelligence_health(app)
    llm = intel.get("llm_status") if isinstance(intel.get("llm_status"), dict) else {}
    if intel.get("status") != "ok":
        checks.append(_check("Intelligence service", "down", str(intel.get("reason", "unavailable"))))
    else:
        mode = intel.get("llm_mode", "fixture")
        detail = f"LLM {llm.get('model', '?')} via {llm.get('provider', '?')}" if mode == "openai" else "LLM not configured: heuristic fallback only"
        detail += f"; last run {_age_minutes(intel.get('last_run_at'), now)} min ago; {intel.get('fallbacks', 0)} fallbacks since start"
        checks.append(_check("Intelligence service", "ok" if mode == "openai" else "warn", detail, llm=llm))
    events = repository.list_system_events(limit=1)
    if not events:
        checks.append(_check("Trace recorder", "warn", "no bus messages recorded yet"))
    else:
        checks.append(_check("Trace recorder", "ok", f"newest recorded message {_age_minutes(events[0]['recorded_at'], now)} min ago"))
    beat = heartbeat_view(app.state.worker_heartbeat_at, now, int(app.state.worker_heartbeat_interval_seconds))
    running = repository.paper_running()
    if beat["status"] == "available":
        checks.append(_check("Paper worker (orchestrator)", "ok", f"heartbeat at {beat['heartbeat_at']}"))
    else:
        checks.append(_check("Paper worker (orchestrator)", "idle", "stopped: starts only on explicit authorization"))
    book = repository.active_paper_session()
    checks.append(
        _check(
            "Paper session",
            "ok" if book is not None else "warn",
            f"{'active session ' + book.session_id[:8] if book else 'no active session'}; paper {'running' if running else 'stopped'}; "
            f"kill switch {'armed' if repository.kill_switch_armed() else 'disarmed'}",
        )
    )
    return checks


def _intelligence_health(app: FastAPI) -> dict[str, object]:
    client = getattr(app.state, "intelligence_client", None)
    if client is None:
        client = _HttpIntelligence(os.environ.get("INTELLIGENCE_URL", "http://intelligence:8080"))
    try:
        return client.health()
    except Exception:
        return {"status": "degraded", "reason": "intelligence_unavailable"}


class _HttpIntelligence:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def rows(self, kind: str, symbol: str, as_of: str | None) -> list[dict[str, object]]:
        import httpx

        params = {} if as_of is None else {"as_of": as_of}
        response = httpx.get(f"{self._base_url}/{kind}/{symbol}", params=params, timeout=3.0)
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, list) else []

    def health(self) -> dict[str, object]:
        import httpx

        response = httpx.get(f"{self._base_url}/health", timeout=2.0)
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {"status": "degraded"}


def _execute_backtest(body: object) -> dict[str, object]:
    from core_market_data.replay import SnapshotRefused, stream_candles
    from core_paper.backtest import run_backtest
    from core_paper.costs import CostSchedule

    try:
        start = _parse_time(body.start)  # type: ignore[attr-defined]
        end = _parse_time(body.end)  # type: ignore[attr-defined]
        if start is None or end is None:
            raise HTTPException(status_code=400, detail="start_and_end_required")
        candles, missing, digest = stream_candles(body.snapshot_id, tuple(body.symbols), start, end)  # type: ignore[attr-defined]
    except SnapshotRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    report = run_backtest(
        candles,
        symbols=tuple(body.symbols),  # type: ignore[attr-defined]
        timeframe=body.timeframe,  # type: ignore[attr-defined]
        start=start,
        end=end,
        snapshot_id=body.snapshot_id,  # type: ignore[attr-defined]
        candle_sha256=digest,
        initial_cash=Decimal(body.initial_cash),  # type: ignore[attr-defined]
        schedule=CostSchedule.research(Decimal(body.transaction_cost_bps), Decimal(body.slippage_bps)),  # type: ignore[attr-defined]
        missing_candles=missing,
    )
    report["backtest_id"] = uuid4().hex
    report["strategy"] = body.strategy  # type: ignore[attr-defined]
    return report


def _not_ready(path: str):
    def endpoint() -> None:
        raise HTTPException(status_code=501, detail="not_implemented")

    endpoint.__name__ = "later_" + path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return endpoint


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORE_API_CORS_ORIGINS", "")
    extra = [item.strip() for item in raw.split(",") if item.strip()]
    return ["http://127.0.0.1:3000", "http://localhost:3000", *extra]


def _trace_item(item: dict) -> dict[str, object]:
    envelope = item["envelope"]
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
    return {
        "event_id": item["event_id"],
        "event_type": item["event_type"],
        "recorded_at": item["recorded_at"].isoformat(),
        "timestamp": envelope.get("timestamp"),
        "channel": envelope.get("channel"),
        "source": envelope.get("source"),
        "agent": payload.get("agent_name"),
        "symbol": payload.get("symbol"),
        "correlation_id": envelope.get("correlation_id"),
        "payload": payload,
    }


def _publisher(redis_url: str) -> EventPublisher:
    try:
        import redis
    except ImportError:
        return MemoryEventPublisher()
    return RedisEventPublisher(redis.Redis.from_url(redis_url))
