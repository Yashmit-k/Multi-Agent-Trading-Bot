"""One logistic regression. Validation labels are not an argument to the fit or the cutoff."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression

from quant_agents.research.h001.features import FEATURE_COLUMNS
from quant_agents.research.h001.split import P_WITH_INTERCEPT

MAX_ITER = 1000


@dataclass(frozen=True, slots=True)
class FittedH001:
    model: LogisticRegression
    threshold: float
    predictor_count: int

    @property
    def coefficients(self) -> np.ndarray:
        return np.asarray(self.model.coef_, dtype=float)


def fit_h001(x_train: np.ndarray, y_train: np.ndarray) -> FittedH001:
    """Fit on training arrays only. There is no validation-label parameter."""
    features = np.asarray(x_train, dtype=float)
    labels = np.asarray(y_train, dtype=int)
    if features.ndim != 2 or features.shape[1] != len(FEATURE_COLUMNS):
        raise ValueError("x_train must have four predictor columns")
    if labels.shape != (features.shape[0],):
        raise ValueError("y_train must have one label per training row")
    if set(labels.tolist()) != {0, 1}:
        raise ValueError("training labels must include both classes")
    model = LogisticRegression(fit_intercept=True, random_state=0, max_iter=MAX_ITER)
    model.fit(features, labels)
    threshold = float(labels.mean())
    if model.coef_.shape != (1, P_WITH_INTERCEPT - 1):
        raise ValueError("unexpected coefficient shape")
    return FittedH001(model, threshold, P_WITH_INTERCEPT)


def positive_probability(fitted: FittedH001, x: np.ndarray) -> np.ndarray:
    features = np.asarray(x, dtype=float)
    if features.ndim != 2 or features.shape[1] != len(FEATURE_COLUMNS):
        raise ValueError("x must have four predictor columns")
    return np.asarray(fitted.model.predict_proba(features)[:, 1], dtype=float)


def take_trade(probability: float, training_prevalence: float) -> bool:
    """A probability equal to the training prevalence does not trade."""
    return float(probability) > float(training_prevalence)
