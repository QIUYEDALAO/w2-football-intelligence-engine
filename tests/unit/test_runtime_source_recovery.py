"""An exact anomaly receipt admits replacement, never unknown runtime source."""

from __future__ import annotations

import hashlib
import io
import json
import runpy
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

TOOL = Path(__file__).parents[2] / "scripts/w2_runtime_source_recovery.py"


@pytest.mark.parametrize(
    "attack,reason",
    [
        ("manifest_digest", "RECOVERY_MANIFEST_HASH_MISMATCH"),
        ("target", "RECOVERY_TARGET_MISMATCH"),
        ("revision", "RECOVERY_DATABASE_REVISION_MISMATCH"),
        ("source", "RECOVERY_CURRENT_SOURCE_CONFLICT"),
        ("archive", "RECOVERY_ARCHIVE_HASH_MISMATCH"),
        ("expired", "RECOVERY_EXPIRED"),
    ],
)
def test_recovery_requires_same_current_source_and_immutable_archive(tmp_path, attack, reason):
    verify = runpy.run_path(str(TOOL))["verify"]
    target = "a" * 40
    original = b"print('source')\n"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        nested = tarfile.TarInfo("src/w2/example/a.py")
        nested.size = len(original)
        tar.addfile(nested, io.BytesIO(original))
        member = tarfile.TarInfo("src/w2/example.py")
        member.size = len(original)
        tar.addfile(member, io.BytesIO(original))
    archive_path = tmp_path / "source.tar.gz"
    archive_path.write_bytes(archive.getvalue())
    # Independent byte-concatenation oracle for the source tree identity.
    source_hash = hashlib.sha256(
        b"src/w2/example/a.py\0" + original + b"\0" + b"src/w2/example.py\0" + original + b"\0"
    ).hexdigest()
    values = ["sha256:image", "0076", "0084", "b" * 64, source_hash]
    manifest = {
        "schema_version": "w2.runtime_source_recovery.v1",
        "target_sha": target,
        "database_revision": "0076",
        "captured_at": datetime.now(UTC).isoformat(),
        "services": {
            "api": dict(
                zip(
                    ("image", "image_head", "container_head", "image_hash", "container_hash"),
                    values,
                    strict=True,
                )
            )
            | {
                "archive": archive_path.name,
                "archive_sha256": hashlib.sha256(archive.getvalue()).hexdigest(),
            }
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    verify(path, digest, target, "api", "0076", values)
    if attack == "manifest_digest":
        path.write_text(path.read_text() + " ")
    elif attack == "target":
        target = "c" * 40
    elif attack == "revision":
        manifest["database_revision"] = "0088"
    elif attack == "source":
        values = [*values[:-1], "c" * 64]
    elif attack == "archive":
        archive_path.write_bytes(archive.getvalue() + b"changed")
    elif attack == "expired":
        manifest["captured_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    if attack in {"revision", "expired"}:
        path.write_text(json.dumps(manifest))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(AssertionError, match=reason):
        verify(path, digest, target, "api", "0076", values)
