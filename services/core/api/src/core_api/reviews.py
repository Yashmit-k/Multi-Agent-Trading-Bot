"""Routes for the portfolio-manager agent: its review queue, its read-only tools, and ad-hoc reviews.

The manager runs in its own container and talks to Core only through these routes, with the
internal token. Core publishes every step it reports on the Redis bus, so the trace recorder keeps
the whole conversation. Nothing here can create an order: a verdict only gates a proposal that the
decision engine already made, and the risk engine still runs after it.
"""


import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Callable
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ValidationError

from contracts.enums import Horizon, Side, Timeframe
from contracts.events import EventType
from contracts.schemas.review import AgentRequest, ProposalReview, ReviewKind, ReviewRequest, ReviewStep
from core_db.repository import CoreRepository
from core_features.engine import build_feature_set
from core_fusion import fuse, select_signals
from core_paper.review_gate import correlation_for, publish
from core_risk.portfolio import sector_of

HORIZON_TIMEFRAME = {Horizon.SWING: Timeframe.D1, Horizon.INTRADAY: Timeframe.M5}
FEATURE_KEYS = (
    "rsi_14", "return_1", "return_5", "return_20", "momentum_10", "roc_10_z", "atr_14_pct", "adx_14",
    "zscore_20", "volume_ratio_20", "dist_ema_20", "vwap_distance", "bb_percent_b", "gap_atr",
)


# ---- the manager's tools: read-only views of the shared blackboard -------------------------------------


def _weights(repository: CoreRepository) -> dict[str, dict[str, float]]:
    stored = repository.get_setting("agent_weights")
    return dict((stored or {}).get("payload", {}).get("weights", {}) or {})


def _short_metadata(metadata: dict) -> dict:
    """The parts of an agent's metadata worth showing a reader: headlines, votes, short facts."""
    out: dict[str, object] = {}
    for key, value in metadata.items():
        if key in {"llm", "content_hash", "articles"}:
            continue
        if key == "headlines" and isinstance(value, list):
            out[key] = [{"title": str(item.get("title", ""))[:160], "source": item.get("source"), "published_at": item.get("published_at")} for item in value[:5] if isinstance(item, dict)]
        elif key == "votes" and isinstance(value, list):
            out[key] = [{"name": item.get("name"), "value": item.get("value")} for item in value[:8] if isinstance(item, dict)]
        elif isinstance(value, (int, float, bool)) or (isinstance(value, str) and len(value) <= 120):
            out[key] = value
        if len(out) >= 8:
            break
    return out


def _used_fallback(metadata: dict) -> bool | None:
    """True when an LLM agent's opinion came from the fixture heuristic instead of the model; None for rule agents."""
    llm = metadata.get("llm")
    if not isinstance(llm, list) or not llm:
        return None
    return any(isinstance(item, dict) and (item.get("fallback") or item.get("model") == "fixture") for item in llm)


def tool_opinions(repository: CoreRepository, symbol: str, horizon: Horizon, now: datetime) -> dict[str, object]:
    signals = select_signals(repository.signals_for(symbol), horizon=horizon, as_of=now)
    weights = _weights(repository).get(horizon.value, {})
    aggregate = fuse(signals, horizon=horizon, as_of=now, weights={horizon: weights} if weights else None)
    fused = 0.0 if aggregate is None else aggregate.aggregated_signal
    rows = []
    for item in sorted(signals, key=lambda s: s.agent_name.value):
        rows.append(
            {
                "agent": item.agent_name.value,
                "version": item.agent_version,
                "score": round(item.signal, 3),
                "confidence": round(item.confidence, 3),
                "fusion_weight": weights.get(item.agent_name.value),
                "age_minutes": round((now - item.timestamp.astimezone(timezone.utc)).total_seconds() / 60, 1),
                "reason_codes": item.reason_codes[:5],
                "llm_fallback": _used_fallback(item.metadata),
                "details": _short_metadata(item.metadata),
            }
        )
    disagree = [row["agent"] for row in rows if fused and abs(row["score"]) >= 0.2 and (row["score"] > 0) != (fused > 0)]
    return {
        "symbol": symbol,
        "horizon": horizon.value,
        "fused_signal": round(fused, 3),
        "fused_confidence": None if aggregate is None else round(aggregate.aggregated_confidence, 3),
        "agents": rows,
        "agents_disagreeing_with_fusion": disagree,
        "note": "fusion_weight 0 means the agent is shown but does not move the fused signal; llm_fallback true means an LLM agent fell back to a fixed heuristic",
    }


