from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class HashScheme(StrEnum):
    SHA256_FILE_BYTES_V1 = "SHA256_FILE_BYTES_V1"
    SHA256_CANONICAL_JSON_V1 = "SHA256_CANONICAL_JSON_V1"
    LEGACY_UNKNOWN = "LEGACY_UNKNOWN"


def sha256_file_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_canonical_json(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True, kw_only=True)
class HashCheck:
    field: str
    path: str
    declared_hash: str | None
    file_bytes_hash: str | None
    canonical_json_hash: str | None
    matched_scheme: HashScheme | None
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "path": self.path,
            "declared_hash": self.declared_hash,
            "file_bytes_hash": self.file_bytes_hash,
            "canonical_json_hash": self.canonical_json_hash,
            "matched_scheme": self.matched_scheme.value if self.matched_scheme else None,
            "status": self.status,
        }


class SnapshotHashSchemeRegistry:
    def identify(self, declared_hash: str | None, path: Path) -> HashScheme | None:
        if not declared_hash or not path.exists():
            return None
        if declared_hash == sha256_file_bytes(path):
            return HashScheme.SHA256_FILE_BYTES_V1
        try:
            if declared_hash == sha256_canonical_json(path):
                return HashScheme.SHA256_CANONICAL_JSON_V1
        except json.JSONDecodeError:
            return None
        return None


class SnapshotIntegrityCorrectionLedger:
    def __init__(self, ledger_path: Path) -> None:
        self.ledger_path = ledger_path
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, payload: dict[str, Any]) -> None:
        event = {
            "event_id": str(uuid.uuid4()),
            "detected_at_utc": datetime.now(UTC).isoformat(),
            "append_only": True,
            **payload,
        }
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


class SnapshotHashVerifier:
    def __init__(
        self,
        *,
        registry: SnapshotHashSchemeRegistry | None = None,
        ledger: SnapshotIntegrityCorrectionLedger | None = None,
    ) -> None:
        self.registry = registry or SnapshotHashSchemeRegistry()
        self.ledger = ledger

    def verify_snapshot(self, snapshot_dir: Path) -> dict[str, Any]:
        manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
        checks = [
            self._check(
                manifest,
                "normalized_data_sha256",
                snapshot_dir / "normalized_odds.json",
            ),
            self._check(manifest, "model_artifact_sha256", snapshot_dir / "model_output.json"),
            self._check(manifest, "decision_sha256", snapshot_dir / "decision.json"),
        ]
        statuses = {check.status for check in checks}
        if statuses <= {"PASS"}:
            integrity_status = "PASS"
        elif statuses <= {"PASS", "RECONCILED"}:
            integrity_status = "LEGACY_HASH_SCHEME_RECONCILED"
        else:
            integrity_status = "QUARANTINED"
        payload = {
            "snapshot_id": snapshot_dir.name,
            "hash_scheme_version": manifest.get(
                "hash_scheme_version", HashScheme.LEGACY_UNKNOWN.value
            ),
            "integrity_status": integrity_status,
            "file_mtime": datetime.fromtimestamp(
                (snapshot_dir / "manifest.json").stat().st_mtime,
                tz=UTC,
            ).isoformat(),
            "checks": [check.as_dict() for check in checks],
            "raw_payload_sha256": manifest.get("raw_payload_sha256"),
        }
        if integrity_status == "LEGACY_HASH_SCHEME_RECONCILED" and self.ledger:
            self.ledger.append(
                {
                    "event_type": "HASH_SCHEME_RECONCILIATION",
                    "snapshot_id": snapshot_dir.name,
                    "integrity_status": integrity_status,
                    "checks": payload["checks"],
                }
            )
        if integrity_status == "QUARANTINED" and self.ledger:
            self.ledger.append(
                {
                    "event_type": "HASH_SCHEME_QUARANTINE",
                    "snapshot_id": snapshot_dir.name,
                    "integrity_status": integrity_status,
                    "checks": payload["checks"],
                }
            )
        return payload

    def _check(self, manifest: dict[str, Any], field: str, path: Path) -> HashCheck:
        declared = manifest.get(field)
        declared_hash = str(declared) if isinstance(declared, str) else None
        file_hash = sha256_file_bytes(path) if path.exists() else None
        canonical_hash = None
        try:
            canonical_hash = sha256_canonical_json(path) if path.exists() else None
        except json.JSONDecodeError:
            canonical_hash = None
        matched = self.registry.identify(declared_hash, path)
        if matched == HashScheme.SHA256_FILE_BYTES_V1:
            status = "PASS"
        elif matched == HashScheme.SHA256_CANONICAL_JSON_V1:
            status = "PASS"
        elif declared_hash and path.exists() and declared_hash not in {file_hash, canonical_hash}:
            status = "RECONCILED" if manifest.get("hash_scheme_version") is None else "FAIL"
        else:
            status = "FAIL"
        return HashCheck(
            field=field,
            path=str(path),
            declared_hash=declared_hash,
            file_bytes_hash=file_hash,
            canonical_json_hash=canonical_hash,
            matched_scheme=matched,
            status=status,
        )
