from pathlib import Path

from quant_agents.research.h001.authorization import (
    REQUIRED_AUTHORIZATION_B_STATEMENT,
    AuthorizationB,
    AuthorizationDenied,
)
from quant_agents.research.h001_integrity import HISTORICAL_DIGEST, verify_authorized_inputs


def test_integrity_requires_authorization_b() -> None:
    try:
        verify_authorized_inputs(None, Path("."))
    except AuthorizationDenied:
        return
    raise AssertionError("integrity check ran without Authorization B")


def test_historical_digest_is_the_full_protocol_value() -> None:
    protocol = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "h001-protocol-approval.md"
    ).read_text(encoding="utf-8")
    assert HISTORICAL_DIGEST in protocol
    assert HISTORICAL_DIGEST.startswith("b0f4760f")
    assert len(HISTORICAL_DIGEST) == 64


def test_matching_grant_fields_are_accepted_by_the_gate() -> None:
    token = AuthorizationB(
        statement=REQUIRED_AUTHORIZATION_B_STATEMENT,
        granted_by="user",
        granted_on="2026-10-14",
    )
    from quant_agents.research.h001.authorization import authorization_b_status

    assert authorization_b_status(token) == "AUTHORIZATION_B_PRESENT"
