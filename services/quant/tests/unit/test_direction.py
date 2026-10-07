from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from quant_agents.direction.inventory import StoredBar, SymbolTape, classify_holes, empirical_grid
from quant_agents.direction.rows import (
    assert_window_leakage,
    classify_pair,
    feature_census,
    is_same_session_gap,
    label_counts,
    leakage_cases,
    modeling_indexes,
    next_step_ok,
)
from quant_agents.direction.window import model_version, window_bars
from quant_agents.ml.features import DIRECTION_COLUMNS, FORBIDDEN_X_COLUMNS, direction_row


def _bar(index: int, *, symbol: str = "RELIANCE", close: str = "100", timeframe: str = "5m") -> StoredBar:
    start = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc) + timedelta(minutes=5 * index)
    # Skip overnight: after 75 bars, jump to the next IST session.
    session = index // 75
    slot = index % 75
    day = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc) + timedelta(days=session)
    start = day + timedelta(minutes=5 * slot)
    end = start + timedelta(minutes=5)
    price = Decimal(close) + Decimal(index)
    return StoredBar(
        symbol=symbol,
        timeframe=timeframe,
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price + Decimal("0.5"),
        volume=100 + index,
        start=start,
        end=end,
    )


def _tape(count: int, **kwargs: str) -> SymbolTape:
    return SymbolTape(bars=[_bar(index, **kwargs) for index in range(count)])


def test_window_is_recorded_and_at_least_34() -> None:
    assert window_bars("5m") >= 34
    assert window_bars("1d") >= 34
    assert model_version("5m").endswith(f"window={window_bars('5m')}")


def test_label_buckets_sum_and_match_the_labeler() -> None:
    tape = _tape(80)
    tape.bars[10] = StoredBar(
        symbol="RELIANCE",
        timeframe="5m",
        open=Decimal("110"),
        high=Decimal("111"),
        low=Decimal("109"),
        close=tape.bars[9].close,
        volume=10,
        start=tape.bars[10].start,
        end=tape.bars[10].end,
    )
    cutoff = tape.bars[-1].end + timedelta(seconds=1)
    counted = label_counts(tape, cutoff)
    assert sum(counted.values()) == len(tape.bars)
    assert counted["equal"] == 1
    assert counted["cross_session"] == 1
    assert counted["no_next_bar"] == 1
    assert counted["cutoff"] == 0
    assert counted["up"] + counted["down"] + counted["equal"] + counted["cross_session"] + counted["no_next_bar"] == 80


def test_cross_session_classification_uses_the_same_inputs() -> None:
    current = _bar(74)
    future = _bar(75)
    assert classify_pair(current, future, future.end) == "cross_session"
    assert classify_pair(current, None, current.end) == "no_next_bar"


def test_direction_row_guards_flat_range_and_hides_labels() -> None:
    row = {
        "last_close": 100.0,
        "sma_10": 98.0,
        "sma_20": 97.0,
        "ema_12": 99.0,
        "ema_26": 96.0,
        "macd": 0.4,
        "macd_signal": 0.2,
        "rsi_14": 55.0,
        "atr_14": 1.5,
        "vwap": 101.0,
        "bollinger_lower": 94.0,
        "bollinger_upper": 106.0,
        "last_volume": 10.0,
        "volume_mean": 8.0,
        "return_1": 0.01,
        "volatility": 0.02,
        "momentum_10": 2.0,
    }
    features, reason = direction_row(row, open_=100.0, high=101.0, low=99.0, close=100.5)
    assert reason is None
    assert features is not None
    assert "close_window_vwap" in features
    assert "close_vwap" not in features
    assert set(features).isdisjoint(FORBIDDEN_X_COLUMNS)
    assert not any(name.startswith("future_") for name in features)
    assert set(features) == set(DIRECTION_COLUMNS)
    empty, flat = direction_row(row, open_=100.0, high=100.0, low=100.0, close=100.0)
    assert empty is None
    assert flat == "flat_range"
    zero_volume = dict(row)
    zero_volume["volume_mean"] = 0.0
    dropped, why = direction_row(zero_volume, open_=100.0, high=101.0, low=99.0, close=100.5)
    assert dropped is None
    assert why == "zero_denominator"


