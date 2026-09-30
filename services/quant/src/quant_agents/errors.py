"""Quant-local errors. LeakageError is never swallowed in BACKTEST."""


class QuantError(Exception):
    """Base class."""


class ConfigError(QuantError):
    """Invalid horizon/timeframe configuration."""


class LeakageError(QuantError):
    """Agent saw data with timestamp or source_data_timestamp after as_of."""


class CalendarCoverageError(QuantError):
    """Calendar method called for a date outside the covered range."""
