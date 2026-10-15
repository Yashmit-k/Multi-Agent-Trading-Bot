import pytest

from intelligence_agents.agents.grounding import quality_gate
from intelligence_agents.llm.types import LLMAssessment
from intelligence_agents.llm.validate import ValidationError


def _assessment(codes: tuple[str, ...], sentiment: float = -0.3) -> LLMAssessment:
    return LLMAssessment(
        sentiment=sentiment, impact=0.2, confidence=0.3, event_type="context.note", reason_codes=codes,
        horizon="SWING", high_impact=False, model="openai/gpt-oss-20b", tier="tier1",
    )


def test_price_move_is_supported_by_a_price_headline() -> None:
    result = quality_gate(_assessment(("price_move",)), task="news", evidence="Sun Pharma down 2%, stock hits over 5-month low")
    assert result.reason_codes == ("price_move",)
    assert result.sentiment == -0.3


def test_price_move_needs_price_language() -> None:
    with pytest.raises(ValidationError):
        quality_gate(_assessment(("price_move",)), task="news", evidence="Board meeting scheduled to consider dividend")


def test_insufficient_data_is_a_neutral_llm_answer() -> None:
    result = quality_gate(_assessment(("insufficient_data",)), task="news", evidence="Board meeting scheduled")
    assert result.reason_codes == ("insufficient_data",)
    assert result.sentiment == 0.0 and result.impact == 0.0
    assert result.fallback is False


def test_invented_codes_are_still_rejected() -> None:
    with pytest.raises(ValidationError):
        quality_gate(_assessment(("rocket_ship",)), task="news", evidence="Infosys shares jump")


def test_new_codes_need_matching_evidence() -> None:
    ok = quality_gate(_assessment(("capital_raise",)), task="news", evidence="Reliance Jio files RHP for IPO; issue opens October 21")
    assert ok.reason_codes == ("capital_raise",)
    assert quality_gate(_assessment(("analyst_view",)), task="news", evidence="Brokerage raises target price on TCS").reason_codes == ("analyst_view",)
    assert quality_gate(_assessment(("results_preview",)), task="news", evidence="Wipro Q2 results preview: margins in focus").reason_codes == ("results_preview",)
    assert quality_gate(_assessment(("operating_updates",)), task="news", evidence="Tata Motors announces partnership for EV plant").reason_codes == ("operating_updates",)
    with pytest.raises(ValidationError):
        quality_gate(_assessment(("capital_raise",)), task="news", evidence="Sun Pharma shares hit 5-month low")