def test_leakage_holds_across_session_edges() -> None:
    tape = _tape(160)
    grid = {bar.start for bar in tape.bars}
    # Remove one interior bar from the grid so a neighbour is sampled, but keep the tape intact.
    hole = tape.bars[90].start
    grid.discard(hole)
    cases = leakage_cases(tape, grid)
    assert cases
    assert_window_leakage(tape, cases)
    census = feature_census(tape)
    assert census["short_window_dropped"] == window_bars("5m") - 1
    assert census["rows_remaining"] > 0
    assert census["first_bars_of_session"] >= 1


def test_hole_list_names_every_missing_timestamp() -> None:
    full = _tape(10, symbol="RELIANCE")
    short = SymbolTape(bars=[full.bars[0], full.bars[2], full.bars[3]])
    short.bars = [StoredBar(
        symbol="ITC",
        timeframe=bar.timeframe,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        start=bar.start,
        end=bar.end,
    ) for bar in short.bars]
    grid = empirical_grid({"RELIANCE": full, "INFY": full, "ITC": short})
    missing = [stamp for stamp in grid if stamp not in {bar.start for bar in short.bars}]
    holes = classify_holes(missing, grid, "5m")
    listed = [stamp for hole in holes for stamp in hole["timestamps"]]
    assert listed == [stamp.isoformat() for stamp in missing]
    assert missing
    open_hole = classify_holes([grid[0]], grid, "5m")
    assert open_hole[0]["session_open"] is True
    assert open_hole[0]["same_session_labels_affected"] == 0


def _expected_modeling_indexes(bars: list[StoredBar]) -> list[int]:
    """Independent of modeling_indexes. Reads only the bar fields."""
    kept: list[int] = []
    for index, bar in enumerate(bars):
        if index < 59 or bar.high == bar.low or index + 1 >= len(bars):
            continue
        future = bars[index + 1]
        if bar.timeframe == "5m" and future.end - bar.end != timedelta(minutes=5):
            continue
        if future.close == bar.close:
            continue
        kept.append(index)
    return kept


def test_modeling_bounds_follow_the_first_and_last_eligible_bar() -> None:
    tape = _tape(160)
    # An equal close on the 60th bar must move the first modeling bar later.
    tape.bars[59] = StoredBar(
        symbol=tape.bars[59].symbol,
        timeframe=tape.bars[59].timeframe,
        open=tape.bars[59].open,
        high=tape.bars[59].high,
        low=tape.bars[59].low,
        close=tape.bars[60].close,
        volume=tape.bars[59].volume,
        start=tape.bars[59].start,
        end=tape.bars[59].end,
    )
    expected = _expected_modeling_indexes(tape.bars)
    kept = modeling_indexes(tape)
    assert kept == expected
    assert kept[0] > 59
    assert tape.bars[kept[0]].end == tape.bars[expected[0]].end
    assert tape.bars[kept[-1]].end == tape.bars[expected[-1]].end


def test_real_tape_modeling_bounds_match_raw_candles() -> None:
    root = Path("/Users/yashmitkotekar/Coding/Multi-Agent-Trading-Bot/snapshots/nifty50")
    if not (root / "5m" / "candles.jsonl").exists():
        pytest.skip("real snapshot is not on this machine")
    from quant_agents.direction.inventory import EXCLUDED, load_tapes

    for folder in ("1D", "5m"):
        tapes = load_tapes(root / folder / "candles.jsonl")
        for symbol, tape in tapes.items():
            if symbol == EXCLUDED or not tape.bars:
                continue
            expected = _expected_modeling_indexes(tape.bars)
            kept = modeling_indexes(tape)
            assert kept == expected, symbol
            assert tape.bars[kept[0]].end == tape.bars[expected[0]].end
            assert tape.bars[kept[-1]].end == tape.bars[expected[-1]].end


def test_feature_window_has_no_bar_after_as_of() -> None:
    tape = _tape(80)
    length = window_bars("5m")
    for index in modeling_indexes(tape):
        window = tape.bars[index + 1 - length : index + 1]
        assert window[-1].end == tape.bars[index].end
        assert all(bar.end <= tape.bars[index].end for bar in window)
    assert_window_leakage(tape, [59, 70])


def test_five_minute_rule_drops_same_session_gaps() -> None:
    tape = _tape(80)
    current = tape.bars[10]
    future = tape.bars[12]
    assert not next_step_ok(current, future)
    assert is_same_session_gap(current, future)
    assert next_step_ok(current, tape.bars[11])


