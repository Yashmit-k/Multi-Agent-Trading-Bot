"""Scan the existing NSE freeze. Does not mutate frozen files or the holdout."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from intelligence_agents.h001v2.integrity import freeze_integrity
from intelligence_agents.h001v2.missingness import classify_missing_cells, quarter_counts, slice_inventory
from intelligence_agents.h001v2.normalize import (
    QUARTERS,
    ist_calendar_quarter,
    parse_exchdisstime,
    partition,
    results_like_section15,
    section15_false_positive_bucket,
    v1_class,
    v2_class,
)
from intelligence_agents.h001v2.prepare import prepare_scope_a
from intelligence_agents.h001v2.readiness import decide
from intelligence_agents.h001v2.timestamps import audit_timestamps

REPO = Path(__file__).resolve().parents[5]
FREEZE = REPO / "datasets" / "h001-nse-raw-20261010T140237Z"
ANN = FREEZE / "corporate-announcements"
SNAP = REPO / "snapshots 2" / "nifty50" / "1D" / "manifest.json"
DOCS = REPO / "services" / "intelligence" / "docs"
STATUS = {
    "DATA_NOT_READY": True,
    "BLOCKED_PRECONDITION": True,
    "READY_TO_RUN": "NO",
    "PROTOCOL_APPROVED_EXECUTION_NOT_AUTHORIZED": True,
    "model_fit": False,
    "labels_generated": False,
    "holdout_accessed": False,
    "announcement_count_ge_50_is_not_fit_authorization": True,
}


def universe_symbols() -> list[str]:
    body = json.loads(SNAP.read_text(encoding="utf-8"))
    return [row["symbol"] for row in body["symbols"] if row.get("count", 0) > 0]


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(ANN.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, dict))
    return rows


def event_key(row: dict) -> str:
    return f"{row.get('symbol')}|{row.get('seq_id')}"


def _gate(counter: Counter) -> dict:
    train = counter.get("train", 0)
    val = counter.get("validate", 0)
    return {
        "train": train,
        "validate": val,
        "post_validation_reported_separately": counter.get("post_validation", 0),
        "min_class_50_train": train >= 50,
        "min_class_50_validate": val >= 50,
        "ready_under_current_threshold": train >= 50 and val >= 50,
    }


def summarize() -> dict:
    integrity = freeze_integrity(FREEZE, repo=REPO)
    if integrity.get("status") == "FREEZE_ABSENT":
        gate = decide(
            {
                "integrity": integrity,
                "timestamps": {},
                "section16": {},
                "scope": {"required": "B", "available": "A"},
                "protocol": {"status": "DRAFT_UNAPPROVED"},
                "labels_generated": False,
                "holdout_accessed": False,
            }
        )
        return {
            "status": STATUS,
            "integrity": {k: v for k, v in integrity.items() if k not in {"sha256sums", "files"}},
            "freeze_absent": True,
            "DATA_PREP_READY": gate["DATA_PREP_READY"],
            "readiness": gate,
        }

    symbols = universe_symbols()
    universe = set(symbols)
    rows = load_rows()
    v1_keys: dict[str, dict] = {}
    v2_keys: dict[str, dict] = {}
    v1_part = Counter()
    v2_part = Counter()
    v1_desc = Counter()
    v2_kind = Counter()
    missing_clock = 0
    excluded_v2 = Counter()
    post_val_v2 = 0
    by_symbol_v1 = Counter()
    by_symbol_v2 = Counter()

    s15_evidence = Counter()
    s15_desc = Counter()
    s15_fp = Counter()
    s15_kept = 0
    s15_not = 0
    s15_missing_clock = 0
    cells: dict[str, set[str]] = {symbol: set() for symbol in symbols}
    by_symbol_s15 = Counter()
    in_universe_rows: list[dict] = []

    in_universe = 0
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol not in universe:
            continue
        in_universe += 1
        in_universe_rows.append(row)
        ts = parse_exchdisstime(row.get("exchdisstime"))
        keep, evidence = results_like_section15(row)
        if keep:
            s15_kept += 1
            s15_evidence[evidence] += 1
            s15_desc[str(row.get("desc") or "")] += 1
            s15_fp[section15_false_positive_bucket(row.get("desc"))] += 1
            by_symbol_s15[symbol] += 1
            if ts is None:
                s15_missing_clock += 1
            else:
                quarter = ist_calendar_quarter(ts)
                if quarter in QUARTERS:
                    cells[symbol].add(quarter)
        else:
            s15_not += 1

        if ts is None:
            missing_clock += 1
            continue
        part = partition(ts)
        key = event_key(row)
        if v1_class(row.get("desc")):
            if key not in v1_keys:
                v1_keys[key] = row
                v1_part[part] += 1
                v1_desc[str(row.get("desc"))] += 1
                by_symbol_v1[symbol] += 1
        in_v2, kind = v2_class(row)
        if in_v2:
            if key not in v2_keys:
                v2_keys[key] = row
                v2_part[part] += 1
                v2_kind[kind] += 1
                by_symbol_v2[symbol] += 1
                if part == "post_validation":
                    post_val_v2 += 1
        else:
            excluded_v2[kind] += 1

    missing_cells = [
        {"symbol": symbol, "quarter": quarter}
        for symbol in symbols
        for quarter in QUARTERS
        if quarter not in cells[symbol]
    ]
    covered_cells = 49 * 8 - len(missing_cells)
    grid = {
        symbol: {quarter: (quarter in cells[symbol]) for quarter in QUARTERS} for symbol in symbols
    }
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    integrity_pub = {k: v for k, v in integrity.items() if k not in {"sha256sums", "files"}}
    timestamps = audit_timestamps(in_universe_rows)
    qcounts = quarter_counts(in_universe_rows, universe)
    slices = slice_inventory(ANN, symbols)
    missingness = classify_missing_cells(missing_cells, slices, qcounts)
    prepared = prepare_scope_a(in_universe_rows, symbols)
    prepared_pub = {k: v for k, v in prepared.items() if k != "records"}
    scope = {
        "required": "B",
        "available": "A",
        "rationale": (
            "H001 source audit requires event/value fields (EPS and restatement history). "
            "Intelligence EarningsAgent scores EPS growth from FundamentalDataPoint. "
            "The NSE freeze is an announcement tape without vintage fundamentals. "
            "Scope A is implemented; Scope B remains the blocking dependency."
        ),
        "researcher_approval_required": True,
    }
    protocol = {
        "status": "DRAFT_UNAPPROVED",
        "v1_event_include_list_immutable": True,
        "target": "UNFROZEN",
        "features": "UNFROZEN",
        "horizon": "UNFROZEN",
        "decision_time": "UNFROZEN",
        "entry_price": "UNFROZEN",
        "note": "Do not adopt quant label_v1 next_close_direction as H001 without approval.",
    }
    gate = decide(
        {
            "integrity": integrity,
            "timestamps": timestamps,
            "section16": {
                "covered_cells": covered_cells,
                "missing_cell_count": len(missing_cells),
            },
            "scope": scope,
            "protocol": protocol,
            "labels_generated": False,
            "holdout_accessed": False,
        }
    )
    return {
        "status": STATUS,
        "integrity": integrity_pub,
        "freeze_absent": False,
        "raw_announcement_rows_in_universe": in_universe,
        "universe_symbols": len(symbols),
        "universe": symbols,
        "snapshot_id": snap.get("snapshot_id"),
        "candle_sha256": snap.get("candle_sha256"),
        "unique_v1_events": len(v1_keys),
        "unique_v2_events": len(v2_keys),
        "v1_by_partition": dict(v1_part),
        "v2_by_partition": dict(v2_part),
        "v1_by_desc": dict(v1_desc),
        "v2_by_evidence_kind": dict(v2_kind),
        "v1_gate": _gate(v1_part),
        "v2_gate": _gate(v2_part),
        "missing_exchdisstime": missing_clock,
        "excluded_v2_kinds": dict(excluded_v2),
        "v1_symbols_with_zero": sorted(set(symbols) - set(by_symbol_v1)),
        "v2_symbols_with_zero": sorted(set(symbols) - set(by_symbol_v2)),
        "post_validation_v2_not_used_for_threshold": post_val_v2,
        "exchdisstime_limitation": (
            "candidate IST-tagged proxy; not proven first public print; not proven immutable"
        ),
        "section15": {
            "rule": "hasXbrl truthy OR desc matches result|financial|earnings (case-insensitive)",
            "kept": s15_kept,
            "not_kept": s15_not,
            "historical_undocumented_3690_not_used": True,
            "evidence": dict(s15_evidence),
            "desc_histogram": dict(s15_desc.most_common()),
            "false_positive_buckets": dict(s15_fp),
            "missing_or_unparseable_exchdisstime": s15_missing_clock,
            "symbols_with_zero": sorted(set(symbols) - set(by_symbol_s15)),
        },
        "section16": {
            "quarters": list(QUARTERS),
            "covered_cells": covered_cells,
            "missing_cells": missing_cells,
            "missing_cell_count": len(missing_cells),
            "grid": grid,
            "financial_results_endpoint_merged": False,
        },
        "holdout_accessed": False,
        "labels_generated": False,
        "timestamps": timestamps,
        "quarter_counts": qcounts,
        "slice_inventory_2025Q2": slices,
        "missingness": missingness,
        "prepared_scope_a": prepared_pub,
        "scope": scope,
        "protocol": protocol,
        "readiness": gate,
        "DATA_PREP_READY": gate["DATA_PREP_READY"],
        "READY_TO_RUN": "NO",
        "_sha256sums": integrity.get("sha256sums", ""),
        "_files": integrity.get("files") or [],
    }


def write_evidence(report: dict) -> dict[str, str]:
    DOCS.mkdir(parents=True, exist_ok=True)
    integrity_path = DOCS / "h001-scope-a-integrity.json"
    sums_path = DOCS / "h001-scope-a-SHA256SUMS.txt"
    coverage_json = DOCS / "h001-scope-a-coverage.json"
    coverage_md = DOCS / "h001-scope-a-coverage.md"
    v2_md = DOCS / "h001-v2-candidate.md"
    v2_json = DOCS / "h001-v2-coverage.json"
    files_path = DOCS / "h001-integrity-v2-files.json"
    prep_path = DOCS / "h001-prep-readiness.json"
    ts_path = DOCS / "h001-timestamp-provenance.json"

    integrity = dict(report.get("integrity") or {})
    sums = report.get("_sha256sums", "") or ""
    files_path.write_text(
        json.dumps(report.get("_files") or [], indent=2) + "\n",
        encoding="utf-8",
    )
    integrity_path.write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")
    if integrity.get("status") == "MEASURED":
        sums_path.write_text(sums, encoding="utf-8")
    else:
        sums_path.write_text(
            "# FREEZE_ABSENT — no hashes invented\n",
            encoding="utf-8",
        )

    pub = {k: v for k, v in report.items() if not str(k).startswith("_")}
    if "section16" in pub and "grid" in pub["section16"]:
        # keep missing_cells; drop dense grid from the committed JSON (see coverage.md)
        pub["section16"] = {k: v for k, v in pub["section16"].items() if k != "grid"}
    coverage_json.write_text(json.dumps(pub, indent=2) + "\n", encoding="utf-8")
    coverage_md.write_text(_scope_a_markdown(report), encoding="utf-8")
    v2_md.write_text(_v2_markdown(report), encoding="utf-8")
    v2_json.write_text(json.dumps(_v2_json(report), indent=2) + "\n", encoding="utf-8")
    ts_path.write_text(json.dumps(report.get("timestamps") or {}, indent=2) + "\n", encoding="utf-8")
    prep_path.write_text(
        json.dumps(
            {
                "DATA_PREP_READY": report.get("DATA_PREP_READY", "NO"),
                "READY_TO_RUN": "NO",
                "readiness": report.get("readiness"),
                "scope": report.get("scope"),
                "protocol": report.get("protocol"),
                "prepared_scope_a": report.get("prepared_scope_a"),
                "missingness": report.get("missingness"),
                "slice_inventory_2025Q2": report.get("slice_inventory_2025Q2"),
                "quarter_counts": report.get("quarter_counts"),
                "gate_2_data_ready": "WITHDRAWN",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "integrity": str(integrity_path),
        "sha256sums": str(sums_path),
        "integrity_files": str(files_path),
        "coverage_json": str(coverage_json),
        "coverage_md": str(coverage_md),
        "prep_readiness": str(prep_path),
        "timestamps": str(ts_path),
    }


def _scope_a_markdown(report: dict) -> str:
    if report.get("freeze_absent"):
        return """# H001 Scope A coverage

