"""Intelligence-local errors. LeakageError is never swallowed in BACKTEST."""


class IntelligenceError(Exception):
    """Base class."""


class ConfigError(IntelligenceError):
    """Invalid mode/source combination or settings."""


class LeakageError(IntelligenceError):
    """Provider returned data that was not knowable at as_of."""
