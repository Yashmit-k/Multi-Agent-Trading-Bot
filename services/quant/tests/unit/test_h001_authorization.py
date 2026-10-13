from pathlib import Path

import pytest

from quant_agents.research.h001.authorization import (
    AUTHORIZATION_PENDING,
    AuthorizationB,
    AuthorizationDenied,
    RealDataAuditNotExecuted,
    RestrictedSourceRefused,
    authorization_b_status,
    refuse_restricted_source,
    require_authorization_b,
    require_source_after_authorization_b,
)
from quant_agents.research.h001.eligibility import (
    ORIGIN_FROZEN,
    EligibilityBundle,
    run_frozen_eligibility_audit,
)


def test_authorization_b_fails_closed_when_absent_or_wrong() -> None:
    assert authorization_b_status(None) == AUTHORIZATION_PENDING
    assert authorization_b_status("AUTHORIZATION B GRANTED") == AUTHORIZATION_PENDING
    assert authorization_b_status({"statement": "yes"}) == AUTHORIZATION_PENDING
    with pytest.raises(AuthorizationDenied, match="AUTHORIZATION_PENDING"):
        require_authorization_b(None)
    wrong = AuthorizationB(statement="not the supervisor grant", granted_by="quant", granted_on="2026-10-14")
    assert authorization_b_status(wrong) == AUTHORIZATION_PENDING
    with pytest.raises(AuthorizationDenied):
        require_authorization_b(wrong)
    empty = AuthorizationB(
        statement="",
        granted_by="",
        granted_on="2026-10-14",
    )
    with pytest.raises(AuthorizationDenied):
        require_authorization_b(empty)


def test_holdout_and_freeze_names_are_refused_without_reading() -> None:
    with pytest.raises(RestrictedSourceRefused, match="holdout"):
        refuse_restricted_source("snapshots/holdout_after_20261005/nifty50_1d.jsonl")
    with pytest.raises(RestrictedSourceRefused, match="frozen"):
        refuse_restricted_source("datasets/h001-nse-raw-20261010T140237Z/RELIANCE.json")
    with pytest.raises(AuthorizationDenied):
        require_source_after_authorization_b(None, "tmp/synthetic-rows.json")


def test_frozen_entry_point_does_not_execute_even_with_matching_wording() -> None:
    from quant_agents.research.h001.authorization import REQUIRED_AUTHORIZATION_B_STATEMENT

    token = AuthorizationB(
        statement=REQUIRED_AUTHORIZATION_B_STATEMENT,
        granted_by="unit-test",
        granted_on="2026-10-14",
    )
    with pytest.raises(RestrictedSourceRefused):
        require_source_after_authorization_b(token, "C:/data/snapshots/holdout_after_20261005")
    bundle = EligibilityBundle((), (), (), ORIGIN_FROZEN, ("unverified",))
    from quant_agents.research.h001_integrity import IntegrityVerificationFailed

    with pytest.raises(RealDataAuditNotExecuted, match="historical digest"):
        require_source_after_authorization_b(token, "datasets/h001-nse-raw-20261010T140237Z")
    with pytest.raises(IntegrityVerificationFailed):
        run_frozen_eligibility_audit(token, bundle, historical_digest_verified=False)
    with pytest.raises(IntegrityVerificationFailed, match="UNVERIFIED"):
        run_frozen_eligibility_audit(token, bundle, historical_digest_verified=True)
    with pytest.raises(AuthorizationDenied):
        run_frozen_eligibility_audit(None, bundle, historical_digest_verified=False)


def test_authorization_and_eligibility_modules_do_not_open_files() -> None:
    package = Path(__file__).resolve().parents[2] / "src" / "quant_agents" / "research" / "h001"
    for path in package.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "open(" not in text
        assert "read_parquet" not in text
        assert "read_bytes" not in text
        assert "candles.jsonl" not in text
        if path.name != "authorization.py":
            assert "holdout_after_20261005" not in text
            assert "parquet" not in text
