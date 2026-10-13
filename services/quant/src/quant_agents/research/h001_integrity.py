"""Historical-digest verification for Authorization B. Not a model path."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from quant_agents.research.h001.authorization import refuse_restricted_source, require_authorization_b

# Copied in full from services/quant/docs/h001-protocol-approval.md. Not reconstructed.
HISTORICAL_DIGEST = (
    "b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae"
)
NEW_VERIFICATION_BASELINE = (
    "adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2"
)
PARQUET_BYTES_DIGEST = (
    "8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494"
)
MANIFEST_BYTES_DIGEST = (
    "d0a481cbaf87ceae8679d0918f5001af76793ed5ec9b08c3a5f89876c2b9ec7a"
)
ZIP_BYTES_DIGEST = (
    "271dd1ce85a1a1c326a87a2c870f567148bed604914c993fd6eb5f1ff157f83c"
)
DAILY_CANDLE_SHA256 = (
    "0411a89535ab50ae6488c7d93c5ce7572feba4f55fd9ecb0f73478bf33bd2a7d"
)
FIVE_MINUTE_CANDLE_SHA256 = (
    "0f2df34d35e5a02ab6cd725882afd3fca7354eff65e4c1d219cf7fa9bdf1cb9b"
)

EXTRACTED_FREEZE = Path("datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z")
NAMED_FREEZE = Path("datasets/h001-nse-raw-20261010T140237Z")
PARQUET_PATH = Path("datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet")
PARQUET_MANIFEST = Path("datasets/h001-pit-events-nse-ann-2024-2025-v1.manifest.json")
ZIP_PATH = Path("datasets/h001-nse-ann-2024-2025-v1.zip")
DAILY_CANDLES = Path("snapshots 2/nifty50/1D/candles.jsonl")
DAILY_MANIFEST = Path("snapshots 2/nifty50/1D/manifest.json")
FIVE_MINUTE_CANDLES = Path("snapshots 2/nifty50/5m/candles.jsonl")
FIVE_MINUTE_MANIFEST = Path("snapshots 2/nifty50/5m/manifest.json")


class IntegrityVerificationFailed(RuntimeError):
    """Historical digest not verified. Eligibility counts must not be computed."""


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    historical_expected: str
    historical_status: str
    historical_blocker: str
    tree_digest: str | None
    tree_matches_new_verification_baseline: bool | None
    parquet_digest: str | None
    parquet_matches_recorded: bool | None
    freeze_root_used: str | None
    named_freeze_present: bool
    extracted_freeze_present: bool
    parquet_present: bool
    daily_snapshot_id: str | None
    five_minute_snapshot_id: str | None
    daily_manifest_sha_field: str | None
    five_minute_manifest_sha_field: str | None
    retrieval_describes_hash_procedure: bool
    holdout_accessed: bool


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _new_verification_baseline_digest(root: Path) -> tuple[str, int, int]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(part.startswith(".") for part in relative.split("/")):
            continue
        files.append(path)
    files.sort(key=lambda item: item.relative_to(root).as_posix().encode("utf-8"))
    stream = hashlib.sha256()
    content_bytes = 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        payload = path.read_bytes()
        content_bytes += len(payload)
        stream.update(relative.encode("utf-8"))
        stream.update(b"\x00")
        stream.update(len(payload).to_bytes(8, "big"))
        stream.update(payload)
    return stream.hexdigest(), len(files), content_bytes


def _assert_not_holdout(*paths: Path) -> None:
    for path in paths:
        refuse_restricted_source(str(path), authorization_present=True)


def _read_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_authorized_inputs(authorization: object | None, repo_root: Path) -> IntegrityReport:
    require_authorization_b(authorization)
    named = repo_root / NAMED_FREEZE
    extracted = repo_root / EXTRACTED_FREEZE
    parquet = repo_root / PARQUET_PATH
    daily_manifest = repo_root / DAILY_MANIFEST
    five_manifest = repo_root / FIVE_MINUTE_MANIFEST
    _assert_not_holdout(named, extracted, parquet, daily_manifest, five_manifest)

    freeze_root: Path | None = None
    if extracted.is_dir():
        freeze_root = extracted
    elif named.is_dir():
        freeze_root = named

    retrieval_describes = False
    tree_digest: str | None = None
    tree_match: bool | None = None
    if freeze_root is not None:
        retrieval = freeze_root / "retrieval.json"
        if retrieval.is_file():
            payload = json.loads(retrieval.read_text(encoding="utf-8"))
            retrieval_describes = bool(
                payload.get("hashed_files")
                or payload.get("hash_order")
                or payload.get("hash_procedure")
            )
        tree_digest, _, _ = _new_verification_baseline_digest(freeze_root)
        tree_match = tree_digest == NEW_VERIFICATION_BASELINE

    parquet_digest: str | None = None
    parquet_match: bool | None = None
    if parquet.is_file():
        parquet_digest = _sha256_file(parquet)
        parquet_match = parquet_digest == PARQUET_BYTES_DIGEST

    daily_id = None
    five_id = None
    daily_sha = None
    five_sha = None
    if daily_manifest.is_file():
        daily = _read_manifest(daily_manifest)
        daily_id = str(daily.get("snapshot_id", ""))
        daily_sha = str(daily.get("candle_sha256", daily.get("sha256", "")))
    if five_manifest.is_file():
        five = _read_manifest(five_manifest)
        five_id = str(five.get("snapshot_id", ""))
        five_sha = str(five.get("candle_sha256", five.get("sha256", "")))

    historical_match = tree_digest == HISTORICAL_DIGEST if tree_digest else False
    if historical_match:
        status = "VERIFIED"
        blocker = ""
    else:
        status = "UNVERIFIED"
        blocker = (
            "The approved historical digest "
            f"{HISTORICAL_DIGEST} cannot be verified against the actual freeze "
            "bytes. retrieval.json does not document the hashed filenames or "
            "byte order. NEW_VERIFICATION_BASELINE is a different checksum and "
            "is not substituted. Eligibility counts are not computed."
        )

    return IntegrityReport(
        historical_expected=HISTORICAL_DIGEST,
        historical_status=status,
        historical_blocker=blocker,
        tree_digest=tree_digest,
        tree_matches_new_verification_baseline=tree_match,
        parquet_digest=parquet_digest,
        parquet_matches_recorded=parquet_match,
        freeze_root_used=None if freeze_root is None else str(freeze_root),
        named_freeze_present=named.is_dir(),
        extracted_freeze_present=extracted.is_dir(),
        parquet_present=parquet.is_file(),
        daily_snapshot_id=daily_id,
        five_minute_snapshot_id=five_id,
        daily_manifest_sha_field=daily_sha,
        five_minute_manifest_sha_field=five_sha,
        retrieval_describes_hash_procedure=retrieval_describes,
        holdout_accessed=False,
    )


def require_historical_digest_verified(report: IntegrityReport) -> None:
    if report.historical_status != "VERIFIED":
        raise IntegrityVerificationFailed(report.historical_blocker)