def tool_features(repository: CoreRepository, symbol: str, horizon: Horizon, now: datetime) -> dict[str, object]:
    timeframe = HORIZON_TIMEFRAME.get(horizon, Timeframe.D1)
    latest = repository.latest_candle(symbol, timeframe)
    if latest is None:
        return {"error": f"no {timeframe.value} candles for {symbol}"}
    bars = repository.candles_until(symbol, timeframe, latest.end, last=None if timeframe == Timeframe.D1 else 400)
    built = build_feature_set(symbol, timeframe, bars, latest.end)
    if built is None:
        return {"error": "not enough history for features"}
    values = {key: round(float(value), 4) for key, value in built.features.items() if key in FEATURE_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))}
    return {"symbol": symbol, "timeframe": timeframe.value, "as_of": latest.end.isoformat(), "close": float(latest.close), "features": values}


def tool_market(repository: CoreRepository, now: datetime) -> dict[str, object]:
    out: dict[str, object] = {}
    for symbol in ("NIFTY50", "INDIAVIX"):
        bars = repository.candles_until(symbol, Timeframe.D1, now, last=21)
        if len(bars) >= 2:
            out[symbol] = {
                "close": float(bars[-1].close),
                "day_change_pct": round(float(bars[-1].close / bars[-2].close - 1) * 100, 2),
                "change_20d_pct": round(float(bars[-1].close / bars[0].close - 1) * 100, 2) if len(bars) >= 21 else None,
                "as_of": bars[-1].end.isoformat(),
            }
    regime = select_signals(repository.signals_for("RELIANCE"), horizon=Horizon.SWING, as_of=now)
    for item in regime:
        if item.agent_name.value == "regime":
            votes = {str(v.get("name")): v.get("value") for v in item.metadata.get("votes", []) if isinstance(v, dict)}
            out["regime"] = {"score": round(item.signal, 3), "votes": votes, "risk_off": votes.get("index_trend") == -1 and votes.get("fear_gauge") == -1}
    if not out:
        return {"error": "no market data stored yet"}
    return out


def tool_portfolio(repository: CoreRepository, now: datetime, starting_cash: Decimal, daily_limit: int) -> dict[str, object]:
    book = repository.active_paper_session()
    base = book.starting_cash if book is not None and book.starting_cash is not None else starting_cash
    positions = []
    sectors: dict[str, int] = {}
    for item in repository.list_positions():
        if item.quantity <= 0:
            continue
        candle = repository.latest_candle(item.symbol, Timeframe.D1)
        last = float(candle.close) if candle else float(item.average_price)
        positions.append({"symbol": item.symbol, "quantity": item.quantity, "average_price": float(item.average_price), "unrealised_pct": round((last / float(item.average_price) - 1) * 100, 2), "sector": sector_of(item.symbol)})
        sectors[sector_of(item.symbol)] = sectors.get(sector_of(item.symbol), 0) + 1
    return {
        "cash": float(repository.cash_balance(base)),
        "starting_cash": float(base),
        "open_positions": positions,
        "positions_per_sector": sectors,
        "entries_today": repository.daily_entry_count(now),
        "daily_entry_limit": daily_limit,
    }


