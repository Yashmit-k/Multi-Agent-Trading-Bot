"""Train a synthetic baseline model."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from contracts.enums import Timeframe
from sklearn.metrics import accuracy_score

from quant_agents.ml.artifact import write_artifact
from quant_agents.ml.dataset import FEATURE_COLUMNS, build_dataset
from quant_agents.ml.model import make_model
from quant_agents.ml.splits import chronological_split
from quant_agents.testing.history import HistoryFeatureProvider


def _as_of_grid(start: datetime, count: int) -> list[datetime]:
    return [start + timedelta(days=offset) for offset in range(count)]


def train(
    *,
    output_dir: Path,
    cutoff: datetime,
    symbol: str = "RELIANCE",
    timeframe: Timeframe = Timeframe.D1,
    label_horizon: int = 1,
) -> Path:
    provider = HistoryFeatureProvider()
    as_of_points = _as_of_grid(datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), 80)
    dataset = build_dataset(
        provider,
        symbol=symbol,
        timeframe=timeframe,
        as_of_points=as_of_points,
        label_horizon=label_horizon,
        training_data_cutoff=cutoff,
    )
    split = chronological_split(len(dataset.rows), label_horizon=label_horizon)
    x_train = [[row[col] for col in FEATURE_COLUMNS] for row in dataset.rows[: split.train_end]]
    y_train = dataset.labels[: split.train_end]
    x_valid = [[row[col] for col in FEATURE_COLUMNS] for row in dataset.rows[split.train_end : split.valid_end]]
    y_valid = dataset.labels[split.train_end : split.valid_end]
    model = make_model()
    model.fit(x_train, y_train)
    diagnostics = {
        "n_rows": len(dataset.rows),
        "dropped_zero": dataset.dropped_zero,
        "dropped_cutoff": dataset.dropped_cutoff,
        "valid_accuracy": float(accuracy_score(y_valid, model.predict(x_valid))) if y_valid else None,
        "not_live_performance": True,
    }
    write_artifact(
        output_dir,
        model=model,
        model_version="1.0.0-baseline",
        feature_version="1.0.0",
        timeframe=timeframe.value,
        training_data_cutoff=cutoff,
        trained_at=datetime(2024, 6, 1, 0, 0, tzinfo=timezone.utc),
        label_horizon=label_horizon,
        embargo_bars=split.embargo_bars,
        diagnostics=diagnostics,
    )
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a synthetic ML baseline (not live performance)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff", type=str, default="2024-04-01T10:00:00+00:00")
    args = parser.parse_args()
    cutoff = datetime.fromisoformat(args.cutoff)
    train(output_dir=args.output, cutoff=cutoff)


if __name__ == "__main__":
    main()
