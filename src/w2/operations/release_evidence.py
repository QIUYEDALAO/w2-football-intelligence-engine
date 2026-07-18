from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel, Field
from sqlalchemy import text

from w2.config import Settings, get_settings
from w2.infrastructure.database import create_engine

SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
GIT_SHA = re.compile(r"[0-9a-f]{7,40}\Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _env_identity(name: str, *, pattern: re.Pattern[str] | None = None) -> dict[str, str]:
    value = os.getenv(name, "").strip()
    if not value or value.upper() in {"UNKNOWN", "UNAVAILABLE"}:
        return {"status": "UNAVAILABLE", "value": "UNAVAILABLE"}
    if pattern is not None and pattern.fullmatch(value) is None:
        return {"status": "INVALID", "value": value}
    return {"status": "AVAILABLE", "value": value}


def _alembic_identity(settings: Settings) -> dict[str, str]:
    current = "UNAVAILABLE"
    head = "UNAVAILABLE"
    with suppress(Exception):
        migrations = settings.readiness_migrations_path
        if not migrations.is_absolute():
            migrations = settings.readiness_release_root / migrations
        config = Config()
        config.set_main_option("script_location", str(migrations))
        heads = ScriptDirectory.from_config(config).get_heads()
        if len(heads) == 1:
            head = heads[0]
    engine = None
    with suppress(Exception):
        engine = create_engine(settings)
        with engine.connect() as connection:
            value = connection.execute(text("select version_num from alembic_version")).scalar_one()
        current = str(value)
    if engine is not None:
        engine.dispose()
    status = (
        "MATCH"
        if current != "UNAVAILABLE" and current == head
        else "MISMATCH"
        if current != "UNAVAILABLE" and head != "UNAVAILABLE"
        else "UNAVAILABLE"
    )
    return {"status": status, "current": current, "head": head}


def _readiness_manifest_identity(settings: Settings) -> dict[str, Any]:
    root = settings.readiness_release_root.resolve()
    path = settings.readiness_manifest_path
    manifest_path = (path if path.is_absolute() else root / path).resolve()
    display_path = str(path)
    if not manifest_path.is_relative_to(root) or not manifest_path.is_file():
        return {
            "status": "UNAVAILABLE",
            "path": display_path,
            "sha256": "UNAVAILABLE",
            "schema_version": "UNAVAILABLE",
            "artifacts": [],
        }
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = payload["required_artifacts"]
        if payload.get("schema_version") != "w2.readiness.manifest.v1":
            raise ValueError("unsupported readiness manifest schema")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("required_artifacts must be a non-empty list")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {
            "status": "INVALID",
            "path": display_path,
            "sha256": file_sha256(manifest_path),
            "schema_version": "UNAVAILABLE",
            "artifacts": [],
        }

    evidence: list[dict[str, Any]] = []
    valid = True
    for item in artifacts:
        if not isinstance(item, dict):
            valid = False
            continue
        relative = Path(str(item.get("path") or ""))
        candidate = (root / relative).resolve()
        expected = str(item.get("sha256") or "")
        actual = (
            file_sha256(candidate)
            if candidate.is_relative_to(root) and candidate.is_file()
            else None
        )
        status = "MATCH" if actual == expected and len(expected) == 64 else "MISMATCH"
        required = item.get("required", True) is True
        if required and status != "MATCH":
            valid = False
        evidence.append(
            {
                "path": str(relative),
                "required": required,
                "status": status,
                "expected_sha256": expected or "UNAVAILABLE",
                "actual_sha256": actual or "UNAVAILABLE",
            }
        )
    return {
        "status": "VALID" if valid else "INVALID",
        "path": display_path,
        "sha256": file_sha256(manifest_path),
        "schema_version": str(payload["schema_version"]),
        "artifacts": evidence,
    }


def build_release_identity(settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or get_settings()
    local_git_sha = _env_identity("W2_GIT_SHA", pattern=GIT_SHA)
    release_id = _env_identity("W2_RELEASE_ID")
    return {
        "schema_version": "w2.release-identity.v1",
        "local_git_sha": local_git_sha,
        "release_id": release_id,
        "image": {
            "image_id": _env_identity("W2_IMAGE_ID", pattern=SHA256_DIGEST),
            "oci_digest": _env_identity("W2_OCI_DIGEST", pattern=SHA256_DIGEST),
            "registry_digest": _env_identity(
                "W2_REGISTRY_DIGEST", pattern=SHA256_DIGEST
            ),
        },
        "alembic": _alembic_identity(resolved),
        "readiness_manifest": _readiness_manifest_identity(resolved),
    }


class GateEvidence(BaseModel):
    name: str = Field(min_length=1)
    result: Literal["PASS", "FAIL", "NOT_APPLICABLE"]
    evidence_path: str = Field(min_length=1)
    checked_at: datetime
    evidence_sha256: str


class ReleaseGateManifest(BaseModel):
    schema_version: Literal["w2.release-gate-manifest.v1"] = (
        "w2.release-gate-manifest.v1"
    )
    generated_at: datetime
    overall_result: Literal["PASS", "FAIL"]
    release_identity: dict[str, Any]
    gates: list[GateEvidence] = Field(min_length=1)


def build_release_gate_manifest(
    gate_rows: list[dict[str, Any]],
    *,
    evidence_root: Path,
    settings: Settings | None = None,
    generated_at: datetime | None = None,
) -> ReleaseGateManifest:
    root = evidence_root.resolve()
    gates: list[GateEvidence] = []
    for row in gate_rows:
        evidence_path = Path(str(row.get("evidence_path") or ""))
        candidate = (root / evidence_path).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise ValueError(f"gate evidence is missing or outside evidence root: {evidence_path}")
        gates.append(
            GateEvidence(
                name=str(row.get("name") or ""),
                result=str(row.get("result") or "FAIL"),
                evidence_path=str(evidence_path),
                checked_at=row.get("checked_at"),
                evidence_sha256=file_sha256(candidate),
            )
        )
    return ReleaseGateManifest(
        generated_at=generated_at or datetime.now(UTC),
        overall_result="FAIL" if any(gate.result == "FAIL" for gate in gates) else "PASS",
        release_identity=build_release_identity(settings),
        gates=gates,
    )