def tool_track_record(repository: CoreRepository, symbol: str, now: datetime) -> dict[str, object]:
    """The manager's memory: its own past reviews of this stock and how the price moved afterwards."""
    candle = repository.latest_candle(symbol, Timeframe.D1)
    last = float(candle.close) if candle else None
    past = []
    for row in repository.list_reviews(limit=6, symbol=symbol):
        verdict = row.get("verdict")
        if not verdict or verdict.get("verdict") == "UNAVAILABLE":
            continue
        entry = float(row["request"]["entry_price"])
        past.append(
            {
                "reviewed_at": row["created_at"],
                "kind": row["kind"],
                "verdict": verdict["verdict"],
                "critique": str(verdict.get("critique", ""))[:200],
                "price_then": entry,
                "move_since_pct": None if last is None else round((last / entry - 1) * 100, 2),
            }
        )
    trades = []
    executions = {item.order_id: item for item in repository.list_executions()}
    for order in repository.list_orders():
        if order.symbol == symbol and order.order_id in executions:
            fill = executions[order.order_id]
            trades.append({"side": order.side.value, "price": float(fill.price), "quantity": fill.quantity, "at": fill.executed_at.isoformat(), "reason": order.metadata.get("reason")})
    return {"symbol": symbol, "last_close": last, "past_reviews": past[:5], "paper_fills": trades[-6:]}


class AskBody(BaseModel):
    symbol: str
    horizon: str = "SWING"