`DATA NOT READY` · `BLOCKED_PRECONDITION` · `READY_TO_RUN = NO`

Freeze `datasets/h001-nse-raw-20261010T140237Z` was **absent**. No hashes invented. No coverage table.
"""
    s15 = report["section15"]
    s16 = report["section16"]
    v1 = report["v1_gate"]
    missing = s16["missing_cells"]
    missing_block = (
        "\n".join(f"- `{row['symbol']}` {row['quarter']}" for row in missing) or "- (none)"
    )
    hist = s15["desc_histogram"]
    top = list(hist.items())[:15]
    hist_preview = ", ".join(f"{name}: {count}" for name, count in top)
    grid_lines = ["| symbol | " + " | ".join(QUARTERS) + " |", "|---|---|---|---|---|---|---|---|---|"]
    for symbol in report["universe"]:
        marks = ["Y" if report["section16"]["grid"][symbol][q] else "n" for q in QUARTERS]
        grid_lines.append("| `" + symbol + "` | " + " | ".join(marks) + " |")
    zero = ", ".join(s15["symbols_with_zero"]) or "(none)"
    return f"""# H001 Scope A coverage

`DATA NOT READY` · `BLOCKED_PRECONDITION` · `READY_TO_RUN = NO`

Scope A only: announcement tape + named hasher + §15/§16 table. **Not** PIT-certified. **Not** fit authorization.
No labels. No train. Historical digest `b0f4760f…` remains **UNVERIFIED**.

