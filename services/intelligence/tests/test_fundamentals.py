from datetime import datetime, timezone
from decimal import Decimal

from contracts.fixtures import FIXTURE_AS_OF, all_fundamentals
from contracts.schemas.fundamental import FundamentalDataPoint

from intelligence_agents.fundamentals.csv_loader import load_csv_text
from intelligence_agents.fundamentals.provider import IntelligenceFundamentalProvider
from intelligence_agents.fundamentals.store import MemoryFundamentalStore
from intelligence_agents.news.fixtures import load_fundamental_fixtures


def test_q1_hidden_until_available():
    store = MemoryFundamentalStore()
    load_fundamental_fixtures(store)
    provider = IntelligenceFundamentalProvider(store)
    visible = provider.get_fundamentals("RELIANCE", FIXTURE_AS_OF)
    assert all(point.available_at <= FIXTURE_AS_OF for point in visible)
    assert not any(point.period == "Q1FY2025" for point in visible)


def test_restatement_is_new_row():
    store = MemoryFundamentalStore()
    original = all_fundamentals("RELIANCE")[0]
    store.insert(original)
    restated = original.model_copy(
        update={
            "source_id": original.source_id + "-restated",
            "value": Decimal("50.00"),
            "available_at": datetime(2024, 8, 1, tzinfo=timezone.utc),
        }
    )
    store.insert(restated)
    early = store.points_for("RELIANCE", FIXTURE_AS_OF)
    later = store.points_for("RELIANCE", datetime(2024, 8, 2, tzinfo=timezone.utc))
    assert len(later) == len(early) + 1


def test_csv_loader():
    store = MemoryFundamentalStore()
    text = (
        "symbol,metric,value,unit,period,announced_at,available_at,source,source_id\n"
        "RELIANCE,roe,15.2,pct,FY2024,2024-04-20T10:00:00+00:00,2024-04-20T12:00:00+00:00,csv,rel-roe-1\n"
    )
    assert load_csv_text(store, text) == 1
    assert store.points_for("RELIANCE", FIXTURE_AS_OF)[0].metric == "roe"
