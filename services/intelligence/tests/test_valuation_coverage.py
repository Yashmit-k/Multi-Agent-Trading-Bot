from contracts.enums import TradingMode
from contracts.fixtures import FIXTURE_AS_OF
from contracts.schemas.submission import SubmissionResult

from intelligence_agents.agents.valuation import ValuationAgent
from intelligence_agents.errors import FixtureCoverageError
from intelligence_agents.runner import Runner
from intelligence_agents.testing import CLOCK, make_context, make_stores

from test_agents import _router


class _Sink:
    def __init__(self) -> None:
        self.signals = []

    def submit(self, signal):
        self.signals.append(signal)
        return SubmissionResult(accepted=True, duplicate=False, signal_id=signal.signal_id, message="ok")


def test_valuation_evaluates_a_fixture_symbol() -> None:
    signal = ValuationAgent(CLOCK, _router()).evaluate("RELIANCE", FIXTURE_AS_OF, make_context(*make_stores()))
    assert signal.symbol == "RELIANCE"
    assert "last_price" in signal.features


def test_valuation_does_not_invent_a_price_for_a_missing_symbol() -> None:
    try:
        ValuationAgent(CLOCK, _router()).evaluate("TRENT", FIXTURE_AS_OF, make_context(*make_stores()))
    except FixtureCoverageError as exc:
        assert exc.symbol == "TRENT"
    else:
        raise AssertionError("missing fixture symbol produced a valuation signal")


def test_runner_skips_unsupported_symbols_and_keeps_supported_ones() -> None:
    news, funds = make_stores()
    sink = _Sink()
    runner = Runner(
        [ValuationAgent(CLOCK, _router())],
        sink,
        CLOCK,
        lambda _symbol, _as_of, _horizon: make_context(news, funds),
        TradingMode.PAPER,
    )
    produced = runner.run(("RELIANCE", "TRENT"), FIXTURE_AS_OF)
    assert [signal.symbol for signal in produced] == ["RELIANCE"]
    assert [signal.symbol for signal in sink.signals] == ["RELIANCE"]
    assert runner.skipped == [{"agent": "valuation", "symbol": "TRENT", "reason": "fixture_coverage"}]


def _with_points(rows: list[tuple[str, str]]):  # type: ignore[no-untyped-def]
    from datetime import timedelta

    from intelligence_agents.fundamentals.csv_loader import load_csv_text
    from intelligence_agents.fundamentals.store import MemoryFundamentalStore

    stamp = (FIXTURE_AS_OF - timedelta(days=1)).isoformat()
    lines = ["symbol,metric,value,unit,period,announced_at,available_at,source,source_id"]
    lines += [f"RELIANCE,{metric},{value},ratio,2026Q3,{stamp},{stamp},test,rel-{metric}" for metric, value in rows]
    store = MemoryFundamentalStore()
    load_csv_text(store, "\n".join(lines) + "\n")
    news, _ = make_stores()
    return make_context(news, store)


def test_valuation_compares_ttm_pe_with_sector_peers() -> None:
    probe = ValuationAgent(CLOCK, _router()).evaluate("RELIANCE", FIXTURE_AS_OF, _with_points([("eps", "1")]))
    price = float(probe.features["last_price"])
    cheap = ValuationAgent(CLOCK, _router()).evaluate("RELIANCE", FIXTURE_AS_OF, _with_points([("eps", str(price / 10)), ("peer_median_pe", "20")]))
    rich = ValuationAgent(CLOCK, _router()).evaluate("RELIANCE", FIXTURE_AS_OF, _with_points([("eps", str(price / 40)), ("peer_median_pe", "20")]))
    assert cheap.metadata["pe_basis"] == "sector_peers" and cheap.signal == 1.0  # P/E 10 vs peers 20: 50% cheaper saturates
    assert rich.signal == -1.0
    assert probe.metadata["pe_basis"] == "fixed_pe_20"  # no peer median: lower-confidence fallback


def _peer_rows(*rows: tuple[str, str, int]):  # type: ignore[no-untyped-def]
    """(metric, value, days before FIXTURE_AS_OF the row became available)."""
    from datetime import timedelta

    from intelligence_agents.fundamentals.csv_loader import load_csv_text
    from intelligence_agents.fundamentals.store import MemoryFundamentalStore

    lines = ["symbol,metric,value,unit,period,announced_at,available_at,source,source_id"]
    for metric, value, days in rows:
        stamp = (FIXTURE_AS_OF - timedelta(days=days)).isoformat()
        lines.append(f"RELIANCE,{metric},{value},ratio,{stamp[:10]},{stamp},{stamp},test,rel-{metric}-{days}")
    store = MemoryFundamentalStore()
    load_csv_text(store, "\n".join(lines) + "\n")
    news, _ = make_stores()
    return make_context(news, store)


def test_a_newer_zero_peer_count_retires_an_old_peer_median() -> None:
    agent = ValuationAgent(CLOCK, _router())
    stale = agent.evaluate("RELIANCE", FIXTURE_AS_OF, _peer_rows(("eps", "100", 5), ("peer_median_pe", "7.95", 3), ("peer_count", "0", 1)))
    assert stale.metadata["pe_basis"] == "fixed_pe_20"  # no comparable peers: the old 7.95 is ignored
    newer = agent.evaluate("RELIANCE", FIXTURE_AS_OF, _peer_rows(("eps", "100", 5), ("peer_count", "0", 3), ("peer_median_pe", "21", 1), ("peer_count", "4", 1)))
    assert newer.metadata["pe_basis"] == "sector_peers" and newer.features["peer_count"] == "4"