def test_features_ignore_bars_after_as_of(monkeypatch: pytest.MonkeyPatch) -> None:
    tape = _tape(80)
    seen: list[datetime] = []
    real = __import__("core_features.engine", fromlist=["build_feature_set"]).build_feature_set

    def _spy(symbol: str, timeframe, candles, as_of: datetime):
        for bar in candles:
            if bar.end > as_of:
                seen.append(bar.end)
        return real(symbol, timeframe, candles, as_of)

    monkeypatch.setattr("quant_agents.direction.rows.build_feature_set", _spy)
    assert_window_leakage(tape, leakage_cases(tape, {bar.start for bar in tape.bars}))
    # The engine is allowed to receive later bars. It must ignore them, which the
    # mutation assertion already checks. This records that the call saw them.
    assert seen


def test_review_selection_reliability_and_folds() -> None:
    from datetime import date, time

    import numpy as np

    from quant_agents.direction.fit import BOOTSTRAP_DRAWS, _bootstrap
    from quant_agents.direction.review import (
        choose_candidate,
        fixed_split_review,
        fold_bounds,
        reliability_table,
        time_of_day_bucket,
        walk_forward,
    )

    assert choose_candidate({"base": 0.2, "time_of_day": 0.1}, ("base", "time_of_day")) == "time_of_day"
    assert choose_candidate({"base": 0.2, "time_of_day": 0.2}, ("base", "time_of_day")) == "base"
    assert fold_bounds(date(2026, 10, 5))[-1] == (date(2026, 10, 1), date(2027, 1, 1))
    assert time_of_day_bucket(9 * 60 + 20) == "09:15-10:15"
    assert time_of_day_bucket(15 * 60 + 30) == "15:15-15:30"

    y = np.array([0, 0, 1, 1, 1])
    table = reliability_table(y, np.array([0.1, 0.2, 0.55, 0.7, 0.95]))
    assert len(table) == 10
    assert sum(row["rows"] for row in table) == 5
    assert table[0]["rows"] == 0

    days = np.array(["2026-01-02", "2026-01-02", "2026-01-05"], dtype="datetime64[D]")
    boot = _bootstrap(np.array([0, 1, 1]), np.array([0.4, 0.6, 0.7]), days, 0.5)
    assert boot["samples"] == BOOTSTRAP_DRAWS == 1000

    rng = np.random.default_rng(0)
    ends = []
    cursor = date(2024, 1, 3)
    while cursor <= date(2026, 10, 5):
        if cursor.weekday() < 5:
            stamp = datetime.combine(cursor, time(10, 0), tzinfo=timezone.utc)
            ends.extend((stamp, stamp, stamp))
        cursor += timedelta(days=1)
    count = len(ends)
    x = rng.normal(size=(count, len(DIRECTION_COLUMNS)))
    signal = x[:, DIRECTION_COLUMNS.index("return_1")]
    labels = (signal + rng.normal(scale=2, size=count) > 0).astype(np.int8)
    frame = {
        "x": x,
        "y": labels,
        "day": np.array([np.datetime64(item.date()) for item in ends]),
        "symbol": np.array(["RELIANCE"] * count),
        "end": np.array(ends),
        "future_end": np.array([item + timedelta(days=1) for item in ends]),
        "next_return": rng.normal(scale=0.001, size=count),
        "minute": np.array([9 * 60 + 20 + (index % 70) * 5 for index in range(count)], dtype=np.int16),
        "weekday": np.array([item.weekday() for item in ends], dtype=np.int8),
        "month": np.array([item.month for item in ends], dtype=np.int8),
    }
    daily = fixed_split_review(frame, "1d")
    assert daily["primary_calibration"] == "platt"
    assert daily["day_bootstrap"]["samples"] == 1000
    for name in ("uncalibrated", "platt", "isotonic"):
        for side in ("validation", "test"):
            block = daily["methods"][name][side]
            assert set(block) >= {"log_loss", "auc", "brier", "reliability"}
            assert sum(row["rows"] for row in block["reliability"]) == block["rows"]
    assert daily["ablation"]["selected"] in {"base", "day_of_week", "month", "day_of_week_and_month"}
    assert "test_evaluated_once" in daily["ablation"]

    intraday = fixed_split_review(frame, "5m")
    assert len(intraday["coefficients_standardized"]) == len(DIRECTION_COLUMNS)
    assert len(intraday["log_loss_gap_by_symbol"]) == 1
    assert intraday["economics"]["cost_assumption_bps_round_trip"] == 5.0
    assert intraday["return_1_versus_all"]["test"]["share_of_gain"] is not None
    folded = walk_forward(frame, "5m")
    assert folded["folds"]
    assert any(not row["skipped"] for row in folded["folds"])


