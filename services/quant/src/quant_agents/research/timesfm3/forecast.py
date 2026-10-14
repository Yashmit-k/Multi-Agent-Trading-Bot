"""Zero-shot median forecast. Importing this module does not download weights."""

from __future__ import annotations

from decimal import Decimal

from quant_agents.research.timesfm3.scores import DecisionRow

CHECKPOINT = "google/timesfm-3.0-pytorch"


def median_forecasts(rows: tuple[DecisionRow, ...] | list[DecisionRow]) -> tuple[Decimal, ...]:
    """One median next-close per row. The horizon is 1 session."""
    if not rows:
        raise ValueError("rows must be non-empty")
    import numpy as np
    from timesfm3.mlx import TimesFM3Forecaster

    forecaster = TimesFM3Forecaster.from_pretrained(CHECKPOINT)
    forecasts: list[Decimal] = []
    batch: list[DecisionRow] = []
    for row in rows:
        batch.append(row)
        if len(batch) == 32:
            forecasts.extend(_batch(forecaster, np, batch))
            batch = []
    if batch:
        forecasts.extend(_batch(forecaster, np, batch))
    return tuple(forecasts)


def _batch(forecaster, np, rows: list[DecisionRow]) -> list[Decimal]:
    contexts = [np.asarray([float(price) for price in row.context], dtype=np.float32) for row in rows]
    outputs = list(forecaster.predict_batch(contexts, horizon=1, return_quantiles=True))
    if len(outputs) != len(rows):
        raise RuntimeError("forecast batch length does not match the decision rows")
    return [Decimal(str(float(item.forecast.reshape(-1)[0]))) for item in outputs]
