from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.domain.time import require_utc
from w2.models.independent import artifact_hash


@dataclass(frozen=True, kw_only=True)
class BackupManifest:
    backup_id: str
    created_at: datetime
    source: str
    row_count: int
    sha256: str
    encrypted_backup_interface: str = "PLACEHOLDER_NO_KEY_GENERATED"

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))


class LocalBackupRestoreDrill:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def synthetic_rows(self) -> list[dict[str, Any]]:
        return [
            {"id": "synthetic-1", "kind": "api_request_audit", "value": 1},
            {"id": "synthetic-2", "kind": "operational_metric_snapshot", "value": 2},
        ]

    def backup(self, rows: list[dict[str, Any]]) -> BackupManifest:
        payload = {"rows": rows}
        sha = artifact_hash(payload)
        path = self.root / "backup.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = BackupManifest(
            backup_id="stage11a-local-drill",
            created_at=datetime.now(UTC),
            source="synthetic_temp_instance",
            row_count=len(rows),
            sha256=sha,
        )
        (self.root / "manifest.json").write_text(
            json.dumps(manifest.__dict__, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return manifest

    def restore(self, manifest: BackupManifest) -> dict[str, Any]:
        path = self.root / "backup.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        restored_sha = artifact_hash(payload)
        return {
            "backup_id": manifest.backup_id,
            "original_row_count": manifest.row_count,
            "restored_row_count": len(payload["rows"]),
            "original_sha256": manifest.sha256,
            "restored_sha256": restored_sha,
            "verified": (
                manifest.sha256 == restored_sha
                and manifest.row_count == len(payload["rows"])
            ),
            "real_runtime_touched": False,
        }
