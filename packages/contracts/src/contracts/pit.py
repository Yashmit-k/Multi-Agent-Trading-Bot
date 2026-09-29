"""Point-in-time gate for fundamental data."""

from collections.abc import Sequence
from datetime import datetime

from contracts.schemas.fundamental import FundamentalDataPoint
from contracts.time import require_aware


class FutureDataError(ValueError):
    """Raised when a fundamental point was not yet available at as_of."""


def assert_available(point: FundamentalDataPoint, as_of: datetime) -> FundamentalDataPoint:
    """Return the point when ``available_at <= as_of``.

    Backtests and paper replay must call this before an agent can see the row.
    """
    aware_as_of = require_aware(as_of, "as_of")
    if point.available_at > aware_as_of:
        raise FutureDataError(
            f"{point.symbol} {point.metric} {point.period} available_at "
            f"{point.available_at.isoformat()} is after as_of {aware_as_of.isoformat()}"
        )
    return point


def filter_available(
    points: Sequence[FundamentalDataPoint],
    as_of: datetime,
) -> list[FundamentalDataPoint]:
    """Drop points that were not available at as_of. Order is preserved."""
    aware_as_of = require_aware(as_of, "as_of")
    return [point for point in points if point.available_at <= aware_as_of]
