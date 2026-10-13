"""DATA_PREP_READY gate. Separate from READY_TO_RUN. Does not manufacture YES."""

from __future__ import annotations


def decide(payload: dict) -> dict:
    blockers: list[dict] = []
    checks: list[dict] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})
        if status in {"FAIL", "BLOCKED"}:
            blockers.append({"name": name, "status": status, "detail": detail})

    integrity = payload.get("integrity") or {}
    if integrity.get("status") == "MEASURED" and integrity.get("integrity_baseline_sha256"):
        add(
            "integrity_reproducible",
            "PASS",
            f"v1 listing {integrity.get('integrity_baseline_sha256')}; "
            f"historical b0f4760f UNVERIFIED; equivalent={integrity.get('equivalent_to_b0f4760f')}",
        )
    elif integrity.get("status") == "FREEZE_ABSENT":
        add("integrity_reproducible", "BLOCKED", "freeze directory absent")
    else:
        add("integrity_reproducible", "FAIL", "integrity not measured")

    if integrity.get("historical_digest_status") == "UNVERIFIED":
        add(
            "historical_digest_b0f4760f",
            "BLOCKED",
            "recipe unknown; new named measurement must not replace it",
        )

    ts = payload.get("timestamps") or {}
    if ts.get("exchdatetime_found"):
        add("exchdatetime", "FAIL", "unexpected exchdatetime present; mapping required")
    else:
        add("exchdatetime", "PASS", "field absent; not aliased to exchdisstime")

    if ts.get("limitation"):
        add(
            "exchdisstime_semantics",
            "BLOCKED",
            "IST convention / candidate proxy; not proven first public print; not Scope B",
        )

    coverage = payload.get("section16") or {}
    missing = coverage.get("missing_cell_count")
    if missing is None:
        add("coverage_49x8", "BLOCKED", "coverage not computed")
    elif missing > 0:
        add(
            "coverage_49x8",
            "FAIL",
            f"{coverage.get('covered_cells')} / 392 covered; {missing} missing (not imputed)",
        )
    else:
        add("coverage_49x8", "PASS", "392/392 cells covered under §15")

    scope = payload.get("scope") or {}
    required = scope.get("required")
    available = scope.get("available")
    if required == "B" and available != "B":
        add(
            "scope",
            "BLOCKED",
            "intended earnings values (Scope B) not available from announcement freeze (Scope A)",
        )
    elif required == "A" and available == "A":
        add("scope", "PASS", "Scope A tape matches intended event-tape research")
    else:
        add("scope", "BLOCKED", f"required={required} available={available}")

    protocol = payload.get("protocol") or {}
    if protocol.get("status") != "FROZEN_APPROVED":
        add(
            "protocol",
            "BLOCKED",
            protocol.get("status") or "UNFROZEN",
        )

    parquet = ((integrity.get("sidecars") or {}).get("parquet") or {})
    if parquet.get("status") != "PRESENT":
        add(
            "normalized_parquet",
            "BLOCKED",
            "Gate 2 parquet sidecar absent or unhashed as freeze member; not mixed into listing digest",
        )
    else:
        add(
            "normalized_parquet",
            "PASS",
            f"sidecar hashed separately {parquet.get('sha256')}; not mixed into freeze listing digest",
        )

    if payload.get("labels_generated"):
        add("labels", "FAIL", "labels were generated; this task forbids final research labels")
    else:
        add("labels", "PASS", "no research labels generated")

    if payload.get("holdout_accessed"):
        add("holdout", "FAIL", "holdout accessed")
    else:
        add("holdout", "PASS", "holdout not accessed")

    mandatory_pass = all(item["status"] == "PASS" for item in checks if item["name"] != "historical_digest_b0f4760f")
    # historical digest remaining UNVERIFIED is allowed if a new named measurement exists
    prep_yes = (
        all(item["status"] == "PASS" for item in checks if item["name"] not in {"historical_digest_b0f4760f"})
        and integrity.get("status") == "MEASURED"
        and required == available
        and protocol.get("status") == "FROZEN_APPROVED"
    )
    # Do not award YES while Scope B is required and missing, coverage holes exist, or protocol unfrozen.
    data_prep_ready = "YES" if prep_yes else "NO"
    blocked = any(item["status"] == "BLOCKED" for item in checks)
    return {
        "DATA_PREP_READY": data_prep_ready,
        "READY_TO_RUN": "NO",
        "BLOCKED_PRECONDITION": blocked or data_prep_ready != "YES",
        "checks": checks,
        "blockers": blockers,
        "mandatory_all_pass": mandatory_pass,
        "note": (
            "DATA_PREP_READY is not READY_TO_RUN. A written limitation is not a passed criterion. "
            "Gate 2 DATA READY remains withdrawn."
        ),
    }
