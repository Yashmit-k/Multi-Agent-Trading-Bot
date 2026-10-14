"""Opt-in synthetic demo model. These rows are not market outcomes.

training_positive_rate is recorded in the manifest and is not a decision threshold.
Inference uses score_probability (clip(2p - 1)) and does not read that rate.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from quant_agents.errors import ConfigError
from quant_agents.ml.artifact import read_manifest, write_artifact
from quant_agents.ml.registry import ModelRegistry

DEMO_COLUMNS = ("return_1", "rsi_14", "macd", "last_close")
TRAINING_DATA = "synthetic_unvalidated_demo"
FEATURE_VERSION = "1.1.0"
TIMEFRAME = "1d"
MODEL_VERSION = "demo-synthetic-1"
DEMO_SEED = 0
TRAIN_END = 24
_CUTOFF = datetime(2020, 1, 1, tzinfo=timezone.utc)
_TRAINED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def finite_value(value: object, name: str) -> float:
    """Reject missing, non-numeric, NaN, and infinite values. Never fill with zero."""
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"missing or non-numeric feature {name}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite feature {name}")
    return number


def finite_row(values: list[object], columns: tuple[str, ...] = DEMO_COLUMNS) -> list[float]:
    if len(values) != len(columns):
        raise ValueError("feature row does not match the demo column list")
    return [finite_value(value, name) for name, value in zip(columns, values, strict=True)]


def synthetic_dataset() -> tuple[list[dict[str, float]], list[int]]:
    """Fixed rows. DEMO_SEED documents the model seed; the rows are not drawn from a market."""
    rows: list[dict[str, float]] = []
    labels: list[int] = []
    for index in range(40):
        return_1 = -0.02 + (index % 5) * 0.01
        row = {
            "return_1": return_1,
            "rsi_14": 30.0 + (index % 7) * 5.0,
            "macd": -1.0 + (index % 4) * 0.5,
            "last_close": 1000.0 + index * 10.0,
        }
        rows.append(row)
        labels.append(1 if return_1 > 0 else 0)
    return rows, labels


def _matrix(rows: list[dict[str, float]]) -> list[list[float]]:
    return [finite_row([row[name] for name in DEMO_COLUMNS]) for row in rows]


def fit_demo_pipeline(rows: list[dict[str, float]], labels: list[int]) -> tuple[Pipeline, float]:
    """Fit the scaler and classifier on the training slice only."""
    if len(rows) != len(labels) or len(rows) <= TRAIN_END:
        raise ValueError("synthetic demo rows must include a held-out tail")
    matrix = _matrix(rows)
    x_train = matrix[:TRAIN_END]
    y_train = labels[:TRAIN_END]
    if set(y_train) != {0, 1}:
        raise ValueError("synthetic training slice must contain both classes")
    model = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            (
                "clf",
                LogisticRegression(random_state=DEMO_SEED, max_iter=1000, solver="lbfgs"),
            ),
        ]
    )
    model.fit(x_train, y_train)
    rate = float(sum(y_train) / len(y_train))
    return model, rate


def _require_demo_manifest(manifest: dict) -> None:
    if manifest.get("training_data") != TRAINING_DATA:
        raise ConfigError("demo directory does not contain the synthetic demo artifact")
    if list(manifest.get("feature_columns") or []) != list(DEMO_COLUMNS):
        raise ConfigError("demo artifact feature order does not match")
    if manifest.get("feature_version") != FEATURE_VERSION:
        raise ConfigError("demo artifact feature_version does not match")
    if manifest.get("timeframe") != TIMEFRAME:
        raise ConfigError("demo artifact timeframe does not match")
    diagnostics = manifest.get("diagnostics_only") or {}
    if "training_positive_rate" not in diagnostics:
        raise ConfigError("demo artifact is missing training_positive_rate")


def prepare_demo_artifact(directory: Path) -> ModelRegistry:
    """Train once into directory. A later call only loads and checks the existing files."""
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    model_path = directory / "model.joblib"
    if manifest_path.exists() or model_path.exists():
        if not (manifest_path.exists() and model_path.exists()):
            raise ConfigError("demo artifact is incomplete and will not be overwritten")
        registry = ModelRegistry(directory)
        loaded = registry.load(directory)
        _require_demo_manifest(loaded.manifest)
        return registry
    rows, labels = synthetic_dataset()
    model, rate = fit_demo_pipeline(rows, labels)
    write_artifact(
        directory,
        model=model,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        timeframe=TIMEFRAME,
        training_data_cutoff=_CUTOFF,
        trained_at=_TRAINED_AT,
        label_horizon=1,
        embargo_bars=0,
        feature_columns=DEMO_COLUMNS,
        training_data=TRAINING_DATA,
        diagnostics={
            "demo": True,
            "seed": DEMO_SEED,
            "training_positive_rate": rate,
            "training_positive_rate_is_decision_threshold": False,
            "validation_rows_used_for_fit": False,
            "sklearn_version": version("scikit-learn"),
            "not_market_outcomes": True,
        },
    )
    registry = ModelRegistry(directory)
    loaded = registry.load(directory)
    _require_demo_manifest(loaded.manifest)
    return registry


def manifest_rate(directory: Path) -> float:
    manifest = read_manifest(directory / "manifest.json")
    return float(manifest["diagnostics_only"]["training_positive_rate"])
