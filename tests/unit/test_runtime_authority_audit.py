from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_w2_runtime_authorities as audit

SOURCE_SHA = "a" * 40


def test_env_audit_uses_actual_readers_not_schema_titles() -> None:
    index = audit.build_symbol_index()
    matrix = audit.build_env_matrix(
        index,
        generated_at="2026-07-20T00:00:00Z",
        source_sha=SOURCE_SHA,
        generator_sha="test",
    )
    names = {row["name"] for row in matrix["variables"]}
    assert "W2_PROVIDER_CALLS_DISABLED" in names
    assert "W2_AI_RECOMMENDATION_CARD_V1" not in names
    assert "W2_SYSTEM_TRUTH_MATRIX_V1" not in names


def test_finding_registry_is_single_source_for_p0_count() -> None:
    findings = audit.build_findings(
        generated_at="2026-07-20T00:00:00Z",
        source_sha=SOURCE_SHA,
        generator_sha="test",
    )
    authority = audit.build_authority_map(
        findings,
        generated_at="2026-07-20T00:00:00Z",
        source_sha=SOURCE_SHA,
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
        source_sha=SOURCE_SHA,
        generator_sha="test",
    )
    text = json.dumps(registry, sort_keys=True)
    assert "$W2_FOOTBALL_DATA_ROOT" in text
    assert "/Users/" not in text
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
        source_sha=SOURCE_SHA,
        generator_sha="test",
    )
    expected = payload["artifact_sha"]
    body = dict(payload)
    body.pop("artifact_sha")
    assert expected == audit._sha_payload(body)


def test_generator_defaults_to_runtime_and_supports_output_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "system-truth"

    def fake_lineage(*, generated_at: str, source_sha: str, generator_sha: str):
        return audit.build_simple_report(
            "W2_PR_LINEAGE_MAP_V2",
            [],
            {"pull_requests": "not queried in unit test"},
            generated_at=generated_at,
            source_sha=source_sha,
            generator_sha=generator_sha,
        )

    monkeypatch.setattr(audit, "build_lineage", fake_lineage)
    monkeypatch.setattr(audit, "_safe_alembic_head", lambda: "0041")

    result = audit.write_all(output_dir)
    generation_head = audit._git("rev-parse", "HEAD")

    assert audit.DEFAULT_OUTPUT_DIR == audit.ROOT / "runtime" / "audits" / "system_truth"
    assert result["output_dir"] == output_dir.resolve().as_posix()
    assert result["source_review_sha"] == generation_head
    assert list(output_dir.glob("*.json"))
    assert list(output_dir.glob("*.md"))

    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in output_dir.glob("*.json")
    ]
    assert all(payload["source_review_sha"] == generation_head for payload in payloads)
    assert all("audit_output_commit_sha" not in payload for payload in payloads)
    assert "PENDING" + "_COMMIT" not in "\n".join(
        path.read_text(encoding="utf-8") for path in output_dir.iterdir()
    )
    alias_names = {
        "W2_RUNTIME_CALL_GRAPH_V2",
        "W2_SCHEDULER_CHECKPOINT_MATRIX_V2",
        "W2_PROVIDER_ENDPOINT_MATRIX_V2",
        "W2_FACTOR_STRATEGY_REGISTRY_V2",
        "W2_RECOMMENDATION_LIFECYCLE_TRACE_V2",
        "W2_TEST_COVERAGE_AUTHORITY_MATRIX_V2",
        "W2_SYSTEM_TRUTH_AUDIT_MANIFEST_V2",
    }
    assert not {
        path.stem for path in output_dir.iterdir()
    } & alias_names
    assert all("/Users/" not in path.read_text(encoding="utf-8") for path in output_dir.iterdir())


def test_head_change_aborts_publish_without_touching_destination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    staged_dir = tmp_path / "staged"
    output_dir = tmp_path / "published"
    staged_dir.mkdir()
    output_dir.mkdir()
    (staged_dir / "new.json").write_text("{}\n", encoding="utf-8")
    (output_dir / "existing.json").write_text('{"keep": true}\n', encoding="utf-8")
    monkeypatch.setattr(audit, "_git", lambda *args: "b" * 40)

    try:
        audit._publish_generated_audits(staged_dir, output_dir, "a" * 40)
    except RuntimeError as error:
        assert "Git HEAD changed" in str(error)
    else:
        raise AssertionError("HEAD drift must fail closed")

    assert (output_dir / "existing.json").exists()
    assert (staged_dir / "new.json").exists()
