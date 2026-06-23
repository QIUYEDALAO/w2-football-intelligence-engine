from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "reports/W2_GATE0_W1_SHA256_MANIFEST.json"
CLASSIFICATION = ROOT / "reports/W2_GATE0_W1_ASSET_CLASSIFICATION.json"
STATUS = ROOT / "reports/W2_ROADMAP_STATUS.json"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"
ROADMAP = ROOT / "docs/W2_MASTER_ROADMAP.md"


def test_w1_tracked_files_have_sha_or_sensitive_exclusion() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    classification = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))

    manifest_files = manifest["files"]
    classification_files = classification["files"]
    assert len(manifest_files) == manifest["tracked_file_count"]
    assert len(classification_files) == classification["w1_tracked_file_count"]
    assert {row["relative_path"] for row in manifest_files} == {
        row["relative_path"] for row in classification_files
    }

    sha_re = re.compile(r"^[0-9a-f]{64}$")
    for row in manifest_files:
        if row.get("excluded"):
            assert row["sensitive_excluded"] is True
            assert "sha256" not in row
        else:
            assert row["sensitive_excluded"] is False
            assert sha_re.match(row["sha256"])
            assert row["size"] >= 0


def test_w1_asset_classifications_are_complete_and_legal() -> None:
    payload = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))
    legal = {"PORT", "REFERENCE", "MIGRATE_DATA", "ARCHIVE", "DELETE_LATER"}

    for row in payload["files"]:
        if row.get("excluded"):
            assert row["migration_status"] == "EXCLUDED_SENSITIVE_PATH"
        else:
            assert row["classification"] in legal
            assert row["classification_reason"]
            assert "evidence" in row and row["evidence"]


def test_gate0_remains_partial_when_required_evidence_is_missing() -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))

    assert status["phases"]["0"]["status"] == "PARTIAL"
    assert status["gates"]["0"]["status"] == "PARTIAL"
    blockers = set(status["phases"]["0"]["blockers"])
    assert "W1_TAG_W1_LEGACY_FINAL_MISSING" in blockers
    assert "FULL_W1_BACKUP_NOT_VERIFIED" in blockers
    assert "W1_WORKTREE_NOT_CLEAN" in blockers


def test_gate0_handoff_and_global_safety_flags_are_preserved() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    status = json.loads(STATUS.read_text(encoding="utf-8"))

    assert "gate0_audit_path: reports/W2_GATE0_LEGACY_CLOSURE_AUDIT.md" in handoff
    assert "gate0_status: PARTIAL" in handoff
    assert "candidate: false" in handoff
    assert "formal_recommendation: false" in handoff
    assert status["candidate"] is False
    assert status["formal_recommendation"] is False


def test_master_roadmap_was_not_revised_for_gate0_evidence() -> None:
    text = ROADMAP.read_text(encoding="utf-8")

    assert "roadmap_version: 1" in text
    assert "status: ACTIVE" in text
    assert "only by explicit user approval" in text
