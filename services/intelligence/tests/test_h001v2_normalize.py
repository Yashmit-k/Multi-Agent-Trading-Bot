from hashlib import sha256
from pathlib import Path

from intelligence_agents.h001v2.integrity import digest_of_listing, freeze_integrity, sha256sums_text
from intelligence_agents.h001v2.normalize import (
    ist_calendar_quarter,
    normalize_desc,
    parse_exchdisstime,
    partition,
    results_like_section15,
    v1_class,
    v2_class,
)


def test_v1_exact_normalized_desc():
    assert v1_class("Financial Result Updates")
    assert v1_class("  CONSOLIDATED RESULT UPDATES - IFRS ") is False  # punctuation kept
    assert v1_class("consolidated result updates ifrs")
    assert v1_class("Publish Audited Results")
    assert not v1_class("Outcome of Board Meeting")
    assert not v1_class("Integrated Filing- Financial")


def test_v2_does_not_take_all_board_meetings():
    board = {
        "desc": "Outcome of Board Meeting",
        "attchmntText": "Appointment of director",
    }
    ok, kind = v2_class(board)
    assert ok is False
    assert kind == "board_outcome_unrelated_or_unproven"
    results = {
        "desc": "Outcome of Board Meeting",
        "attchmntText": "submitted the financial results for the quarter",
    }
    ok, kind = v2_class(results)
    assert ok is True
    assert kind == "source_backed_board_outcome_financial_results"


def test_v2_integrated_filing_from_circular_label():
    ok, kind = v2_class({"desc": "Integrated Filing- Financial"})
    assert ok is True
    assert "nse_cml_2025_20" in kind


def test_timestamps_and_partitions():
    ts = parse_exchdisstime("15-Jan-2024 13:41:18")
    assert ts is not None
    assert ts.tzinfo is not None
    assert partition(ts) == "train"
    val = parse_exchdisstime("02-Jan-2025 10:00:00")
    assert partition(val) == "validate"
    late = parse_exchdisstime("01-Jun-2025 10:00:00")
    assert partition(late) == "post_validation"


def test_normalize_desc_collapse_space():
    assert normalize_desc("  Financial   Result Updates ") == "financial result updates"


def test_section15_hasxbrl_only():
    keep, evidence = results_like_section15(
        {"desc": "Appointment of Director", "hasXbrl": True}
    )
    assert keep is True
    assert evidence == "hasXbrl_only"


def test_section15_regex_only():
    keep, evidence = results_like_section15(
        {"desc": "Financial Result Updates", "hasXbrl": False}
    )
    assert keep is True
    assert evidence == "regex_only"


def test_section15_both_and_neither():
    keep, evidence = results_like_section15(
        {"desc": "Financial Result Updates", "hasXbrl": True}
    )
    assert keep is True
    assert evidence == "both"
    keep, evidence = results_like_section15(
        {"desc": "Appointment of Director", "hasXbrl": False}
    )
    assert keep is False
    assert evidence == "neither"


def test_ist_calendar_quarter_edges():
    q1 = parse_exchdisstime("01-Jan-2024 00:00:00")
    q2 = parse_exchdisstime("01-Apr-2024 00:00:00")
    q4 = parse_exchdisstime("31-Dec-2025 23:59:59")
    before = parse_exchdisstime("31-Dec-2023 23:59:59")
    assert ist_calendar_quarter(q1) == "2024Q1"
    assert ist_calendar_quarter(q2) == "2024Q2"
    assert ist_calendar_quarter(q4) == "2025Q4"
    assert ist_calendar_quarter(before) is None


def test_hasher_two_temp_files(tmp_path: Path):
    (tmp_path / "a.json").write_bytes(b"A")
    (tmp_path / "z.raw").write_bytes(b"B")
    ha = sha256(b"A").hexdigest()
    hz = sha256(b"B").hexdigest()
    listing = f"{ha}  a.json\n{hz}  z.raw\n"
    expected = sha256(listing.encode("utf-8")).hexdigest()
    assert sha256sums_text(tmp_path) == listing
    assert digest_of_listing(listing) == expected
    measured = freeze_integrity(tmp_path)
    assert measured["status"] == "MEASURED"
    assert measured["n_files"] == 2
    assert measured["integrity_baseline_sha256"] == expected
    assert measured["historical_digest_status"] == "UNVERIFIED"
    assert measured["equivalent_to_b0f4760f"] is False
    assert measured["READY_TO_RUN"] == "NO"


def test_hasher_freeze_absent_does_not_pass(tmp_path: Path):
    missing = tmp_path / "no-such-freeze"
    measured = freeze_integrity(missing)
    assert measured["status"] == "FREEZE_ABSENT"
    assert measured["integrity_baseline_sha256"] is None
    assert measured["n_files"] == 0
    assert measured["sha256sums"] == ""
    assert measured["READY_TO_RUN"] == "NO"
    assert measured["historical_digest_status"] == "UNVERIFIED"


def test_scan_freeze_absent_is_not_ready(monkeypatch, tmp_path: Path):
    from intelligence_agents.h001v2 import scan as h001_scan

    monkeypatch.setattr(h001_scan, "FREEZE", tmp_path / "missing-freeze")
    report = h001_scan.summarize()
    assert report["freeze_absent"] is True
    assert report["status"]["READY_TO_RUN"] == "NO"
    assert report["integrity"]["status"] == "FREEZE_ABSENT"
    assert report["integrity"].get("integrity_baseline_sha256") is None
    assert "unique_v1_events" not in report
    assert report.get("DATA_PREP_READY") == "NO"
