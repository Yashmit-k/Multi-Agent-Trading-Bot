"""Dev 3 platform checks. Safety assertions stay strict."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from contracts.enums import Exchange, Timeframe, TradingMode
from contracts.fixtures import FIXTURE_AS_OF, candles_for
from contracts.schemas.market import Candle
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_features.engine import FEATURE_VERSION, build_feature_set
from core_ingestion.service import MemoryEventPublisher
from core_market_data.replay import bar_visible
from core_paper.costs import CostSchedule
from core_paper.cycle import kill_switch, paper_schedule, run_paper_cycle
from test_phase4 import _prepare_buy

ROOT = Path(__file__).resolve().parents[1]


def _bar(symbol: str, end: datetime, close: str, *, open_: str | None = None) -> Candle:
    price = Decimal(close)
    opened = Decimal(open_ or close)
    return Candle(
        symbol=symbol,
        exchange=Exchange.NSE,
        timeframe=Timeframe.D1,
        open=opened,
        high=max(price, opened) + Decimal("1"),
        low=min(price, opened) - Decimal("1"),
        close=price,
        volume=1000,
        start=end - timedelta(hours=6),
        end=end,
    )


def test_short_history_omits_indicators_and_marks_imbalance_unavailable() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar("RELIANCE", start + timedelta(days=index), str(100 + index)) for index in range(3)]
    feature = build_feature_set("RELIANCE", Timeframe.D1, bars, bars[-1].end)
    assert feature is not None
    assert feature.feature_version == FEATURE_VERSION == "1.1.0"
    assert "trend_strength_adx" not in feature.features
    assert "volatility_percentile" not in feature.features
    assert "volume_imbalance" in feature.unavailable
    assert "volume_imbalance" not in feature.features


def test_relative_strength_uses_the_supplied_index_return() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar("RELIANCE", start + timedelta(days=index), str(100 + index)) for index in range(5)]
    feature = build_feature_set("RELIANCE", Timeframe.D1, bars, bars[-1].end, nifty_return=0.01)
    assert feature is not None
    assert "relative_strength_nifty" in feature.features
    missing = build_feature_set("RELIANCE", Timeframe.D1, bars, bars[-1].end)
    assert missing is not None
    assert "relative_strength_nifty" not in missing.features


def test_future_bar_is_excluded() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar("RELIANCE", start + timedelta(days=index), str(100 + index)) for index in range(4)]
    feature = build_feature_set("RELIANCE", Timeframe.D1, bars, bars[1].end)
    assert feature is not None
    assert feature.source_data_timestamp == bars[1].end


def test_agents_do_not_compute_feature_set_1_1_fields() -> None:
    agents = ROOT / "services" / "quant" / "src" / "quant_agents" / "agents"
    banned = ("def _adx", "def _half_life", "bollinger_pct_b =", "reversion_half_life =")
    for path in agents.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text


def test_unconfigured_paper_cost_is_two_bps_and_explicit_zero_stays_zero() -> None:
    assert paper_schedule(None).flat_bps == Decimal("2")
    assert paper_schedule(CostSchedule.research(Decimal("0"), Decimal("0"))).flat_bps == Decimal("0")


def test_bar_visible_hides_a_later_end() -> None:
    as_of = datetime(2024, 6, 3, tzinfo=timezone.utc)
    assert bar_visible(as_of, as_of)
    assert not bar_visible(as_of + timedelta(minutes=5), as_of)


def test_kill_switch_queues_a_flatten_and_waits_for_the_next_bar(repository: CoreRepository) -> None:
    _prepare_buy(repository)
    publisher = MemoryEventPublisher()
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=Decimal("1000000"))
    later = FIXTURE_AS_OF + timedelta(days=1)
    repository.upsert_candles([_bar("RELIANCE", later, "2935", open_="2930")])
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=Decimal("1000000"))
    assert repository.position_for("RELIANCE") is not None
    assert kill_switch(repository) is True
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=Decimal("1000000"))
    assert repository.position_for("RELIANCE") is not None
    nxt = later + timedelta(days=1)
    repository.upsert_candles([_bar("RELIANCE", nxt, "2940", open_="2936")])
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=Decimal("1000000"))
    assert repository.position_for("RELIANCE") is None


def test_agent_routes_and_news_proxy(repository: CoreRepository) -> None:
    settings = Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        core_api_token="core",
        internal_signal_token="internal",
        max_clock_skew_seconds=5,
        trading_mode=TradingMode.PAPER,
    )
    app = create_app(settings, repository, MemoryEventPublisher())

    class Down:
        def rows(self, kind: str, symbol: str, as_of: str | None) -> list[dict[str, object]]:
            raise ConnectionError(kind)

        def health(self) -> dict[str, object]:
            return {"status": "degraded", "reason": "no_signal_sink"}

    app.state.intelligence_client = Down()
    client = TestClient(app)
    headers = {"Authorization": "Bearer core"}
    agents = client.get("/api/v1/agents", headers=headers)
    assert agents.status_code == 200
    names = {row["agent_name"]: row for row in agents.json()}
    assert names["technical"]["enabled"] is True
    assert names["ml"]["enabled"] is False
    assert names["technical"]["feature_version"] == "1.1.0"
    news = client.get("/api/v1/stocks/RELIANCE/news", headers=headers)
    assert news.status_code == 503
    health = client.get("/api/v1/agents/news/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["enabled"] is False
    assert health.json()["reason"] == "no_signal_sink"

    class Up:
        def rows(self, kind: str, symbol: str, as_of: str | None) -> list[dict[str, object]]:
            if symbol == "EMPTY":
                return []
            return [{"symbol": symbol, "kind": kind}]

        def health(self) -> dict[str, object]:
            return {"status": "ok"}

    app.state.intelligence_client = Up()
    assert client.get("/api/v1/stocks/RELIANCE/fundamentals", headers=headers).json() == [
        {"symbol": "RELIANCE", "kind": "fundamentals"}
    ]
    assert client.get("/api/v1/stocks/EMPTY/news", headers=headers).json() == []
