from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "ops" / "host" / "w2-release"

FAKE_ONLINE = "f" * 40  # 40 字符假 sha（!= 任何真实 commit）


def _bash(expr: str, *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", expr], cwd=cwd, env=env, capture_output=True, text=True)


def _source_call(func_expr: str) -> subprocess.CompletedProcess[str]:
    """source 脚本后调用纯函数，返回码即函数返回值。"""
    return _bash(f'source "{SCRIPT}"; {func_expr}')


# ─────────────────────────────────────────────────────────────────────────────
# 测试 1：禁止时段判断
# ─────────────────────────────────────────────────────────────────────────────
def test_blocked_window_inside() -> None:
    assert _source_call("in_blocked_window '2026-09-18T15:00:00Z' '13:00-19:30'").returncode == 0


def test_blocked_window_outside() -> None:
    assert _source_call("in_blocked_window '2026-09-18T10:00:00Z' '13:00-19:30'").returncode == 1


def test_blocked_window_start_inclusive() -> None:
    assert _source_call("in_blocked_window '2026-09-18T13:00:00Z' '13:00-19:30'").returncode == 0


def test_blocked_window_end_exclusive() -> None:
    assert _source_call("in_blocked_window '2026-09-18T19:30:00Z' '13:00-19:30'").returncode == 1


# ─────────────────────────────────────────────────────────────────────────────
# 测试 2：迁移检测（有/无）
# ─────────────────────────────────────────────────────────────────────────────
def _make_repo(tmp_path: Path, with_migration: bool) -> tuple[Path, str, str]:
    repo = tmp_path / ("mig" if with_migration else "nomig")
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "main"], check=True)
    (repo / "readme.txt").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    if with_migration:
        (repo / "migrations").mkdir()
        (repo / "migrations" / "x.py").write_text("x", encoding="utf-8")
    else:
        (repo / "src.txt").write_text("s", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "change"], check=True)
    target = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    return repo, base, target


def test_needs_backup_yes(tmp_path: Path) -> None:
    repo, base, target = _make_repo(tmp_path, with_migration=True)
    r = _bash(f'cd "{repo}"; source "{SCRIPT}"; needs_backup {base} {target}')
    assert r.returncode == 0
    assert r.stdout.strip() == "yes"


def test_needs_backup_no(tmp_path: Path) -> None:
    repo, base, target = _make_repo(tmp_path, with_migration=False)
    r = _bash(f'cd "{repo}"; source "{SCRIPT}"; needs_backup {base} {target}')
    assert r.returncode == 0
    assert r.stdout.strip() == "no"


# ─────────────────────────────────────────────────────────────────────────────
# 测试 3：回读某项失败时不推送、不轮转
# ─────────────────────────────────────────────────────────────────────────────
def _write_fake_ssh(tmp_path: Path, *, fail_readback: bool) -> tuple[Path, Path]:
    log = tmp_path / "ssh.log"
    fake = tmp_path / "fake-ssh"
    fake.write_text(
        f"""#!/usr/bin/env bash
echo "$*" >> "{log}"
host="$1"; shift
cmd="$*"
case "$cmd" in
  *"/v1/version"*)
    echo '{{"release_id":"{FAKE_ONLINE}","api_git_sha":"{FAKE_ONLINE}"}}'
    exit 0 ;;
  *"image inspect"*)
    echo "127.0.0.1:5000/w2/python@sha256:fake0000000000000000000000000000000000000000000000000000000000000000"
    exit 0 ;;
  *"bash -s"*)
    cat >/dev/null
    echo "READBACK_FAILED a"
    exit 1 ;;
  *)
    exit 0 ;;
esac
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake, log


def _write_fake_git(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "git.log"
    fake = tmp_path / "fake-git"
    real = shutil.which("git")
    assert real is not None
    fake.write_text(
        f"""#!/usr/bin/env bash
echo "$*" >> "{log}"
exec "{real}" "$@"
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake, log


def _write_fake_scp(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "scp.log"
    fake = tmp_path / "fake-scp"
    fake.write_text(
        f"""#!/usr/bin/env bash
echo "$*" >> "{log}"
exit 0
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake, log


def _write_fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "docker.log"
    fake = tmp_path / "fake-docker"
    fake.write_text(
        f"""#!/usr/bin/env bash
echo "$*" >> "{log}"
exit 0
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake, log


def _build_test_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    fake_ssh, ssh_log = _write_fake_ssh(tmp_path, fail_readback=True)
    fake_git, git_log = _write_fake_git(tmp_path)
    fake_scp, _scp_log = _write_fake_scp(tmp_path)
    fake_docker, _docker_log = _write_fake_docker(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **os.environ,
        "W2_RELEASE_SSH_CMD": str(fake_ssh),
        "W2_RELEASE_SCP_CMD": str(fake_scp),
        "W2_RELEASE_DOCKER_CMD": str(fake_docker),
        "W2_RELEASE_GIT": str(fake_git),
        "W2_RELEASE_BRANCH": "main",
        "W2_RELEASE_NOW": "2026-09-18T10:00:00Z",
        "HOME": str(home),
    }
    return env, home


def test_readback_fail_no_push_no_rotate(tmp_path: Path) -> None:
    repo, _base, target = _make_repo(tmp_path, with_migration=False)
    env, home = _build_test_env(tmp_path)
    r = subprocess.run(
        ["bash", str(SCRIPT), "--target", target], cwd=repo, env=env, capture_output=True, text=True
    )
    assert r.returncode == 1
    assert "不推送、不轮转" in r.stderr
    assert "READBACK_FAILED" in r.stdout
    # 不推送：fake git 记录里没有 push
    git_log = tmp_path / "git.log"
    git_calls = git_log.read_text(encoding="utf-8") if git_log.exists() else ""
    assert "push" not in git_calls
    # 不轮转：无回执（回执在推送/轮转之后）
    receipt_dir = home / "Desktop" / "W2文档"
    assert not receipt_dir.exists()


# ─────────────────────────────────────────────────────────────────────────────
# 测试 4：--dry-run 不产生副作用
# ─────────────────────────────────────────────────────────────────────────────
def test_dry_run_no_side_effects(tmp_path: Path) -> None:
    repo, _base, target = _make_repo(tmp_path, with_migration=False)
    fake_ssh, ssh_log = _write_fake_ssh(tmp_path, fail_readback=False)
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **os.environ,
        "W2_RELEASE_SSH_CMD": str(fake_ssh),
        "W2_RELEASE_BRANCH": "main",
        "W2_RELEASE_NOW": "2026-09-18T10:00:00Z",
        "HOME": str(home),
    }
    r = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--target", target], cwd=repo, env=env, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    assert "dry-run" in r.stdout
    # 不写回执
    receipt_dir = home / "Desktop" / "W2文档"
    assert not receipt_dir.exists()
    # fake ssh 只被调用一次（读线上 release），未触发构建/部署
    calls = ssh_log.read_text(encoding="utf-8").splitlines() if ssh_log.exists() else []
    assert len(calls) == 1
    assert "/v1/version" in calls[0]
