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
