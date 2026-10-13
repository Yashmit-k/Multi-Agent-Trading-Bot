"""§16 missing-cell diagnostics. Does not impute events."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from intelligence_agents.h001v2.normalize import (
    QUARTERS,
    ist_calendar_quarter,
    parse_exchdisstime,
    results_like_section15,
)

Q2_SLICE_SUFFIX = "_01-04-2025_30-06-2025.raw"


def slice_inventory(ann_dir: Path, symbols: list[str]) -> dict:
    """Distinguish missing qualifying events from missing source files."""
    present = 0
    absent: list[str] = []
    empty: list[str] = []
    for symbol in symbols:
        path = ann_dir / f"{symbol}{Q2_SLICE_SUFFIX}"
        if not path.is_file():
            absent.append(symbol)
            continue
        present += 1
        if path.stat().st_size == 0:
            empty.append(symbol)
    return {
        "slice": "corporate-announcements/*_01-04-2025_30-06-2025.raw",
        "symbols": len(symbols),
        "files_present": present,
        "files_absent": absent,
        "files_empty": empty,
        "origin_if_absent_files": "failed_or_unretrieved_source_query",
        "origin_if_present_without_section15": "genuine_missing_qualifying_event_under_section15",
    }


def quarter_counts(rows: list[dict], universe: set[str]) -> dict:
    all_rows = Counter()
    s15_rows = Counter()
    parse_fail = Counter()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol not in universe:
            continue
        ts = parse_exchdisstime(row.get("exchdisstime"))
        if ts is None:
            parse_fail["unparseable_exchdisstime"] += 1
            continue
        quarter = ist_calendar_quarter(ts) or "outside_2024_2025"
        all_rows[quarter] += 1
        keep, _ = results_like_section15(row)
        if keep:
            s15_rows[quarter] += 1
    return {
        "all_in_universe_rows_by_quarter": dict(all_rows),
        "section15_rows_by_quarter": dict(s15_rows),
        "unparseable": dict(parse_fail),
        "quarters": list(QUARTERS),
    }


def classify_missing_cells(
    missing_cells: list[dict],
    slice_info: dict,
    quarter_info: dict,
) -> dict:
    """Map each missing cell to origin. No imputation."""
    absent = set(slice_info.get("files_absent") or [])
    classified = []
    for cell in missing_cells:
        symbol = cell["symbol"]
        quarter = cell["quarter"]
        if quarter == "2025Q2" and symbol in absent:
            origin = "source_slice_file_absent"
        elif quarter == "2025Q2":
            origin = "source_slice_present_or_rows_elsewhere_but_no_section15_in_quarter"
        else:
            origin = "no_section15_row_in_quarter"
        classified.append({**cell, "origin": origin})
    origins = Counter(item["origin"] for item in classified)
    return {
        "missing_cells": classified,
        "origin_counts": dict(origins),
        "section15_rows_2025Q2": (quarter_info.get("section15_rows_by_quarter") or {}).get("2025Q2", 0),
        "all_rows_2025Q2": (quarter_info.get("all_in_universe_rows_by_quarter") or {}).get("2025Q2", 0),
        "imputed": False,
    }
