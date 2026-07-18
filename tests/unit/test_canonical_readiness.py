from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import SecretStr

from w2.config import Environment, Settings
from w2.monitoring.readiness import _artifact_manifest_check, build_readiness_payload


def _settings(tmp_path: Path, *, environment: Environment = Environment.TEST) -> Settings:
    (tmp_path / "runtime").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "migrations").mkdir()
    return Settings(
        environment=environment,
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        redis_url=SecretStr("redis://127.0.0.1:1/0"),
        readiness_release_root=tmp_path,
    )


def _pass(_: Settings) -> tuple[bool, str]:
    return True, "passed"


def _artifact_pass(_: Settings) -> tuple[bool, str, list[str]]:
    return True, "passed", []


@pytest.mark.parametrize("failed", ["database", "redis", "schema", "mounts", "artifacts"])
def test_each_critical_failure_is_deterministically_not_ready(
    tmp_path: Path,
    failed: str,
) -> None:
    def fail(_: Settings) -> tuple[bool, str]:
        return False, f"{failed} failed"

    checks: dict[str, Callable[[Settings], tuple[bool, str]]] = {
        name: fail if name == failed else _pass
        for name in ("database", "redis", "schema", "mounts")
    }

    def artifacts(_: Settings) -> tuple[bool, str, list[str]]:
        return (False, "artifacts failed", []) if failed == "artifacts" else _artifact_pass(_)

    payload = build_readiness_payload(
        _settings(tmp_path),
        database_check=checks["database"],
        redis_check=checks["redis"],
        schema_check=checks["schema"],
        mounts_check=checks["mounts"],
        artifact_check=artifacts,
    )
    assert payload.status == "NOT_READY"
    assert payload.checks[failed].status == "FAIL"


def test_all_critical_checks_recover_to_ready(tmp_path: Path) -> None:
    payload = build_readiness_payload(
        _settings(tmp_path),
        database_check=_pass,
        redis_check=_pass,
        schema_check=_pass,
        mounts_check=_pass,
        artifact_check=_artifact_pass,
    )
    assert payload.status == "READY"
    assert all(check.status == "PASS" for check in payload.checks.values())


def test_staging_artifact_manifest_checks_path_and_sha256(tmp_path: Path) -> None:
    settings = _settings(tmp_path, environment=Environment.STAGING)
    artifact = tmp_path / "config" / "required.json"
    artifact.write_text('{"ready":true}\n', encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_dir = tmp_path / "config" / "readiness"
    manifest_dir.mkdir()
    manifest = {
        "schema_version": "w2.readiness.manifest.v1",
        "required_artifacts": [
            {"path": "config/required.json", "sha256": digest, "required": True}
        ],
    }
    (manifest_dir / "staging.v1.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert _artifact_manifest_check(settings)[0] is True
    artifact.write_text('{"ready":false}\n', encoding="utf-8")
    passed, detail, _ = _artifact_manifest_check(settings)
    assert passed is False
    assert detail == "1 required artifact checks failed"


def test_committed_staging_manifest_is_valid() -> None:
    root = Path(__file__).resolve().parents[2]
    settings = Settings(
        environment=Environment.STAGING,
        readiness_release_root=root,
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
    )
    passed, detail, warnings = _artifact_manifest_check(settings)
    assert passed, detail
    assert warnings == []
