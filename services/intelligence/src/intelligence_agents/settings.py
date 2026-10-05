"""Environment for the intelligence service. Secrets never enter AgentContext."""

from __future__ import annotations

import os
from dataclasses import dataclass

from contracts.enums import TradingMode

from intelligence_agents.errors import ConfigError

LIVE_SOURCES = frozenset({"rss", "csv-live"})
LIVE_MODES = frozenset({TradingMode.PAPER, TradingMode.SHADOW, TradingMode.LIVE})


@dataclass(frozen=True, slots=True)
class IntelligenceSettings:
    data_source: str
    trading_mode: TradingMode
    store: str
    sqlite_path: str
    log_level: str
    symbols: tuple[str, ...]
    eval_interval_seconds: int
    core_api_url: str
    internal_signal_token: str
    llm_base_url: str
    llm_api_key: str
    llm_tier1_model: str
    llm_tier2_model: str
    llm_daily_budget_usd: float
    llm_timeout_seconds: float
    news_rss_urls: tuple[str, ...]
    tier2_enabled: bool
    rss_interval_seconds: int
    rss_max_bytes: int
    rss_max_items: int
    service_mode: str

    @classmethod
    def from_env(cls) -> IntelligenceSettings:
        mode = TradingMode(os.environ.get("INTELLIGENCE_TRADING_MODE", "BACKTEST"))
        source = os.environ.get("INTELLIGENCE_DATA_SOURCE", "fixtures").strip().lower()
        store = os.environ.get("INTELLIGENCE_STORE", "sqlite").strip().lower()
        symbols_raw = os.environ.get("INTELLIGENCE_SYMBOLS", "RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK")
        rss_raw = os.environ.get("NEWS_RSS_URLS", "")
        settings = cls(
            data_source=source,
            trading_mode=mode,
            store=store,
            sqlite_path=os.environ.get("INTELLIGENCE_SQLITE_PATH", "intelligence.db"),
            log_level=os.environ.get("INTELLIGENCE_LOG_LEVEL", "INFO"),
            symbols=tuple(item.strip().upper() for item in symbols_raw.split(",") if item.strip()),
            eval_interval_seconds=int(os.environ.get("INTELLIGENCE_EVAL_INTERVAL_SECONDS", "300")),
            core_api_url=os.environ.get("CORE_API_URL", "http://localhost:8000").rstrip("/"),
            internal_signal_token=os.environ.get("INTERNAL_SIGNAL_TOKEN", ""),
            llm_base_url=os.environ.get("LLM_BASE_URL", ""),
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            llm_tier1_model=os.environ.get("LLM_TIER1_MODEL", "fixture"),
            llm_tier2_model=os.environ.get("LLM_TIER2_MODEL", "fixture"),
            llm_daily_budget_usd=float(os.environ.get("LLM_DAILY_BUDGET_USD", "0")),
            llm_timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", "30")),
            news_rss_urls=tuple(item.strip() for item in rss_raw.split(",") if item.strip()),
            tier2_enabled=os.environ.get("INTELLIGENCE_TIER2_ENABLED", "false").lower() == "true",
            rss_interval_seconds=int(os.environ.get("NEWS_RSS_INTERVAL_SECONDS", "300")),
            rss_max_bytes=int(os.environ.get("NEWS_RSS_MAX_BYTES", str(1024 * 1024))),
            rss_max_items=int(os.environ.get("NEWS_RSS_MAX_ITEMS", "100")),
            service_mode=os.environ.get("INTELLIGENCE_SERVICE_MODE", "oneshot").strip().lower(),
        )
        settings.validate()
        return settings

    def llm_mode(self) -> str:
        if self.llm_api_key and self.llm_base_url:
            return "openai"
        return "fixture"

    def llm_provider(self) -> str:
        from intelligence_agents.llm.router import provider_name_from_url

        if not self.llm_api_key or not self.llm_base_url:
            return "fixture"
        return provider_name_from_url(self.llm_base_url)

    def llm_host(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.llm_base_url).hostname or ""

    def validate(self) -> None:
        if self.data_source not in {"fixtures", "rss", "csv-live"}:
            raise ConfigError(f"unknown INTELLIGENCE_DATA_SOURCE: {self.data_source}")
        if self.store not in {"sqlite", "memory"}:
            raise ConfigError(f"unknown INTELLIGENCE_STORE: {self.store}")
        if self.service_mode not in {"oneshot", "serve"}:
            raise ConfigError(f"unknown INTELLIGENCE_SERVICE_MODE: {self.service_mode}")
        if self.service_mode == "serve" and self.trading_mode is TradingMode.BACKTEST:
            raise ConfigError("BACKTEST is oneshot only; do not serve it from uvicorn")
        if self.trading_mode is TradingMode.BACKTEST and self.data_source in LIVE_SOURCES:
            raise ConfigError("BACKTEST cannot use RSS or csv-live; fixtures only")
        if self.data_source == "rss" and not self.news_rss_urls and self.trading_mode in LIVE_MODES:
            raise ConfigError("NEWS_RSS_URLS required when INTELLIGENCE_DATA_SOURCE=rss")
        if not self.symbols:
            raise ConfigError("INTELLIGENCE_SYMBOLS must list at least one symbol")
        if self.service_mode == "serve" and self.trading_mode in LIVE_MODES:
            if not self.internal_signal_token or not self.core_api_url:
                raise ConfigError("PAPER/SHADOW/LIVE serve requires CORE_API_URL and INTERNAL_SIGNAL_TOKEN")
