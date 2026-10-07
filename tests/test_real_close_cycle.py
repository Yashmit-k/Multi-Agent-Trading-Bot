"""One paper fill from the real RELIANCE and TCS closes. Agents, fusion, decision, and risk stay as they are."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from contracts.enums import AgentName, Exchange, Horizon, OrderStatus, Timeframe, TradingMode
from contracts.fixtures import sample_agent_signal
from contracts.schemas.market import Candle
from core_db.repository import CoreRepository
from core_db.session import create_schema
from core_features.engine import build_feature_set
from core_ingestion.service import MemoryEventPublisher, ingest_signal
from core_paper import run_paper_cycle
from quant_agents.paper import publish_symbol_signals

UTC = timezone.utc
RELIANCE_CLOSE = Decimal("1167.70")
TCS_CLOSE = Decimal("2075.00")
AS_OF = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


class _IngestSink:
    def __init__(self, repository: CoreRepository, publisher: MemoryEventPublisher) -> None:
        self._repository = repository
        self._publisher = publisher

    def submit(self, signal) -> None:
        ingest_signal(
            self._repository,
            self._publisher,
            signal,
            mode=TradingMode.PAPER,
            now=signal.timestamp,
            replay_as_of=None,
            skew_seconds=5,
        )


def test_real_closes_produce_one_filled_paper_order(repository: CoreRepository | None = None) -> None:
    repository = repository or CoreRepository(create_schema("sqlite://"))
    _store_symbol(repository, "RELIANCE", _rising_closes(RELIANCE_CLOSE))
    _store_symbol(repository, "TCS", (TCS_CLOSE, TCS_CLOSE))
    moment = repository.stored_candles("RELIANCE", Timeframe.D1)[-1].end
    features = build_feature_set("RELIANCE", Timeframe.D1, repository.stored_candles("RELIANCE", Timeframe.D1), moment)
    assert features is not None
    publisher = MemoryEventPublisher()
    assert publish_symbol_signals("RELIANCE", features, _IngestSink(repository, publisher)) == 5
    news = sample_agent_signal("RELIANCE").model_copy(
        update={
            "signal_id": "sig-reliance-news-proof",
            "agent_name": AgentName.NEWS,
            "horizon": Horizon.SWING,
            "timestamp": moment,
            "as_of": moment,
            "valid_until": moment + timedelta(days=10),
        }
    )
    stored = ingest_signal(
        repository,
        publisher,
        news,
        mode=TradingMode.PAPER,
        now=moment,
        replay_as_of=None,
        skew_seconds=5,
    )
    assert stored.accepted
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=Decimal("1000000"))
    orders = repository.list_orders()
    assert len(orders) == 1
    assert orders[0].status == OrderStatus.OPEN
    nxt = moment + timedelta(days=1)
    repository.upsert_candles(
        [
            Candle(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=Decimal("1170.00"),
                high=Decimal("1180.00"),
                low=Decimal("1160.00"),
                close=Decimal("1175.00"),
                volume=1000,
                start=nxt - timedelta(hours=6),
                end=nxt,
            )
        ]
    )
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=Decimal("1000000"))
    orders = repository.list_orders()
    assert orders[0].status == OrderStatus.FILLED
    assert orders[0].symbol == "RELIANCE"
    fills = repository.list_executions()
    assert len(fills) == 1
    assert fills[0].price == Decimal("1170.00")


def _store_symbol(repository: CoreRepository, symbol: str, closes: tuple[Decimal, ...]) -> None:
    instrument = repository.upsert_instrument(symbol=symbol, exchange="NSE", trading_symbol=symbol)
    assert instrument.instrument_id == f"NSE:{symbol}"
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    bars = []
    day = AS_OF.date()
    for close in reversed(closes):
        while day.weekday() >= 5:
            day = day - timedelta(days=1)
        start = datetime(day.year, day.month, day.day, 3, 45, tzinfo=UTC)
        end = datetime(day.year, day.month, day.day, 10, 0, tzinfo=UTC)
        bars.append(
            Candle(
                symbol=symbol,
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=close - Decimal("1.00"),
                high=close + Decimal("1.00"),
                low=close - Decimal("2.00"),
                close=close,
                volume=1_000 + len(bars) * 50,
                start=start,
                end=end,
            )
        )
        day = day - timedelta(days=1)
    repository.upsert_candles(list(reversed(bars)))


def _rising_closes(last: Decimal) -> tuple[Decimal, ...]:
    count = 40
    start = Decimal("900.00")
    step = (last - start) / Decimal(count - 1)
    return tuple((start + step * index).quantize(Decimal("0.01")) for index in range(count))
