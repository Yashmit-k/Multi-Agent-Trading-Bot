"""Per-column sklearn preprocessing. No cross-feature columns."""

from __future__ import annotations

from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def make_preprocessor() -> Pipeline:
    return Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="constant", fill_value=0.0)),
            ("scale", StandardScaler()),
        ]
    )
