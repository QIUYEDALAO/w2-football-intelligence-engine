from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "ops" / "host" / "w2-update-v3-monitor"


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
    """纯运维变更（只改 ops）→ 业务 tree 一致（F3 闸门放行）。"""
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
