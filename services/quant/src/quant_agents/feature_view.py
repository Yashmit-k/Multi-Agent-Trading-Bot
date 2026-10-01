"""Read-only FeatureSet lookup. No aliases and no derived values."""

from __future__ import annotations

from contracts.schemas.feature_set import FeatureSet


class FeatureView:
    def __init__(self, feature_set: FeatureSet) -> None:
        self._feature_set = feature_set
        self._used: list[str] = []
        self._missing: list[str] = []

    @property
    def feature_set(self) -> FeatureSet:
        return self._feature_set

    @property
    def used(self) -> tuple[str, ...]:
        return tuple(self._used)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(self._missing)

    def get(self, name: str) -> float | None:
        raw = self._feature_set.features.get(name)
        if raw is None:
            if name not in self._missing:
                self._missing.append(name)
            return None
        if name not in self._used:
            self._used.append(name)
        if isinstance(raw, bool):
            return None
        if isinstance(raw, int):
            return float(raw)
        if isinstance(raw, float):
            return raw
        if isinstance(raw, str):
            try:
                return float(raw)
            except ValueError:
                return None
        return None

    def snapshot_features(self) -> dict[str, str | int | float | bool]:
        out: dict[str, str | int | float | bool] = {}
        for name in self._used:
            value = self._feature_set.features.get(name)
            if value is not None:
                out[name] = value
        return out
