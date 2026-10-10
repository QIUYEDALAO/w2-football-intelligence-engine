from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "ops" / "host" / "w2-update-xg-scripts"


def _bash(expr: str, *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", expr], cwd=cwd, capture_output=True, text=True)


def _biz_tree(repo: Path, commit: str) -> subprocess.CompletedProcess[str]:
    return _bash(f'source "{SCRIPT}"; biz_tree_of "{commit}"', cwd=repo)


def _make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    for d in ("src", "migrations", "config", "apps", "ops"):
        (repo / d).mkdir()
    for p in (
        "src/a.py",
        "migrations/m.py",
        "config/c.py",
        "apps/a.py",
        "ops/o.py",
    ):
        (repo / p).write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    return repo, base


def _commit(repo: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True)
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()


def test_biz_tree_pure_ops_release(tmp_path: Path) -> None:
    """纯运维变更（只改 ops）→ 业务 tree 一致（F3 闸门放行，与 w2-update-v3-monitor 同源）。"""
    repo, base = _make_repo(tmp_path)
    (repo / "ops" / "o.py").write_text("ops only\n", encoding="utf-8")
    ops_sha = _commit(repo, "ops only")

    base_tree = _biz_tree(repo, base)
    ops_tree = _biz_tree(repo, ops_sha)
    assert base_tree.returncode == 0
    assert ops_tree.returncode == 0
    assert base_tree.stdout.strip() == ops_tree.stdout.strip()


def test_biz_tree_biz_change_reject(tmp_path: Path) -> None:
    """业务变更（改 src）→ 业务 tree 不一致（F3 闸门拒绝）。"""
    repo, base = _make_repo(tmp_path)
    (repo / "src" / "a.py").write_text("src change\n", encoding="utf-8")
    src_sha = _commit(repo, "src change")

    base_tree = _biz_tree(repo, base)
    src_tree = _biz_tree(repo, src_sha)
    assert base_tree.returncode == 0
    assert src_tree.returncode == 0
    assert base_tree.stdout.strip() != src_tree.stdout.strip()


def test_biz_tree_rev_parse_fail_closed(tmp_path: Path) -> None:
    """rev-parse 失败（commit 不存在）→ 非零退出（fail-closed，拒绝）。"""
    repo, _base = _make_repo(tmp_path)
    missing = "deadbeef" * 5
    result = _biz_tree(repo, missing)
    assert result.returncode != 0


def test_sync_scope_is_explicit_whitelist() -> None:
    """E3：同步清单必须是显式白名单，恰好两项——防「顺手多同步一个」扩大影响面。"""
    result = _bash(f'source "{SCRIPT}"; printf "%s\\n" "${{XG_SYNC_SCRIPTS[@]}}"')
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [
        "w2-xg-materialize",
        "w2-xg-refresh",
        # G（指令书 G，2026-10-10）：补采守闸执行器也必须随发布同步。
        # 它原先不在白名单里 ⇒ 仓库修了执行器（零调用留痕 + 额度让位提前结束）也上不了机，
        # 只能手工 scp，属「文档说该同步、通道不管」的漂移源。
        "w2-xg-backfill-window",
    ]


def test_sync_script_has_no_side_effect_actions() -> None:
    """E3：同步脚本只做「传文件 + 校验」，不得含重启服务 / 起容器 / 发布 / pg 写入等手段。

    该通道在每次发布时自动运行，因此必须证明它不可能调用 Provider、重启容器或改库。
    """
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "systemctl",
        "docker",
        "alembic",
        "git push",
        "psql",
        "curl",
    ):
        assert forbidden not in source, f"同步脚本不应包含 {forbidden!r}"


def test_sync_rejects_invalid_inputs_fail_closed() -> None:
    """E3：身份非法 / mode 非法时必须 fail-closed，且发生在任何远程动作之前。"""
    invalid_sha = _bash(f'bash "{SCRIPT}" notasha codex_w2_authority')
    assert invalid_sha.returncode == 2
    assert "XG_SYNC_TARGET_IDENTITY_INVALID" in (invalid_sha.stdout + invalid_sha.stderr)

    invalid_schema = _bash(f'bash "{SCRIPT}" {"a" * 40} "bad schema"')
    assert invalid_schema.returncode == 2
    assert "XG_SYNC_TARGET_IDENTITY_INVALID" in (invalid_schema.stdout + invalid_schema.stderr)

    bad_mode = _bash(f'bash "{SCRIPT}" {"a" * 40} codex_w2_authority --bogus')
    assert bad_mode.returncode == 2
    assert "XG_SYNC_MODE_INVALID" in (bad_mode.stdout + bad_mode.stderr)


def test_sync_requires_target_equals_clean_head(tmp_path: Path) -> None:
    """E3：target 必须等于当前 HEAD 且工作区干净，否则拒绝——防把未经审的本地态同步上主机。"""
    repo, _base = _make_repo(tmp_path)
    result = _bash(f'bash "{SCRIPT}" {"a" * 40} codex_w2_authority', cwd=repo)
    assert result.returncode == 2
    assert "XG_SYNC_SOURCE_NOT_FIXED_CLEAN_HEAD" in (result.stdout + result.stderr)
