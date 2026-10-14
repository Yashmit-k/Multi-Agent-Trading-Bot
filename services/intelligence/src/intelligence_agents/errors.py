"""Intelligence-local errors. LeakageError is never swallowed in BACKTEST."""


class IntelligenceError(Exception):
    """Base class."""


class ConfigError(IntelligenceError):
    """Invalid mode/source combination or settings."""


class LeakageError(IntelligenceError):
    """Provider returned data that was not knowable at as_of."""


class FixtureCoverageError(IntelligenceError):
    """The fixture set has no quote for this symbol. No price is invented."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"no fixture quote for {symbol}")


class LLMProviderError(IntelligenceError):
    """Observable LLM failure. Never silently invents an assessment."""

    def __init__(self, failure_type: str, message: str = "") -> None:
        super().__init__(message or failure_type)
        self.failure_type = failure_type
