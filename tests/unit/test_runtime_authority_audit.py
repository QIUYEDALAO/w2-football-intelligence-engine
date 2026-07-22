from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_w2_runtime_authorities as audit


def test_env_audit_uses_actual_readers_not_schema_titles() -> None:
    index = audit.build_symbol_index()
    matrix = audit.build_env_matrix(
        index,
        generated_at="2026-07-20T00:00:00Z",
        generator_sha="test",
    )
    names = {row["name"] for row in matrix["variables"]}
    assert "W2_PROVIDER_CALLS_DISABLED" in names
    assert "W2_AI_RECOMMENDATION_CARD_V1" not in names
    assert "W2_SYSTEM_TRUTH_MATRIX_V1" not in names


def test_finding_registry_is_single_source_for_p0_count() -> None:
    findings = audit.build_findings(
        generated_at="2026-07-20T00:00:00Z",
        generator_sha="test",
    )
    authority = audit.build_authority_map(
        findings,
        generated_at="2026-07-20T00:00:00Z",
        generator_sha="test",
    )
    p0_ids = {item["finding_id"] for item in findings["findings"] if item["severity"] == "P0"}
    referenced = {
        ref
        for entry in authority["entries"]
        for ref in entry["finding_refs"]
        if ref.startswith("P0-")
    }
    assert len(p0_ids) == 6
    assert referenced <= p0_ids
    assert authority["summary"]["core_concept_count"] == 48


def test_data_asset_registry_is_tracked_alias_only() -> None:
    registry = audit.build_data_asset_registry(
        generated_at="2026-07-20T00:00:00Z",
        generator_sha="test",
    )
    text = json.dumps(registry, sort_keys=True)
    assert "$W2_FOOTBALL_DATA_ROOT" in text
    assert "/Users/liudehua" not in text
    assert registry["assets"][0]["restore_state"] in {
        "RESTORE_DRILL_NOT_EXECUTED",
        "RESTORE_DRILL_PENDING",
    }


def test_report_artifacts_self_hash_without_private_absolute_path(tmp_path: Path) -> None:
    payload = audit.build_simple_report(
        "W2_TEST_REPORT",
        ["P0-EXAMPLE"],
        {"status": "OK"},
        generated_at="2026-07-20T00:00:00Z",
        generator_sha="test",
    )
    expected = payload["artifact_sha"]
    body = dict(payload)
    body.pop("artifact_sha")
    assert expected == audit._sha_payload(body)
