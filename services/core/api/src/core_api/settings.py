import os
from dataclasses import dataclass
from decimal import Decimal

from contracts.enums import TradingMode


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    core_api_token: str
    internal_signal_token: str
    max_clock_skew_seconds: int
    trading_mode: TradingMode
    paper_starting_cash: Decimal = Decimal("1000000")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", "sqlite:///./core.db"),
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            core_api_token=os.environ.get("CORE_API_TOKEN", "dev-core-token"),
            internal_signal_token=os.environ.get("INTERNAL_SIGNAL_TOKEN", "dev-internal-token"),
            max_clock_skew_seconds=int(os.environ.get("MAX_CLOCK_SKEW_SECONDS", "5")),
            trading_mode=TradingMode(os.environ.get("TRADING_MODE", TradingMode.PAPER.value)),
            paper_starting_cash=Decimal(os.environ.get("PAPER_STARTING_CASH", "1000000")),
        )
