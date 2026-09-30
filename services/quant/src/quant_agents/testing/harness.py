from datetime import datetime, timezone

from contracts.enums import Horizon, Timeframe
from contracts.fakes import FakeFundamentalProvider, FakeNewsProvider

from quant_agents.testing.audit import AuditingContext

OPEN_AS_OF = datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc)
SWING_CONFIG = {"horizon": Horizon.SWING, "timeframe": Timeframe.D1}
INTRADAY_CONFIG = {"horizon": Horizon.INTRADAY, "timeframe": Timeframe.M5}


def make_context(provider, config=None):
    context, calls = AuditingContext(
        feature_provider=provider,
        news_provider=FakeNewsProvider(),
        fundamental_provider=FakeFundamentalProvider(),
        configuration=dict(config or SWING_CONFIG),
    )
    return context, calls
