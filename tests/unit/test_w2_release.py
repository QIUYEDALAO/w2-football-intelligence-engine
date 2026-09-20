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
    (repo / "migrations" / "versions").mkdir(parents=True)
    (repo / "migrations" / "versions" / "a.py").write_text(
        'revision = "aaa"\ndown_revision = None\n', encoding="utf-8"
    )
    override = repo / "infra" / "compose" / "controlled-future-refresh.override.yml"
    override.parent.mkdir(parents=True)
    override.write_text(
        'services:\n  worker:\n    environment:\n      '
        'W2_POSTMATCH_RESULT_DAILY_HARD_CAP: "800"\n'
        '  scheduler:\n    environment:\n      '
        'W2_POSTMATCH_RESULT_DAILY_HARD_CAP: "800"\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    if with_migration:
        (repo / "migrations" / "versions" / "b.py").write_text(
            'revision = "bbb"\ndown_revision = "aaa"\n', encoding="utf-8"
        )
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
def _deploy_body(mode: str, target: str) -> str:
    """模拟 VPS 端 heredoc 在 `bash -s` 分支的输出（不同失败/成功模式）。"""
    if mode == "readback_fail":
        return 'cat >/dev/null\necho "READBACK_FAILED a"\nexit 1'
    if mode == "early_exit_0":
        return "cat >/dev/null\nexit 0"
    if mode == "missing_readback":
        lines = ['cat >/dev/null', 'echo "SWITCH_OK backup=/opt/w2/shared/release.pre-x.env"']
        for k in "abcdefg":
            lines.append(f'echo "READBACK {k}=PASS"')
        lines.append(f'echo "DEPLOY_COMPLETE {target}"')
        lines.append("exit 0")
        return "\n".join(lines)
    if mode == "full_success":
        lines = ['cat >/dev/null', 'echo "SWITCH_OK backup=/opt/w2/shared/release.pre-x.env"']
        for k in "abcdefgh":
            lines.append(f'echo "READBACK {k}=PASS"')
        lines.append(f'echo "DEPLOY_COMPLETE {target}"')
        lines.append("exit 0")
        return "\n".join(lines)
    raise ValueError(f"unknown mode: {mode}")


def _write_fake_ssh(
    tmp_path: Path, *, mode: str, target: str = FAKE_ONLINE, window_fail: bool = False
) -> tuple[Path, Path]:
    log = tmp_path / "ssh.log"
    fake = tmp_path / "fake-ssh"
    window_exit = "exit 1" if window_fail else "exit 0"
    fake.write_text(
        f"""#!/usr/bin/env bash
echo "$*" >> "{log}"
host="$1"; shift
cmd="$*"
case "$cmd" in
  *"/v1/version"*)
    echo '{{"release_id":"{FAKE_ONLINE}","api_git_sha":"{FAKE_ONLINE}"}}'
    exit 0 ;;
  *"matchday_checkpoint_plans"*)
    {window_exit} ;;
  *"image inspect"*)
    echo "127.0.0.1:5000/w2/python@sha256:fake0000000000000000000000000000000000000000000000000000000000000000"
    exit 0 ;;
  *"bash -s"*)
{_deploy_body(mode, target)}
    ;;
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
case "$2" in
  *:/tmp/w2-controlled-future-refresh-*.override.yml)
    cp "$1" "${{2#*:}}" ;;
esac
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


def _build_test_env(
    tmp_path: Path, *, mode: str, target: str = FAKE_ONLINE, window_fail: bool = False
) -> tuple[dict[str, str], Path]:
    fake_ssh, ssh_log = _write_fake_ssh(tmp_path, mode=mode, target=target, window_fail=window_fail)
    fake_git, git_log = _write_fake_git(tmp_path)
    fake_scp, _scp_log = _write_fake_scp(tmp_path)
    fake_docker, _docker_log = _write_fake_docker(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    (home / "Desktop" / "W2文档" / "backups").mkdir(parents=True)
    env = {
        **os.environ,
        "W2_RELEASE_SSH_CMD": str(fake_ssh),
        "W2_RELEASE_SCP_CMD": str(fake_scp),
        "W2_RELEASE_DOCKER_CMD": str(fake_docker),
        "W2_RELEASE_GIT": str(fake_git),
        "W2_RELEASE_BRANCH": "main",
        "W2_RELEASE_NOW": "2026-09-18T10:00:00Z",
        "W2_RELEASE_GATE_MAX_WAIT_SEC": "2",
        "W2_RELEASE_GATE_POLL_SEC": "1",
        "HOME": str(home),
    }
    return env, home


def test_readback_fail_no_push_no_rotate(tmp_path: Path) -> None:
    repo, _base, target = _make_repo(tmp_path, with_migration=False)
    env, home = _build_test_env(tmp_path, mode="readback_fail", target=target)
    r = subprocess.run(
        ["bash", str(SCRIPT), "--target", target], cwd=repo, env=env, capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 1
    assert "READBACK_FAILED" in r.stdout
    # 不推送：fake git 记录里没有 push
    git_log = tmp_path / "git.log"
    git_calls = git_log.read_text(encoding="utf-8") if git_log.exists() else ""
    assert "push" not in git_calls
    # 失败也写回执，且首行是「结果：失败」
    receipt_dir = home / "Desktop" / "W2文档"
    receipts = list(receipt_dir.glob("W2_发布_*.md"))
    assert receipts
    assert any("结果：失败" in l for l in receipts[0].read_text(encoding="utf-8").splitlines())


# ─────────────────────────────────────────────────────────────────────────────
# 测试 4：--dry-run 不产生副作用
# ─────────────────────────────────────────────────────────────────────────────
def test_dry_run_no_side_effects(tmp_path: Path) -> None:
    repo, _base, target = _make_repo(tmp_path, with_migration=False)
    fake_ssh, ssh_log = _write_fake_ssh(tmp_path, mode="full_success", target=target)
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
        ["bash", str(SCRIPT), "--dry-run", "--target", target], cwd=repo, env=env, capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 0, r.stderr
    assert "dry-run" in r.stdout
    # 不写回执
    receipt_dir = home / "Desktop" / "W2文档"
    assert not receipt_dir.exists()
    # fake ssh 只读线上 release + 评估档位查询，未触发构建/部署（无 bash -s）
    calls = ssh_log.read_text(encoding="utf-8").splitlines() if ssh_log.exists() else []
    assert any("/v1/version" in c for c in calls)
    assert not any("bash -s" in c for c in calls)


# ─────────────────────────────────────────────────────────────────────────────
# REL-01B 新增：评估档位窗口判断
# ─────────────────────────────────────────────────────────────────────────────
def test_checkpoint_window_conflict_inside_future() -> None:
    # 档位在 now+10min（未来 15min 内）→ 冲突
    r = _source_call("checkpoint_window_conflict '2026-09-18T10:00:00Z' '2026-09-18T10:10:00Z'")
    assert r.stdout.startswith("1 ")


def test_checkpoint_window_conflict_inside_past() -> None:
    # 档位在 now-3min（过去 5min 内）→ 冲突
    r = _source_call("checkpoint_window_conflict '2026-09-18T10:00:00Z' '2026-09-18T09:57:00Z'")
    assert r.stdout.startswith("1 ")


def test_checkpoint_window_conflict_outside_future() -> None:
    # 档位在 now+30min（未来 15min 之外）→ 不冲突
    r = _source_call("checkpoint_window_conflict '2026-09-18T10:00:00Z' '2026-09-18T10:30:00Z'")
    assert r.stdout.strip() == "0"


def test_checkpoint_window_conflict_outside_past() -> None:
    # 档位在 now-10min（过去 5min 之外）→ 不冲突
    r = _source_call("checkpoint_window_conflict '2026-09-18T10:00:00Z' '2026-09-18T09:50:00Z'")
    assert r.stdout.strip() == "0"


# ─────────────────────────────────────────────────────────────────────────────
# REL-01B 新增：schema 版本动态读取
# ─────────────────────────────────────────────────────────────────────────────
def test_migration_heads_from_dir(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "a.py").write_text('revision = "aaa"\ndown_revision = None\n', encoding="utf-8")
    (versions / "b.py").write_text('revision = "bbb"\ndown_revision = "aaa"\n', encoding="utf-8")
    r = _source_call(f"migration_heads_from_dir '{versions}'")
    assert r.stdout.strip() == "bbb"


# ─────────────────────────────────────────────────────────────────────────────
# REL-01B 新增：VPS 段回滚与迁移（提取 heredoc 在 fake 环境执行）
# ─────────────────────────────────────────────────────────────────────────────
def _extract_vps_script() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("<<'VPS_SCRIPT'") + len("<<'VPS_SCRIPT'")
    start = text.index("\n", start) + 1
    end = text.index("\nVPS_SCRIPT\n", start)
    return text[start:end]


def _write_fake_vps_bin(tmp_path: Path, install_log: Path, *, online: str, fail_ready: bool, fail_migration: bool) -> Path:
    bin_dir = tmp_path / "vps-bin"
    bin_dir.mkdir()

    (bin_dir / "install").write_text(
        f"""#!/usr/bin/env bash
echo "$*" >> "{install_log}"
exec /usr/bin/install "$@"
""",
        encoding="utf-8",
    )
    (bin_dir / "docker").write_text(
        f"""#!/usr/bin/env bash
case "$1" in
  compose) exit 0 ;;
  inspect)
    fmt=""
    prev=""
    for a in "$@"; do
      if [ "$prev" = "--format" ]; then fmt="$a"; fi
      prev="$a"
    done
    case "$fmt" in
      *StartedAt*) echo "2026-09-18T00:00:00.000000000Z" ;;
      *Health.Status*) echo "healthy" ;;
      *RepoDigests*) echo "127.0.0.1:5000/w2/python@sha256:fake0000000000000000000000000000000000000000000000000000000000000000" ;;
      *) echo "healthy" ;;
    esac
    exit 0 ;;
  run)
    if [ "{'1' if fail_migration else '0'}" = "1" ]; then exit 1; else exit 0; fi ;;
  exec)
    sql=""
    prev=""
    for a in "$@"; do
      if [ "$prev" = "-c" ]; then sql="$a"; break; fi
      prev="$a"
    done
    case "$sql" in
      *"matchday_checkpoint_plans WHERE status"*) echo "0" ;;
      *"matchday_checkpoint_plans WHERE checkpoint IN"*) ;;  # 切换前档位复查：返回空（无冲突）
      *"candidate_notification_outbox"*) echo "${{SCHEMA}}|0|0" ;;
      "SELECT version_num FROM alembic_version") echo "${{SCHEMA}}" ;;
      *) echo "0" ;;
    esac
    exit 0 ;;
  logs) exit 0 ;;
  *) exit 0 ;;
