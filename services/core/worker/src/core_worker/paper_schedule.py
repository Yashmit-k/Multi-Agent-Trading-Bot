"""One guarded paper cycle during the cash session.

New buys are limited to the ordinary entry window, a fresh 50-name book, an
authenticated broker, and the daily entry cap. Fills, expiries, and sells still
run for the rest of the cash session. The continuous loop lives in ``__main__``.
"""

import json
import logging
import urllib.request
from datetime import datetime

from contracts.enums import Horizon, TradingMode
from core_db.repository import CoreRepository
from core_ingestion.service import EventPublisher
from core_paper.costs import CostSchedule
from core_paper.cycle import run_paper_cycle
from core_paper.trading_calendar import cash_session_open

logger = logging.getLogger(__name__)


def broker_allows_entries(base_url: str, token: str, *, urlopen=urllib.request.urlopen) -> bool:
    """Fail closed. A missing token or any request error blocks new buys."""
    if not base_url or not token:
        return False
    try:
        status = _get(urlopen, base_url, token, "/api/v1/system/status")
        zerodha = _get(urlopen, base_url, token, "/api/v1/zerodha/status")
        ingestion = _get(urlopen, base_url, token, "/api/v1/market/ingestion")
    except Exception as exc:
        logger.info("broker_check_failed error_type=%s", type(exc).__name__)
        return False
    if status.get("trading_mode") != TradingMode.PAPER.value or status.get("live_enabled") is not False:
        return False
    if not zerodha.get("configured") or not zerodha.get("authenticated") or zerodha.get("live_enabled") is not False:
        return False
    if not ingestion.get("authenticated") or ingestion.get("credentials_rejected") or ingestion.get("last_error"):
        return False
    return True


def excluded_agent_weights(raw: str) -> dict[Horizon, dict[str, float]] | None:
    """Weight 0 on every horizon for each listed agent, e.g. agents with no live data source."""
    names = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not names:
        return None
    return {horizon: {name: 0.0 for name in names} for horizon in Horizon}


def run_scheduled_cycle(
    repository: CoreRepository,
    publisher: EventPublisher,
    *,
    mode: TradingMode,
    schedule: CostSchedule | None,
    now: datetime,
    broker_authenticated: bool,
    weights: dict | None = None,
) -> int:
    """Settle and exit whenever the cash session is open. Enter only inside the entry window."""
    if mode != TradingMode.PAPER or not cash_session_open(now):
        return 0
    book = repository.active_paper_session()
    if book is None or book.starting_cash is None:
        return 0
    return run_paper_cycle(
        repository,
        publisher,
        mode=TradingMode.PAPER,
        starting_cash=book.starting_cash,
        weights=weights,
        schedule=schedule,
        require_fresh=True,
        now=now,
        enforce_entry_window=True,
        require_universe_fresh=True,
        broker_authenticated=broker_authenticated,
    )


def _get(urlopen, base_url: str, token: str, path: str) -> dict:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        headers={"Authorization": f"Bearer {token}"},
    )
    with urlopen(request, timeout=8) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(path)
    return payload
