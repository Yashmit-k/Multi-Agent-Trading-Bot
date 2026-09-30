from datetime import datetime, timedelta, timezone

import pytest
from contracts.enums import Horizon, Timeframe
from contracts.fakes import FakeFundamentalProvider, FakeNewsProvider

from quant_agents.calendar.static_nse import StaticNseCalendar
from quant_agents.clock import ReplayClock
from quant_agents.providers.compat import reset_compat_warning
from quant_agents.testing.harness import OPEN_AS_OF

@pytest.fixture
def calendar() -> StaticNseCalendar:
    return StaticNseCalendar()


@pytest.fixture
def clock():
    return ReplayClock(OPEN_AS_OF)


@pytest.fixture(autouse=True)
def _reset_compat() -> None:
    reset_compat_warning()
