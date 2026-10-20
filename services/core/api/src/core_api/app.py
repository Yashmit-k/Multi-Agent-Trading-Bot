"""Core HTTP API. Unfinished product routes return 501."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
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
    if kite_client is not None:
        from core_market_data.collector import INDEX_INSTRUMENTS

        for symbol, (trading_symbol, token) in INDEX_INSTRUMENTS.items():
            repository.upsert_instrument(symbol=symbol, trading_symbol=trading_symbol, instrument_token=token)
    from core_market_data.collector import HistoricalGate, IngestionState

    app.state.ingestion = IngestionState()
    app.state.zerodha_access_token = _restore_broker_token(repository, kite_client, app.state.ingestion, datetime.now(timezone.utc))
    app.state.scorecard_cache = {}
    app.state.scorecard_refreshing = False
    app.state.historical_gate = HistoricalGate()
    app.state.kite_pace = app.state.historical_gate.pace
    app.state.worker_heartbeat_at = None
    app.state.worker_heartbeat_interval_seconds = DEFAULT_WORKER_INTERVAL_SECONDS
    app.state.worker_failed_cycles = 0
    app.state.worker_last_error = None
    app.state.started_at = datetime.now(timezone.utc)

    def require_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> None:
        if credentials is None or credentials.credentials != resolved.core_api_token:
            raise HTTPException(status_code=401, detail="unauthorized")

    def require_internal(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> None:
        if credentials is None or credentials.credentials != resolved.internal_signal_token:
            raise HTTPException(status_code=401, detail="unauthorized")

    from core_api.reviews import register as register_reviews

    register_reviews(app, repository, publisher, require_user, require_internal, starting_cash=resolved.paper_starting_cash)

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
            "market": _market_state(datetime.now(timezone.utc)),
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
        # Intraday: the latest 400 bars cover every indicator, instead of all ~51k 5m bars per symbol.
        # Daily features keep their full history so swing signals are computed exactly as before.
        bars = repository.candles_until(symbol, parsed, moment, last=None if parsed == Timeframe.D1 else FEATURE_HISTORY_BARS)
        index = repository.candles_until("NIFTY50", parsed, moment, last=2) if symbol != "NIFTY50" else []
        nifty_return = float(index[-1].close / index[-2].close - 1) if len(index) == 2 and index[-2].close else None
        built = build_feature_set(symbol, parsed, bars, moment, nifty_return=nifty_return)
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

    @app.get("/api/v1/agents/scorecard")
    def agent_scorecard(_: Annotated[None, Depends(require_user)], background: BackgroundTasks, days: int = 10) -> dict[str, object]:
        days = max(1, min(days, 30))
        now = datetime.now(timezone.utc)
        cache = app.state.scorecard_cache
        cached = cache.get(days)
        if cached and (now - cached[0]) < timedelta(minutes=10):
            return cached[1]
        if cached and not app.state.scorecard_refreshing:  # serve the stale copy; refresh behind it
            app.state.scorecard_refreshing = True
            background.add_task(_refresh_scorecard, app, repository, days)
            return cached[1]
        result = _scorecard(repository, now, days)
        cache[days] = (now, result)
        return result

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
            event = repository.get_system_event(f"decision.created:{proposal.proposal_id}")
            rows.append(
                {
                    "decided_at": None if event is None else event["recorded_at"].isoformat(),
                    "proposal": proposal.model_dump(mode="json"),
                    "risk": None if risk is None else risk.model_dump(mode="json"),
                    "order": None if order is None else order.model_dump(mode="json"),
                }
            )
        return rows

    @app.get("/api/v1/journal")
    def journal(_: Annotated[None, Depends(require_user)], limit: int = 50) -> dict[str, object]:
        """Every entry in the active session as one trade: agent votes, fusion, risk, order, fill, exit, P&L."""
        return {"trades": _journal(repository, max(1, min(limit, 200))), "live_enabled": False}

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
        active = repository.active_paper_session()
        if active is not None and book is not None and book.session_id == active.session_id:
            # Only the open book is revalued at current prices; a closed session keeps its last snapshot.
            _mark_portfolio(body, [_marked(repository, item) for item in repository.list_positions(argument)], base,
                            cash=repository.cash_balance(base))
        body["session_id"] = None if book is None else book.session_id
        body["live_enabled"] = False
        return body

    @app.get("/api/v1/positions")
    def positions(
        _: Annotated[None, Depends(require_user)],
        session_id: str | None = None,
    ) -> list[dict[str, object]]:
        active = repository.active_paper_session()
        rows = repository.list_positions(_session_argument(repository, session_id))
        if session_id is not None and (active is None or session_id != active.session_id):
            return [item.model_dump(mode="json") for item in rows]
        return [_marked(repository, item) for item in rows]

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
    def paper_daily_performance(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        """Stored end-of-day books for the active session, plus today's provisional book while it trades."""
        return _daily_performance(repository, datetime.now(timezone.utc))

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
        failed_cycles: int = 0
        last_error: str | None = None

    @app.post("/api/v1/worker/heartbeat")
    def record_worker_heartbeat(body: HeartbeatBody, _: Annotated[None, Depends(require_user)]) -> dict[str, str]:
        app.state.worker_heartbeat_at = body.heartbeat_at
        app.state.worker_heartbeat_interval_seconds = body.interval_seconds
        app.state.worker_failed_cycles = body.failed_cycles
        app.state.worker_last_error = body.last_error
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

    class RiskSettingsBody(BaseModel):
        values: dict[str, Any]
        operator: str = "operator"

    @app.get("/api/v1/settings/risk")
    def get_risk_settings(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        from core_paper.cycle import load_risk_settings
        from core_risk.settings import describe_bounds

        stored = repository.get_setting("risk")
        return {
            "settings": load_risk_settings(repository).as_json(),
            "bounds": describe_bounds(),
            "updated_at": stored["updated_at"] if stored else None,
            "updated_by": stored["updated_by"] if stored else None,
        }

    @app.post("/api/v1/settings/risk")
    def save_risk_settings(body: RiskSettingsBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        from core_risk.settings import SettingsError, parse_settings

        stored = repository.get_setting("risk")
        merged = {**(stored["payload"] if stored else {}), **body.values}
        try:
            parsed = parse_settings(merged)
        except SettingsError as exc:
            raise HTTPException(status_code=422, detail={"errors": exc.errors}) from exc
        repository.save_setting("risk", parsed.as_json(), updated_by=body.operator[:64] or "operator", now=datetime.now(timezone.utc))
        return get_risk_settings(None)

    class ManualOrderBody(BaseModel):
        symbol: str
        side: str
        quantity: int | None = None
        limit_price: Decimal | None = None
        override_limits: bool = False
        note: str = ""
        operator: str = "operator"

    def _manual(body: ManualOrderBody) -> dict[str, object]:
        from contracts.enums import Side
        from core_paper.manual import ManualOrderRejected, place_manual_order

        try:
            side = Side(body.side.upper())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="side_must_be_BUY_or_SELL") from exc
        try:
            return place_manual_order(
                repository,
                app.state.publisher,
                symbol=body.symbol,
                side=side,
                quantity=body.quantity,
                limit_price=body.limit_price,
                override_limits=body.override_limits,
                operator=body.operator[:64] or "operator",
                note=body.note,
                now=datetime.now(timezone.utc),
            )
        except ManualOrderRejected as exc:
            raise HTTPException(status_code=409, detail=exc.code) from exc

    @app.post("/api/v1/paper/orders/manual")
    def manual_order(body: ManualOrderBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return _manual(body)

    class CloseBody(BaseModel):
        note: str = ""
        operator: str = "operator"

    @app.post("/api/v1/paper/positions/{symbol}/close")
    def close_position(symbol: str, body: CloseBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return _manual(ManualOrderBody(symbol=symbol, side="SELL", note=body.note or "manual close", operator=body.operator))

    @app.post("/api/v1/paper/orders/{order_id}/cancel")
    def cancel_active_order(order_id: str, body: CloseBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        book = repository.active_paper_session()
        order = next((item for item in repository.list_orders() if item.order_id == order_id), None)
        if book is None or order is None:
            raise HTTPException(status_code=404, detail="order_not_found")
        try:
            return cancel_order(
                repository,
                session_id=book.session_id,
                order_id=order_id,
                operator_id=body.operator[:64] or "operator",
                reason=body.note or "manual cancel",
                expected_status=order.status.value,
            )
        except OperatorRejected as exc:
            raise HTTPException(status_code=409, detail=exc.code) from exc

    # --- strategy lab and watchlist -----------------------------------------------------------

    def _load_bars(symbol: str, timeframe: str, start: datetime, end: datetime):  # type: ignore[no-untyped-def]
        from core_paper.strategy_engine import bars_from_rows

        return bars_from_rows(repository.ohlcv(symbol, timeframe, start, end))

    def _universe() -> list[str]:
        members = repository.members_at(datetime.now(timezone.utc))
        return sorted(item.symbol for item in members)

    def _definition(raw: dict[str, Any]):  # type: ignore[no-untyped-def]
        from core_api.strategy_lab import StrategyDefinition

        try:
            return StrategyDefinition.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail={"errors": [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]}) from exc

    def _run(definition, start: str, end: str) -> dict[str, object]:  # type: ignore[no-untyped-def]
        from core_api.strategy_lab import BacktestRequest, run_strategy

        try:
            request = BacktestRequest.model_validate({"start": start, "end": end})
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid_dates") from exc
        bench_start = datetime.combine(request.start, datetime.min.time(), _IST).astimezone(timezone.utc)
        bench_end = datetime.combine(request.end, datetime.max.time(), _IST).astimezone(timezone.utc)
        try:
            return run_strategy(definition, request, _load_bars, _universe(), benchmark=_load_bars("NIFTY50", "1d", bench_start, bench_end))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/strategies/catalog")
    def strategy_catalog(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        from core_api.strategy_lab import MAX_INTRADAY_DAYS, MAX_INTRADAY_SYMBOLS, TEMPLATES, operand_catalog

        return {
            "operands": operand_catalog(),
            "templates": TEMPLATES,
            "universe": _universe(),
            "limits": {"max_5m_symbols": MAX_INTRADAY_SYMBOLS, "max_5m_days": MAX_INTRADAY_DAYS, "max_intraday_symbols": MAX_INTRADAY_SYMBOLS, "max_intraday_days": MAX_INTRADAY_DAYS},
        }

    @app.get("/api/v1/strategies")
    def list_user_strategies(_: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return repository.list_strategies()

    class StrategyBody(BaseModel):
        strategy_id: str | None = None
        definition: dict[str, Any]

    @app.post("/api/v1/strategies")
    def save_user_strategy(body: StrategyBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        definition = _definition(body.definition)
        strategy_id = body.strategy_id or f"strat-{uuid4().hex[:12]}"
        repository.save_strategy(strategy_id, definition.name, definition.model_dump(mode="json"), datetime.now(timezone.utc))
        return repository.get_strategy(strategy_id) or {}

    # --- applying a strategy to paper trading (declared before the {strategy_id} routes) ---

    def _active_view() -> dict[str, object]:
        from core_paper.strategy_live import active_strategy

        found = active_strategy(repository)
        if found is None:
            return {"active": None}
        meta, definition = found
        return {
            "active": {
                "strategy_id": meta["strategy_id"],
                "name": definition.name,
                "applied_at": meta.get("applied_at"),
                "applied_by": meta.get("applied_by"),
                "timeframe": definition.timeframe,
                "symbols": definition.symbols,
                "entry": definition.entry.label(),
                "exit": definition.exit.label() if definition.exit else None,
                "definition": definition.model_dump(mode="json"),
            }
        }

    @app.get("/api/v1/strategies/active")
    def get_active_strategy(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return _active_view()

    class ApplyBody(BaseModel):
        confirm: bool = False
        operator: str = "operator"

    @app.post("/api/v1/strategies/active/stop")
    def stop_active_strategy(body: ApplyBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        if not body.confirm:
            raise HTTPException(status_code=422, detail="confirmation_required")
        repository.save_setting("active_strategy", {"strategy_id": None, "stopped_at": datetime.now(timezone.utc).isoformat(), "stopped_by": body.operator[:64]}, updated_by=body.operator[:64] or "operator", now=datetime.now(timezone.utc))
        return _active_view()

    @app.post("/api/v1/strategies/{strategy_id}/apply")
    def apply_strategy(strategy_id: str, body: ApplyBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        from core_paper.strategy_live import live_problems

        if not body.confirm:
            raise HTTPException(status_code=422, detail="confirmation_required")
        found = repository.get_strategy(strategy_id)
        if found is None:
            raise HTTPException(status_code=404, detail="strategy_not_found")
        definition = _definition(found["definition"])
        problems = live_problems(definition)
        if problems:
            raise HTTPException(status_code=422, detail={"errors": problems})
        now = datetime.now(timezone.utc)
        # A frozen copy: editing the saved strategy later does not change what is being traded.
        repository.save_setting(
            "active_strategy",
            {"strategy_id": strategy_id, "definition": definition.model_dump(mode="json"), "applied_at": now.isoformat(), "applied_by": body.operator[:64] or "operator"},
            updated_by=body.operator[:64] or "operator",
            now=now,
        )
        return _active_view()

    @app.get("/api/v1/strategies/{strategy_id}")
    def get_user_strategy(strategy_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        found = repository.get_strategy(strategy_id)
        if found is None:
            raise HTTPException(status_code=404, detail="strategy_not_found")
        runs = [run for run in repository.list_backtests() if run.get("kind") == "strategy_lab" and run.get("strategy_id") == strategy_id]
        found["runs"] = [
            {"backtest_id": run["backtest_id"], "start": run["start"], "end": run["end"], "metrics": run["metrics"], "created_at": run.get("created_at")}
            for run in runs
        ]
        return found

    @app.post("/api/v1/strategies/{strategy_id}/delete")
    def delete_user_strategy(strategy_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return {"deleted": repository.delete_strategy(strategy_id)}

    class RunBody(BaseModel):
        start: str
        end: str
        definition: dict[str, Any] | None = None

    # Declared before the {strategy_id} routes so "preview" is not read as a strategy id.
    @app.post("/api/v1/strategies/preview/backtest")
    def preview_backtest(body: RunBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        if body.definition is None:
            raise HTTPException(status_code=422, detail="definition_required")
        return _run(_definition(body.definition), body.start, body.end)

    @app.post("/api/v1/strategies/{strategy_id}/backtest")
    def backtest_user_strategy(strategy_id: str, body: RunBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        found = repository.get_strategy(strategy_id)
        if found is None:
            raise HTTPException(status_code=404, detail="strategy_not_found")
        report = _run(_definition(found["definition"]), body.start, body.end)
        backtest_id = f"lab-{uuid4().hex[:12]}"
        report |= {"strategy_id": strategy_id, "created_at": datetime.now(timezone.utc).isoformat()}
        repository.insert_backtest(backtest_id, f"live-db:{strategy_id}", report)
        return report | {"backtest_id": backtest_id}

    @app.get("/api/v1/strategies/{strategy_id}/scan")
    def scan_user_strategy(strategy_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        from core_paper.strategy_live import latest_signal_bars

        found = repository.get_strategy(strategy_id)
        if found is None:
            raise HTTPException(status_code=404, detail="strategy_not_found")
        definition = _definition(found["definition"])
        now = datetime.now(timezone.utc)
        symbols = _universe() if definition.symbols == ["ALL"] else definition.symbols
        hits = []
        for symbol in symbols:
            context, signal = latest_signal_bars(repository, definition, symbol, now)
            if context is not None and signal:
                bars = context.bars
                hits.append({"symbol": symbol, "bar_end": bars.end[-1].isoformat(), "close": round(float(bars.close[-1]), 2)})
        return {"strategy_id": strategy_id, "as_of": now.isoformat(), "matches": hits, "scanned": len(symbols)}

    @app.get("/api/v1/watchlist")
    def watchlist(_: Annotated[None, Depends(require_user)], min_score: int = 7) -> dict[str, object]:
        from core_api.watchlist import build_watchlist

        now = datetime.now(timezone.utc)
        cached = getattr(app.state, "watchlist_cache", None)
        if cached and (now - cached[0]) < timedelta(minutes=10):
            report = cached[1]
        else:
            # Agents' view: mean of each fused agent's newest SWING signal x confidence over the last 3 days.
            latest: dict[tuple[str, str], tuple[str, float]] = {}
            for signal_id, agent, horizon, symbol, stamp, value, confidence in repository.signal_points_since(now - timedelta(days=3)):
                if horizon != "SWING" or agent in {"fundamental", "valuation", "earnings", "ml"}:
                    continue
                key = (symbol, agent)
                if key not in latest or str(stamp) > latest[key][0]:
                    latest[key] = (str(stamp), float(value) * float(confidence))
            grouped: dict[str, list[float]] = {}
            for (symbol, _agent), (_, weighted) in latest.items():
                grouped.setdefault(symbol, []).append(weighted)
            views = {symbol: sum(values) / len(values) for symbol, values in grouped.items()}
            report = build_watchlist(_universe(), lambda symbol: _load_bars(symbol, "1d", now - timedelta(days=900), now), views)
            app.state.watchlist_cache = (now, report)
        threshold = max(0, min(min_score, 10))
        return {**report, "min_score": threshold, "watchlist": [row for row in report["all"] if int(row["score"]) >= threshold]}

    @app.get("/api/v1/zerodha/status")
    def zerodha_status(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        times = _token_times(repository, datetime.now(timezone.utc))
        expired = times.get("hours_left") is not None and times["hours_left"] <= 0
        return {
            "configured": app.state.kite_client is not None,
            "authenticated": bool(app.state.zerodha_access_token) and not expired,
            "live_enabled": False,
            **times,
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
        repository.save_broker_token("zerodha", str(token), datetime.now(timezone.utc))
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
        return [run for run in repository.list_backtests() if run.get("kind") != "strategy_lab"]

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
        runs = [run for run in repository.list_backtests() if run.get("kind") != "strategy_lab"]
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


def _marked(repository: CoreRepository, position) -> dict[str, object]:
    """Position valued at the latest stored 5-minute close (daily close as fallback)."""
    body = position.model_dump(mode="json")
    bar = repository.latest_candle(position.symbol, Timeframe.M5) or repository.latest_candle(position.symbol, Timeframe.D1)
    if bar is None or position.quantity == 0:
        body["price_as_of"] = None
        return body
    price = bar.close
    body["market_price"] = str(price)
    body["market_value"] = str(price * position.quantity)
    body["unrealized_pnl"] = str((price - position.average_price) * position.quantity)
    body["price_as_of"] = bar.end.isoformat()
    return body


def _mark_portfolio(body: dict[str, object], marked: list[dict[str, object]], starting_cash: Decimal, *, cash: Decimal) -> None:
    """Live book: ledger cash plus holdings at current marks.

    total P&L = equity - starting cash (net of every charge);
    unrealized = holdings at mark - holdings at cost; realized = total - unrealized (closed trades and charges).
    """
    snapshot = body.get("snapshot")
    if not isinstance(snapshot, dict):
        return
    market_value = sum((Decimal(item["market_value"]) for item in marked), Decimal("0"))
    unrealized = sum((Decimal(item["unrealized_pnl"]) for item in marked), Decimal("0"))
    equity = cash + market_value
    # Cash already reflects every charge paid, so this is P&L net of costs.
    total = equity - starting_cash
    snapshot.update(
        cash=str(cash),
        realized_pnl=str(total - unrealized),
        market_value=str(market_value),
        gross_exposure=str(market_value),
        net_exposure=str(market_value),
        unrealized_pnl=str(unrealized),
        equity=str(equity),
        total_pnl=str(total),
    )
    stamps = [item["price_as_of"] for item in marked if item.get("price_as_of")]
    body.update(equity=str(equity), total_pnl=str(total), gross_exposure=str(market_value), marked_at=max(stamps) if stamps else None)


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
        checks.append(_check("Zerodha Kite", "warn", "logged out: log in before 09:15 IST", **_token_times(repository, now)))
    else:
        times = _token_times(repository, now)
        hours = times.get("hours_left")
        if hours is not None and hours <= 0:
            checks.append(_check("Zerodha Kite", "down", "login expired at 06:00 IST: log in again before 09:15 IST", **times))
        elif hours is not None and hours < 3:
            checks.append(_check("Zerodha Kite", "warn", f"login expires in {hours:.1f} h (06:00 IST): log in again before 09:15 IST", **times))
        else:
            left = f"; expires in {hours:.0f} h" if hours is not None else ""
            checks.append(_check("Zerodha Kite", "ok", f"authenticated (market data only; orders never sent){left}", **times))
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
    if intel.get("status") == "degraded" and intel.get("runner_running"):
        # The runner is alive but a recent cycle failed (for example a restart of a peer service).
        detail = f"running, {intel.get('consecutive_failures', 0)} recent failed cycle(s): {intel.get('last_error') or intel.get('reason')}"
        checks.append(_check("Intelligence service", "warn", detail, llm=llm))
    elif intel.get("status") != "ok":
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
    running = repository.paper_running()
    seen = getattr(app.state, "manager_seen_at", None)
    if seen is None:
        checks.append(_check("Portfolio manager", "warn", "LLM reviewer has not polled since Core started"))
    else:
        age = (now - seen).total_seconds()
        checks.append(_check("Portfolio manager", "ok" if age < 90 else "down", f"LLM reviewer polled {int(age)} s ago" if age < 90 else f"no poll for {int(age // 60)} min: BUYs wait 150 s, then the risk engine decides alone"))
    checks.append(_worker_check(app, running, now))
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


FEATURE_HISTORY_BARS = 400
_IST = ZoneInfo("Asia/Kolkata")


def kite_token_cutoff(now: datetime) -> datetime:
    """Kite tokens expire at 06:00 IST: a token issued before the latest 06:00 is stale."""
    local = now.astimezone(_IST)
    cutoff = local.replace(hour=6, minute=0, second=0, microsecond=0)
    if local < cutoff:
        cutoff -= timedelta(days=1)
    return cutoff.astimezone(timezone.utc)


def _restore_broker_token(repository: CoreRepository, kite_client: Any | None, state: Any, now: datetime) -> str | None:
    if kite_client is None:
        return None
    try:
        token = repository.broker_token("zerodha", not_before=kite_token_cutoff(now))
    except Exception:
        logger.warning("broker_token_restore_failed")
        return None
    if token is None:
        return None
    kite_client.use_access_token(token)
    state.authenticated = True
    state.credentials_rejected = False
    logger.info("broker_token_restored broker=zerodha")
    return token


def _daily_performance(repository: CoreRepository, now: datetime) -> dict[str, object]:
    from core_paper.daily import book_for_day

    book = repository.active_paper_session()
    if book is None or book.starting_cash is None:
        return {"status": "unavailable", "reason": "no_daily_equity_history"}
    rows = repository.list_daily_equity(book.session_id)
    today = now.astimezone(_IST).date()
    if not any(row["trading_day"] == today.isoformat() for row in rows):
        live = book_for_day(repository, book.starting_cash, today, as_of=now)
        if live is not None:
            live["start_of_day_equity"] = rows[-1]["equity"] if rows else str(book.starting_cash)
            live["day_pnl"] = str(Decimal(live["equity"]) - Decimal(live["start_of_day_equity"]))
            live["written_at"] = None
            rows = [*rows, live]
    if not rows:
        return {"status": "unavailable", "reason": "no_daily_equity_history"}
    days = []
    previous_realized = previous_unrealized = Decimal("0")
    for row in rows:
        realized, unrealized = Decimal(row["realized_pnl"]), Decimal(row["unrealized_pnl"])
        days.append({
            "session_id": book.session_id,
            "calendar_date_ist": row["trading_day"],
            "snapshot_as_of": row["as_of"],
            "complete": bool(row.get("complete")) and row.get("written_at") is not None,
            "pnl_basis": "net_equity",
            "net_pnl_inr": float(Decimal(row["day_pnl"])),
            "start_of_day_equity_inr": float(Decimal(row["start_of_day_equity"])),
            "equity_inr": float(Decimal(row["equity"])),
            "realized_pnl_inr": float(realized - previous_realized),
            "unrealized_change_inr": float(unrealized - previous_unrealized),
            "fees_inr": float(Decimal(row["fees_today"])),
            "has_activity": row["fills_today"] > 0,
            "trading_calendar_state": "open",
            "source_updated_at": row.get("written_at") or row["as_of"],
            "closed_trades": row["closed_trades_today"],
            "open_positions": row["open_positions"],
        })
        previous_realized, previous_unrealized = realized, unrealized
    return {"status": "available", "session_id": book.session_id, "pnl_basis": "net_equity", "days": days}


def _journal(repository: CoreRepository, limit: int) -> list[dict[str, object]]:
    orders = repository.list_orders()
    executions = {item.order_id: item for item in repository.list_executions()}
    entries = sorted(
        (order for order in orders if order.side.value == "BUY" and order.metadata.get("reason") == "entry"),
        key=lambda item: item.created_at,
        reverse=True,
    )[:limit]
    sells = sorted((order for order in orders if order.side.value == "SELL"), key=lambda item: item.created_at)
    trades = []
    for order in entries:
        proposal = repository.get_proposal(order.proposal_id)
        risk = repository.risk_for_proposal(order.proposal_id)
        votes = []
        for signal_id in (proposal.supporting_signal_ids if proposal else []):
            payload = repository.get_signal_payload(signal_id)
            if payload:
                votes.append({key: payload.get(key) for key in ("agent_name", "horizon", "signal", "confidence", "reason_codes", "timestamp")})
        fill = executions.get(order.order_id)
        exit_order = exit_fill = None
        if fill is not None:
            for candidate in sells:
                done = executions.get(candidate.order_id)
                if candidate.symbol == order.symbol and done is not None and done.executed_at >= fill.executed_at:
                    exit_order, exit_fill = candidate, done
                    break
        pnl = None
        mark = None
        if fill is not None and exit_fill is not None:
            pnl = (exit_fill.price - fill.price) * fill.quantity - fill.fees - exit_fill.fees
            status = "closed"
        elif fill is not None:
            bar = repository.latest_candle(order.symbol, Timeframe.M5)
            mark = None if bar is None else bar.close
            pnl = None if mark is None else (mark - fill.price) * fill.quantity - fill.fees
            status = "open"
        else:
            status = order.status.value.lower()
        trades.append({
            "symbol": order.symbol,
            "status": status,
            "horizon": None if proposal is None else proposal.horizon.value,
            "decided_at": None if proposal is None else proposal.metadata.get("decided_at"),
            "decision_bar": None if proposal is None else proposal.timestamp.isoformat(),
            "fused_signal": None if proposal is None else proposal.aggregated_signal,
            "fused_confidence": None if proposal is None else proposal.aggregated_confidence,
            "stop_loss": None if proposal is None else str(proposal.stop_loss),
            "take_profit": None if proposal is None else str(proposal.take_profit),
            "votes": votes,
            "risk": None if risk is None else {"status": risk.status.value, "checks": [check.model_dump(mode="json") for check in risk.checks]},
            "order": {"order_id": order.order_id, "quantity": order.quantity, "limit_price": None if order.limit_price is None else str(order.limit_price),
                      "placed_at": order.created_at.isoformat(), "status": order.status.value,
                      "note": order.metadata.get("cancel_reason") or order.metadata.get("terminal_reason")},
            "entry_fill": None if fill is None else {"price": str(fill.price), "quantity": fill.quantity, "fees": str(fill.fees), "at": fill.executed_at.isoformat()},
            "exit": None if exit_fill is None else {"price": str(exit_fill.price), "fees": str(exit_fill.fees), "at": exit_fill.executed_at.isoformat(),
                                                   "reason": exit_order.metadata.get("reason") if exit_order else None},
            "mark": None if mark is None else str(mark),
            "pnl": None if pnl is None else str(pnl),
        })
    return trades


def _refresh_scorecard(app: FastAPI, repository: CoreRepository, days: int) -> None:
    try:
        now = datetime.now(timezone.utc)
        app.state.scorecard_cache[days] = (now, _scorecard(repository, now, days))
    except Exception:  # noqa: BLE001 - a failed refresh keeps the stale copy
        logging.getLogger(__name__).exception("scorecard refresh failed")
    finally:
        app.state.scorecard_refreshing = False


def _scorecard(repository: CoreRepository, now: datetime, days: int) -> dict[str, object]:
    from core_api import scorecard as sc

    excluded = {item.strip().lower() for item in os.environ.get("FUSION_EXCLUDED_AGENTS", "").split(",") if item.strip()}
    report = sc.compute(repository, now, days, excluded=excluded)
    stored = repository.get_setting("agent_weights")
    if stored:
        report["fusion_weights"] = stored["payload"]
    return report


WORKER_STALE_AFTER = timedelta(minutes=3)
WORKER_FAILURES_DOWN = 3


def _worker_check(app: FastAPI, running: bool, now: datetime) -> dict[str, object]:
    """Down when paper trading is on in market hours and the worker is silent, or its cycles keep failing."""
    from core_paper.trading_calendar import cash_session_open

    beat_at = app.state.worker_heartbeat_at
    interval = timedelta(seconds=int(app.state.worker_heartbeat_interval_seconds))
    stale_after = max(WORKER_STALE_AFTER, 3 * interval)
    name = "Paper worker (orchestrator)"
    failures = int(getattr(app.state, "worker_failed_cycles", 0) or 0)
    error = getattr(app.state, "worker_last_error", None)
    if beat_at is not None and now - beat_at.astimezone(timezone.utc) <= stale_after:
        if failures >= WORKER_FAILURES_DOWN:
            return _check(name, "down", f"{failures} paper cycles in a row failed: {error}", failed_cycles=failures)
        if failures:
            return _check(name, "warn", f"last paper cycle failed ({error}); retrying", failed_cycles=failures)
        return _check(name, "ok", f"heartbeat at {beat_at.astimezone(timezone.utc).isoformat()}")
    silent = "no heartbeat yet" if beat_at is None else f"no heartbeat for {_age_minutes(beat_at, now)} min"
    warming_up = now - app.state.started_at < stale_after
    try:
        market_open = cash_session_open(now)
    except Exception:  # noqa: BLE001 - outside calendar coverage: treat as closed
        market_open = False
    if running and market_open and not warming_up:
        return _check(name, "down", f"paper trading is on and the market is open, but the worker is silent ({silent}). Restart core-worker.")
    if running:
        return _check(name, "warn" if market_open else "idle", f"worker not running ({silent}); paper trading is on" + ("" if market_open else ", market closed"))
    return _check(name, "idle", "stopped: starts only on explicit authorization")


def _market_state(now: datetime) -> dict[str, object]:
    """NSE cash session state from the trading calendar (weekends and exchange holidays included)."""
    from core_paper.trading_calendar import cash_session_open, session_for

    local = now.astimezone(_IST)
    try:
        trading_day = session_for(local.date()) is not None
        is_open = cash_session_open(now)
    except Exception:  # noqa: BLE001 - outside calendar coverage
        trading_day, is_open = local.weekday() < 5, False
    return {"open": is_open, "trading_day": trading_day, "reason": "open" if is_open else ("closed" if trading_day else "holiday_or_weekend")}


def _token_times(repository: CoreRepository, now: datetime) -> dict[str, object]:
    """When the stored Kite token was issued and when it expires (06:00 IST after issue)."""
    issued = repository.broker_token_issued_at("zerodha")
    if issued is None:
        return {"issued_at": None, "expires_at": None, "hours_left": None}
    local = issued.astimezone(_IST)
    expiry = local.replace(hour=6, minute=0, second=0, microsecond=0)
    if local >= expiry:
        expiry += timedelta(days=1)
    left = (expiry.astimezone(timezone.utc) - now).total_seconds() / 3600
    return {"issued_at": issued.isoformat(), "expires_at": expiry.astimezone(timezone.utc).isoformat(), "hours_left": round(left, 2)}


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
