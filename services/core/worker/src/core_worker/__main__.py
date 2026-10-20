import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from contracts.enums import TradingMode
from core_db.repository import CoreRepository
from core_db.seed import load_seed
from core_db.session import create_schema
from core_ingestion.service import MemoryEventPublisher, RedisEventPublisher
from core_paper.costs import CostSchedule
from core_paper.trading_calendar import cash_session_open
from core_worker.heartbeat import publish_heartbeat
from core_worker.loop import run_once
from core_paper.daily import write_daily_if_due
from core_worker.agent_weights import current_weights
from core_worker.notify import Notifier, health_problems_from_api, maybe_notify
from core_worker.paper_schedule import broker_allows_entries, excluded_agent_weights, run_scheduled_cycle

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

database_url = os.environ.get("DATABASE_URL", "sqlite:///./core.db")
repository = CoreRepository(create_schema(database_url))
load_seed(repository)
interval = int(os.environ.get("WORKER_INTERVAL_SECONDS", "30"))
mode = TradingMode(os.environ.get("TRADING_MODE", TradingMode.PAPER.value))
redis_url = os.environ.get("REDIS_URL", "")
if redis_url:
    import redis

    publisher = RedisEventPublisher(redis.Redis.from_url(redis_url))
else:
    publisher = MemoryEventPublisher()
cost_raw = os.environ.get("PAPER_TRANSACTION_COST_BPS")
slip_raw = os.environ.get("PAPER_SLIPPAGE_BPS", "0")
schedule = None if cost_raw is None else CostSchedule.research(Decimal(cost_raw), Decimal(slip_raw))
api_base = os.environ.get("CORE_API_URL", "http://core-api:8000")
api_token = os.environ.get("CORE_API_TOKEN", "")
weights = excluded_agent_weights(os.environ.get("FUSION_EXCLUDED_AGENTS", ""))
logger.info("fusion_excluded_agents agents=%s", os.environ.get("FUSION_EXCLUDED_AGENTS", ""))
failed_cycles = 0
last_error: str | None = None
excluded = {item.strip().lower() for item in os.environ.get("FUSION_EXCLUDED_AGENTS", "").split(",") if item.strip()}
notifier = Notifier.from_env()
site_url = os.environ.get("PUBLIC_SITE_URL", "")
logger.info("notifications configured=%s", notifier.configured)
while True:
    now = datetime.now(timezone.utc)
    publish_heartbeat(api_base, api_token, now, interval_seconds=interval, failed_cycles=failed_cycles, last_error=last_error)
    if mode != TradingMode.PAPER:
        logger.error("paper_worker_refused mode=%s", mode.value)
    elif cash_session_open(now):
        # One failing cycle must not kill the worker: log it, skip this cycle, and try again next interval.
        try:
            run_once(repository, now)
            authenticated = broker_allows_entries(api_base, api_token)
            live_weights = current_weights(repository, now, excluded) or weights
            run_scheduled_cycle(
                repository,
                publisher,
                mode=TradingMode.PAPER,
                schedule=schedule,
                now=now,
                broker_authenticated=authenticated,
                weights=live_weights,
            )
            failed_cycles, last_error = 0, None
        except Exception as exc:
            failed_cycles += 1
            last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("paper_cycle_failed consecutive=%s", failed_cycles)
    if mode == TradingMode.PAPER and not cash_session_open(now):
        try:
            current_weights(repository, now, excluded)  # hourly, so the Agents page is current on closed days too
        except Exception:
            logger.exception("agent_weights_refresh_failed")
    try:
        # History retention once a day after 17:00 IST (state in user_settings, so a restart does not repeat it).
        local_day = now.astimezone(IST).date().isoformat()
        if now.astimezone(IST).hour >= 17:
            state = repository.get_setting("maintenance_state")
            if not state or state["payload"].get("pruned") != local_day:
                counts = repository.prune_history(now)
                repository.save_setting("maintenance_state", {"pruned": local_day, "counts": counts}, updated_by="worker", now=now)
                logger.info("retention_done %s", counts)
    except Exception:
        logger.exception("retention_failed")
    try:
        # End-of-day book, once per trading day after the close (no-op at other times).
        write_daily_if_due(repository, now)
    except Exception:
        logger.exception("daily_equity_write_failed")
    try:
        # Morning Zerodha reminder and end-of-day summary (no-op unless Telegram or a webhook is configured).
        for key in maybe_notify(repository, notifier, now, site=site_url, health_problems=health_problems_from_api(api_base, api_token)):
            logger.info("notification_sent kind=%s", key)
    except Exception:
        logger.exception("notification_failed")
    time.sleep(interval)
