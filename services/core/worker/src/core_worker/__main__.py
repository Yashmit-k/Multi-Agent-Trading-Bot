import os
import time
from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import TradingMode
from core_db.repository import CoreRepository
from core_db.seed import load_seed
from core_db.session import create_schema
from core_ingestion.service import MemoryEventPublisher, RedisEventPublisher
from core_paper import run_paper_cycle
from core_paper.costs import CostSchedule
from core_worker.loop import run_once

database_url = os.environ.get("DATABASE_URL", "sqlite:///./core.db")
repository = CoreRepository(create_schema(database_url))
load_seed(repository)
interval = int(os.environ.get("WORKER_INTERVAL_SECONDS", "30"))
mode = TradingMode(os.environ.get("TRADING_MODE", TradingMode.PAPER.value))
starting_cash = Decimal(os.environ.get("PAPER_STARTING_CASH", "1000000"))
redis_url = os.environ.get("REDIS_URL", "")
if redis_url:
    import redis

    publisher = RedisEventPublisher(redis.Redis.from_url(redis_url))
else:
    publisher = MemoryEventPublisher()
cost_raw = os.environ.get("PAPER_TRANSACTION_COST_BPS")
slip_raw = os.environ.get("PAPER_SLIPPAGE_BPS", "0")
schedule = None if cost_raw is None else CostSchedule.research(Decimal(cost_raw), Decimal(slip_raw))
require_fresh = os.environ.get("PAPER_REQUIRE_FRESH_CANDLES", "true").strip().lower() not in {"0", "false", "no"}
while True:
    run_once(repository, datetime.now(timezone.utc))
    run_paper_cycle(
        repository,
        publisher,
        mode=mode,
        starting_cash=starting_cash,
        schedule=schedule,
        require_fresh=require_fresh,
    )
    time.sleep(interval)