## Integrity

Freeze `{report["integrity"]["freeze_id"]}`. Recipe: `{report["integrity"]["recipe"]}`.
New baseline `{report["integrity"].get("integrity_baseline_sha256")}`. Files: {report["integrity"].get("n_files")}.
Matches prior listing digest 18dbec4a…: `{report["integrity"].get("matches_expected_unchanged_baseline")}`.
`equivalent_to_b0f4760f`: false.

## v1 (immutable three-desc; unique seq_id)

| Unique | Train | Validate | Post-val | >=50 train | >=50 val |
|---|---|---|---|---|---|
| {report["unique_v1_events"]} | {v1["train"]} | {v1["validate"]} | {v1["post_validation_reported_separately"]} | {v1["min_class_50_train"]} | {v1["min_class_50_validate"]} |

v1 by desc: `{report["v1_by_desc"]}`

Announcement count ≥50 is **not** fit authorization.

## §15 results-like (exact rule)

Keep if `hasXbrl` is truthy **or** `desc` matches `result|financial|earnings` (case-insensitive).
Not the undocumented historical 3,690.

| kept | not kept | hasXbrl only | regex only | both | unparseable exchdisstime |
|---|---|---|---|---|---|
| {s15["kept"]} | {s15["not_kept"]} | {s15["evidence"].get("hasXbrl_only", 0)} | {s15["evidence"].get("regex_only", 0)} | {s15["evidence"].get("both", 0)} | {s15["missing_or_unparseable_exchdisstime"]} |

