from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from w2.config import Settings
from w2.operations import release_evidence
from w2.operations.release_evidence import (
    build_release_gate_manifest,
    build_release_identity,
)


def _settings(tmp_path: Path) -> Settings:
    migrations = tmp_path / "migrations"
    versions = migrations / "versions"
    versions.mkdir(parents=True)
    (migrations / "env.py").write_text("", encoding="utf-8")
    (migrations / "script.py.mako").write_text("", encoding="utf-8")
    (versions / "0001_head.py").write_text(
        "revision = '0001_head'\ndown_revision = None\n",
        encoding="utf-8",
    )
    database = tmp_path / "identity.db"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("create table alembic_version (version_num varchar(64))"))
        connection.execute(text("insert into alembic_version values ('0001_head')"))
    engine.dispose()

    artifact = tmp_path / "config" / "artifact.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"ok":true}\n', encoding="utf-8")
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    readiness = tmp_path / "config" / "readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "schema_version": "w2.readiness.manifest.v1",
                "required_artifacts": [
                    {
                        "path": "config/artifact.json",
                        "sha256": artifact_hash,
                        "required": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return Settings(
        database_url=f"sqlite+pysqlite:///{database}",
        readiness_release_root=tmp_path,
        readiness_migrations_path=Path("migrations"),
        readiness_manifest_path=Path("config/readiness.json"),
    )


def test_release_identity_reports_exact_runtime_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("W2_GIT_SHA", "a" * 40)
    monkeypatch.setenv("W2_RELEASE_ID", "local-r1")
    monkeypatch.setenv("W2_IMAGE_ID", "sha256:" + "b" * 64)
    monkeypatch.setenv("W2_OCI_DIGEST", "api:latest")
    monkeypatch.delenv("W2_REGISTRY_DIGEST", raising=False)

    identity = build_release_identity(_settings(tmp_path))

    assert identity["local_git_sha"] == {"status": "AVAILABLE", "value": "a" * 40}
    assert identity["image"]["image_id"]["status"] == "AVAILABLE"
    assert identity["image"]["oci_digest"]["status"] == "INVALID"
    assert identity["image"]["registry_digest"] == {
        "status": "UNAVAILABLE",
        "value": "UNAVAILABLE",
    }
    assert identity["alembic"] == {
        "status": "MATCH",
        "current": "0001_head",
        "head": "0001_head",
    }
    assert identity["readiness_manifest"]["status"] == "VALID"
    assert identity["readiness_manifest"]["artifacts"][0]["status"] == "MATCH"


def test_release_gate_manifest_hashes_evidence_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "pytest.txt"
    evidence.write_text("1137 passed\n", encoding="utf-8")
    monkeypatch.setattr(
        release_evidence,
        "build_release_identity",
        lambda _settings=None: {"schema_version": "test"},
    )
    checked_at = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)

    manifest = build_release_gate_manifest(
        [
            {
                "name": "pytest",
                "result": "PASS",
                "evidence_path": "pytest.txt",
                "checked_at": checked_at,
            },
            {
                "name": "canary",
                "result": "FAIL",
                "evidence_path": "pytest.txt",
                "checked_at": checked_at,
            },
        ],
        evidence_root=tmp_path,
        generated_at=checked_at,
    )

    assert manifest.overall_result == "FAIL"
    assert manifest.gates[0].evidence_sha256 == hashlib.sha256(evidence.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="missing or outside"):
        build_release_gate_manifest(
            [
                {
                    "name": "escape",
                    "result": "PASS",
                    "evidence_path": "../outside.txt",
                    "checked_at": checked_at,
                }
            ],
            evidence_root=tmp_path,
        )


def test_staging_deploy_captures_real_image_id_without_faking_digest() -> None:
    script = Path("scripts/deploy_stage7h_staging.sh").read_text(encoding="utf-8")

    assert "docker image inspect --format='{{.Id}}' w2-staging-api:latest" in script
    assert "images -q api" not in script
    assert r"rollback-\${ROLLBACK_REVISION}" in script
    assert "docker image tag" in script
    assert "rollback images preserved" in script
    assert "W2_API_IMAGE_ID=" in script
    assert "W2_API_OCI_DIGEST=" not in script
    assert "W2_API_REGISTRY_DIGEST=" not in script