def test_audit_deciles_final_bars_and_target_freeze() -> None:
    import numpy as np

    from quant_agents.direction.audit import (
        COST_LADDER_BPS,
        decile_edges,
        final_two_usable,
        freeze_target,
    )

    symbol = np.array(["A", "A", "A", "A", "B"])
    day = np.array(["2026-07-01"] * 4 + ["2026-07-02"], dtype="datetime64[D]")
    minute = np.array([20, 25, 30, 35, 20])
    last = final_two_usable(symbol, day, minute)
    assert last.tolist() == [False, False, True, True, True]

    probability = np.linspace(0.2, 0.8, 100)
    returns = np.where(probability >= 0.5, 0.002, -0.002)
    table = decile_edges(probability, returns)
    assert len(table) == 10
    assert table[0]["gross_edge_bps"] > 0
    assert table[-1]["gross_edge_bps"] > COST_LADDER_BPS[-1]
    assert 5.0 in table[-1]["clears_cost_bps"]

    gaps = {"horizon_6": -0.001, "horizon_12": -0.002, "return_above_5bps": -0.002, "volatility_scaled": 0.01}
    assert freeze_target(gaps) == "horizon_12"


def test_every_bar_edge_keeps_small_moves_and_stops_at_2_bps() -> None:
    import numpy as np

    from quant_agents.direction.audit import every_bar_edge, no_tradable_edge, three_class_edge

    edge = every_bar_edge(np.array([0.9, 0.9, 0.1]), np.array([0.01, 0.0001, -0.01]))
    assert edge["trades"] == 3
    assert edge["gross_edge_bps"] == pytest.approx((100 + 1 + 100) / 3)
    assert edge["net_edge_bps"]["2.0"] == pytest.approx(edge["gross_edge_bps"] - 2)

    three = three_class_edge(np.array([0.2, 0.6]), np.array([0.7, 0.3]), np.array([-0.001, 0.0001]))
    assert three["trades"] == 2
    assert three["gross_edge_bps"] == pytest.approx(5.5)
    assert no_tradable_edge([{"net_edge_bps": {"2.0": -0.1}}, {"net_edge_bps": {"2.0": 0.0}}])
    assert not no_tradable_edge([{"net_edge_bps": {"2.0": 0.01}}])


def test_hypotheses_stay_off_the_frozen_test_and_context_names_must_match() -> None:
    import numpy as np

    from core_market_data.context_pull import (
        UnconfirmedSymbols,
        assert_holdout_starts_after_frozen_file,
        assert_new_snapshot_id,
        confirm_index_symbols,
    )
    from quant_agents.direction.hypotheses import LOOKBACK, assert_no_frozen_test, score_hypotheses

    with pytest.raises(SystemExit):
        assert_no_frozen_test(np.array(["2026-01-02"], dtype="datetime64[D]"))
    with pytest.raises(SystemExit):
        assert_new_snapshot_id("nifty50_5m_20261005")
    with pytest.raises(SystemExit):
        assert_holdout_starts_after_frozen_file(datetime(2026, 10, 5, tzinfo=timezone.utc))
    rows = [
        {"tradingsymbol": "NIFTY 50", "instrument_token": 1, "segment": "INDICES"},
        {"tradingsymbol": "NIFTY 50", "instrument_token": 2, "segment": "NSE"},
    ]
    assert confirm_index_symbols(rows, ("NIFTY 50",)) == {"NIFTY 50": 1}
    with pytest.raises(UnconfirmedSymbols):
        confirm_index_symbols(rows, ("INDIA VIX",))

    tapes = {}
    for symbol_index in range(12):
        bars = []
        for session in range(40):
            day = datetime(2025, 6, 2, tzinfo=timezone.utc) + timedelta(days=session)
            price = Decimal("100") + Decimal(symbol_index)
            close = price + (Decimal("1") if session % 2 == 0 else Decimal("-1"))
            bars.append(
                StoredBar(
                    symbol=f"S{symbol_index}",
                    timeframe="1d",
                    open=price,
                    high=price + Decimal("2"),
                    low=price - Decimal("2"),
                    close=close,
                    volume=100,
                    start=day,
                    end=day + timedelta(hours=6),
                )
            )
        tapes[f"S{symbol_index}"] = SymbolTape(bars=bars)
    report = score_hypotheses(tapes, "1d", context_present=False)
    assert report["test_rows_used"] is False
    assert report["lookback_bars"] == LOOKBACK["1d"]
    assert report["hypotheses"]["regime_vix_or_nifty"]["skipped"] is True
    assert "positive_net_at_2_bps" in report["hypotheses"]["momentum_continuation"]
    from quant_agents.direction.hypotheses import score_context_rules

    context_report = score_context_rules(tapes, {}, "1d")
    assert context_report["stock_only_rules_refit"] is False
    assert context_report["hypotheses"]["regime_vix"]["discarded"] is True
    assert context_report["hypotheses"]["sector_relative"]["skipped"] is True


