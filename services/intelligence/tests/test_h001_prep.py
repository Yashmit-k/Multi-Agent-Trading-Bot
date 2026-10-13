from hashlib import sha256
from pathlib import Path

from intelligence_agents.h001v2.integrity import freeze_integrity, sha256sums_text
from intelligence_agents.h001v2.missingness import classify_missing_cells, quarter_counts
from intelligence_agents.h001v2.normalize import parse_exchdisstime
from intelligence_agents.h001v2.prepare import exclude_reason, prepare_scope_a
from intelligence_agents.h001v2.readiness import decide
from intelligence_agents.h001v2.timestamps import audit_timestamps


def test_integrity_v2_records_size_and_class(tmp_path: Path):
    (tmp_path / "corporate-announcements").mkdir()
    raw = tmp_path / "corporate-announcements" / "RELIANCE.raw"
    raw.write_bytes(b"abc")
    listing = sha256sums_text(tmp_path)
    again = sha256sums_text(tmp_path)
    assert listing == again
    measured = freeze_integrity(tmp_path, repo=tmp_path)
    assert measured["n_files"] == 1
    assert measured["files"][0]["size_bytes"] == 3
    assert measured["files"][0]["artifact_class"] == "announcement_raw"
    assert measured["files"][0]["sha256"] == sha256(b"abc").hexdigest()
    assert measured["files_manifest_sha256"]
    assert measured["sidecars"]["parquet"]["status"] == "ABSENT"
    assert measured["READY_TO_RUN"] == "NO"


def test_timestamp_audit_no_exchdatetime_and_invalid():
    rows = [
        {
            "symbol": "TCS",
            "seq_id": "1",
            "exchdisstime": "15-Jan-2024 13:41:18",
            "an_dt": "15-Jan-2024 13:41:12",
            "sort_date": "2024-01-15 13:41:12",
        },
        {
            "symbol": "TCS",
            "seq_id": "2",
            "exchdisstime": "not-a-date",
            "an_dt": "",
        },
    ]
    report = audit_timestamps(rows)
    assert report["exchdatetime_found"] is False
    assert report["parse_ok"]["exchdisstime"] == 1
    assert report["parse_fail"]["exchdisstime"] == 1
    ts = parse_exchdisstime("15-Jan-2024 13:41:18")
    assert ts is not None
    assert ts.tzinfo is not None


def test_prepare_excludes_invalid_and_is_stable():
    universe = ["RELIANCE"]
    rows = [
        {
            "symbol": "RELIANCE",
            "seq_id": "10",
            "desc": "Financial Result Updates",
            "exchdisstime": "15-Jan-2024 10:00:00",
            "hasXbrl": False,
        },
        {
            "symbol": "RELIANCE",
            "seq_id": "10",
            "desc": "Financial Result Updates",
            "exchdisstime": "15-Jan-2024 10:00:00",
            "hasXbrl": False,
        },
        {"symbol": "ZZZ", "seq_id": "1", "desc": "x", "exchdisstime": "15-Jan-2024 10:00:00"},
        {"symbol": "RELIANCE", "seq_id": "11", "desc": "x"},
    ]
    first = prepare_scope_a(rows, universe)
    second = prepare_scope_a(rows, universe)
    assert first["output_sha256"] == second["output_sha256"]
    assert first["n_kept"] == 1
    assert first["exclusions"]["unmapped_symbol"] == 1
    assert first["exclusions"]["missing_required_fields:exchdisstime"] == 1
    assert first["duplicate_identical"] == 1
    rec = first["records"][0]
    assert rec["available_at_basis"] == "exchdisstime_ist_convention"
    assert rec["fixture"] is False
    assert rec["v1_class"] is True
    assert rec["section15"] is True
    assert exclude_reason({"desc": "x"}, {"RELIANCE"}) == "missing_required_fields:symbol,seq_id,exchdisstime"


def test_coverage_missing_cells_not_imputed():
    universe = {"AAA", "BBB"}
    rows = [
        {
            "symbol": "AAA",
            "desc": "Financial Result Updates",
            "exchdisstime": "15-Jan-2024 10:00:00",
            "hasXbrl": False,
        }
    ]
    counts = quarter_counts(rows, universe)
    assert counts["section15_rows_by_quarter"]["2024Q1"] == 1
    assert "2025Q2" not in counts["section15_rows_by_quarter"]
    classified = classify_missing_cells(
        [{"symbol": "BBB", "quarter": "2025Q2"}],
        {"files_absent": ["BBB"]},
        counts,
    )
    assert classified["imputed"] is False
    assert classified["missing_cells"][0]["origin"] == "source_slice_file_absent"


def test_leakage_sensitive_available_at_not_after_as_of():
    rows = [
        {
            "symbol": "RELIANCE",
            "seq_id": "1",
            "desc": "Financial Result Updates",
            "exchdisstime": "03-Jun-2024 15:30:00",
            "hasXbrl": False,
        }
    ]
    prepared = prepare_scope_a(rows, ["RELIANCE"])
    as_of = parse_exchdisstime("03-Jun-2024 10:00:00")
    later = parse_exchdisstime(prepared["records"][0]["exchdisstime_raw"])
    assert as_of is not None and later is not None
    assert later > as_of
    visible = [row for row in prepared["records"] if parse_exchdisstime(row["exchdisstime_raw"]) <= as_of]
    assert visible == []


def test_readiness_gate_fails_closed_on_scope_b():
    gate = decide(
        {
            "integrity": {
                "status": "MEASURED",
                "integrity_baseline_sha256": "abc",
                "equivalent_to_b0f4760f": False,
                "historical_digest_status": "UNVERIFIED",
                "sidecars": {"parquet": {"status": "ABSENT"}},
            },
            "timestamps": {
                "exchdatetime_found": False,
                "limitation": "proxy",
            },
            "section16": {"covered_cells": 345, "missing_cell_count": 47},
            "scope": {"required": "B", "available": "A"},
            "protocol": {"status": "DRAFT_UNAPPROVED"},
            "labels_generated": False,
            "holdout_accessed": False,
        }
    )
    assert gate["DATA_PREP_READY"] == "NO"
    assert gate["READY_TO_RUN"] == "NO"
    assert gate["BLOCKED_PRECONDITION"] is True
    names = {item["name"] for item in gate["blockers"]}
    assert "scope" in names
    assert "protocol" in names
    assert "coverage_49x8" in names
