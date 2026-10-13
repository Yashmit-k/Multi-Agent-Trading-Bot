import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import TradingMode
from core_db.repository import CoreRepository
from core_db.seed import load_seed
from core_db.session import create_schema
from core_ingestion.service import MemoryEventPublisher, RedisEventPublisher
from core_paper.costs import CostSchedule
from core_paper.trading_calendar import cash_session_open
from core_worker.heartbeat import publish_heartbeat
from core_worker.loop import run_once
from core_worker.paper_schedule import broker_allows_entries, run_scheduled_cycle

logger = logging.getLogger(__name__)

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
while True:
    now = datetime.now(timezone.utc)
    publish_heartbeat(api_base, api_token, now, interval_seconds=interval)
    if mode != TradingMode.PAPER:
        logger.error("paper_worker_refused mode=%s", mode.value)
    elif cash_session_open(now):
        run_once(repository, now)
        authenticated = broker_allows_entries(api_base, api_token)
        run_scheduled_cycle(
            repository,
            publisher,
            mode=TradingMode.PAPER,
            schedule=schedule,
            now=now,
            broker_authenticated=authenticated,
        )
    time.sleep(interval)
