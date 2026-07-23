from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
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
    monkeypatch.setattr(audit, "_source_tree_mismatches", lambda: {})

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
    for payload in payloads:
        expected_sha = payload["artifact_sha"]
        body = dict(payload)
        body.pop("artifact_sha")
        assert audit._sha_payload(body) == expected_sha
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
    serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output_dir.glob("W2_*.*")
    )
    assert "/Users/" not in serialized
    assert str(audit.ROOT.resolve()) not in serialized
    assert str(Path.home().resolve()) not in serialized


def _init_source_repo(tmp_path: Path, monkeypatch) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    for root in audit.SCANNED_SOURCE_ROOTS:
        (repository / root).mkdir()
    tracked = repository / "src" / "tracked.py"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    (repository / ".gitignore").write_text("ignored_*.py\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "audit-test@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Audit Test"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "add", ".gitignore", "src/tracked.py"],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repository, check=True)
    monkeypatch.setattr(audit, "ROOT", repository)
    return repository, audit._git("rev-parse", "HEAD")


def test_staged_change_fails_source_identity_check(tmp_path: Path, monkeypatch) -> None:
    repository, generation_head = _init_source_repo(tmp_path, monkeypatch)
    (repository / "src" / "tracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "src/tracked.py"], cwd=repository, check=True)

    with pytest.raises(RuntimeError, match="staged changes: src/tracked.py"):
        audit._ensure_source_tree_matches_head(generation_head)


def test_unstaged_change_fails_source_identity_check(tmp_path: Path, monkeypatch) -> None:
    repository, generation_head = _init_source_repo(tmp_path, monkeypatch)
    (repository / "src" / "tracked.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="unstaged tracked changes: src/tracked.py",
    ):
        audit._ensure_source_tree_matches_head(generation_head)


@pytest.mark.parametrize("source_root", audit.SCANNED_SOURCE_ROOTS)
def test_untracked_scanned_python_file_fails_source_identity_check(
    source_root: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository, generation_head = _init_source_repo(tmp_path, monkeypatch)
    untracked = repository / source_root / "nested" / "untracked.py"
    untracked.parent.mkdir()
    untracked.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match=rf"untracked scanned Python files: {source_root}/nested/untracked.py",
    ):
        audit._ensure_source_tree_matches_head(generation_head)


def test_ignored_untracked_python_file_fails_source_identity_check(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository, generation_head = _init_source_repo(tmp_path, monkeypatch)
    ignored = repository / "scripts" / "ignored_probe.py"
    ignored.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="untracked scanned Python files: scripts/ignored_probe.py",
    ):
        audit._ensure_source_tree_matches_head(generation_head)


def test_dirty_tree_aborts_before_output_or_scan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "existing-output"
    output_dir.mkdir()
    existing = output_dir / "keep.txt"
    existing.write_text("keep\n", encoding="utf-8")
    monkeypatch.setattr(
        audit,
        "_source_tree_mismatches",
        lambda: {"staged changes": ["src/changed.py"]},
    )
    monkeypatch.setattr(
        audit,
        "build_symbol_index",
        lambda: pytest.fail("source scanning must not start for a dirty tree"),
    )

    with pytest.raises(RuntimeError, match="staged changes"):
        audit.write_all(output_dir)

    assert existing.read_text(encoding="utf-8") == "keep\n"


@pytest.mark.parametrize(
    "unsafe_path",
    [
        audit.ROOT,
        audit.ROOT / "src",
        audit.ROOT / "docs" / "audits",
        Path.home(),
        Path("/"),
    ],
)
def test_unsafe_output_directories_are_rejected(unsafe_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Unsafe audit output directory"):
        audit._validate_output_dir(unsafe_path.resolve())


def test_existing_non_generator_output_is_rejected_and_preserved(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "ordinary"
    output_dir.mkdir()
    existing = output_dir / "keep.txt"
    existing.write_text("keep\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="not owned by this generator"):
        audit._validate_output_dir(output_dir.resolve())

    assert existing.read_text(encoding="utf-8") == "keep\n"


def test_existing_generator_marker_allows_output_replacement(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated"
    output_dir.mkdir()
    (output_dir / audit.OUTPUT_MARKER_NAME).write_text(
        audit.OUTPUT_MARKER_CONTENT,
        encoding="utf-8",
    )

    audit._validate_output_dir(output_dir.resolve())


def test_valid_manifest_allows_existing_output_replacement(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated"
    output_dir.mkdir()
    manifest = audit.build_manifest(
        output_dir,
        generated_at="2026-07-24T00:00:00Z",
        source_sha=SOURCE_SHA,
        generator_sha=SOURCE_SHA,
    )
    audit.write_json(
        output_dir,
        "W2_CONSOLIDATION_MANIFEST_V1.json",
        manifest,
    )

    audit._validate_output_dir(output_dir.resolve())


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


def test_publish_failure_restores_existing_generator_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    staged_dir = tmp_path / "staged"
    output_dir = tmp_path / "published"
    staged_dir.mkdir()
    output_dir.mkdir()
    for directory in (staged_dir, output_dir):
        (directory / audit.OUTPUT_MARKER_NAME).write_text(
            audit.OUTPUT_MARKER_CONTENT,
            encoding="utf-8",
        )
    (staged_dir / "new.json").write_text("{}\n", encoding="utf-8")
    existing = output_dir / "existing.json"
    existing.write_text('{"keep": true}\n', encoding="utf-8")
    monkeypatch.setattr(audit, "_git", lambda *args: SOURCE_SHA)
    monkeypatch.setattr(audit, "_source_tree_mismatches", lambda: {})
    replace_calls = 0
    real_replace = audit._replace_directory

    def fail_new_publish(source: Path, destination: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("simulated publish failure")
        real_replace(source, destination)

    monkeypatch.setattr(audit, "_replace_directory", fail_new_publish)

    with pytest.raises(OSError, match="simulated publish failure"):
        audit._publish_generated_audits(staged_dir, output_dir, SOURCE_SHA)

    assert existing.read_text(encoding="utf-8") == '{"keep": true}\n'
    assert not (output_dir / "new.json").exists()