def register(app: FastAPI, repository: CoreRepository, publisher, require_user: Callable, require_internal: Callable, *, starting_cash: Decimal) -> None:
    from core_paper.cycle import load_risk_settings

    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _review_or_404(review_id: str) -> dict:
        row = repository.get_review(review_id)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown_review")
        return row

    def _horizon(raw: str) -> Horizon:
        try:
            return Horizon(raw.upper())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_horizon") from exc

    @app.post("/api/v1/reviews")
    def ask_review(body: AskBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        """An operator asks the manager whether it would buy this stock now. Nothing is traded."""
        symbol = body.symbol.strip().upper()
        horizon = _horizon(body.horizon)
        if repository.get_by_symbol(symbol) is None or symbol in {"NIFTY50", "INDIAVIX"}:
            raise HTTPException(status_code=422, detail="unknown_symbol")
        candle = repository.latest_candle(symbol, HORIZON_TIMEFRAME[horizon])
        if candle is None:
            raise HTTPException(status_code=409, detail="no_price_yet")
        now = _now()
        pending = [row for row in repository.list_reviews(limit=20) if row["status"] != "done" and row["kind"] == ReviewKind.AD_HOC.value]
        if len(pending) >= 3:
            raise HTTPException(status_code=429, detail="manager_busy")
        weights = _weights(repository).get(horizon.value, {})
        aggregate = fuse(repository.signals_for(symbol), horizon=horizon, as_of=now, weights={horizon: weights} if weights else None)
        cap = load_risk_settings(repository).max_order_notional
        request = ReviewRequest(
            review_id=f"rv-adhoc-{uuid4().hex[:24]}",
            kind=ReviewKind.AD_HOC,
            symbol=symbol,
            horizon=horizon,
            side=Side.BUY,
            quantity=max(1, int(cap // candle.close)),
            entry_price=candle.close,
            aggregated_signal=0.0 if aggregate is None else aggregate.aggregated_signal,
            aggregated_confidence=0.0 if aggregate is None else aggregate.aggregated_confidence,
            requested_at=now,
            requested_by="operator",
            metadata={"hypothetical": True, "question": f"Would you buy {symbol} now for the {horizon.value.lower()} book?"},
        )
        repository.insert_review(request)
        publish(publisher, EventType.REVIEW_REQUESTED, f"review.requested:{request.review_id}", request.review_id, request, source="operator", now=now)
        return {"review_id": request.review_id, "status": "pending"}

    @app.get("/api/v1/reviews")
    def list_reviews(_: Annotated[None, Depends(require_user)], limit: int = 50, symbol: str | None = None) -> dict[str, object]:
        rows = repository.list_reviews(limit=max(1, min(limit, 200)), symbol=None if symbol is None else symbol.strip().upper())
        return {"reviews": [{key: value for key, value in row.items() if key != "steps"} | {"step_count": len(row["steps"])} for row in rows]}

    @app.get("/api/v1/reviews/{review_id}")
    def get_review(review_id: str, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        row = _review_or_404(review_id)
        correlation = row["proposal_id"] or row["review_id"]
        chain = None
        if row["proposal_id"]:
            risk = repository.risk_for_proposal(row["proposal_id"])
            order = repository.order_for_proposal(row["proposal_id"])
            chain = {"risk": None if risk is None else risk.model_dump(mode="json"), "order": None if order is None else order.model_dump(mode="json")}
        return {**row, "correlation_id": correlation, "chain": chain}

    @app.post("/api/v1/internal/reviews/claim")
    def claim(_: Annotated[None, Depends(require_internal)], limit: int = 2) -> list[dict[str, object]]:
        app.state.manager_seen_at = _now()
        return [item.model_dump(mode="json") for item in repository.claim_reviews(_now(), limit=max(1, min(limit, 5)))]

    @app.post("/api/v1/internal/reviews/{review_id}/steps")
    def add_step(review_id: str, body: dict, _: Annotated[None, Depends(require_internal)]) -> dict[str, object]:
        row = _review_or_404(review_id)
        request = ReviewRequest.model_validate(row["request"])
        now = _now()
        try:
            if body.get("to_agent"):
                message = AgentRequest.model_validate(body)
                event_type, event_id = EventType.AGENT_REQUEST, f"agent.request:{message.request_id}"
                stored = {"event": "agent.request", **message.model_dump(mode="json")}
            else:
                message = ReviewStep.model_validate(body)
                event_type, event_id = EventType.REVIEW_STEP, f"review.step:{review_id}:{message.step}"
                stored = {"event": "review.step", **message.model_dump(mode="json")}
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid_step") from exc
        if message.review_id != review_id:
            raise HTTPException(status_code=422, detail="review_id_mismatch")
        if not repository.append_review_step(review_id, stored, now):
            raise HTTPException(status_code=409, detail="review_closed")
        publish(publisher, event_type, event_id, correlation_for(request), message, source="portfolio-manager", now=now)
        return {"stored": True}

    @app.post("/api/v1/internal/reviews/{review_id}/verdict")
    def add_verdict(review_id: str, body: dict, _: Annotated[None, Depends(require_internal)]) -> dict[str, object]:
        row = _review_or_404(review_id)
        request = ReviewRequest.model_validate(row["request"])
        try:
            review = ProposalReview.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid_verdict") from exc
        if review.review_id != review_id or review.proposal_id != request.proposal_id:
            raise HTTPException(status_code=422, detail="review_mismatch")
        now = _now()
        if not repository.complete_review(review, now):
            raise HTTPException(status_code=409, detail="review_closed")
        publish(publisher, EventType.REVIEW_COMPLETED, f"review.completed:{review_id}", correlation_for(request), review, source="portfolio-manager", now=now)
        return {"stored": True}

    @app.get("/api/v1/internal/tools/{tool}")
    def tool(tool: str, _: Annotated[None, Depends(require_internal)], symbol: str | None = None, horizon: str = "SWING") -> dict[str, object]:
        now = _now()
        parsed = _horizon(horizon)
        name = (symbol or "").strip().upper()
        if tool in {"opinions", "features", "track_record"} and repository.get_by_symbol(name) is None:
            return {"error": f"unknown symbol {name!r}"}
        if tool == "opinions":
            return tool_opinions(repository, name, parsed, now)
        if tool == "features":
            return tool_features(repository, name, parsed, now)
        if tool == "market":
            return tool_market(repository, now)
        if tool == "portfolio":
            return tool_portfolio(repository, now, starting_cash, load_risk_settings(repository).daily_entry_limit)
        if tool == "track_record":
            return tool_track_record(repository, name, now)
        raise HTTPException(status_code=404, detail="unknown_tool")

