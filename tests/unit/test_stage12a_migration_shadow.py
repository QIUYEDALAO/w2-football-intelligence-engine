from __future__ import annotations

from datetime import UTC
from pathlib import Path

from w2.migration import (
    DATA_DOMAINS,
    MigrationDecision,
    MigrationDryRunEngine,
    ShadowComparisonEngine,
    ShadowRunManifest,
    W1SnapshotAdapter,
    W2SnapshotAdapter,
    build_default_contracts,
    build_source_inventory,
    quarantine_registry,
)
from w2.migration.foundation import parse_decimal, parse_utc, stable_uuid


def _write_fixture(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_source_inventory_records_hash_and_decisions(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        "data/local_odds/world_cup_odds_historical.csv",
        "fixture_id,home,away\n1,Alpha,Beta\n",
    )
    _write_fixture(
        tmp_path,
        "reports/w1_backtest_1x2_only_baseline_v1.json",
        '{"rows": [{"fixture_id": "1"}]}',
    )
    inventory = build_source_inventory(tmp_path, "abc123")
    assert {item.domain for item in inventory} == set(DATA_DOMAINS)
    odds = next(item for item in inventory if item.domain == "bookmaker_odds_snapshots")
    assert odds.source_system == "W1"
    assert odds.source_sha256 != "MISSING"
    assert odds.migration_eligibility == MigrationDecision.READY_FOR_TRANSFORM
    scout = next(item for item in inventory if item.domain == "w1_ai_scout_outputs")
    assert scout.migration_eligibility in {
        MigrationDecision.AUDIT_ONLY,
        MigrationDecision.QUARANTINE,
    }


def test_transform_contracts_and_dry_run_are_deterministic(tmp_path: Path) -> None:
    _write_fixture(tmp_path, "data/odds_snapshots/raw/payload.json", '{"fixture": 1}')
    inventory = build_source_inventory(tmp_path, "abc123")
    contracts = build_default_contracts()
    assert all(contract.rollback_metadata for contract in contracts)
    engine = MigrationDryRunEngine(inventory, contracts)
    first = engine.run(run_id="same-run")
    second = engine.run(run_id="same-run")
    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert first["temporary_load_touched_w2_database"] is False
    assert first["w1_writes"] is False
    assert first["business_data_copy_retained"] is False


def test_quarantine_and_conversion_helpers(tmp_path: Path) -> None:
    inventory = build_source_inventory(tmp_path, "abc123")
    quarantine = quarantine_registry(inventory)
    assert quarantine["silent_drop_allowed"] is False
    assert quarantine["records"]
    parsed_time = parse_utc("2026-06-22T10:00:00+00:00", "event_time")
    assert parsed_time.tzinfo == UTC
    assert parse_decimal("1.95").as_tuple().digits == (1, 9, 5)
    assert stable_uuid("fixture:1") == stable_uuid("fixture:1")


def test_shadow_comparison_is_offline_and_gate_blocked() -> None:
    manifest = ShadowRunManifest(
        run_id="unit-shadow",
        created_at=parse_utc("2026-06-22T00:00:00+00:00", "created_at"),
        w1_source="frozen",
        w2_source="archived",
        strategy_comparison_status="NOT_AVAILABLE_GATE4",
    )
    payload = ShadowComparisonEngine().compare(
        manifest=manifest,
        w1_snapshot=W1SnapshotAdapter().load_sample(),
        w2_snapshot=W2SnapshotAdapter().load_sample(),
    )
    assert payload["network_used"] is False
    assert payload["real_prediction_run"] is False
    assert payload["candidate_or_recommend_output"] is False
    assert payload["manifest"]["strategy_comparison_status"] == "NOT_AVAILABLE_GATE4"
    assert payload["comparison_sha256"]
