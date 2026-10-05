import pytest

from intelligence_agents.agents.grounding import quality_gate
from intelligence_agents.llm.types import LLMAssessment
from intelligence_agents.llm.validate import ValidationError


def _assessment(*codes: str, model: str = "phi3:mini", fallback: bool = False) -> LLMAssessment:
    return LLMAssessment(
        sentiment=0.1,
        impact=0.3,
        confidence=0.4,
        event_type="context.note",
        reason_codes=codes,
        horizon="SWING",
        high_impact=False,
        model=model,
        tier="tier1",
        fallback=fallback,
    )


def test_article_id_is_not_a_reason_code():
    with pytest.raises(ValidationError, match="unsupported_reason"):
        quality_gate(
            _assessment("news_tcs_20240603", "tcs"),
            task="news",
            evidence="TCS fixture headline news-tcs-20240603. The company reported steady operating updates.",
            raw='{"reason_codes":["news_tcs_20240603"]}',
        )


def test_news_keeps_operating_updates_when_supported():
    out = quality_gate(
        _assessment("operating_updates", "profit_growth"),
        task="news",
        evidence="The company reported steady operating updates.",
    )
    assert out.reason_codes == ("operating_updates",)


def test_news_rejects_profit_growth_without_growth_language():
    with pytest.raises(ValidationError, match="unsupported_reason"):
        quality_gate(_assessment("profit_growth"), task="news", evidence="The company reported steady operating updates.")


def test_fundamental_keeps_eps_when_metric_present():
    out = quality_gate(_assessment("eps"), task="fundamental", evidence="metrics={'eps': '48.25'}")
    assert out.reason_codes == ("eps",)


def test_earnings_codes_must_be_allowlisted_and_supported():
    out = quality_gate(
        _assessment("eps", "operating_updates"),
        task="earnings",
        evidence="metrics={'eps': '12.5'} The company reported steady operating updates.",
    )
    assert out.reason_codes == ("eps", "operating_updates")
    with pytest.raises(ValidationError, match="unsupported_reason"):
        quality_gate(_assessment("revenue_growth"), task="earnings", evidence="metrics={'eps': '12.5'}")


def test_valuation_maps_price_synonym_to_last_price():
    out = quality_gate(
        _assessment("valuation.price", "profit_growth"),
        task="valuation",
        evidence="last_price=2500 eps=48.25 implied_pe=51.8",
    )
    assert out.reason_codes == ("last_price",)


def test_unsupported_and_order_language_raise_not_fake_codes():
    with pytest.raises(ValidationError, match="unsupported_reason") as unsupported:
        quality_gate(_assessment("made_up_token"), task="news", evidence="random commentary without cues")
    assert unsupported.value.failure_type == "unsupported_reason"
    with pytest.raises(ValidationError, match="order_language") as order:
        quality_gate(
            _assessment("operating_updates"),
            task="news",
            evidence="The company reported steady operating updates.",
            raw='{"reason_codes":["operating_updates"],"note":"BUY now"}',
        )
    assert order.value.failure_type == "order_language"


def test_fixture_provider_keeps_heuristic_code():
    out = quality_gate(
        _assessment("fixture.heuristic", model="fixture"),
        task="news",
        evidence="operating updates",
    )
    assert out.reason_codes == ("fixture.heuristic",)
    fallback = quality_gate(
        _assessment("fixture.heuristic", fallback=True),
        task="news",
        evidence="operating updates",
    )
    assert fallback.reason_codes == ("fixture.heuristic",)


def test_quality_gate_does_not_invent_residual_tokens():
    with pytest.raises(ValidationError, match="unsupported_reason"):
        quality_gate(_assessment("headline", "wire"), task="news", evidence="headline on the wire")
