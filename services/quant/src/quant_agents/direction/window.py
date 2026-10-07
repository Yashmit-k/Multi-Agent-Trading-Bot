"""Fixed trailing-window length. It is a model parameter because several engine fields depend on it."""

WINDOW_BARS = {"1d": 60, "5m": 60}
MIN_WINDOW_BARS = 34
PURGE_BARS = 36


def window_bars(timeframe: str) -> int:
    key = timeframe.lower()
    if key not in WINDOW_BARS:
        raise SystemExit(f"unsupported timeframe {timeframe}")
    length = WINDOW_BARS[key]
    if length < MIN_WINDOW_BARS:
        raise SystemExit(f"window for {key} must be at least {MIN_WINDOW_BARS}")
    return length


def model_version(timeframe: str) -> str:
    """Identity of this baseline. Includes the window so training and inference cannot drift."""
    return f"direction-v1:{timeframe.lower()}:window={window_bars(timeframe)}"