This scan's kept count is **under the written §15 rule**. It happens to equal Gate 2's undocumented `results_like_kept: 3690`; that coincidence does **not** certify Gate 2's predicate. `hasXbrl`-only rows (analyst meets, general updates, newspaper copies, etc.) dominate and are **false positives for an earnings-print class**. The rule was not tightened.

False-positive / ambiguous buckets (not a filter): `{s15["false_positive_buckets"]}`

desc histogram (top 15; full list in `h001-scope-a-coverage.json`): {hist_preview}

Symbols with zero §15 rows: {zero}

## §16 49 × 8 IST calendar quarters

Universe: 49 snapshot symbols with bars (`TATAMOTORS` excluded, not substituted).
Covered cell: ≥1 §15-kept row with parseable `exchdisstime` in that IST quarter.
Financial-results auxiliary endpoint: **not merged**.

Covered cells: **{s16["covered_cells"]} / 392**. Missing cells: **{s16["missing_cell_count"]}**.
Missing cells stay missing (no imputation). Observed missing quarters are listed below (this freeze: almost all `2025Q2`).

Missing cells:

{missing_block}

{chr(10).join(grid_lines)}

## Timestamp limitation

{report["exchdisstime_limitation"]} (see `h001-timestamp-leakage.md`).

Scope B restatement-safe earnings values: **not established**.
"""


def _v2_markdown(report: dict) -> str:
    if report.get("freeze_absent"):
        return """# H001-v2 candidate (not approved)

`DATA NOT READY` · `READY_TO_RUN = NO`

Freeze absent; v2 candidate not recounted.
"""
    v1 = report["v1_gate"]
    v2 = report["v2_gate"]
    return f"""# H001-v2 candidate (not approved)

Status: `PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED` for **v1**.  
H001-v2 is a **candidate only**.

`DATA NOT READY` · `BLOCKED_PRECONDITION` · `READY_TO_RUN = NO`

No labels, no fit, no backtest, no holdout.

Scope A evidence (hasher, §15, 49×8): `h001-scope-a-coverage.md`, `h001-scope-a-integrity.json`, `h001-scope-a-SHA256SUMS.txt`. Those artifacts do **not** authorize labels or fit.

## Original v1 include-list (immutable)

Normalized exact `desc`:

