from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "W2DataAssetRegistryV1"
FOOTBALL_DATA_ALIAS = "$W2_FOOTBALL_DATA_ROOT"
BACKUP_ALIAS = "$W2_DATA_BACKUP_ROOT"


@dataclass(frozen=True, kw_only=True)
class W2DataAssetRegistryV1:
    asset_id: str
    source: str
    purpose: tuple[str, ...]
    schema_version: str
    private_storage_location_alias: str
    source_file_hashes: dict[str, str]
    dataset_manifest_hash: str
    coverage: dict[str, Any]
    license_review_status: str
    created_at: str
    last_verified_at: str
    code_compatibility_version: str
    restore_command: str
    backup_location: str
    restore_test_status: str
    consumers: tuple[str, ...]
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "asset_id": self.asset_id,
            "source": self.source,
            "purpose": list(self.purpose),
            "asset_schema_version": self.schema_version,
            "private_storage_location_alias": self.private_storage_location_alias,
            "source_file_hashes": dict(sorted(self.source_file_hashes.items())),
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "coverage": dict(self.coverage),
            "license_review_status": self.license_review_status,
            "created_at": self.created_at,
            "last_verified_at": self.last_verified_at,
            "code_compatibility_version": self.code_compatibility_version,
            "restore_command": self.restore_command,
            "backup_location": self.backup_location,
            "restore_test_status": self.restore_test_status,
            "consumers": list(self.consumers),
            "blockers": list(self.blockers),
            "registry_hash": self.registry_hash,
        }

    @property
    def registry_hash(self) -> str:
        payload = self.as_hash_payload()
        return stable_hash(payload)

    def as_hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "asset_id": self.asset_id,
            "source": self.source,
            "purpose": list(self.purpose),
            "asset_schema_version": self.schema_version,
            "private_storage_location_alias": self.private_storage_location_alias,
            "source_file_hashes": dict(sorted(self.source_file_hashes.items())),
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "coverage": dict(self.coverage),
            "license_review_status": self.license_review_status,
            "code_compatibility_version": self.code_compatibility_version,
            "restore_command": self.restore_command,
            "backup_location": self.backup_location,
            "restore_test_status": self.restore_test_status,
            "consumers": list(self.consumers),
            "blockers": list(self.blockers),
        }


def build_football_data_registry(
    *,
    data_root: Path | None = None,
    backup_root: Path | None = None,
    coverage: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> W2DataAssetRegistryV1:
    current = now or datetime.now(UTC)
    resolved_data_root = data_root or _env_path("W2_FOOTBALL_DATA_ROOT")
    resolved_backup_root = backup_root or _env_path("W2_DATA_BACKUP_ROOT")
    blockers: list[str] = []
    source_hashes: dict[str, str] = {}
    manifest_hash = "SOURCE_LOCAL_NOT_AVAILABLE"
    if resolved_data_root is None:
        blockers.append("W2_FOOTBALL_DATA_ROOT_REQUIRED")
    elif not resolved_data_root.exists():
        blockers.append("W2_FOOTBALL_DATA_ROOT_NOT_FOUND")
    else:
        source_hashes = hash_source_files(resolved_data_root)
        manifest_hash = stable_hash(source_hashes)
    backup_location = "BACKUP_LOCATION_REQUIRED"
    restore_status = "RESTORE_DRILL_NOT_EXECUTED"
    if resolved_backup_root is None:
        blockers.append("BACKUP_LOCATION_REQUIRED")
    elif not resolved_backup_root.exists():
        blockers.append("BACKUP_LOCATION_NOT_FOUND")
    elif resolved_data_root is not None and resolved_data_root.exists():
        backup_location = BACKUP_ALIAS
        restore_status = restore_drill(
            data_root=resolved_data_root,
            backup_root=resolved_backup_root,
            expected_hashes=source_hashes,
        )
        if restore_status != "RESTORE_DRILL_PASS":
            blockers.append(restore_status)
    if "LICENSE_HUMAN_REVIEW_REQUIRED" not in blockers:
        blockers.append("LICENSE_HUMAN_REVIEW_REQUIRED")
    return W2DataAssetRegistryV1(
        asset_id="football_data_co_uk_historical_ah_2019_2026_v1",
        source="FOOTBALL_DATA_CO_UK",
        purpose=("historical_market_fact", "F5_dataset", "phase_market_evidence"),
        schema_version="football_data_co_uk_adapter.v2",
        private_storage_location_alias=FOOTBALL_DATA_ALIAS,
        source_file_hashes=source_hashes,
        dataset_manifest_hash=manifest_hash,
        coverage=dict(coverage or {}),
        license_review_status="HUMAN_REVIEW_REQUIRED",
        created_at=_iso(current),
        last_verified_at=_iso(current),
        code_compatibility_version="0029_consolidate_matchday_runtime_authority",
        restore_command=("python -m w2.data_assets.registry --asset football-data --json"),
        backup_location=backup_location,
        restore_test_status=restore_status,
        consumers=("football_data_co_uk_adapter.v2", "F5_runtime_query"),
        blockers=tuple(sorted(set(blockers))),
    )


def hash_source_files(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(_iter_source_files(root)):
        rel = path.relative_to(root).as_posix()
        hashes[rel] = sha256_file(path)
    return hashes


def restore_drill(
    *,
    data_root: Path,
    backup_root: Path,
    expected_hashes: Mapping[str, str],
) -> str:
    target = backup_root / data_root.name
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
        for path in _iter_source_files(data_root):
            rel = path.relative_to(data_root)
            destination = target / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    with tempfile.TemporaryDirectory(prefix="w2-data-restore-") as tmp:
        restored = Path(tmp) / "restore"
        shutil.copytree(target, restored)
        restored_hashes = hash_source_files(restored)
    return (
        "RESTORE_DRILL_PASS"
        if restored_hashes == dict(expected_hashes)
        else "RESTORE_HASH_MISMATCH"
    )


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_registry(path: Path, registry: W2DataAssetRegistryV1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(registry.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _iter_source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".jsonl", ".txt"}:
            yield path


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else None


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
