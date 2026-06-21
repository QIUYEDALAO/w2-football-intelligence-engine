from __future__ import annotations

from w2.operations.governance import (
    OperationsCycleKind,
    build_cycle,
    build_operations_report,
    build_release_audit,
)


def test_cycle_hash_is_deterministic_and_checkpointed() -> None:
    first = build_cycle(OperationsCycleKind.DAILY)
    second = build_cycle(OperationsCycleKind.DAILY)
    assert first.deterministic_hash == second.deterministic_hash
    assert first.checkpoint == "DAILY:dry-run"
    assert first.immutable_audit is True


def test_all_cycle_types_and_gate4_disabled_items() -> None:
    report = build_operations_report()
    kinds = {cycle["kind"] for cycle in report["cycles"]}
    assert kinds == {"DAILY", "WEEKLY", "MATCHDAY", "ROUND_END", "SEASON_END", "MODEL_RELEASE"}
    daily = next(cycle for cycle in report["cycles"] if cycle["kind"] == "DAILY")
    assert any(check["status"] == "DISABLED_GATE4" for check in daily["checks"])


def test_release_gate_block_and_retention_dry_run() -> None:
    release = build_release_audit()
    assert release["approval_status"] == "PRODUCTION_RELEASE_DISABLED"
    assert release["model_published"] is False
    report = build_operations_report()
    assert report["retention"]["files_deleted"] is False
    assert report["external_alerting"] is False
    assert report["production_release"] is False