esac
""",
        encoding="utf-8",
    )
    (bin_dir / "curl").write_text(
        f"""#!/usr/bin/env bash
url=""
for a in "$@"; do
  case "$a" in
    http*) url="$a" ;;
  esac
done
case "$url" in
  */ready)
    if [ "{'1' if fail_ready else '0'}" = "1" ]; then exit 1; else echo '{{}}'; fi ;;
  */v1/version) echo '{{"release_id":"{online}","api_git_sha":"{online}"}}' ;;
  *) echo '{{}}' ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "preflight").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (bin_dir / "sync-preflight").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (bin_dir / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    # macOS sed 的 -i 需要参数；把 VPS 脚本里 GNU 风格的 `sed -i -e` 转成 `sed -i '' -e`
    (bin_dir / "sed").write_text(
        """#!/usr/bin/env bash
if [ "$1" = "-i" ] && [ "$2" = "-e" ]; then
  shift
  exec /usr/bin/sed -i '' "$@"
fi
exec /usr/bin/sed "$@"
""",
        encoding="utf-8",
    )
    for f in ("install", "docker", "curl", "preflight", "sync-preflight", "sed", "sleep"):
        (bin_dir / f).chmod(0o755)
    return bin_dir


def _write_fake_ssh_run_heredoc(tmp_path: Path, vps_bin: Path, *, online: str) -> tuple[Path, Path]:
    vps_script_file = tmp_path / "vps-script.sh"
    opt_w2 = tmp_path / "opt-w2"
    fake = tmp_path / "fake-ssh-run"
    fake.write_text(
        f"""#!/usr/bin/env bash
host="$1"; shift
cmd="$*"
if echo "$cmd" | grep -q "/v1/version"; then
  echo '{{"release_id":"{online}","api_git_sha":"{online}"}}'
  exit 0
fi
if echo "$cmd" | grep -q "bash -s"; then
  args="${{cmd#*-- }}"
  eval "set -- $args"
  mkdir -p "{opt_w2}/shared" "{opt_w2}/deploy"
  echo old-override > "{opt_w2}/deploy/controlled-future-refresh.override.yml"
  cat > "{opt_w2}/shared/release.env" <<'ENVEOF'
W2_PYTHON_IMAGE=old
W2_WEB_IMAGE=old
W2_GIT_SHA=old
W2_BUILD_TIME=old
W2_RELEASE_ID=old
W2_API_IMAGE_ID=old
W2_API_OCI_DIGEST=old
W2_API_REGISTRY_DIGEST=old
ENVEOF
  # 模拟真实 ssh：stdin（heredoc）直接经 sed 管道传给 bash -s
  sed -e "s|/usr/local/bin/w2-release-preflight|{vps_bin}/preflight|g; s|/opt/w2/deploy/w2-release-sync-preflight|{vps_bin}/sync-preflight|g; s|/opt/w2|{opt_w2}|g" | PATH="{vps_bin}:$PATH" bash -s -- "$@"
  exit $?
fi
if echo "$cmd" | grep -q "image inspect"; then
  echo "127.0.0.1:5000/w2/python@sha256:fake0000000000000000000000000000000000000000000000000000000000000000"
  exit 0
fi
if echo "$cmd" | grep -q "stat -c %s"; then
  echo "12345"
  exit 0
fi
if echo "$cmd" | grep -q "pg_restore --list"; then
  echo "archive-header"
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake, vps_script_file


def _run_release_with_vps(tmp_path: Path, *, with_migration: bool, fail_ready: bool, fail_migration: bool) -> tuple[subprocess.CompletedProcess[str], Path]:
    repo, base, target = _make_repo(tmp_path, with_migration=with_migration)
    install_log = tmp_path / "install.log"
    vps_bin = _write_fake_vps_bin(tmp_path, install_log, online=base, fail_ready=fail_ready, fail_migration=fail_migration)
    fake_ssh, _vps_file = _write_fake_ssh_run_heredoc(tmp_path, vps_bin, online=base)
    fake_git, _git_log = _write_fake_git(tmp_path)
    fake_scp, _scp_log = _write_fake_scp(tmp_path)
    fake_docker, _docker_log = _write_fake_docker(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    (home / "Desktop" / "W2文档" / "backups").mkdir(parents=True)
    env = {
        **os.environ,
        "W2_RELEASE_SSH_CMD": str(fake_ssh),
        "W2_RELEASE_SCP_CMD": str(fake_scp),
        "W2_RELEASE_DOCKER_CMD": str(fake_docker),
        "W2_RELEASE_GIT": str(fake_git),
        "W2_RELEASE_BRANCH": "main",
        "W2_RELEASE_NOW": "2026-09-18T10:00:00Z",
        "W2_RELEASE_STABILIZE_SEC": "0",
        "W2_RELEASE_GATE_MAX_WAIT_SEC": "2",
        "W2_RELEASE_GATE_POLL_SEC": "1",
        "HOME": str(home),
        "SCHEMA": "aaa",
    }
    r = subprocess.run(
        ["bash", str(SCRIPT), "--target", target], cwd=repo, env=env, capture_output=True, text=True, timeout=120
    )
    return r, install_log


def test_api_ready_timeout_rolls_back_release_env(tmp_path: Path) -> None:
    r, install_log = _run_release_with_vps(tmp_path, with_migration=False, fail_ready=True, fail_migration=False)
    assert r.returncode == 1
    assert "ROLLBACK" in r.stdout
    lines = install_log.read_text(encoding="utf-8").splitlines() if install_log.exists() else []
    # 切换：candidate -> release.env；回滚：backup -> release.env（恢复旧内容）
    assert any("release.candidate-" in l and "release.env" in l for l in lines)
    assert any("release.pre-" in l and "release.env" in l for l in lines)


def test_migration_fail_does_not_switch(tmp_path: Path) -> None:
    r, install_log = _run_release_with_vps(tmp_path, with_migration=True, fail_ready=False, fail_migration=True)
    assert r.returncode == 1
    assert "alembic upgrade head 失败" in r.stdout
    lines = install_log.read_text(encoding="utf-8").splitlines() if install_log.exists() else []
    # 迁移失败 → 不切换：install 日志里没有 candidate -> release.env
    assert not any("release.candidate-" in l and "release.env" in l for l in lines)


# ─────────────────────────────────────────────────────────────────────────────
# REL-01C 新增：正向成功标记判定（无 FAIL 即成功 → 必须看到全部成功标记）
# ─────────────────────────────────────────────────────────────────────────────
def _git_calls(tmp_path: Path) -> str:
    git_log = tmp_path / "git.log"
    return git_log.read_text(encoding="utf-8") if git_log.exists() else ""


def test_vps_early_exit_zero_judged_failed(tmp_path: Path) -> None:
    """VPS 端提前退出且返回 0（无任何成功标记）→ Mac 判失败、不推送。"""
    repo, _base, target = _make_repo(tmp_path, with_migration=False)
    env, home = _build_test_env(tmp_path, mode="early_exit_0", target=target)
    r = subprocess.run(
        ["bash", str(SCRIPT), "--target", target], cwd=repo, env=env, capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 1
    assert "正向成功标记缺失" in r.stderr
    assert "DEPLOY_COMPLETE" in r.stderr
    assert "push" not in _git_calls(tmp_path)
    receipt_dir = home / "Desktop" / "W2文档"
    receipts = list(receipt_dir.glob("W2_发布_*.md"))
    assert receipts
    assert any("结果：失败" in l for l in receipts[0].read_text(encoding="utf-8").splitlines())


def test_missing_readback_marker_judged_failed(tmp_path: Path) -> None:
    """缺任一 READBACK 行（缺 h）→ Mac 判失败、不推送。"""
    repo, _base, target = _make_repo(tmp_path, with_migration=False)
    env, home = _build_test_env(tmp_path, mode="missing_readback", target=target)
    r = subprocess.run(
        ["bash", str(SCRIPT), "--target", target], cwd=repo, env=env, capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 1
    assert "READBACK_h" in r.stderr
    assert "push" not in _git_calls(tmp_path)


def test_verify_release_id_mismatch_judged_failed(tmp_path: Path) -> None:
    """VPS 端输出完整成功标记，但推送前独立回读 /v1/version 与目标不符 → 判失败、不推送。"""
    repo, _base, target = _make_repo(tmp_path, with_migration=False)
    env, home = _build_test_env(tmp_path, mode="full_success", target=target)
    r = subprocess.run(
        ["bash", str(SCRIPT), "--target", target], cwd=repo, env=env, capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 1
    assert "release_id 与目标不符" in r.stderr
    assert "push" not in _git_calls(tmp_path)
    receipt_dir = home / "Desktop" / "W2文档"
    receipts = list(receipt_dir.glob("W2_发布_*.md"))
    assert receipts
    assert any("结果：失败" in l for l in receipts[0].read_text(encoding="utf-8").splitlines())


def test_window_query_fail_rejects_deploy(tmp_path: Path) -> None:
    """评估档位窗口查询失败 → 拒绝部署（fail-closed，不 fail-open）。"""
    repo, _base, target = _make_repo(tmp_path, with_migration=False)
    env, home = _build_test_env(tmp_path, mode="early_exit_0", target=target, window_fail=True)
    r = subprocess.run(
        ["bash", str(SCRIPT), "--target", target], cwd=repo, env=env, capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 2
    assert "窗口查询失败" in r.stderr
    assert "push" not in _git_calls(tmp_path)
    # 未进入部署：fake ssh 无 bash -s 调用
    ssh_log = tmp_path / "ssh.log"
    calls = ssh_log.read_text(encoding="utf-8").splitlines() if ssh_log.exists() else []
    assert not any("bash -s" in c for c in calls)


def test_release_syncs_override_and_verifies_sha_before_activation() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    sync = text.index("== sync controlled future refresh override ==")
    activate = text.index("== activate release.env ==")

    assert sync < activate
    assert 'git" show' not in text  # guard against an accidental malformed invocation
    assert 'show "${TARGET}:infra/compose/controlled-future-refresh.override.yml"' in text
    assert "override_before_sha" in text
    assert "override_after_sha" in text
    assert 'OVERRIDE_SYNC before_sha=$override_before_sha repo_sha=$override_repo_sha after_sha=$override_after_sha' in text


def test_readback_e_polls_health_before_started_at_and_checks_cap_800() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    section = text.split("# e. 最长 180 秒", 1)[1].split("# f.", 1)[0]

    assert "health_deadline=$(( $(date +%s) + 180 ))" in section
    assert "sleep 5" in section
    assert section.index('Health.Status') < section.index('st="$(docker inspect')
    assert 'printenv W2_POSTMATCH_RESULT_DAILY_HARD_CAP' in section
    assert '[ "$cap" = "800" ]' in section


def test_readback_h_requires_progress_not_zero() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    section = text.split("# h. 最长 10 分钟", 1)[1].split('echo "== 回读汇总 =="', 1)[0]

    assert 'overdue_due_n0" != "0"' in section
    assert '"$h_n1" -lt "$overdue_due_n0"' in section
    assert '"$h_n1" = "0"' not in section
    assert 'deploy_done_epoch + drain_max_wait_sec' in section
    assert "drain_max_wait_sec" in section
