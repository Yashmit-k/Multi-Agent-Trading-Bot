"""Serialize a baseline model with a provenance manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib

from quant_agents.labelers import LABEL_VERSION
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
    training_data: str = "synthetic_fixture",
    cutoff_source: str = "explicit",
    survivorship_bias: str = "current_nifty50_constituents",
    prices_adjusted: str = "unspecified",
    label_version: str = LABEL_VERSION,
    snapshot_id: str = "",
    snapshot_sha256: str = "",
    dataset_schema_version: str = "",
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
        "label_version": label_version,
        "label_definition": "binary: last_close[t+h] > last_close[t]; equal closes dropped",
        "zero_return_handling": "dropped",
        "training_data_cutoff": training_data_cutoff.isoformat(),
        "embargo_bars": embargo_bars,
        "trained_at": trained_at.isoformat(),
        "sha256": digest,
        "baseline": True,
        "training_data": training_data,
        "cutoff_source": cutoff_source,
        "survivorship_bias": survivorship_bias,
        "prices_adjusted": prices_adjusted,
        "snapshot_id": snapshot_id,
        "snapshot_sha256": snapshot_sha256,
        "dataset_schema_version": dataset_schema_version,
        "diagnostics_only": diagnostics,
    }
    if cutoff_source == "explicit":
        manifest["training_data_cutoff"] = training_data_cutoff.isoformat()
    else:
        manifest.pop("training_data_cutoff", None)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return ArtifactPaths(directory=directory, model_path=model_path, manifest_path=manifest_path)


def read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
