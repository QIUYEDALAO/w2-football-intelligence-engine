from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel
from sqlalchemy import text

from w2.config import Environment, Settings, get_settings
from w2.infrastructure.cache import create_redis
from w2.infrastructure.database import create_engine


class ReadinessCheck(BaseModel):
    status: Literal["PASS", "FAIL", "WARN"]
    critical: bool
    detail: str


class ReadinessPayload(BaseModel):
    service: str
    version: str
    environment: str
    status: Literal["READY", "NOT_READY"]
    checks: dict[str, ReadinessCheck]
    warnings: list[str]


CheckFunction = Callable[[Settings], tuple[bool, str]]


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _database_check(settings: Settings) -> tuple[bool, str]:
    try:
        engine = create_engine(settings)
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        engine.dispose()
    except Exception:
        return False, "database query failed"
    return True, "select 1 succeeded"


def _redis_check(settings: Settings) -> tuple[bool, str]:
    client = create_redis(settings)
    if client is None:
        return False, "redis is not configured"
    try:
        ready = bool(client.ping())
        client.close()
    except Exception:
        return False, "redis ping failed"
    return (True, "ping succeeded") if ready else (False, "redis ping returned false")


def _code_head(settings: Settings) -> str:
    root = settings.readiness_release_root
    migrations = _resolve(root, settings.readiness_migrations_path)
    config = Config()
    config.set_main_option("script_location", str(migrations))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError("code must have exactly one migration head")
    return heads[0]


def _schema_check(settings: Settings) -> tuple[bool, str]:
    try:
        code_head = _code_head(settings)
        engine = create_engine(settings)
        with engine.connect() as connection:
            database_head = connection.execute(text("select version_num from alembic_version"))
            database_head = database_head.scalar_one()
        engine.dispose()
    except Exception:
        return False, "schema revision check failed"
    if database_head != code_head:
        return False, "database revision does not match code head"
    return True, f"database revision matches {code_head}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_manifest_check(settings: Settings) -> tuple[bool, str, list[str]]:
    if settings.environment != Environment.STAGING:
        return True, "manifest is required only in staging", []
    root = settings.readiness_release_root.resolve()
    manifest_path = _resolve(root, settings.readiness_manifest_path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = payload["required_artifacts"]
        if payload.get("schema_version") != "w2.readiness.manifest.v1":
            raise ValueError("unsupported manifest schema")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("required_artifacts must be a non-empty list")
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError):
        return False, "readiness manifest is missing or invalid", []

    warnings: list[str] = []
    required_failures = 0
    checked = 0
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            required_failures += 1
            continue
        relative = Path(str(artifact.get("path", "")))
        expected = str(artifact.get("sha256", ""))
        required = artifact.get("required", True) is True
        candidate = _resolve(root, relative).resolve()
        valid_path = candidate.is_relative_to(root)
        matches = (
            valid_path
            and candidate.is_file()
            and len(expected) == 64
            and _sha256(candidate) == expected
        )
        checked += 1
        if matches:
            continue
        if required:
            required_failures += 1
        else:
            warnings.append(f"optional artifact unavailable: {relative}")
    if required_failures:
        return False, f"{required_failures} required artifact checks failed", warnings
    return True, f"{checked} artifact hashes verified", warnings


def _mounts_check(settings: Settings) -> tuple[bool, str]:
    root = settings.readiness_release_root
    paths = (
        _resolve(root, settings.readiness_runtime_path),
        _resolve(root, settings.readiness_config_path),
    )
    failed = [
        str(path)
        for path in paths
        if not path.is_dir() or not os.access(path, os.R_OK | os.X_OK)
    ]
    if failed:
        return False, "core runtime/config mount is unreadable"
    return True, "core runtime/config mounts are readable"


def build_readiness_payload(
    settings: Settings | None = None,
    *,
    database_check: CheckFunction = _database_check,
    redis_check: CheckFunction = _redis_check,
    schema_check: CheckFunction = _schema_check,
    mounts_check: CheckFunction = _mounts_check,
    artifact_check: Callable[[Settings], tuple[bool, str, list[str]]] = (
        _artifact_manifest_check
    ),
) -> ReadinessPayload:
    resolved = settings or get_settings()
    checks: dict[str, ReadinessCheck] = {}
    for name, check in (
        ("database", database_check),
        ("redis", redis_check),
        ("schema", schema_check),
        ("mounts", mounts_check),
    ):
        passed, detail = check(resolved)
        checks[name] = ReadinessCheck(
            status="PASS" if passed else "FAIL",
            critical=True,
            detail=detail,
        )
    artifacts_passed, artifacts_detail, warnings = artifact_check(resolved)
    checks["artifacts"] = ReadinessCheck(
        status="PASS" if artifacts_passed else "FAIL",
        critical=True,
        detail=artifacts_detail,
    )
    return ReadinessPayload(
        service=resolved.service_name,
        version=resolved.service_version,
        environment=resolved.environment.value,
        status="READY" if all(item.status != "FAIL" for item in checks.values()) else "NOT_READY",
        checks=checks,
        warnings=warnings,
    )
