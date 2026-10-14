from datetime import datetime
from pathlib import Path

from quant_agents.research.h001.events import (
    ExclusionReason,
    classify_rows,
    normalize_desc,
    parse_exchdisstime,
)

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "quant_agents" / "research" / "h001"


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "seq_id": "1",
        "symbol": "RELIANCE",
        "desc": "Financial Result Updates",
        "exchdisstime": "11-Jan-2024 15:53:23",
        "available_at": "2024-01-11T15:53:23+05:30",
        "attchmntText": "results",
        "hasXbrl": False,
    }
    row.update(overrides)
    return row


def test_normalization_and_exact_subjects() -> None:
    assert normalize_desc(None) == ""
    assert normalize_desc("  Financial-Result / Updates ") == "financial result updates"
    result = classify_rows(
        [
            _row(seq_id="a", desc="Consolidated Result Updates - IFRS"),
            _row(seq_id="b", desc="Publish Audited Results"),
            _row(seq_id="c", desc="Integrated Filing- Financial"),
            _row(seq_id="d", desc="Outcome of Board Meeting"),
        ]
    )
    assert [event.seq_id for event in result.events] == ["a", "b"]
    assert result.exclusions[-1].reason == ExclusionReason.DESC_NOT_IN_CLASS


def test_hasxbrl_does_not_include_and_contradiction_excludes() -> None:
    included = classify_rows([_row(hasXbrl=True)])
    assert len(included.events) == 1
    blocked = classify_rows([_row(attchmntText="Proposed Trading Window closure")])
    assert blocked.exclusions[0].reason == ExclusionReason.CONTRADICTION
    empty = classify_rows([_row(attchmntText="")])
    assert len(empty.events) == 1


def test_clock_match_mismatch_and_window() -> None:
    parsed = parse_exchdisstime("11-Jan-2024 15:53:23")
    assert parsed.isoformat() == "2024-01-11T15:53:23+05:30"
    matched = classify_rows([_row()])
    assert matched.events[0].exchdisstime_raw == "11-Jan-2024 15:53:23"
    assert matched.events[0].available_at == parsed
    mismatch = classify_rows([_row(available_at="2024-01-11T15:53:24+05:30")])
    assert mismatch.exclusions[0].reason == ExclusionReason.CLOCK_MISMATCH
    naive = classify_rows([_row(available_at=datetime(2024, 1, 11, 15, 53, 23))])
    assert naive.exclusions[0].reason == ExclusionReason.UNPARSED_CLOCK
    early = classify_rows([_row(exchdisstime="31-Dec-2023 23:00:00", available_at="2023-12-31T23:00:00+05:30")])
    assert early.exclusions[0].reason == ExclusionReason.BEFORE_WINDOW
    late = classify_rows([_row(exchdisstime="01-Jan-2026 00:00:00", available_at="2026-01-01T00:00:00+05:30")])
    assert late.exclusions[0].reason == ExclusionReason.AFTER_WINDOW


def test_symbol_exclusion_and_distinct_seq_ids() -> None:
    result = classify_rows(
        [
            _row(seq_id="1", symbol="TATAMOTORS"),
            _row(seq_id="2"),
            _row(seq_id="3"),
        ]
    )
    assert [event.seq_id for event in result.events] == ["2", "3"]
    assert result.exclusions[0].reason == ExclusionReason.SYMBOL_EXCLUDED


def test_package_does_not_open_data_files() -> None:
    for path in PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "open(" not in text
        assert "candles.jsonl" not in text
        assert "read_parquet" not in text
        if path.name == "authorization.py":
            continue
        assert "holdout_after_20261005" not in text
        assert "parquet" not in text