def test_rank_refuses_2026_and_leaves_the_middle_flat() -> None:
    import numpy as np

    from quant_agents.direction.hypotheses import RANK_WIDTH, assert_no_frozen_test, book_positions, score_rank

    with pytest.raises(SystemExit):
        assert_no_frozen_test(np.array(["2026-01-02"], dtype="datetime64[D]"))
    symbols = [f"S{index:02d}" for index in range(12)]
    probability = np.array([float(index) for index in range(12)])
    position = book_positions(symbols, probability, RANK_WIDTH)
    long_names = {symbols[index] for index, side in enumerate(position) if side > 0}
    short_names = {symbols[index] for index, side in enumerate(position) if side < 0}
    flat_names = {symbols[index] for index, side in enumerate(position) if side == 0}
    assert long_names == {"S07", "S08", "S09", "S10", "S11"}
    assert short_names == {"S00", "S01", "S02", "S03", "S04"}
    assert flat_names == {"S05", "S06"}

    stocks = {}
    nifty_bars = []
    for session, day in ((0, datetime(2025, 6, 30, 3, 45, tzinfo=timezone.utc)), (1, datetime(2025, 7, 1, 3, 45, tzinfo=timezone.utc))):
        del session
        for slot in range(40):
            start = day + timedelta(minutes=5 * slot)
            nifty_bars.append(
                StoredBar("NIFTY 50", "5m", Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), 1, start, start + timedelta(minutes=5))
            )
    nifty_bars.append(
        StoredBar(
            "NIFTY 50",
            "5m",
            Decimal("100"),
            Decimal("101"),
            Decimal("99"),
            Decimal("100"),
            1,
            datetime(2026, 1, 2, 3, 45, tzinfo=timezone.utc),
            datetime(2026, 1, 2, 3, 50, tzinfo=timezone.utc),
        )
    )
    for symbol_index, symbol in enumerate(symbols):
        bars = []
        for day in (datetime(2025, 6, 30, 3, 45, tzinfo=timezone.utc), datetime(2025, 7, 1, 3, 45, tzinfo=timezone.utc)):
            for slot in range(40):
                start = day + timedelta(minutes=5 * slot)
                close = Decimal("100") + Decimal(symbol_index) + Decimal(slot) * Decimal("0.1") * Decimal(symbol_index - 5)
                bars.append(
                    StoredBar(symbol, "5m", close, close + Decimal("1"), close - Decimal("1"), close, 100 + slot, start, start + timedelta(minutes=5))
                )
        bars.append(
            StoredBar(
                symbol,
                "5m",
                Decimal("100"),
                Decimal("101"),
                Decimal("99"),
                Decimal("110"),
                100,
                datetime(2026, 1, 2, 3, 45, tzinfo=timezone.utc),
                datetime(2026, 1, 2, 3, 50, tzinfo=timezone.utc),
            )
        )
        stocks[symbol] = SymbolTape(bars=bars)
    report = score_rank(stocks, {"NIFTY 50": SymbolTape(bars=nifty_bars)})
    assert report["test_rows_used"] is False
    assert report["holdout_used"] is False
    assert report["skipped"] is False
    assert report["long_fraction"] == pytest.approx(0.5)


