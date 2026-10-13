"""Authorization B gate. Fail closed. This module does not read research files."""

from __future__ import annotations

from dataclasses import dataclass

AUTHORIZATION_PENDING = "AUTHORIZATION_PENDING"
AUTHORIZATION_B_SCOPE = "H001_ELIGIBILITY_AUDIT"

# Supervisor must send this statement verbatim. Matching it in a unit test is not a grant.
REQUIRED_AUTHORIZATION_B_STATEMENT = (
    "AUTHORIZATION B GRANTED: run the H001 eligibility-only audit on the frozen "
    "Scope A announcement tape identified in services/quant/docs/h001-protocol-approval.md "
    "(protocol dated 2026-10-12). Do not access snapshots/holdout_after_20261005. "
    "Do not fit, backtest, optimize, or evaluate an H001 model. Do not change the "
    "approved event class, features, split, minority threshold, or label definitions."
)

_HOLD_OUT_MARKER = "holdout_after_"
_FREEZE_MARKER = "h001-nse-raw-"


class AuthorizationDenied(PermissionError):
    """Authorization B is absent, malformed, or insufficient."""


class RestrictedSourceRefused(PermissionError):
    """A holdout or otherwise forbidden location was named."""


class RealDataAuditNotExecuted(RuntimeError):
    """The frozen-tape audit entry point is gated and has not been run."""


@dataclass(frozen=True, slots=True)
class AuthorizationB:
    statement: str
    granted_by: str
    granted_on: str
    scope: str = AUTHORIZATION_B_SCOPE


def authorization_b_status(token: object | None) -> str:
    if token is None:
        return AUTHORIZATION_PENDING
    if not isinstance(token, AuthorizationB):
        return AUTHORIZATION_PENDING
    if token.scope != AUTHORIZATION_B_SCOPE:
        return AUTHORIZATION_PENDING
    if not token.granted_by.strip() or not token.granted_on.strip():
        return AUTHORIZATION_PENDING
    if token.statement != REQUIRED_AUTHORIZATION_B_STATEMENT:
        return AUTHORIZATION_PENDING
    return "AUTHORIZATION_B_PRESENT"


def require_authorization_b(token: object | None) -> AuthorizationB:
    if authorization_b_status(token) != "AUTHORIZATION_B_PRESENT":
        raise AuthorizationDenied(
            "Authorization B is pending. The eligibility audit on the frozen tape "
            "is not authorized. Status remains AUTHORIZATION_PENDING."
        )
    assert isinstance(token, AuthorizationB)
    return token


def refuse_restricted_source(source: str, *, authorization_present: bool = False) -> None:
    """Path inspection only. No bytes are read."""
    normalized = source.replace("\\", "/").casefold()
    if _HOLD_OUT_MARKER in normalized:
        raise RestrictedSourceRefused(
            "holdout snapshot is excluded from H001 and cannot be named as an input"
        )
    if _FREEZE_MARKER in normalized and not authorization_present:
        raise RestrictedSourceRefused(
            "frozen announcement source is closed until Authorization B is granted"
        )


def require_source_after_authorization_b(token: object | None, source: str) -> None:
    """Fail closed: auth first, then refuse holdout even if a token is present."""
    require_authorization_b(token)
    refuse_restricted_source(source, authorization_present=True)
    raise RealDataAuditNotExecuted(
        "Freeze bytes are not loaded for eligibility until the approved "
        "historical digest is verified against the actual input. "
        f"Holdout remains closed. Status remains gated."
    )
