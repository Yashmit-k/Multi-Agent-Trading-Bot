"""Named hasher for freeze `h001-nse-raw-20261010T140237Z`.

Audit v1 listing digest is independent of historical digest b0f4760f.
Audit v2 adds size_bytes and artifact class; it is a new named measurement.
Does not mutate freeze files. Does not invent hashes when the freeze is absent.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

HISTORICAL_DIGEST = "b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae"
RECIPE = (
    "sha256 of sorted sha256sum-style lines (HASH two-spaces POSIX-relpath newline) "
    "over freeze .raw and .json files"
)
RECIPE_V2 = (
    "JSON array of {relpath, size_bytes, sha256, artifact_class} sorted by POSIX relpath; "
    "aggregate = sha256 of canonical sha256sum listing (v1) plus a separate "
    "files_manifest_sha256 of UTF-8 JSON lines (one object per file, sorted)"
)
FREEZE_ID = "h001-nse-raw-20261010T140237Z"
EXPECTED_BASELINE_IF_UNCHANGED = "18dbec4a4712b1430a6dabeca03a157af03cba45dac346c1a21d6b39d3f77f2d"
AUDIT_VERSION = "h001-integrity-audit-v2"
EXTERNAL_PARQUET = "datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet"
EXTERNAL_PARQUET_MANIFEST = "datasets/h001-pit-events-nse-ann-2024-2025-v1.manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def listing_files(freeze: Path) -> list[Path]:
    return sorted(
        p for p in freeze.rglob("*") if p.is_file() and p.suffix.lower() in {".raw", ".json"}
    )


def artifact_class(rel: str) -> str:
    lower = rel.lower()
    if lower.endswith(".parquet"):
        return "normalized_parquet"
    if lower.endswith(".zip"):
        return "archive"
    if lower.startswith("corporate-announcements/") and lower.endswith(".raw"):
        return "announcement_raw"
    if lower.startswith("corporate-announcements/") and lower.endswith(".json"):
        return "announcement_concat_json"
    if lower.startswith("financial-results/"):
        return "financial_results_auxiliary"
    if lower == "retrieval.json":
        return "retrieval_record"
    if lower == "audit_stats.json":
        return "historical_audit_stats"
    return "other_json_or_raw"


def sha256sums_text(freeze: Path, files: list[Path] | None = None) -> str:
    paths = files if files is not None else listing_files(freeze)
    lines = []
    for path in paths:
        rel = path.relative_to(freeze).as_posix()
        lines.append(f"{sha256_file(path)}  {rel}")
    return "\n".join(lines) + "\n"


def digest_of_listing(listing: str) -> str:
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def _file_records(freeze: Path, files: list[Path]) -> list[dict]:
    records = []
    for path in files:
        rel = path.relative_to(freeze).as_posix()
        records.append(
            {
                "relpath": rel,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "artifact_class": artifact_class(rel),
            }
        )
    return records


def _external_sidecar(repo: Path, rel: str) -> dict:
    path = repo / rel
    if not path.is_file():
        return {
            "relpath": rel,
            "status": "ABSENT",
            "artifact_class": artifact_class(rel),
            "note": "Not inside the raw freeze. Hash not invented.",
        }
    return {
        "relpath": rel,
        "status": "PRESENT",
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "artifact_class": artifact_class(rel),
        "note": "Separate from freeze listing digest; not mixed into b0f4760f or 18dbec4a",
    }


def freeze_integrity(freeze: Path, repo: Path | None = None) -> dict:
    base_absent = {
        "freeze_id": FREEZE_ID,
        "freeze_path": f"datasets/{FREEZE_ID}",
        "audit_version": AUDIT_VERSION,
        "recipe": RECIPE,
        "recipe_v2": RECIPE_V2,
        "n_files": 0,
        "sha256sums": "",
        "files": [],
        "by_class": {},
        "integrity_baseline_sha256": None,
        "files_manifest_sha256": None,
        "historical_digest": HISTORICAL_DIGEST,
        "historical_digest_status": "UNVERIFIED",
        "equivalent_to_b0f4760f": False,
        "matches_expected_unchanged_baseline": False,
        "historical_note": "Do not treat integrity_baseline_sha256 as equal to b0f4760f",
        "READY_TO_RUN": "NO",
        "DATA_PREP_READY": "UNSET",
    }
    if not freeze.is_dir():
        return {**base_absent, "status": "FREEZE_ABSENT"}

    files = listing_files(freeze)
    listing = sha256sums_text(freeze, files)
    baseline = digest_of_listing(listing)
    records = _file_records(freeze, files)
    class_counts: dict[str, int] = {}
    for row in records:
        class_counts[row["artifact_class"]] = class_counts.get(row["artifact_class"], 0) + 1
    manifest_blob = "".join(
        f'{item["sha256"]} {item["size_bytes"]} {item["relpath"]}\n' for item in records
    )
    files_manifest_sha256 = hashlib.sha256(manifest_blob.encode("utf-8")).hexdigest()
    root = repo or freeze.parent.parent
    return {
        "freeze_id": FREEZE_ID,
        "freeze_path": f"datasets/{FREEZE_ID}",
        "audit_version": AUDIT_VERSION,
        "status": "MEASURED",
        "recipe": RECIPE,
        "recipe_v2": RECIPE_V2,
        "n_files": len(files),
        "sha256sums": listing,
        "files": records,
        "by_class": class_counts,
        "integrity_baseline_sha256": baseline,
        "files_manifest_sha256": files_manifest_sha256,
        "historical_digest": HISTORICAL_DIGEST,
        "historical_digest_status": "UNVERIFIED",
        "equivalent_to_b0f4760f": False,
        "expected_baseline_if_unchanged": EXPECTED_BASELINE_IF_UNCHANGED,
        "matches_expected_unchanged_baseline": baseline == EXPECTED_BASELINE_IF_UNCHANGED,
        "historical_note": "Do not treat integrity_baseline_sha256 as equal to b0f4760f",
        "sidecars": {
            "parquet": _external_sidecar(root, EXTERNAL_PARQUET),
            "parquet_manifest": _external_sidecar(root, EXTERNAL_PARQUET_MANIFEST),
        },
        "READY_TO_RUN": "NO",
        "DATA_PREP_READY": "UNSET",
    }
