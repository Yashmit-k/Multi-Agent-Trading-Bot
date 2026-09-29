"""Contract tests for AgentSignal."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.fixtures import FIXTURE_AS_OF, sample_agent_signal
from contracts.schemas.agent_signal import AgentSignal


def test_valid_agent_signal_succeeds() -> None:
    signal = sample_agent_signal()
    parsed = AgentSignal.model_validate(signal.model_dump())
    assert parsed.signal_id == "sig-reliance-technical-20240603"
    assert parsed.schema_version == "1.0"
    assert parsed.symbol == "RELIANCE"
    assert parsed.metadata["feature_version"] == "1.0.0"


@pytest.mark.parametrize("signal", [-1.01, 1.01])
def test_invalid_signal_range_fails(signal: float) -> None:
    data = sample_agent_signal().model_dump()
    data["signal"] = signal
    with pytest.raises(ValidationError):
        AgentSignal.model_validate(data)


def test_signal_bounds_succeed() -> None:
    for value in (-1.0, 0.0, 1.0):
        data = sample_agent_signal().model_dump()
        data["signal"] = value
        assert AgentSignal.model_validate(data).signal == value


def test_invalid_agent_name_fails() -> None:
    data = sample_agent_signal().model_dump()
    data["agent_name"] = "rsi"
    with pytest.raises(ValidationError):
        AgentSignal.model_validate(data)


def test_invalid_horizon_fails() -> None:
    data = sample_agent_signal().model_dump()
    data["horizon"] = "DAILY"
    with pytest.raises(ValidationError):
        AgentSignal.model_validate(data)


def test_naive_timestamp_fails() -> None:
    data = sample_agent_signal().model_dump()
    data["timestamp"] = datetime(2024, 6, 3, 10, 0)
    with pytest.raises(ValidationError):
        AgentSignal.model_validate(data)


def test_empty_symbol_fails() -> None:
    data = sample_agent_signal().model_dump()
    data["symbol"] = "  "
    with pytest.raises(ValidationError):
        AgentSignal.model_validate(data)


def test_unknown_field_fails() -> None:
    data = sample_agent_signal().model_dump()
    data["broker"] = "zerodha"
    with pytest.raises(ValidationError):
        AgentSignal.model_validate(data)


def test_as_of_after_timestamp_fails() -> None:
    data = sample_agent_signal().model_dump()
    data["as_of"] = datetime(2024, 6, 3, 12, 0, tzinfo=timezone.utc)
    data["timestamp"] = FIXTURE_AS_OF
    with pytest.raises(ValidationError):
        AgentSignal.model_validate(data)
