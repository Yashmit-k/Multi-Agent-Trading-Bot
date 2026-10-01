"""ML agent. Arithmetic on probability happens in scoring.py only."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from contracts.enums import AgentName

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.feature_view import FeatureView
from quant_agents.ml.dataset import FEATURE_COLUMNS
from quant_agents.ml.registry import ArtifactCorrupt, ModelRegistry


class MlAgent(BaseQuantAgent):
    agent_name = AgentName.ML
    required_features = FEATURE_COLUMNS
    optional_features: tuple[str, ...] = ()

    def __init__(self, clock, calendar, registry: ModelRegistry | None) -> None:
        super().__init__(clock, calendar)
        self._registry = registry

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        if self._registry is None:
            return AgentDecision(force_neutral=True, reason_codes=("ml.no_eligible_model",), metadata={"baseline": True})
        as_of = view.feature_set.timestamp
        timeframe = view.feature_set.timeframe.value
        directory = self._registry.eligible(as_of=as_of, timeframe=timeframe)
        if directory is None:
            return AgentDecision(force_neutral=True, reason_codes=("ml.no_eligible_model",), metadata={"baseline": True})
        try:
            loaded = self._registry.load(directory)
        except ArtifactCorrupt:
            return AgentDecision(force_neutral=True, reason_codes=("ml.artifact_corrupt",), metadata={"baseline": True})
        manifest = loaded.manifest
        if manifest.get("feature_version") != view.feature_set.feature_version:
            return AgentDecision(
                force_neutral=True,
                reason_codes=("ml.feature_version_mismatch",),
                metadata={"baseline": True, "model_version": manifest.get("model_version")},
            )
        if manifest.get("timeframe") != timeframe:
            return AgentDecision(
                force_neutral=True,
                reason_codes=("ml.timeframe_mismatch",),
                metadata={"baseline": True},
            )
        columns = list(manifest.get("feature_columns") or FEATURE_COLUMNS)
        row: list[float] = []
        missing = False
        for column in columns:
            value = view.get(column)
            if value is None:
                missing = True
                break
            row.append(value)
        if missing:
            return AgentDecision(force_neutral=True, reason_codes=("ml.no_eligible_model",), metadata={"baseline": True})
        proba = loaded.model.predict_proba([row])[0][1]
        return AgentDecision(
            probability=float(proba),
            metadata={
                "model_version": manifest.get("model_version"),
                "feature_version": manifest.get("feature_version"),
                "timeframe": timeframe,
                "prediction_timestamp": as_of.isoformat(),
                "training_data_cutoff": manifest.get("training_data_cutoff"),
                "baseline": True,
                "manifest_sha256": manifest.get("sha256"),
            },
        )
