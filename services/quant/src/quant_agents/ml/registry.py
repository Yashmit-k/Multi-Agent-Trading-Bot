"""Load versioned artifacts. Hash is verified once per path and cached."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib

from quant_agents.ml.artifact import file_sha256, read_manifest

logger = logging.getLogger(__name__)


class ArtifactCorrupt(Exception):
    """Manifest sha256 does not match the joblib file."""


@dataclass
class LoadedArtifact:
    model: Any
    manifest: dict[str, Any]
    path: Path


class ModelRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._hash_ok: dict[Path, str] = {}
        self._loaded: dict[Path, LoadedArtifact] = {}

    def _iter_manifests(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(self.root.rglob("manifest.json"))

    def eligible(self, *, as_of: datetime, timeframe: str) -> Path | None:
        chosen: tuple[datetime, Path] | None = None
        for manifest_path in self._iter_manifests():
            try:
                manifest_path.resolve().relative_to(self.root)
            except ValueError:
                continue
            manifest = read_manifest(manifest_path)
            if manifest.get("timeframe") != timeframe:
                continue
            cutoff = datetime.fromisoformat(str(manifest["training_data_cutoff"]))
            if cutoff.tzinfo is None:
                continue
            if cutoff > as_of:
                continue
            if chosen is None or cutoff > chosen[0]:
                chosen = (cutoff, manifest_path.parent)
        return None if chosen is None else chosen[1]

    def load(self, directory: Path) -> LoadedArtifact:
        directory = directory.resolve()
        directory.relative_to(self.root)
        if directory in self._loaded:
            return self._loaded[directory]
        model_path = directory / "model.joblib"
        manifest_path = directory / "manifest.json"
        manifest = read_manifest(manifest_path)
        expected = str(manifest.get("sha256") or "")
        if directory not in self._hash_ok:
            actual = file_sha256(model_path)
            if actual != expected:
                logger.error("ml_artifact_corrupt", extra={"path": str(model_path)})
                raise ArtifactCorrupt(str(model_path))
            self._hash_ok[directory] = actual
        model = joblib.load(model_path)
        loaded = LoadedArtifact(model=model, manifest=manifest, path=directory)
        self._loaded[directory] = loaded
        return loaded
