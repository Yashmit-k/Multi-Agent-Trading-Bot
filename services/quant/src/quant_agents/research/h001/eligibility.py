"""Eligibility-only audit for caller-supplied rows. No fit. Opens nothing."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from quant_agents.research.h001.authorization import require_authorization_b
from quant_agents.research.h001.calendar import (
    DailyBar,
    FiveMinuteBar,
    research_calendar,
    select_entry,
)
from quant_agents.research.h001.events import Exclusion, classify_rows
from quant_agents.research.h001.features import FEATURE_COLUMNS, build_features
from quant_agents.research.h001.labels import horizon_close, make_label
from quant_agents.research.h001.split import (
    MINORITY_BAR,
    SATISFIED,
    TRAIN_END,
    VALIDATION_END,
    UnexpectedDecisionDate,
    assign_partition,
    smaller_class_check,
)

PROTOCOL_ID = "H001-2026-10-12"
PROTOCOL_STATUS = "PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED"
ORIGIN_SYNTHETIC = "synthetic_fixture"
ORIGIN_FROZEN = "frozen_h001_tape"
AUDIT_COMPLETE_INCONCLUSIVE = "AUDIT_COMPLETE_INCONCLUSIVE"
DATA_READY = "DATA_READY"
SYNTHETIC_FIXTURE_NOT_PRODUCTION = "SYNTHETIC_FIXTURE_NOT_PRODUCTION"
INTEGRITY_UNVERIFIED = "UNVERIFIED"
PRIOR_TRAINING_MINORITY_UNVERIFIED = 34


@dataclass(frozen=True, slots=True)
class EligibilityBundle:
    rows: tuple[Mapping[str, object], ...]
    daily_bars: tuple[DailyBar, ...]
    five_minute_bars: tuple[FiveMinuteBar, ...]
    origin: str
    snapshot_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EligibleRow:
    seq_id: str
    symbol: str
    y: int
    partition: str
    decision: object
    h1_session: object


@dataclass(frozen=True, slots=True)
class SplitCounts:
    n: int
    positive: int
    negative: int
    minority: int
    status: str


@dataclass(frozen=True, slots=True)
class EligibilityAuditReport:
    protocol_id: str
    protocol_status: str
    origin: str
    snapshot_ids: tuple[str, ...]
    integrity_verification_status: str
    input_records: int
    unique_event_identifiers: int
    stage_counts: dict[str, int]
    exclusion_counts: dict[str, int]
    train: SplitCounts
    validation: SplitCounts
    minority_threshold: int
    readiness_decision: str
    readiness_reason: str
    execution_authorized: bool
    prior_training_minority_unverified: int
    executed_at: str
    reproducibility: dict[str, str]


def _count_split(rows: list[EligibleRow]) -> SplitCounts:
    labels = tuple(row.y for row in rows)
    check = smaller_class_check(labels) if labels else smaller_class_check(())
    positives = sum(labels)
    negatives = len(labels) - positives
    return SplitCounts(len(labels), positives, negatives, check.minority_count, check.status)


def _production_readiness(train: SplitCounts, validation: SplitCounts) -> tuple[str, str]:
    official = (
        "Official readiness remains AUDIT_COMPLETE_INCONCLUSIVE; execution is unauthorized."
    )
    if train.status == SATISFIED and validation.status == SATISFIED:
        return (
            DATA_READY,
            "EXPERIMENTAL_NOT_APPROVED. "
            f"{official} Both splits meet the experimental {MINORITY_BAR}-observation "
            "minority-class bar. The approved bar remains 50. "
            "This is not execution authorization.",
        )
    return (
        AUDIT_COMPLETE_INCONCLUSIVE,
        "EXPERIMENTAL_NOT_APPROVED. "
        f"{official} The experimental minority-class bar of {MINORITY_BAR} was not met "
        "in both splits. The approved threshold remains 50. The event class is not widened.",
    )


def run_eligibility_stages(
    bundle: EligibilityBundle,
    *,
    integrity_verification_status: str = INTEGRITY_UNVERIFIED,
) -> EligibilityAuditReport:
    """Deterministic staged counts. Callers supply rows and bars in memory."""
    if bundle.origin not in {ORIGIN_SYNTHETIC, ORIGIN_FROZEN}:
        raise ValueError("unknown eligibility origin")
    classified = classify_rows(bundle.rows)
    calendar = research_calendar(bundle.daily_bars)
    exclusions = list(classified.exclusions)
    with_entry = 0
    with_label = 0
    with_features = 0
    after_validation = 0
    eligible: list[EligibleRow] = []
    for event in classified.events:
        entry = select_entry(
            event.seq_id,
            event.symbol,
            event.available_at,
            calendar,
            bundle.five_minute_bars,
        )
        if isinstance(entry, Exclusion):
            exclusions.append(entry)
            continue
        with_entry += 1
        horizon = horizon_close(
            event.seq_id,
            event.symbol,
            entry.decision,
            calendar,
            bundle.daily_bars,
        )
        if isinstance(horizon, Exclusion):
            exclusions.append(horizon)
            continue
        h1_session, p1 = horizon
        labeled = make_label(event.seq_id, event.symbol, entry.p0, p1)
        if isinstance(labeled, Exclusion):
            exclusions.append(labeled)
            continue
        with_label += 1
        feats = build_features(
            event.seq_id,
            event.symbol,
            entry.decision,
            event.available_at,
            calendar,
            bundle.daily_bars,
        )
        if isinstance(feats, Exclusion):
            exclusions.append(feats)
            continue
        with_features += 1
        try:
            assignment = assign_partition(event.seq_id, event.symbol, entry.decision, h1_session)
        except UnexpectedDecisionDate:
            after_validation += 1
            continue
        if assignment.reason is not None:
            exclusions.append(Exclusion(event.seq_id, event.symbol, assignment.reason))
            continue
        eligible.append(
            EligibleRow(
                event.seq_id,
                event.symbol,
                labeled.y,
                assignment.partition,
                entry.decision,
                h1_session,
            )
        )
    train_rows = [row for row in eligible if row.partition == "train"]
    val_rows = [row for row in eligible if row.partition == "validation"]
    train = _count_split(train_rows)
    validation = _count_split(val_rows)
    seq_ids = [str(row.get("seq_id", "")) for row in bundle.rows]
    production_decision, production_reason = _production_readiness(train, validation)
    if bundle.origin == ORIGIN_SYNTHETIC:
        readiness_decision = SYNTHETIC_FIXTURE_NOT_PRODUCTION
        readiness_reason = (
            "Synthetic fixture only. Production DATA_READY is not claimed. "
            f"Sample check if this were production: {production_decision}."
        )
    else:
        readiness_decision = production_decision
        readiness_reason = production_reason
    executed = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    stage_counts = {
        "input_records": len(bundle.rows),
        "unique_event_identifiers": len({item for item in seq_ids if item}),
        "classified_in_class": len(classified.events),
        "with_entry_p0": with_entry,
        "with_h1_label": with_label,
        "with_features": with_features,
        "eligible_labelled_train": train.n,
        "eligible_labelled_validation": validation.n,
        "eligible_labelled_total": train.n + validation.n,
        "decision_after_validation_end": after_validation,
    }
    exclusion_counts = dict(Counter(item.reason.value for item in exclusions))
    return EligibilityAuditReport(
        protocol_id=PROTOCOL_ID,
        protocol_status=PROTOCOL_STATUS,
        origin=bundle.origin,
        snapshot_ids=bundle.snapshot_ids,
        integrity_verification_status=integrity_verification_status,
        input_records=len(bundle.rows),
        unique_event_identifiers=stage_counts["unique_event_identifiers"],
        stage_counts=stage_counts,
        exclusion_counts=exclusion_counts,
        train=train,
        validation=validation,
        minority_threshold=MINORITY_BAR,
        readiness_decision=readiness_decision,
        readiness_reason=readiness_reason,
        execution_authorized=False,
        prior_training_minority_unverified=PRIOR_TRAINING_MINORITY_UNVERIFIED,
        executed_at=executed,
        reproducibility={
            "train_end": TRAIN_END.isoformat(),
            "validation_end": VALIDATION_END.isoformat(),
            "minority_bar": str(MINORITY_BAR),
            "feature_columns": ",".join(("intercept",) + FEATURE_COLUMNS),
            "label": "1 if (P1-P0)/P0 > 0 else 0",
        },
    )


def run_synthetic_eligibility_audit(bundle: EligibilityBundle) -> EligibilityAuditReport:
    if bundle.origin != ORIGIN_SYNTHETIC:
        raise ValueError("synthetic audit requires origin synthetic_fixture")
    return run_eligibility_stages(bundle)


def run_frozen_eligibility_audit(
    authorization: object | None,
    bundle: EligibilityBundle,
    *,
    historical_digest_verified: bool = False,
    alternative_eligibility_basis: bool = False,
) -> EligibilityAuditReport:
    """Eligibility-only freeze audit. Requires Authorization B and an allowed integrity basis."""
    require_authorization_b(authorization)
    if bundle.origin != ORIGIN_FROZEN:
        raise ValueError("frozen audit requires origin frozen_h001_tape")
    from quant_agents.research.h001_integrity import IntegrityVerificationFailed

    if historical_digest_verified:
        raise IntegrityVerificationFailed(
            "Historical digest b0f4760f remains UNVERIFIED. Do not mark it verified."
        )
    if not alternative_eligibility_basis:
        raise IntegrityVerificationFailed(
            "Historical digest is not verified against the actual freeze bytes. "
            "Eligibility counts are not computed unless the recorded alternative "
            "basis is used. Model fitting remains unauthorized."
        )
    return run_eligibility_stages(
        bundle,
        integrity_verification_status="ALTERNATIVE_BASIS_USED_HISTORICAL_UNVERIFIED",
    )
