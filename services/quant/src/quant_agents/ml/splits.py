"""Chronological splits. Embargo is at least label_horizon bars."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Split:
    train_end: int
    valid_end: int
    test_end: int
    embargo_bars: int


def chronological_split(n_rows: int, *, label_horizon: int, embargo_bars: int | None = None) -> Split:
    embargo = embargo_bars if embargo_bars is not None else label_horizon
    if embargo < label_horizon:
        raise AssertionError("embargo_bars must be >= label_horizon")
    if n_rows < embargo + 9:
        raise ValueError("not enough rows for train/validation/test")
    train_end = int(n_rows * 0.6)
    valid_end = int(n_rows * 0.8)
    if train_end < 3 or valid_end <= train_end:
        raise ValueError("degenerate split")
    return Split(train_end=train_end, valid_end=valid_end, test_end=n_rows, embargo_bars=embargo)


class WalkForwardSplitter:
    def __init__(self, *, train_size: int, test_size: int, label_horizon: int, embargo_bars: int | None = None) -> None:
        self.train_size = train_size
        self.test_size = test_size
        self.label_horizon = label_horizon
        self.embargo_bars = embargo_bars if embargo_bars is not None else label_horizon
        if self.embargo_bars < self.label_horizon:
            raise AssertionError("embargo_bars must be >= label_horizon")

    def split(self, n_rows: int) -> list[tuple[slice, slice]]:
        folds: list[tuple[slice, slice]] = []
        start = 0
        while True:
            train_end = start + self.train_size
            test_start = train_end + self.embargo_bars
            test_end = test_start + self.test_size
            if test_end > n_rows:
                break
            folds.append((slice(start, train_end), slice(test_start, test_end)))
            start += self.test_size
        return folds
