import inspect

import numpy as np
import pytest

from quant_agents.research.h001.model import fit_h001, positive_probability, take_trade


def _sample() -> tuple[np.ndarray, np.ndarray]:
    rows = []
    labels = []
    for _ in range(30):
        rows.append([0.0, 0.0, 0.0, 0.0])
        labels.append(0)
        rows.append([1.0, 1.0, 1.0, 1.0])
        labels.append(1)
    return np.array(rows), np.array(labels)


def test_fit_uses_training_prevalence_and_four_columns() -> None:
    x_train, y_train = _sample()
    fitted = fit_h001(x_train, y_train)
    assert fitted.predictor_count == 5
    assert fitted.threshold == pytest.approx(0.5)
    assert fitted.model.intercept_.shape == (1,)
    assert fitted.coefficients.shape == (1, 4)
    probability = positive_probability(fitted, np.array([[1.0, 1.0, 1.0, 1.0]]))[0]
    assert take_trade(probability, fitted.threshold) is True
    assert take_trade(fitted.threshold, fitted.threshold) is False


def test_validation_labels_cannot_change_the_fit() -> None:
    x_train, y_train = _sample()
    y_valid = np.ones(8, dtype=int)
    first = fit_h001(x_train, y_train)
    second = fit_h001(x_train, y_train)
    assert np.array_equal(first.coefficients, second.coefficients)
    assert first.threshold == second.threshold == float(y_train.mean())
    assert first.threshold != float(y_valid.mean())
    assert "y_valid" not in inspect.signature(fit_h001).parameters
    with pytest.raises(TypeError):
        fit_h001(x_train, y_train, y_valid)  # type: ignore[call-arg]
    text = inspect.getsource(fit_h001)
    assert "IsotonicRegression" not in text
    assert "direction.fit" not in text
