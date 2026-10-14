"""Guarded parameters for the 13 October 2026 paper test cycle.

The continuous worker does not call this module. The function reads a new UTC
clock immediately before the final guard and passes that same instant to
``run_paper_cycle``. A refused guard raises before the cycle.
"""

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text

from contracts.enums import TradingMode
from core_db.repository import DAILY_ENTRY_LIMIT, CoreRepository
from core_ingestion.service import EventPublisher
from core_paper.cycle import CycleRefused, require_entry_window, require_fresh_constituents, run_paper_cycle
from core_paper.trading_calendar import IST, TEST_EXTENSION_DATE, cash_session_open

logger = logging.getLogger(__name__)

AUTHORIZED_SESSION_ID = "c6c7f91fe84f4d48862c4a1b85646f3b"
REQUIRED_REVISION = "0007_entry_day_gates"


def one_shot_blockers(
    *,
    mode: TradingMode,
    live_enabled: bool,
    session_id: str,
    revision: str,
    broker_authenticated: bool,
    daily_count: int,
    now: datetime,
) -> list[str]:
    reasons: list[str] = []
    if mode != TradingMode.PAPER:
        reasons.append("mode")
    if live_enabled is not False:
        reasons.append("live_enabled")
    if session_id != AUTHORIZED_SESSION_ID:
        reasons.append("session")
    if revision != REQUIRED_REVISION:
        reasons.append("revision")
    if not broker_authenticated:
        reasons.append("broker")
    if daily_count >= DAILY_ENTRY_LIMIT:
        reasons.append("daily_entry_cap")
    if now.astimezone(IST).date() != TEST_EXTENSION_DATE:
        reasons.append("extension_date")
    if not cash_session_open(now):
        reasons.append("cash_session_closed")
    try:
        require_entry_window(now, mode=TradingMode.PAPER, allow_extension=True)
    except CycleRefused as exc:
        reasons.append(str(exc))
    return reasons


def database_revision(repository: CoreRepository) -> str:
    """Alembic revision, or an empty string when it cannot be read. Fail closed."""
    try:
        with repository._session_factory() as session:
            value = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:
        logger.info("revision_unreadable error_type=%s", type(exc).__name__)
        return ""
    return str(value or "")


def run_authorized_one_shot(
    repository: CoreRepository,
    publisher: EventPublisher,
    *,
    starting_cash: Decimal,
    clock=None,
    live_gates=None,
) -> int:
    """One paper cycle. The clock is read here, and every guard uses that instant."""
    moment = (clock or _utc_now)()
    gates = (live_gates or _live_gates)()
    book = repository.active_paper_session()
    reasons = one_shot_blockers(
        mode=gates["mode"],
        live_enabled=gates["live_enabled"],
        session_id=book.session_id if book is not None else "",
        revision=database_revision(repository),
        broker_authenticated=gates["broker_authenticated"],
        daily_count=repository.daily_entry_count(moment),
        now=moment,
    )
    try:
        require_fresh_constituents(repository, moment)
    except CycleRefused as exc:
        reasons.append(str(exc))
    if reasons:
        raise CycleRefused("; ".join(reasons))
    return run_paper_cycle(
        repository,
        publisher,
        mode=TradingMode.PAPER,
        starting_cash=starting_cash,
        schedule=None,
        require_fresh=True,
        now=moment,
        max_new_orders=1,
        enforce_entry_window=True,
        require_universe_fresh=True,
        broker_authenticated=gates["broker_authenticated"],
        allow_test_extension=True,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _live_gates() -> dict:
    """PAPER, live_enabled, and Zerodha, read when the final guard runs. Fail closed."""
    closed = {"mode": TradingMode.LIVE, "live_enabled": True, "broker_authenticated": False}
    base = os.environ.get("CORE_API_URL", "http://core-api:8000")
    token = os.environ.get("CORE_API_TOKEN", "")
    if not base or not token:
        return closed
    try:
        status = _get(base, token, "/api/v1/system/status")
        zerodha = _get(base, token, "/api/v1/zerodha/status")
        ingestion = _get(base, token, "/api/v1/market/ingestion")
        mode = TradingMode(str(status.get("trading_mode")))
    except Exception as exc:
        logger.info("live_gate_unreadable error_type=%s", type(exc).__name__)
        return closed
    broker = bool(
        zerodha.get("configured")
        and zerodha.get("authenticated")
        and zerodha.get("live_enabled") is False
        and ingestion.get("authenticated")
        and not ingestion.get("credentials_rejected")
        and not ingestion.get("last_error")
    )
    return {"mode": mode, "live_enabled": status.get("live_enabled"), "broker_authenticated": broker}


def _get(base_url: str, token: str, path: str) -> dict:
    request = urllib.request.Request(base_url.rstrip("/") + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(path)
    return payload
