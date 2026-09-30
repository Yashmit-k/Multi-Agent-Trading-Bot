"""Deterministic FeatureSet providers for tests. Production agents do not import this package for live data."""

from quant_agents.testing.audit import AuditingContext, RecordingProvider
from quant_agents.testing.core_compatible import CoreCompatibleFeatureProvider
from quant_agents.testing.extended import ExtendedFeatureProvider

__all__ = [
    "AuditingContext",
    "RecordingProvider",
    "CoreCompatibleFeatureProvider",
    "ExtendedFeatureProvider",
]
