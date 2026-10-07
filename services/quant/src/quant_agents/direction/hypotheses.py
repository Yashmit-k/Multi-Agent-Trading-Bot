"""New hypotheses on the frozen stock tapes. Logistic only. Validation net bps.

The 2026 test rows are not fit and not scored. LightGBM and XGBoost are not used.
Context-relative and VIX regime rules stay unfitted until a confirmed context snapshot exists.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from quant_agents.direction.inventory import EXCLUDED, IST, SymbolTape

TRAIN_LAST = date(2025, 6, 30)
VALID_LAST = date(2025, 12, 31)
FROZEN_TEST_START = date(2026, 1, 1)
COST_LADDER_BPS = (1.0, 2.0, 3.0, 5.0)
SECTOR_OF = {
    "AXISBANK": "NIFTY BANK",
    "HDFCBANK": "NIFTY BANK",
    "ICICIBANK": "NIFTY BANK",
    "INDUSINDBK": "NIFTY BANK",
    "KOTAKBANK": "NIFTY BANK",
    "SBIN": "NIFTY BANK",
    "BAJFINANCE": "NIFTY FIN SERVICE",
    "BAJAJFINSV": "NIFTY FIN SERVICE",
    "HDFCLIFE": "NIFTY FIN SERVICE",
    "SBILIFE": "NIFTY FIN SERVICE",
    "SHRIRAMFIN": "NIFTY FIN SERVICE",
    "HCLTECH": "NIFTY IT",
    "INFY": "NIFTY IT",
    "TCS": "NIFTY IT",
    "TECHM": "NIFTY IT",
    "WIPRO": "NIFTY IT",
    "BAJAJ-AUTO": "NIFTY AUTO",
    "EICHERMOT": "NIFTY AUTO",
    "HEROMOTOCO": "NIFTY AUTO",
    "M&M": "NIFTY AUTO",
    "MARUTI": "NIFTY AUTO",
    "BRITANNIA": "NIFTY FMCG",
    "HINDUNILVR": "NIFTY FMCG",
    "ITC": "NIFTY FMCG",
    "NESTLEIND": "NIFTY FMCG",
    "TATACONSUM": "NIFTY FMCG",
    "HINDALCO": "NIFTY METAL",
    "JSWSTEEL": "NIFTY METAL",
    "TATASTEEL": "NIFTY METAL",
    "CIPLA": "NIFTY PHARMA",
    "DRREDDY": "NIFTY PHARMA",
    "SUNPHARMA": "NIFTY PHARMA",
    "BPCL": "NIFTY ENERGY",
    "COALINDIA": "NIFTY ENERGY",
    "NTPC": "NIFTY ENERGY",
    "ONGC": "NIFTY ENERGY",
    "POWERGRID": "NIFTY ENERGY",
    "RELIANCE": "NIFTY ENERGY",
    "TITAN": "NIFTY CONSR DURBL",
}
HOLD_STEPS = 12
HOLD_CLOCKS = frozenset({"09:15", "10:15", "11:15", "12:15", "13:15", "14:15"})
RANK_WIDTH = 5
RANK_HORIZONS = (1, 6, 12)
RANK_VOLUME_BARS = 20
RANK_FEATURES = (
    "momentum_5m",
    "momentum_30m",
    "momentum_60m",
    "stock_minus_nifty_5m",
    "stock_minus_nifty_30m",
    "stock_minus_nifty_60m",
    "stock_minus_sector_5m",
    "stock_minus_sector_30m",
    "stock_minus_sector_60m",
    "relative_volume",
    "volatility_60m",
)
LOOKBACK = {"5m": 12, "1d": 20}
EXTREME = {"5m": 0.005, "1d": 0.03}
FIVE_MINUTES = timedelta(minutes=5)


def assert_no_frozen_test(days: np.ndarray) -> None:
    if len(days) and np.max(days) >= np.datetime64(FROZEN_TEST_START):
        raise SystemExit("refusing to score the frozen 2026 test rows")


def every_bar_nets(probability: np.ndarray, forward: np.ndarray) -> dict[str, object]:
    position = np.where(probability >= 0.5, 1.0, -1.0)
    gross = float((position * forward * 10000).mean())
    always_long = float((forward * 10000).mean())
    return {
        "trades": int(len(forward)),
        "long_fraction": float((position > 0).mean()),
        "gross_edge_bps": gross,
        "always_long_gross_bps": always_long,
        "net_edge_bps": {str(cost): gross - cost for cost in COST_LADDER_BPS},
        "positive_net_at_2_bps": gross > 2.0,
    }


def score_hypotheses(tapes: dict[str, SymbolTape], timeframe: str, *, context_present: bool) -> dict[str, object]:
    """Fit on train through 2025-06-30. Score validation through 2025-12-31 only."""
    frame = _frame(tapes, timeframe)
    valid_start = np.datetime64(date(2025, 7, 1))
    train_last = np.datetime64(TRAIN_LAST)
    valid_last = np.datetime64(VALID_LAST)
    train = (frame["day"] <= train_last) & (frame["next_day"] <= train_last)
    valid = (frame["day"] >= valid_start) & (frame["next_day"] >= valid_start) & (frame["next_day"] <= valid_last)
    assert_no_frozen_test(frame["day"][train | valid])
    lookback = LOOKBACK[timeframe]
    extreme = EXTREME[timeframe]
    results = {
        "timeframe": timeframe,
        "test_rows_used": False,
        "estimator": "sklearn.linear_model.LogisticRegression",
        "lookback_bars": lookback,
        "extreme_abs_return": extreme,
        "hypotheses": {
            "cross_sectional_relative_strength": _logistic_edge(
                frame["z"][train], frame["up"][train], frame["z"][valid], frame["up"][valid], frame["next"][valid]
            ),
            "momentum_continuation": _logistic_edge(
                frame["lookback"][train], frame["up"][train], frame["lookback"][valid], frame["up"][valid], frame["next"][valid]
            ),
            "mean_reversion_after_extreme": _extreme_edge(frame, train, valid, extreme),
            "regime_vix_or_nifty": {
                "skipped": not context_present,
                "reason": None
                if context_present
                else "India VIX and NIFTY context snapshot is absent, so this rule was not fit.",
                "rule": "Split validation by whether India VIX is above its own trailing 20-session median, known at the prior close. Not fit without that series.",
            },
        },
    }
    results["hypotheses"]["cross_sectional_relative_strength"]["definition"] = (
        f"Cross-sectional z-score of the {lookback}-bar return among names at the same bar end. "
        "Sector-index relative strength is not included because those series are not confirmed."
    )
    results["hypotheses"]["momentum_continuation"]["definition"] = (
        f"The stock's own {lookback}-bar return. Stock-minus-index momentum waits on the context snapshot."
    )
    results["hypotheses"]["mean_reversion_after_extreme"]["definition"] = (
        f"Trade only when the completed bar's own absolute return is at least {extreme:.3f}. "
        "The cutoff is stated in advance. The next bar's outcome does not decide entry."
    )
    scored = [
        item
        for item in results["hypotheses"].values()
        if not item.get("skipped")
    ]
    results["any_positive_net_at_2_bps"] = any(item.get("positive_net_at_2_bps") for item in scored)
    return results


def score_context_rules(stocks: dict[str, SymbolTape], context: dict[str, SymbolTape], timeframe: str) -> dict[str, object]:
    """Fit only the context rules. Already scored stock-only rules are left untouched."""
    rows = _labeled_rows(stocks, timeframe)
    days = np.array([np.datetime64(row["day"].isoformat()) for row in rows]) if rows else np.array([], dtype="datetime64[D]")
    next_days = np.array([np.datetime64(row["next_day"].isoformat()) for row in rows]) if rows else np.array([], dtype="datetime64[D]")
    train_last = np.datetime64(TRAIN_LAST)
    valid_start = np.datetime64(date(2025, 7, 1))
    valid_last = np.datetime64(VALID_LAST)
    train = (days <= train_last) & (next_days <= train_last) if len(rows) else np.array([], dtype=bool)
    valid = (days >= valid_start) & (next_days >= valid_start) & (next_days <= valid_last) if len(rows) else np.array([], dtype=bool)
    assert_no_frozen_test(days[train | valid] if len(rows) else days)
    present = set(context)
    vix = context.get("INDIA VIX")
    if vix is None or not vix.bars:
        regime = {
            "skipped": True,
            "discarded": True,
            "reason": "India VIX did not arrive, so no stock average was substituted.",
        }
    else:
        regime = _regime_edges(rows, train, valid, _vix_high_before_session(vix))
    sector = _sector_edge(rows, train, valid, context, timeframe)
    return {
        "timeframe": timeframe,
        "estimator": "sklearn.linear_model.LogisticRegression",
        "test_rows_used": False,
        "stock_only_rules_refit": False,
        "context_symbols": sorted(present),
        "hypotheses": {"regime_vix": regime, "sector_relative": sector},
    }


def _regime_edges(rows: list[dict], train: np.ndarray, valid: np.ndarray, high_vix: dict[date, bool]) -> dict[str, object]:
    known = np.array([row["day"] in high_vix for row in rows])
    high = np.array([high_vix.get(row["day"], False) for row in rows])
    look = np.array([row["lookback"] for row in rows], dtype=np.float64)
    up = np.array([row["up"] for row in rows], dtype=np.float64)
    forward = np.array([row["next"] for row in rows], dtype=np.float64)
    sides = {}
    for name, mask in (("vix_above_median", high), ("vix_at_or_below_median", ~high)):
        fitted = _logistic_edge(look[train & known & mask], up[train & known & mask], look[valid & known & mask], up[valid & known & mask], forward[valid & known & mask])
        fitted["discarded"] = not bool(fitted.get("positive_net_at_2_bps"))
        sides[name] = fitted
    return {"skipped": False, "rule": "India VIX versus its trailing 20-session median, known at the prior close.", "sides": sides}


def _sector_edge(rows: list[dict], train: np.ndarray, valid: np.ndarray, context: dict[str, SymbolTape], timeframe: str) -> dict[str, object]:
    indexes = {name: _index_lookback(tape, timeframe) for name, tape in context.items() if name in set(SECTOR_OF.values())}
    if not indexes:
        return {"skipped": True, "discarded": True, "reason": "no verified sector index was available"}
    feature = []
    keep = []
    for row in rows:
        sector = SECTOR_OF.get(row["symbol"])
        series = indexes.get(sector) if sector else None
        value = None if series is None else series.get(row["key"])
        feature.append(np.nan if value is None else row["lookback"] - value)
        keep.append(sector if value is not None else None)
    used = sorted({name for name in keep if name})
    x = np.array(feature, dtype=np.float64)
    up = np.array([row["up"] for row in rows], dtype=np.float64)
    forward = np.array([row["next"] for row in rows], dtype=np.float64)
    fitted = _logistic_edge(x[train], up[train], x[valid], up[valid], forward[valid])
    fitted["discarded"] = not bool(fitted.get("positive_net_at_2_bps"))
    fitted["sectors"] = used
    fitted["rule"] = "Stock lookback return minus the same lookback return of its verified sector index."
    return fitted


def _vix_high_before_session(tape: SymbolTape) -> dict[date, bool]:
    """True when the prior close is above the median of the 20 sessions ending at that close."""
    closes = [(bar.session_date, float(bar.close)) for bar in tape.bars if bar.timeframe == "1d" and bar.session_date <= VALID_LAST]
    state: dict[date, bool] = {}
    for index in range(20, len(closes)):
        window = [value for _, value in closes[index - 20 : index]]
        state[closes[index][0]] = closes[index - 1][1] > float(np.median(window))
    return state


def _index_lookback(tape: SymbolTape, timeframe: str) -> dict[object, float]:
    lookback = LOOKBACK[timeframe]
    bars = [bar for bar in tape.bars if bar.timeframe == timeframe and bar.session_date <= VALID_LAST]
    found: dict[object, float] = {}
    for index, bar in enumerate(bars):
        distant = _back(bars, index, lookback, timeframe)
        if distant in (None, 0) or bar.close == 0:
            continue
        key = bar.end if timeframe == "5m" else bar.session_date
        found[key] = float(bar.close / distant - 1)
    return found


def _labeled_rows(tapes: dict[str, SymbolTape], timeframe: str) -> list[dict]:
    lookback = LOOKBACK[timeframe]
    rows: list[dict] = []
    for symbol, tape in sorted(tapes.items()):
        if symbol == EXCLUDED or not tape.bars:
            continue
        bars = [bar for bar in tape.bars if bar.timeframe == timeframe]
        for index, bar in enumerate(bars):
            if bar.session_date > VALID_LAST:
                break
            nxt = index + 1
            if nxt >= len(bars) or not _step(bars, index, nxt, timeframe):
                continue
            distant = _back(bars, index, lookback, timeframe)
            if distant in (None, 0) or bar.close == 0 or bars[nxt].close == 0:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "day": bar.session_date,
                    "next_day": bars[nxt].session_date,
                    "key": bar.end if timeframe == "5m" else bar.session_date,
                    "lookback": float(bar.close / distant - 1),
                    "next": float(bars[nxt].close / bar.close - 1),
                    "up": 1.0 if bars[nxt].close > bar.close else 0.0 if bars[nxt].close < bar.close else np.nan,
                }
            )
    return rows


def book_positions(symbols: list[str], probability: np.ndarray, width: int = RANK_WIDTH) -> np.ndarray:
    """Long the highest probabilities and short the lowest. Ties break by symbol."""
    position = np.zeros(len(symbols), dtype=np.float64)
    if len(symbols) < width * 2:
        return position
    order = sorted(range(len(symbols)), key=lambda index: (-float(probability[index]), symbols[index]))
    for index in order[:width]:
        position[index] = 1.0
    for index in order[-width:]:
        position[index] = -1.0
    return position


def score_rank(stocks: dict[str, SymbolTape], context: dict[str, SymbolTape]) -> dict[str, object]:
    """Rank the 5-minute cross-section. Trade the top and bottom five names only."""
    nifty = context.get("NIFTY 50")
    if nifty is None or not nifty.bars:
        return {
            "timeframe": "5m",
            "estimator": "sklearn.linear_model.LogisticRegression",
            "test_rows_used": False,
            "holdout_used": False,
            "stock_only_rules_refit": False,
            "skipped": True,
            "discarded": True,
            "reason": "NIFTY 50 context is absent.",
        }
    sector_returns = {
        name: _horizon_returns(tape) for name, tape in context.items() if name in set(SECTOR_OF.values())
    }
    rows = _rank_rows(stocks, _horizon_returns(nifty), sector_returns)
    kept = _label_relative(rows)
    if not kept:
        return _rank_skip("no cross-section cleared the 10-name median filter")
    days = np.array([np.datetime64(row["day"].isoformat()) for row in kept])
    next_days = np.array([np.datetime64(row["next_day"].isoformat()) for row in kept])
    train_last = np.datetime64(TRAIN_LAST)
    valid_start = np.datetime64(date(2025, 7, 1))
    valid_last = np.datetime64(VALID_LAST)
    train = (days <= train_last) & (next_days <= train_last)
    valid = (days >= valid_start) & (next_days >= valid_start) & (next_days <= valid_last)
    assert_no_frozen_test(days[train | valid])
    features = np.array([row["features"] for row in kept], dtype=np.float64)
    labels = np.array([row["label"] for row in kept], dtype=np.int8)
    y = labels[train]
    if len(np.unique(y)) < 2 or int(valid.sum()) < 50:
        return _rank_skip("not enough classes or validation rows")
    scaler = StandardScaler()
    model = LogisticRegression(random_state=0, max_iter=500)
    model.fit(scaler.fit_transform(features[train]), y)
    probability = model.predict_proba(scaler.transform(features[valid]))[:, 1]
    traded_position, traded_forward = _ranked_book(kept, np.flatnonzero(valid), probability)
    if len(traded_forward) < 50:
        return _rank_skip("fewer than 50 ranked trades")
    gross = float((traded_position * traded_forward * 10000).mean())
    always_long = float((traded_forward * 10000).mean())
    report = {
        "timeframe": "5m",
        "estimator": "sklearn.linear_model.LogisticRegression",
        "test_rows_used": False,
        "holdout_used": False,
        "stock_only_rules_refit": False,
        "skipped": False,
        "rank_width": RANK_WIDTH,
        "features": list(RANK_FEATURES),
        "coefficient": [float(value) for value in model.coef_[0]],
        "intercept": float(model.intercept_[0]),
        "trades": int(len(traded_forward)),
        "long_fraction": float((traded_position > 0).mean()),
        "gross_edge_bps": gross,
        "always_long_gross_bps": always_long,
        "net_edge_bps": {str(cost): gross - cost for cost in COST_LADDER_BPS},
        "positive_net_at_2_bps": gross > 2.0,
        "discarded": not (gross > 2.0),
        "rule": "Long the five highest probabilities of beating the cross-sectional median and short the five lowest.",
    }
    labeled = labels[valid]
    if len(np.unique(labeled)) == 2:
        report["auc"] = float(roc_auc_score(labeled, probability))
        report["accuracy"] = float(accuracy_score(labeled, probability >= 0.5))
    return report


def score_hold(stocks: dict[str, SymbolTape], context: dict[str, SymbolTape]) -> dict[str, object]:
    """One 60-minute cross-sectional hold. The 2 bp cost is charged once per hold."""
    nifty = context.get("NIFTY 50")
    if nifty is None or not nifty.bars:
        skipped = _rank_skip("NIFTY 50 context is absent.")
        skipped["hold_minutes"] = 60
        return skipped
    sector_returns = {
        name: _horizon_returns(tape) for name, tape in context.items() if name in set(SECTOR_OF.values())
    }
    rows = _hold_rows(stocks, _horizon_returns(nifty), sector_returns)
    kept = _label_relative(rows)
    if not kept:
        return _rank_skip("no 60-minute cross-section cleared the 10-name median filter")
    days = np.array([np.datetime64(row["day"].isoformat()) for row in kept])
    next_days = np.array([np.datetime64(row["next_day"].isoformat()) for row in kept])
    train_last = np.datetime64(TRAIN_LAST)
    valid_start = np.datetime64(date(2025, 7, 1))
    valid_last = np.datetime64(VALID_LAST)
    train = (days <= train_last) & (next_days <= train_last)
    valid = (days >= valid_start) & (next_days >= valid_start) & (next_days <= valid_last)
    assert_no_frozen_test(days[train | valid])
    features = np.array([row["features"] for row in kept], dtype=np.float64)
    labels = np.array([row["label"] for row in kept], dtype=np.int8)
    if len(np.unique(labels[train])) < 2 or int(valid.sum()) < 50:
        return _rank_skip("not enough classes or validation rows")
    scaler = StandardScaler()
    model = LogisticRegression(random_state=0, max_iter=500)
    model.fit(scaler.fit_transform(features[train]), labels[train])
    probability = model.predict_proba(scaler.transform(features[valid]))[:, 1]
    traded_position, traded_forward = _ranked_book(kept, np.flatnonzero(valid), probability)
    if len(traded_forward) < 50:
        return _rank_skip("fewer than 50 ranked trades")
    gross = float((traded_position * traded_forward * 10000).mean())
    always_long = float((traded_forward * 10000).mean())
    report = {
        "timeframe": "5m",
        "hold_minutes": HOLD_STEPS * 5,
        "bars_per_hold": HOLD_STEPS,
        "cost_charges_per_trade": 1,
        "estimator": "sklearn.linear_model.LogisticRegression",
        "test_rows_used": False,
        "holdout_used": False,
        "stock_only_rules_refit": False,
        "skipped": False,
        "rank_width": RANK_WIDTH,
        "features": list(RANK_FEATURES),
        "coefficient": [float(value) for value in model.coef_[0]],
        "intercept": float(model.intercept_[0]),
        "trades": int(len(traded_forward)),
        "long_fraction": float((traded_position > 0).mean()),
        "gross_edge_bps": gross,
        "always_long_gross_bps": always_long,
        "net_edge_bps": {str(cost): gross - cost for cost in COST_LADDER_BPS},
        "positive_net_at_2_bps": gross > 2.0,
        "discarded": not (gross > 2.0),
        "rule": "Every hour, long the five names most likely to beat the 60-minute cross-sectional median and short the five least likely. Cost is charged once per hold.",
    }
    if len(np.unique(labels[valid])) == 2:
        report["auc"] = float(roc_auc_score(labels[valid], probability))
        report["accuracy"] = float(accuracy_score(labels[valid], probability >= 0.5))
    return report


def _hold_rows(stocks: dict[str, SymbolTape], nifty: dict, sectors: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    for symbol, tape in sorted(stocks.items()):
        if symbol == EXCLUDED or not tape.bars:
            continue
        bars = [bar for bar in tape.bars if bar.timeframe == "5m"]
        sector_name = SECTOR_OF.get(symbol)
        sector = sectors.get(sector_name) if sector_name else None
        for index, bar in enumerate(bars):
            if bar.session_date > VALID_LAST:
                break
            if bar.start.astimezone(IST).strftime("%H:%M") not in HOLD_CLOCKS:
                continue
            exit_index = _forward_index(bars, index, HOLD_STEPS)
            if exit_index is None:
                continue
            exit_bar = bars[exit_index]
            if exit_bar.session_date != bar.session_date or exit_bar.session_date > VALID_LAST:
                continue
            if bar.close == 0 or exit_bar.close == 0:
                continue
            features = _rank_features(bars, index, nifty.get(bar.end), None if sector is None else sector.get(bar.end))
            if features is None:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "end": bar.end,
                    "day": bar.session_date,
                    "next_day": exit_bar.session_date,
                    "next": float(exit_bar.close / bar.close - 1),
                    "features": features,
                }
            )
    return rows


def _forward_index(bars, index: int, steps: int) -> int | None:
    cursor = index
    for _ in range(steps):
        nxt = cursor + 1
        if nxt >= len(bars) or not _step(bars, cursor, nxt, "5m"):
            return None
        cursor = nxt
    return cursor


def _rank_skip(reason: str) -> dict[str, object]:
    return {
        "timeframe": "5m",
        "estimator": "sklearn.linear_model.LogisticRegression",
        "test_rows_used": False,
        "holdout_used": False,
        "stock_only_rules_refit": False,
        "skipped": True,
        "discarded": True,
        "reason": reason,
    }


def _ranked_book(rows: list[dict], valid_index: np.ndarray, probability: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    groups: dict[object, list[tuple[str, float, float]]] = {}
    for slot, row_index in enumerate(valid_index):
        row = rows[int(row_index)]
        groups.setdefault(row["end"], []).append((row["symbol"], float(probability[slot]), row["next"]))
    positions: list[float] = []
    forward: list[float] = []
    for items in groups.values():
        if len(items) < RANK_WIDTH * 2:
            continue
        symbols = [item[0] for item in items]
        scores = np.array([item[1] for item in items])
        book = book_positions(symbols, scores)
        for item, side in zip(items, book, strict=True):
            if side == 0:
                continue
            positions.append(float(side))
            forward.append(item[2])
    return np.array(positions, dtype=np.float64), np.array(forward, dtype=np.float64)


def _label_relative(rows: list[dict]) -> list[dict]:
    """Keep names strictly above or below the cross-sectional median of the next return."""
    if not rows:
        return []
    stamps = np.array([row["end"].timestamp() for row in rows])
    order = np.argsort(stamps, kind="mergesort")
    stamps = stamps[order]
    change = np.flatnonzero(stamps[1:] != stamps[:-1]) + 1
    starts = np.r_[0, change]
    stops = np.r_[change, len(order)]
    kept: list[dict] = []
    for start, stop in zip(starts, stops, strict=True):
        chosen = order[start:stop]
        if len(chosen) < 10:
            continue
        forward = np.array([rows[int(index)]["next"] for index in chosen], dtype=np.float64)
        middle = float(np.median(forward))
        survivors = [(int(index), value) for index, value in zip(chosen, forward, strict=True) if value != middle]
        if len(survivors) < 10:
            continue
        for index, value in survivors:
            row = dict(rows[index])
            row["label"] = 1 if value > middle else 0
            kept.append(row)
    return kept


def _rank_rows(stocks: dict[str, SymbolTape], nifty: dict, sectors: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    for symbol, tape in sorted(stocks.items()):
        if symbol == EXCLUDED or not tape.bars:
            continue
        bars = [bar for bar in tape.bars if bar.timeframe == "5m"]
        sector_name = SECTOR_OF.get(symbol)
        sector = sectors.get(sector_name) if sector_name else None
        for index, bar in enumerate(bars):
            if bar.session_date > VALID_LAST:
                break
            nxt = index + 1
            if nxt >= len(bars) or not _step(bars, index, nxt, "5m"):
                continue
            if bars[nxt].session_date > VALID_LAST or bar.close == 0 or bars[nxt].close == 0:
                continue
            features = _rank_features(bars, index, nifty.get(bar.end), None if sector is None else sector.get(bar.end))
            if features is None:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "end": bar.end,
                    "day": bar.session_date,
                    "next_day": bars[nxt].session_date,
                    "next": float(bars[nxt].close / bar.close - 1),
                    "features": features,
                }
            )
    return rows


def _rank_features(bars, index: int, nifty_return, sector_return) -> list[float] | None:
    if nifty_return is None or _back(bars, index, RANK_VOLUME_BARS, "5m") is None:
        return None
    momentum = []
    for step in RANK_HORIZONS:
        distant = bars[index - step].close
        if distant == 0 or bars[index].close == 0:
            return None
        momentum.append(float(bars[index].close / distant - 1))
    versus_nifty = [left - right for left, right in zip(momentum, nifty_return, strict=True)]
    versus_sector = [0.0, 0.0, 0.0] if sector_return is None else [left - right for left, right in zip(momentum, sector_return, strict=True)]
    volumes = [bars[index - step].volume for step in range(1, RANK_VOLUME_BARS + 1)]
    baseline = float(np.mean(volumes))
    if baseline == 0:
        return None
    returns = []
    for step in range(1, RANK_HORIZONS[-1] + 1):
        previous = bars[index - step].close
        current = bars[index - step + 1].close
        if previous == 0:
            return None
        returns.append(float(current / previous - 1))
    return [*momentum, *versus_nifty, *versus_sector, float(bars[index].volume) / baseline, float(np.std(returns))]


def _horizon_returns(tape: SymbolTape) -> dict:
    bars = [bar for bar in tape.bars if bar.timeframe == "5m" and bar.session_date <= VALID_LAST]
    found: dict = {}
    for index, bar in enumerate(bars):
        if bar.close == 0 or _back(bars, index, RANK_HORIZONS[-1], "5m") is None:
            continue
        returns = []
        for step in RANK_HORIZONS:
            distant = bars[index - step].close
            if distant == 0:
                returns = []
                break
            returns.append(float(bar.close / distant - 1))
        if len(returns) == len(RANK_HORIZONS):
            found[bar.end] = tuple(returns)
    return found


def _extreme_edge(frame: dict[str, np.ndarray], train: np.ndarray, valid: np.ndarray, extreme: float) -> dict[str, object]:
    hot_train = train & (np.abs(frame["one"]) >= extreme)
    hot_valid = valid & (np.abs(frame["one"]) >= extreme)
    if int(hot_train.sum()) < 50 or int(hot_valid.sum()) < 50:
        return {"skipped": True, "reason": "fewer than 50 extreme bars", "trades": int(hot_valid.sum())}
    fitted = _logistic_edge(
        frame["one"][hot_train],
        frame["up"][hot_train],
        frame["one"][hot_valid],
        frame["up"][hot_valid],
        frame["next"][hot_valid],
    )
    fitted["skipped"] = False
    return fitted


def _logistic_edge(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_valid: np.ndarray,
    y_valid: np.ndarray,
    forward_valid: np.ndarray,
) -> dict[str, object]:
    usable_train = np.isfinite(x_train) & np.isfinite(y_train)
    usable_valid = np.isfinite(x_valid) & np.isfinite(forward_valid)
    y = (y_train[usable_train] > 0).astype(np.int8)
    if len(np.unique(y)) < 2 or int(usable_valid.sum()) < 50:
        return {"skipped": True, "reason": "not enough classes or validation rows"}
    scaler = StandardScaler()
    model = LogisticRegression(random_state=0, max_iter=500)
    model.fit(scaler.fit_transform(x_train[usable_train].reshape(-1, 1)), y)
    probability = model.predict_proba(scaler.transform(x_valid[usable_valid].reshape(-1, 1)))[:, 1]
    report = every_bar_nets(probability, forward_valid[usable_valid])
    labeled = np.isfinite(y_valid[usable_valid])
    y = (y_valid[usable_valid][labeled] > 0).astype(np.int8)
    if len(np.unique(y)) == 2:
        report["auc"] = float(roc_auc_score(y, probability[labeled]))
        report["accuracy"] = float(accuracy_score(y, probability[labeled] >= 0.5))
    report["skipped"] = False
    report["coefficient"] = float(model.coef_[0, 0])
    report["intercept"] = float(model.intercept_[0])
    return report


def _frame(tapes: dict[str, SymbolTape], timeframe: str) -> dict[str, np.ndarray]:
    lookback = LOOKBACK[timeframe]
    rows: list[tuple] = []
    for symbol, tape in sorted(tapes.items()):
        if symbol == EXCLUDED or not tape.bars:
            continue
        bars = tape.bars
        for index, bar in enumerate(bars):
            if bar.session_date > VALID_LAST:
                break
            nxt = index + 1
            if nxt >= len(bars) or not _step(bars, index, nxt, timeframe):
                continue
            previous = _back(bars, index, 1, timeframe)
            distant = _back(bars, index, lookback, timeframe)
            if previous is None or distant is None or bar.close == 0 or bars[nxt].close == 0 or distant == 0 or previous == 0:
                continue
            rows.append(
                (
                    bar.end,
                    np.datetime64(bar.session_date.isoformat()),
                    np.datetime64(bars[nxt].session_date.isoformat()),
                    float(bar.close / distant - 1),
                    float(bar.close / previous - 1),
                    float(bars[nxt].close / bar.close - 1),
                )
            )
    ends = [row[0] for row in rows]
    day = np.array([row[1] for row in rows])
    next_day = np.array([row[2] for row in rows])
    look = np.array([row[3] for row in rows], dtype=np.float64)
    one = np.array([row[4] for row in rows], dtype=np.float64)
    nxt_ret = np.array([row[5] for row in rows], dtype=np.float64)
    z = _zscore(ends, look)
    up = np.where(nxt_ret > 0, 1.0, np.where(nxt_ret < 0, 0.0, np.nan))
    return {"day": day, "next_day": next_day, "lookback": look, "one": one, "next": nxt_ret, "z": z, "up": up}


def _zscore(ends: list, values: np.ndarray) -> np.ndarray:
    stamps = np.array([item.timestamp() for item in ends])
    order = np.argsort(stamps, kind="mergesort")
    stamps = stamps[order]
    change = np.flatnonzero(stamps[1:] != stamps[:-1]) + 1
    starts = np.r_[0, change]
    stops = np.r_[change, len(order)]
    score = np.full(len(values), np.nan)
    ordered = values[order]
    for start, stop in zip(starts, stops, strict=True):
        chunk = ordered[start:stop]
        if len(chunk) < 10:
            continue
        scale = float(chunk.std())
        center = float(chunk.mean())
        filled = np.zeros(len(chunk)) if scale == 0 else (chunk - center) / scale
        score[order[start:stop]] = filled
    return score


def _step(bars, left: int, right: int, timeframe: str) -> bool:
    if timeframe == "5m":
        return bars[right].end - bars[left].end == FIVE_MINUTES
    return True


def _back(bars, index: int, steps: int, timeframe: str):
    cursor = index
    for _ in range(steps):
        previous = cursor - 1
        if previous < 0 or not _step(bars, previous, cursor, timeframe):
            return None
        cursor = previous
    return bars[cursor].close