def test_sixty_minute_hold_charges_once_and_skips_2026() -> None:
    from quant_agents.direction.hypotheses import score_hold

    symbols = [f"S{index:02d}" for index in range(12)]
    days = [
        datetime(2025, 6, 26, 3, 45, tzinfo=timezone.utc),
        datetime(2025, 6, 27, 3, 45, tzinfo=timezone.utc),
        datetime(2025, 6, 30, 3, 45, tzinfo=timezone.utc),
        datetime(2025, 7, 1, 3, 45, tzinfo=timezone.utc),
        datetime(2025, 7, 2, 3, 45, tzinfo=timezone.utc),
        datetime(2025, 7, 3, 3, 45, tzinfo=timezone.utc),
        datetime(2026, 1, 2, 3, 45, tzinfo=timezone.utc),
    ]
    nifty_bars = []
    stocks = {symbol: [] for symbol in symbols}
    for day in days:
        for slot in range(75):
            start = day + timedelta(minutes=5 * slot)
            end = start + timedelta(minutes=5)
            nifty_bars.append(StoredBar("NIFTY 50", "5m", Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), 1, start, end))
            for symbol_index, symbol in enumerate(symbols):
                close = Decimal("100") + Decimal(symbol_index) + Decimal(slot) * Decimal(symbol_index - 5) / Decimal("100")
                stocks[symbol].append(
                    StoredBar(symbol, "5m", close, close + Decimal("1"), close - Decimal("1"), close, 100 + slot, start, end)
                )
    report = score_hold(
        {symbol: SymbolTape(bars=bars) for symbol, bars in stocks.items()},
        {"NIFTY 50": SymbolTape(bars=nifty_bars)},
    )
    assert report["skipped"] is False
    assert report["test_rows_used"] is False
    assert report["holdout_used"] is False
    assert report["hold_minutes"] == 60
    assert report["cost_charges_per_trade"] == 1
    assert report["long_fraction"] == pytest.approx(0.5)
    assert report["trades"] == 120
    assert report["net_edge_bps"]["2.0"] == pytest.approx(report["gross_edge_bps"] - 2)
    assert report["net_edge_bps"]["2.0"] != pytest.approx(report["gross_edge_bps"] - 24)


def test_calendar_audit_keeps_exchange_wide_holes_and_backfill_does_not_invent_bars(tmp_path: Path) -> None:
    from core_market_data.hole_backfill import assert_clean_snapshot_id, backfill_snapshot, fetch_jobs
    from quant_agents.direction.completeness import audit_candles

    with pytest.raises(SystemExit):
        assert_clean_snapshot_id("nifty50_5m_20261005")
    lines = []
    for symbol in ("AAA", "BBB"):
        start = datetime(2026, 8, 3, 3, 45, tzinfo=timezone.utc)
        for _ in range(72):
            end = start + timedelta(minutes=5)
            row = {
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 2,
                "end": end.isoformat(),
                "exchange": "NSE",
                "start": start.isoformat(),
                "symbol": symbol,
                "timeframe": "5m",
                "volume": 1,
            }
            lines.append(json.dumps(row))
            start = end
    path = tmp_path / "candles.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = {"5m": audit_candles(path, "5m")}
    wide = report["5m"]["missing_clocks_all_symbols"]
    assert any(item["class"] == "late_session_tail" for item in wide)
    jobs = fetch_jobs(report, "5m")
    assert {job["symbol"] for job in jobs} == {"AAA", "BBB"}

    class EmptyKite:
        access_token = "token"

        def instruments(self, exchange: str):
            del exchange
            return [
                {"tradingsymbol": "AAA", "instrument_token": 1, "segment": "NSE"},
                {"tradingsymbol": "BBB", "instrument_token": 2, "segment": "NSE"},
            ]

        def historical_data(self, instrument_token, from_date, to_date, interval):
            del instrument_token, from_date, to_date, interval
            return []

    from core_market_data.zerodha import RequestPace

    written = backfill_snapshot(
        path,
        tmp_path / "clean",
        snapshot_id="nifty50_clean_20261007",
        timeframe="5m",
        report=report,
        client=EmptyKite(),
        pace=RequestPace(0),
    )
    assert written["appended_bars"] == 0
    assert written["unresolved"]
    assert all(item["status"] == "exchange_returned_no_bar" for item in written["unresolved"])
    assert (tmp_path / "clean" / "candles.jsonl").read_text(encoding="utf-8") == path.read_text(encoding="utf-8")
