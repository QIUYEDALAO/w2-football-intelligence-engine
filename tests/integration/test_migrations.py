from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text


def test_alembic_upgrade_and_downgrade_smoke(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": f"sqlite+pysqlite:///{tmp_path / 'w2.db'}",
        "W2_ENVIRONMENT": "test",
    }
    for command in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *command],
            cwd=root,
            env={**env},
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_arch_p1_01_drops_and_restores_system_metadata(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'arch-p1-01.db'}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }

    def migrate(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    migrate("upgrade", "0037_seed_competition_runtime_authority")
    engine = create_engine(database_url)
    assert "system_metadata" in inspect(engine).get_table_names()

    migrate("upgrade", "head")
    assert "system_metadata" not in inspect(engine).get_table_names()

    migrate("downgrade", "0037_seed_competition_runtime_authority")
    assert "system_metadata" in inspect(engine).get_table_names()

    migrate("upgrade", "head")
    assert "system_metadata" not in inspect(engine).get_table_names()


def test_arch_p1_01_drops_and_restores_all_evidence_backed_dead_tables(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'arch-p1-01-dead-tables.db'}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }
    dropped_tables = {
        "api_request_audit",
        "audit_events",
        "backup_run",
        "challenger_model",
        "data_quality_runs",
        "dataset_sources",
        "dependency_risk",
        "forward_cycle_checkpoint",
        "forward_operational_alert",
        "forward_result_event",
        "forward_scheduler_run",
        "forward_state_transition",
        "freshness_alerts",
        "league_team_membership",
        "market_quality_assessment",
        "migration_dry_run",
        "migration_quarantine_record",
        "migration_source_asset",
        "migration_validation_record",
        "model_gate_decision",
        "operational_alert",
        "operational_metric_snapshot",
        "operations_check_result",
        "operations_cycle",
        "promotion_relegation_mapping",
        "provider_entity_mappings",
        "release_audit",
        "release_candidate",
        "restore_run",
        "retention_audit",
        "season_rollover_plan",
        "security_audit_event",
        "shadow_comparison_record",
        "shadow_run",
        "shadow_strategy_candidate",
        "shadow_strategy_event",
        "shadow_strategy_settlement",
        "slo_evaluation",
        "sync_cursors",
        "tournament_operations_plan",
        "tournament_profile",
        "tournament_readiness_audit",
    }

    def migrate(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    migrate("upgrade", "head")
    engine = create_engine(database_url)
    assert dropped_tables.isdisjoint(inspect(engine).get_table_names())

    migrate("downgrade", "0038_drop_unused_system_metadata")
    assert dropped_tables.issubset(inspect(engine).get_table_names())

    migrate("upgrade", "head")
    assert dropped_tables.isdisjoint(inspect(engine).get_table_names())


def test_arch_p1_01_drops_and_restores_empty_fk_components(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'arch-p1-01-fk-components.db'}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }
    dropped_tables = {
        "ablation_run",
        "asof_samples",
        "bookmakers",
        "calibration_artifact",
        "data_provenance",
        "dataset_artifacts",
        "dataset_versions",
        "evaluation_record",
        "feature_snapshots",
        "forward_cycle_run",
        "forward_evaluation",
        "forward_gate_audit",
        "forward_holdout_run",
        "forward_prediction_lock",
        "injuries",
        "label_references",
        "lineups",
        "market_baseline_run",
        "market_consensus",
        "market_fit_diagnostic",
        "markets",
        "model_artifact",
        "model_evaluation",
        "model_experiment",
        "odds_observations",
        "players",
        "prediction_snapshot",
        "raw_payload_references",
        "replay_checkpoint",
        "replay_event",
        "replay_run",
        "squads",
        "suspensions",
        "team_ratings",
        "weather_observations",
    }

    def migrate(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    migrate("upgrade", "head")
    engine = create_engine(database_url)
    assert dropped_tables.isdisjoint(inspect(engine).get_table_names())

    migrate("downgrade", "0039_drop_evidence_backed_dead_tables")
    assert dropped_tables.issubset(inspect(engine).get_table_names())

    migrate("upgrade", "head")
    assert dropped_tables.isdisjoint(inspect(engine).get_table_names())


def test_staging_state_stage9a_head_upgrades_to_future_refresh_head(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "staging-state.db"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": f"sqlite+pysqlite:///{database_path}",
        "W2_ENVIRONMENT": "test",
    }
    first = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "0017_create_stage9a_shadow_strategy",
        ],
        cwd=root,
        env={**env},
        check=False,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    inspector = inspect(create_engine(env["W2_DATABASE_URL"]))
    tables = set(inspector.get_table_names())
    assert "shadow_strategy_run" in tables
    assert "future_market_observation" not in tables

    second = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env={**env},
        check=False,
        capture_output=True,
        text=True,
    )
    assert second.returncode == 0, second.stderr
    tables = set(inspect(create_engine(env["W2_DATABASE_URL"])).get_table_names())
    assert "shadow_strategy_run" in tables
    assert "future_market_observation" in tables


def test_postgres_staging_state_stage9a_head_upgrades_to_future_refresh_head() -> None:
    database_url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("W2_TEST_POSTGRES_URL is required for PostgreSQL staging-state migration")
    root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    for command in (
        ["upgrade", "0017_create_stage9a_shadow_strategy"],
        ["upgrade", "head"],
        ["downgrade", "0028_create_matchday_evidence_authority"],
        ["upgrade", "head"],
        ["downgrade", "0027_finalize_fah_authority_constraints"],
        ["upgrade", "head"],
    ):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *command],
            cwd=root,
            env={**env},
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
    tables = set(inspect(create_engine(database_url)).get_table_names())
    assert "shadow_strategy_run" in tables
    assert "future_market_observation" in tables
    assert "matchday_market_observations" in tables
