from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "ops" / "host" / "w2-retention"

CURRENT = "cccccccccccccccccccccccccccccccccccccccc"
PREV1 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
PREV2 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OLD = "0000000000000000000000000000000000000000"


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _build_env(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    shared = tmp_path / "shared"
    builds = tmp_path / "builds"
    reports = tmp_path / "reports"
    tmp = tmp_path / "tmp"
    backups = tmp_path / "backups"
    for d in (shared, builds, reports, tmp, backups):
        d.mkdir(parents=True, exist_ok=True)

    _write(shared / "release.env", f"W2_RELEASE_ID={CURRENT}\n")
    prev1_file = shared / f"release.pre-{PREV1}-20260917T100000Z.env"
    prev2_file = shared / f"release.pre-{PREV2}-20260917T090000Z.env"
    old_file = shared / f"release.pre-{OLD}-20260916T080000Z.env"
    _write(prev1_file, f"W2_RELEASE_ID={PREV1}\n")
    _write(prev2_file, f"W2_RELEASE_ID={PREV2}\n")
    _write(old_file, f"W2_RELEASE_ID={OLD}\n")
    # 明确 mtime 顺序（ls -t 依据），避免同秒创建导致排序歧义
    base = 1_700_000_000
    os.utime(prev1_file, (base, base))
    os.utime(prev2_file, (base - 3600, base - 3600))
    os.utime(old_file, (base - 7200, base - 7200))

    for name in (CURRENT[:8], PREV1[:8], PREV2[:8], OLD[:8]):
        (builds / name).mkdir()

    backups_file = backups / "predeploy-keep.dump"
    _write(backups_file, "backup-bytes")

    fake_docker = tmp_path / "fake-docker"
    _write(
        fake_docker,
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = images ]; then\n"
        "cat <<'EOF'\n"
        f"127.0.0.1:5000/w2/python\t{CURRENT}\tip1\tsha256:a\t476MB\n"
        f"127.0.0.1:5000/w2/python\t{PREV1}\tip2\tsha256:b\t476MB\n"
        f"127.0.0.1:5000/w2/python\t{PREV2}\tip3\tsha256:c\t476MB\n"
        f"127.0.0.1:5000/w2/python\t{OLD}\tip4\tsha256:d\t476MB\n"
        "127.0.0.1:5000/w2/python\t728eaf57\tip5\tsha256:e\t480MB\n"
        "127.0.0.1:5000/w2/python\t728eaf57-regression\tip6\tsha256:f\t476MB\n"
        "127.0.0.1:5000/w2/web\t728eaf57-perf3\tip7\tsha256:10\t74MB\n"
        "EOF\n"
        "fi\n",
    )
    fake_docker.chmod(0o755)

    env = {
        **os.environ,
        "W2_RETENTION_RELEASE_ENV": str(shared / "release.env"),
        "W2_RETENTION_BUILDS_DIR": str(builds),
        "W2_RETENTION_REPORTS_DIR": str(reports),
        "W2_RETENTION_TMP_DIR": str(tmp),
        "W2_RETENTION_DOCKER_BIN": str(fake_docker),
    }
    return backups_file, env


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"],
        env=env,
        capture_output=True,
        text=True,
    )


def test_retention_keeps_current_plus_two_prev_builds(tmp_path: Path) -> None:
    _backups_file, env = _build_env(tmp_path)
    result = _run(env)

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert f"keep build dir: {CURRENT[:8]}" in out
    assert f"keep build dir: {PREV1[:8]}" in out
    assert f"keep build dir: {PREV2[:8]}" in out
    assert f"would delete build dir: {OLD[:8]}" in out


def test_retention_keeps_permanent_images(tmp_path: Path) -> None:
    _backups_file, env = _build_env(tmp_path)
    result = _run(env)

    assert result.returncode == 0, result.stderr
    out = result.stdout
    # 永久保留名单不受"前 2 版本"限制
    assert "keep image: 127.0.0.1:5000/w2/python:728eaf57" in out
    assert "keep image: 127.0.0.1:5000/w2/python:728eaf57-regression" in out
    assert "keep image: 127.0.0.1:5000/w2/web:728eaf57-perf3" in out
    # 超出前 2 版本的普通镜像被删除
    assert f"would rmi image: 127.0.0.1:5000/w2/python:{OLD}" in out


def test_retention_tmp_24h_rule(tmp_path: Path) -> None:
    _backups_file, env = _build_env(tmp_path)
    tmp = Path(env["W2_RETENTION_TMP_DIR"])

    old_file = tmp / "w2-build-old.tar.gz"
    new_file = tmp / "w2-build-new.tar.gz"
    _write(old_file, "old")
    _write(new_file, "new")
    # old_file mtime 设为 2 天前；new_file 保持现在
    two_days_ago = os.stat(old_file).st_mtime - 2 * 86400
    os.utime(old_file, (two_days_ago, two_days_ago))

    result = _run(env)

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert f"would delete tmp file: {old_file}" in out
    assert f"would delete tmp file: {new_file}" not in out


def test_retention_never_touches_backups(tmp_path: Path) -> None:
    backups_file, env = _build_env(tmp_path)
    result = _run(env)

    assert result.returncode == 0, result.stderr
    # backups 目录不被脚本触碰
    assert backups_file.exists()
    assert "backup-bytes" in backups_file.read_text(encoding="utf-8")
    assert "backups" not in result.stdout.replace("would delete", "")
