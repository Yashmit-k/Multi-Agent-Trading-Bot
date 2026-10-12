"""ML agent. Arithmetic on probability happens in scoring.py only."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from contracts.enums import AgentName
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal
from contracts.time import require_aware

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.config import parse_evaluation_config
from quant_agents.feature_view import FeatureView
from quant_agents.ml.dataset import FEATURE_COLUMNS
from quant_agents.ml.demo import DEMO_COLUMNS, TRAINING_DATA, finite_value
from quant_agents.ml.registry import ArtifactCorrupt, ModelRegistry


class MlAgent(BaseQuantAgent):
    agent_name = AgentName.ML
    required_features = FEATURE_COLUMNS
    optional_features: tuple[str, ...] = ()

    def __init__(self, clock, calendar, registry: ModelRegistry | None) -> None:
        super().__init__(clock, calendar)
        self._registry = registry

    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        """Probe the active artifact's columns. A demo artifact does not require the legacy list."""
        self.required_features = self._active_columns(symbol, as_of, context)
        return super().evaluate(symbol, as_of, context)

    def _active_columns(self, symbol: str, as_of: datetime, context: AgentContext) -> tuple[str, ...]:
        """Return the loaded manifest order, or the legacy list when no artifact is usable."""
        if self._registry is None:
            return FEATURE_COLUMNS
        try:
            aware = require_aware(as_of, "as_of")
            config = parse_evaluation_config(context.configuration)
            feature_set = context.feature_provider.get_feature_set(symbol, config.timeframe, aware)
            directory = self._registry.eligible(as_of=feature_set.timestamp, timeframe=feature_set.timeframe.value)
            if directory is None:
                return FEATURE_COLUMNS
            loaded = self._registry.load(directory)
        except ArtifactCorrupt:
            return FEATURE_COLUMNS
        manifest = loaded.manifest
        if manifest.get("feature_version") != feature_set.feature_version:
            return FEATURE_COLUMNS
        if manifest.get("timeframe") != feature_set.timeframe.value:
            return FEATURE_COLUMNS
        columns = tuple(manifest.get("feature_columns") or FEATURE_COLUMNS)
        if manifest.get("training_data") == TRAINING_DATA and columns != DEMO_COLUMNS:
            return FEATURE_COLUMNS
        return columns

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
        if manifest.get("training_data") == TRAINING_DATA and columns != list(DEMO_COLUMNS):
            return AgentDecision(force_neutral=True, reason_codes=("ml.feature_invalid",), metadata={"baseline": True})
        try:
            row = [finite_value(view.get(column), column) for column in columns]
        except ValueError:
            return AgentDecision(force_neutral=True, reason_codes=("ml.feature_invalid",), metadata={"baseline": True})
        proba = float(loaded.model.predict_proba([row])[0][1])
        diagnostics = manifest.get("diagnostics_only") or {}
        metadata: dict[str, object] = {
            "model_version": manifest.get("model_version"),
            "feature_version": manifest.get("feature_version"),
            "timeframe": timeframe,
            "prediction_timestamp": as_of.isoformat(),
            "training_data_cutoff": manifest.get("training_data_cutoff"),
            "baseline": True,
            "manifest_sha256": manifest.get("sha256"),
        }
        if manifest.get("training_data") == TRAINING_DATA:
            metadata["demo"] = True
            metadata["training_data"] = TRAINING_DATA
        if "training_positive_rate" in diagnostics:
            metadata["training_positive_rate"] = float(diagnostics["training_positive_rate"])
        return AgentDecision(probability=proba, metadata=metadata)
