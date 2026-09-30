"""Serialize a baseline model with a provenance manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib

from quant_agents.ml.dataset import FEATURE_COLUMNS


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ArtifactPaths:
    directory: Path
    model_path: Path
    manifest_path: Path


def write_artifact(
    directory: Path,
    *,
    model: Any,
    model_version: str,
    feature_version: str,
    timeframe: str,
    training_data_cutoff: datetime,
    trained_at: datetime,
    label_horizon: int,
    embargo_bars: int,
    diagnostics: dict[str, Any],
    feature_columns: tuple[str, ...] = FEATURE_COLUMNS,
) -> ArtifactPaths:
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / "model.joblib"
    manifest_path = directory / "manifest.json"
    joblib.dump(model, model_path)
    digest = file_sha256(model_path)
    manifest = {
        "model_version": model_version,
        "feature_version": feature_version,
        "timeframe": timeframe,
        "feature_columns": list(feature_columns),
        "label_horizon": label_horizon,
        "label_definition": "binary: last_close[t+h] > last_close[t]; equal closes dropped",
        "zero_return_handling": "dropped",
        "training_data_cutoff": training_data_cutoff.isoformat(),
        "embargo_bars": embargo_bars,
        "trained_at": trained_at.isoformat(),
        "sha256": digest,
        "baseline": True,
        "training_data": "synthetic_fixture",
        "diagnostics_only": diagnostics,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return ArtifactPaths(directory=directory, model_path=model_path, manifest_path=manifest_path)


def read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
