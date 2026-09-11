from __future__ import annotations

import hashlib
import subprocess

import pytest
from scripts.check_historical_diff import HISTORICAL_EVIDENCE_SHA256, ROOT, check_diff

EXPECTED_PATHS = (
    "docs/review_packages/W2_REPLAY_EVIDENCE_20260908/changes.patch",
    "docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909/DISPATCH.md",
    "docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909/REMEDIATION_DISPATCH_V1_1.md",
    "docs/review_packages/SC21_FACTOR_INPUT_CHAIN/R17_P0_QUOTA_UNDERESTIMATE_AND_PROVIDER_LIMIT_AUDIT.md",
    "docs/review_packages/SC21_FACTOR_INPUT_CHAIN/R19_PROVIDER_DISPATCH_AND_QUOTA_DEGRADATION_CLOSURE.md",
)


def test_allowlist_is_exact_and_hashes_match() -> None:
    assert set(HISTORICAL_EVIDENCE_SHA256) == set(EXPECTED_PATHS)
    for relative, expected in HISTORICAL_EVIDENCE_SHA256.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_diff_check_excludes_only_pinned_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.extend(command)
        assert kwargs["cwd"] == ROOT
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    check_diff("base", "head")
    assert seen[:5] == ["git", "diff", "--check", "base...head", "--"]
    assert seen[5] == "."
    assert seen[6:] == [f":(exclude){path}" for path in EXPECTED_PATHS]


def test_hash_change_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    relative = next(iter(HISTORICAL_EVIDENCE_SHA256))
    monkeypatch.setitem(HISTORICAL_EVIDENCE_SHA256, relative, "0" * 64)
    with pytest.raises(SystemExit, match="historical evidence hash changed"):
        check_diff("base", "head")


def test_ci_entrypoints_use_the_allowlist_checker() -> None:
    workflow_text = (
        (ROOT / ".github/workflows/release-candidate.yml").read_text(encoding="utf-8")
        + (ROOT / ".github/workflows/context-only-release.yml").read_text(encoding="utf-8")
    )
    dev_check = (ROOT / "scripts/dev_check.py").read_text(encoding="utf-8")
    assert workflow_text.count("scripts/check_historical_diff.py") == 2
    assert "git diff --check" not in workflow_text
    assert "scripts/check_historical_diff.py" in dev_check