- `financial result updates`
- `consolidated result updates ifrs`
- `publish audited results`

Windows: train `exchdisstime` through 2024-06-30 IST; validate 2024-07-01 through 2025-02-14 IST. Later rows reported separately.

## Coverage reproduced from freeze `h001-nse-raw-20261010T140237Z`

Announcement-unique `seq_id` counts (not labelled decision sessions; not a train authorization):

| Class | Unique events | Train | Validate | Post-validation (not for threshold) | Announcement count >=50 train | >=50 val |
|---|---|---|---|---|---|---|
| v1 approved | {report["unique_v1_events"]} | {v1["train"]} | {v1["validate"]} | {v1["post_validation_reported_separately"]} | {"yes" if v1["min_class_50_train"] else "no"} | {"yes" if v1["min_class_50_validate"] else "no"} |
| v2 candidate | {report["unique_v2_events"]} | {v2["train"]} | {v2["validate"]} | {v2["post_validation_reported_separately"]} | {"yes" if v2["min_class_50_train"] else "no"} | {"yes" if v2["min_class_50_validate"] else "no"} |

These counts **do not** make H001 ready to run. They are not session-level positives after candle joins, leakage filters, or a frozen target. A prior brief of **34** minority training rows is **not reproduced** as unique v1 announcements (that figure likely used a stricter eligibility pipeline that this sprint did not re-implement and must not invent). `consolidated result updates ifrs` has **0** rows in the freeze.

Raw in-universe rows: {report["raw_announcement_rows_in_universe"]}. Missing `exchdisstime`: {report["missing_exchdisstime"]}.

v1 by desc: `{report["v1_by_desc"]}`

v2 evidence kinds: `{report["v2_by_evidence_kind"]}`

v1 symbols with zero events: {", ".join(report["v1_symbols_with_zero"]) or "(none)"}

Integrity: historical `{report["integrity"]["historical_digest"]}` remains **UNVERIFIED**. New recipe `{report["integrity"]["recipe"]}` digest `{report["integrity"].get("integrity_baseline_sha256")}` — **not equivalent**.

`exchdisstime`: {report["exchdisstime_limitation"]}

## v2 proposed rule (awaits approval)

1. Keep v1 subjects.
2. Keep `Integrated Filing- Financial` / close spelling variants (NSE/CML/2025/20 XBRL module).
3. Keep `Outcome of Board Meeting` **only if** attachment text matches financial-results language.
4. Do not keep all board outcomes, dividends, appointments.

Do not train on v2 until approved. Do not lower the 50-per-partition threshold.
"""


def _v2_json(report: dict) -> dict:
    integrity = report.get("integrity") or {}
    v1 = report.get("v1_gate") or {}
    v2 = report.get("v2_gate") or {}
    return {
        "status": "PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED",
        "h001_v2": "candidate_only",
        "DATA_NOT_READY": True,
        "BLOCKED_PRECONDITION": True,
        "READY_TO_RUN": False,
        "freeze": "h001-nse-raw-20261010T140237Z",
        "historical_digest_b0f4760f": "UNVERIFIED",
        "new_listing_digest": integrity.get("integrity_baseline_sha256"),
        "new_listing_digest_equivalent_to_historical": False,
        "scope_a_docs": [
            "h001-scope-a-coverage.md",
            "h001-scope-a-coverage.json",
            "h001-scope-a-integrity.json",
            "h001-scope-a-SHA256SUMS.txt",
        ],
        "counts": {
            "v1_unique": report.get("unique_v1_events"),
            "v1_train": v1.get("train"),
            "v1_validate": v1.get("validate"),
            "v2_unique": report.get("unique_v2_events"),
            "v2_train": v2.get("train"),
            "v2_validate": v2.get("validate"),
            "v2_post_validation_not_for_threshold": v2.get("post_validation_reported_separately"),
            "raw_in_universe_rows": report.get("raw_announcement_rows_in_universe"),
        },
        "announcement_count_ge_50_is_not_fit_authorization": True,
        "labels_generated": False,
        "model_trained": False,
    }


def main() -> None:
    report = summarize()
    wrote = write_evidence(report)
    print(
        json.dumps(
            {
                "wrote": wrote,
                "freeze_absent": report.get("freeze_absent"),
                "integrity_status": (report.get("integrity") or {}).get("status"),
                "READY_TO_RUN": "NO",
                "DATA_PREP_READY": report.get("DATA_PREP_READY"),
                "v1_gate": report.get("v1_gate"),
                "section16_missing": (report.get("section16") or {}).get("missing_cell_count"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
