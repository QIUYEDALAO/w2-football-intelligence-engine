from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from scripts.preflight_runtime_writable import check_runtime_writable

TARGET_UID = 10001
TARGET_GID = 10001


def docker_available() -> bool:
    return shutil.which("docker") is not None


def docker_run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        text=True,
        capture_output=True,
    )


def prepare_runtime_dir(
    tmp_path: Path,
    *,
    name: str,
    owner: str,
    mode: str,
) -> Path:
    if not docker_available():
        pytest.skip("docker is required to prepare staging-parity uid/gid fixtures")
    runtime = tmp_path / name
    docker_run(
        [
            "run",
            "--rm",
            "-v",
            f"{tmp_path}:/host",
            "python:3.12-alpine",
            "sh",
            "-c",
            f"mkdir -p /host/{name} && chown {owner} /host/{name} && chmod {mode} /host/{name}",
        ]
    )
    return runtime


def stat_snapshot(path: Path) -> tuple[int, int, int, int]:
    info = path.stat()
    return (info.st_ino, info.st_uid, info.st_gid, info.st_mode)


def assert_preflight_has_no_side_effect(path: Path, result: Any) -> None:
    before = stat_snapshot(path)
    assert result.passed in (True, False)
    after = stat_snapshot(path)
    assert after == before


def test_preflight_fails_root_0700_runtime_for_worker_uid(tmp_path: Path) -> None:
    runtime = prepare_runtime_dir(tmp_path, name="root-runtime", owner="0:0", mode="0700")
    result = check_runtime_writable(runtime, uid=TARGET_UID, gid=TARGET_GID)

    assert result.passed is False
    assert result.reason == "TARGET_UID_GID_CANNOT_WRITE"
    assert result.owner_uid == 0
    assert result.owner_gid == 0
    assert result.mode == 0o700
    assert_preflight_has_no_side_effect(runtime, result)


def test_preflight_passes_worker_owned_0750_runtime(tmp_path: Path) -> None:
    runtime = prepare_runtime_dir(
        tmp_path,
        name="worker-runtime",
        owner=f"{TARGET_UID}:{TARGET_GID}",
        mode="0750",
    )
    result = check_runtime_writable(runtime, uid=TARGET_UID, gid=TARGET_GID)

    assert result.passed is True
    assert result.reason == "TARGET_UID_GID_CAN_WRITE"
    assert result.owner_uid == TARGET_UID
    assert result.owner_gid == TARGET_GID
    assert result.mode == 0o750
    assert_preflight_has_no_side_effect(runtime, result)


def test_worker_uid_container_healthcheck_reproduces_unwritable_runtime(tmp_path: Path) -> None:
    runtime = prepare_runtime_dir(tmp_path, name="runtime", owner="0:0", mode="0700")

    result = docker_run(
        [
            "run",
            "--rm",
            "--user",
            f"{TARGET_UID}:{TARGET_GID}",
            "-v",
            f"{runtime}:/app/runtime",
            "python:3.12-alpine",
            "python",
            "-c",
            "import os; print(os.access('/app/runtime', os.W_OK))",
        ],
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "False"
    assert os.access(runtime, os.W_OK) in (True, False)
