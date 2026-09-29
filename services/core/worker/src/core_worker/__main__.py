import os
import time
from datetime import datetime, timezone

from core_db.repository import CoreRepository
from core_db.seed import load_seed
from core_db.session import create_schema
from core_worker.loop import run_once

database_url = os.environ.get("DATABASE_URL", "sqlite:///./core.db")
repository = CoreRepository(create_schema(database_url))
load_seed(repository)
interval = int(os.environ.get("WORKER_INTERVAL_SECONDS", "30"))
while True:
    run_once(repository, datetime.now(timezone.utc))
    time.sleep(interval)
