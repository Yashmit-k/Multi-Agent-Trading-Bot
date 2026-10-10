"""Intelligence-local errors. LeakageError is never swallowed in BACKTEST."""


class IntelligenceError(Exception):
    """Base class."""


class ConfigError(IntelligenceError):
    """Invalid mode/source combination or settings."""


class LeakageError(IntelligenceError):
    """Provider returned data that was not knowable at as_of."""


class LLMProviderError(IntelligenceError):
    """Observable LLM failure. Never silently invents an assessment."""

    def __init__(self, failure_type: str, message: str = "") -> None:
        super().__init__(message or failure_type)
        self.failure_type = failure_type
