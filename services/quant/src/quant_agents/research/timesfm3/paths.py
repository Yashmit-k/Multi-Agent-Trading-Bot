"""Allowed daily snapshot path. Holdout and the short 2026 tape are refused."""

from __future__ import annotations

from pathlib import Path

SNAPSHOT_DIRNAME = "snapshots 2"
DAILY_SNAPSHOT_ID = "nifty50_1d_20261005"


class SnapshotRefused(RuntimeError):
    """The path is not the frozen daily research snapshot."""


def daily_candle_file(root: Path | None = None) -> Path:
    """`snapshots 2/nifty50/1D/candles.jsonl`. Nothing else is accepted."""
    if root is None:
        root = _default_root()
    path = (root / "1D" / "candles.jsonl").resolve()
    _refuse_unless_daily_snapshot(path)
    if not path.is_file():
        raise SnapshotRefused(f"missing candle file for {DAILY_SNAPSHOT_ID}")
    return path


def _default_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / SNAPSHOT_DIRNAME / "nifty50"
        if candidate.is_dir():
            return candidate
    raise SnapshotRefused("snapshots 2/nifty50 is not available")


def _refuse_unless_daily_snapshot(path: Path) -> None:
    text = str(path)
    if "holdout" in text or "holdout_after_20261005" in text:
        raise SnapshotRefused("refusing holdout snapshot")
    if path.name != "candles.jsonl" or path.parent.name != "1D" or path.parent.parent.name != "nifty50":
        raise SnapshotRefused("refusing a path that is not the daily nifty50 snapshot")
    if path.parent.parent.parent.name != SNAPSHOT_DIRNAME:
        raise SnapshotRefused("refusing the short 2026 tape")
