"""Shared evaluate() flow. No datetime arithmetic; calendar methods supply counts."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

from contracts.enums import AgentName, Exchange, Horizon
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.feature_set import FeatureSet
from contracts.time import require_aware

from quant_agents.calendar.protocol import TradingCalendar
from quant_agents.clock import Clock
from quant_agents.config import EvaluationConfig, parse_evaluation_config
from quant_agents.errors import CalendarCoverageError, LeakageError
from quant_agents.feature_view import FeatureView
from quant_agents.scoring import Score, score_probability, score_votes
from quant_agents.vote import Vote

logger = logging.getLogger(__name__)

AGENT_VERSION = "1.1.0"


@dataclass(frozen=True, slots=True)
class AgentDecision:
    votes: tuple[Vote, ...] | None = None
    probability: float | None = None
    reason_codes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    extra_feature_sets: tuple[FeatureSet, ...] = ()
    present_ratio: float = 1.0
    force_neutral: bool = False


class BaseQuantAgent:
    agent_name: AgentName
    required_features: tuple[str, ...] = ()
    optional_features: tuple[str, ...] = ()
    uses_index_features: bool = False

    def __init__(self, clock: Clock, calendar: TradingCalendar) -> None:
        self._clock = clock
        self._calendar = calendar

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        raise NotImplementedError

    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        aware_as_of = require_aware(as_of, "as_of")
        timestamp = self._clock.now()
        config = parse_evaluation_config(context.configuration)
        if not self._calendar.covers(aware_as_of):
            logger.warning("calendar_not_covered", extra={"as_of": aware_as_of.isoformat()})
            return self._neutral(
                symbol=symbol,
                as_of=aware_as_of,
                timestamp=timestamp,
                config=config,
                reason_codes=("calendar.not_covered",),
                features={},
                metadata={"calendar_covers": False},
                input_payload={"kind": "calendar.not_covered", "as_of": aware_as_of.isoformat()},
            )
        feature_set = context.feature_provider.get_feature_set(symbol, config.timeframe, aware_as_of)
        if feature_set.timestamp > aware_as_of:
            raise LeakageError("feature_set.timestamp is after as_of")
        if feature_set.source_data_timestamp > aware_as_of:
            raise LeakageError("feature_set.source_data_timestamp is after as_of")
        gap = self._calendar.sessions_between(feature_set.source_data_timestamp, aware_as_of)
        if gap > config.staleness_max_sessions:
            return self._neutral(
                symbol=symbol,
                as_of=aware_as_of,
                timestamp=timestamp,
                config=config,
                reason_codes=("feature.stale",),
                features=dict(feature_set.features),
                metadata={
                    "sessions_between": gap,
                    "source_data_timestamp": feature_set.source_data_timestamp.isoformat(),
                },
                input_payload={"kind": "feature.stale", "source": feature_set.model_dump(mode="json")},
            )
        extra_sets: list[FeatureSet] = []
        extra_views: dict[str, FeatureView] = {}
        if self.uses_index_features:
            for index_symbol in config.regime_index_symbols:
                try:
                    extra = context.feature_provider.get_feature_set(index_symbol, config.timeframe, aware_as_of)
                except LookupError:
                    continue
                if extra.timestamp > aware_as_of:
                    raise LeakageError("index feature_set.timestamp is after as_of")
                if extra.source_data_timestamp > aware_as_of:
                    raise LeakageError("index source_data_timestamp is after as_of")
                extra_sets.append(extra)
                extra_views[index_symbol] = FeatureView(extra)
        view = FeatureView(feature_set)
        for name in self.required_features:
            view.get(name)
        for name in self.optional_features:
            view.get(name)
        decision = self.interpret(view, extra_views)
        all_sets = (feature_set, *extra_sets, *decision.extra_feature_sets)
        input_payload = {
            "agent": self.agent_name.value,
            "symbol": symbol,
            "horizon": config.horizon.value,
            "timeframe": config.timeframe.value,
            "as_of": aware_as_of.isoformat(),
            "feature_sets": [item.model_dump(mode="json") for item in all_sets],
            "decision_meta": dict(decision.metadata),
        }
        if decision.force_neutral:
            codes = decision.reason_codes or ("neutral.forced",)
            return self._neutral(
                symbol=symbol,
                as_of=aware_as_of,
                timestamp=timestamp,
                config=config,
                reason_codes=codes,
                features=view.snapshot_features(),
                metadata=dict(decision.metadata),
                input_payload=input_payload,
            )
        score = self._score(decision, view)
        reasons = self._reasons(decision, view)
        try:
            valid_until = self._valid_until(aware_as_of, timestamp, config)
        except CalendarCoverageError:
            logger.warning("calendar_not_covered_valid_until", extra={"as_of": aware_as_of.isoformat()})
            return self._neutral(
                symbol=symbol,
                as_of=aware_as_of,
                timestamp=timestamp,
                config=config,
                reason_codes=("calendar.not_covered",),
                features=view.snapshot_features(),
                metadata={"valid_until": "uncovered"},
                input_payload=input_payload,
            )
        return self._build_signal(
            symbol=symbol,
            as_of=aware_as_of,
            timestamp=timestamp,
            valid_until=valid_until,
            config=config,
            score=score,
            reason_codes=reasons,
            features=view.snapshot_features(),
            metadata=self._metadata(feature_set, view, decision, config),
            input_payload=input_payload,
        )

    def _score(self, decision: AgentDecision, view: FeatureView) -> Score:
        if decision.probability is not None:
            return score_probability(decision.probability, present_ratio=decision.present_ratio)
        if decision.votes is None:
            raise TypeError("AgentDecision must include votes or probability")
        return score_votes(decision.votes, required=self.required_features, missing=view.missing)

    def _reasons(self, decision: AgentDecision, view: FeatureView) -> tuple[str, ...]:
        codes: list[str] = list(decision.reason_codes)
        for name in view.missing:
            codes.append(f"{self.agent_name.value}.feature_missing.{name}")
        if not codes:
            codes.append(f"{self.agent_name.value}.evaluated")
        return tuple(codes)

    def _valid_until(self, as_of: datetime, timestamp: datetime, config: EvaluationConfig) -> datetime:
        if config.horizon is Horizon.INTRADAY:
            return self._calendar.session_close(as_of)
        return self._calendar.add_sessions(as_of, config.swing_valid_sessions)

    def _metadata(
        self,
        feature_set: FeatureSet,
        view: FeatureView,
        decision: AgentDecision,
        config: EvaluationConfig,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "feature_version": feature_set.feature_version,
            "source_data_timestamp": feature_set.source_data_timestamp.isoformat(),
            "timeframe": config.timeframe.value,
            "features_used": list(view.used),
            "features_missing": list(view.missing),
            "votes": [
                {"name": vote.name, "value": vote.value, "weight": vote.weight}
                for vote in (decision.votes or ())
            ],
        }
        payload.update(dict(decision.metadata))
        return payload

    def _neutral(
        self,
        *,
        symbol: str,
        as_of: datetime,
        timestamp: datetime,
        config: EvaluationConfig,
        reason_codes: Sequence[str],
        features: dict[str, str | int | float | bool],
        metadata: Mapping[str, Any],
        input_payload: Mapping[str, Any],
    ) -> AgentSignal:
        return self._build_signal(
            symbol=symbol,
            as_of=as_of,
            timestamp=timestamp,
            valid_until=timestamp,
            config=config,
            score=Score(signal=0.0, confidence=0.0),
            reason_codes=tuple(reason_codes),
            features=features,
            metadata=dict(metadata),
            input_payload=input_payload,
        )

    def _build_signal(
        self,
        *,
        symbol: str,
        as_of: datetime,
        timestamp: datetime,
        valid_until: datetime,
        config: EvaluationConfig,
        score: Score,
        reason_codes: Sequence[str],
        features: dict[str, str | int | float | bool],
        metadata: dict[str, Any],
        input_payload: Mapping[str, Any],
    ) -> AgentSignal:
        input_hash = _hash_payload(input_payload)
        identity = {
            "agent": self.agent_name.value,
            "agent_version": AGENT_VERSION,
            "symbol": symbol,
            "horizon": config.horizon.value,
            "timeframe": config.timeframe.value,
            "as_of": as_of.isoformat(),
            "input_hash": input_hash,
        }
        signal_id = _hash_payload(identity)
        meta = dict(metadata)
        meta["input_hash"] = input_hash
        return AgentSignal(
            signal_id=signal_id,
            symbol=symbol,
            exchange=Exchange.NSE,
            agent_name=self.agent_name,
            agent_version=AGENT_VERSION,
            timestamp=timestamp,
            as_of=as_of,
            horizon=config.horizon,
            signal=score.signal,
            confidence=score.confidence,
            valid_until=valid_until,
            reason_codes=list(reason_codes),
            features=features,
            metadata=meta,
        )


def _hash_payload(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
