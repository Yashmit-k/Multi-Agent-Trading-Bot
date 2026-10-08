"""Core HTTP API. Unfinished product routes return 501."""

import logging
import os
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
from core_db.repository import CoreRepository
from core_db.seed import load_seed
from core_db.session import create_schema
from core_features.engine import build_feature_set
from core_ingestion.service import EventPublisher, MemoryEventPublisher, RedisEventPublisher, ingest_signal
from core_market_data import ZerodhaMarketDataProvider
from core_market_data.zerodha import SEED_HISTORY_DAYS, format_ingestion_report

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
    app = FastAPI(title="Core trading API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.state.settings = resolved
    app.state.repository = repository
    app.state.publisher = publisher
    app.state.kite_client = kite_client
    app.state.zerodha_access_token = None

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
    def signals(_: Annotated[None, Depends(require_user)]) -> list[dict]:
        return repository.list_signal_payloads()

    @app.get("/api/v1/signals/{symbol}")
    def signals_for_symbol(symbol: str, _: Annotated[None, Depends(require_user)]) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in repository.signals_for(symbol)]

    @app.get("/api/v1/stocks")
    def stocks(_: Annotated[None, Depends(require_user)], as_of: datetime | None = None) -> list[dict[str, object]]:
        moment = as_of or datetime.now(timezone.utc)
        rows = []
        for item in repository.members_at(moment):
            body = _instrument_body(item)
            candle = repository.latest_candle(item.symbol, Timeframe.D1)
            body["last_price"] = "" if candle is None else str(candle.close)
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
        return [_agent_row(repository, name, enabled) for name, enabled in _AGENT_ROWS]

    @app.get("/api/v1/agents/{agent_name}/health")
    def agent_health(agent_name: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        known = {name: enabled for name, enabled in _AGENT_ROWS}
        if agent_name not in known:
            raise HTTPException(status_code=404, detail="unknown_agent")
        row = _agent_row(repository, agent_name, known[agent_name])
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
    def portfolio(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return _portfolio_body(repository.latest_snapshot(), resolved.paper_starting_cash)

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
        background.add_task(_ingest_seed_history, repository, client, getattr(app.state, "kite_pace", None))
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


def _ingest_seed_history(repository: CoreRepository, client: Any, pace: Any | None = None) -> None:
    provider = ZerodhaMarketDataProvider(repository, client, pace=pace)
    end = datetime.now(timezone.utc)
    days = int(os.environ.get("SEED_HISTORY_DAYS", str(SEED_HISTORY_DAYS)))
    report = provider.ingest_seed_history(end - timedelta(days=days), end)
    logger.info("%s", format_ingestion_report(report))


def _overview_body(repository: CoreRepository, moment: datetime, mode: TradingMode) -> dict[str, object]:
    closes: list[Decimal] = []
    advancers = 0
    decliners = 0
    for item in repository.members_at(moment):
        bars = repository.candles_until(item.symbol, Timeframe.D1, moment)
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
            "total_pnl": "0",
            "equity": str(starting_cash),
            "gross_exposure": "0",
        }
    return {
        "snapshot": snapshot.model_dump(mode="json"),  # type: ignore[attr-defined]
        "total_pnl": str(snapshot.total_pnl),  # type: ignore[attr-defined]
        "equity": str(snapshot.equity),  # type: ignore[attr-defined]
        "gross_exposure": str(snapshot.gross_exposure),  # type: ignore[attr-defined]
    }


def _paper_body(repository: CoreRepository, settings: Settings) -> dict[str, object]:
    return {
        "running": repository.paper_running(),
        "trading_mode": settings.trading_mode.value,
        "starting_cash": str(settings.paper_starting_cash),
        "kill_switch": "armed" if repository.kill_switch_armed() else "disarmed",
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


def _agent_row(repository: CoreRepository, name: str, enabled: bool) -> dict[str, object]:
    from core_features.engine import FEATURE_VERSION

    rows = [item for item in repository.list_signals() if item.agent_name.value == name]
    last = max(rows, key=lambda item: item.timestamp) if rows else None
    return {
        "agent_name": name,
        "enabled": enabled,
        "mode": "PAPER",
        "feature_version": FEATURE_VERSION,
        "last_signal_at": None if last is None else last.timestamp.isoformat(),
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


def _publisher(redis_url: str) -> EventPublisher:
    try:
        import redis
    except ImportError:
        return MemoryEventPublisher()
    return RedisEventPublisher(redis.Redis.from_url(redis_url))
