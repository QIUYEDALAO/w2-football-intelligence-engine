from __future__ import annotations

from pathlib import Path

from scripts.run_stage7i_observer import resolve_expected_revision, sample


def write_revision(root: Path, revision: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "DEPLOYMENT_REVISION").write_text(revision, encoding="utf-8")


def test_observer_uses_cli_revision_first(tmp_path) -> None:
    write_revision(tmp_path, "actual")
    expected, source = resolve_expected_revision(
        explicit="cli-revision",
        current=tmp_path,
        environ={"W2_STAGE7I_EXPECTED_REVISION": "env-revision"},
    )
    assert expected == "cli-revision"
    assert source == "CLI"


def test_observer_falls_back_to_current_revision(tmp_path) -> None:
    write_revision(tmp_path, "current-revision")
    expected, source = resolve_expected_revision(explicit=None, current=tmp_path, environ={})
    assert expected == "current-revision"
    assert source == "CURRENT_DEPLOYMENT_REVISION"


def test_observer_records_invalidation_reason(tmp_path) -> None:
    write_revision(tmp_path, "actual")
    record = sample(tmp_path, "expected", "CLI")
    assert record["revision_ok"] is False
    assert record["invalidation_reason"] == "REVISION_MISMATCH"
