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
    assert "future_market_observation" not in tables


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
    assert "future_market_observation" not in tables
    assert "matchday_market_observations" in tables


def _arch_p1_02_env(root: Path, database_url: str) -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }


def _alembic(root: Path, env: dict[str, str], *command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *command],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


_CANONICAL_QUOTE = {
    "observation_id": "canonical-1",
    "fixture_id": "api_football:123",
    "provider_fixture_id": "123",
    "competition_id": "eliteserien",
    "provider": "api_football",
    "bookmaker_id": "7",
    "bookmaker_name": "Bookmaker Seven",
    "capture_id": "capture-1",
    "provider_bet_id": "4",
    "raw_market_label": "Asian Handicap",
    "canonical_market": "ASIAN_HANDICAP",
    "canonical_selection": "HOME",
    "provider_selection": "Home -0.5",
    "line": "-0.5",
    "decimal_odds": "1.91",
    "suspended": False,
    "live": False,
    "provider_updated_at": "2026-07-23T01:01:00Z",
    "captured_at": "2026-07-23 01:02:03+00:00",
    "ingested_at": "2026-07-23 01:02:03+00:00",
    "raw_payload_sha256": "a" * 64,
    "source_revision": "canonical-revision",
}

# Same quote as the canonical row, expressed in the legacy column names.
_LEGACY_QUOTE = {
    "observation_id": "legacy-1",
    "fixture_id": "123",
    "provider": "api_football",
    "bookmaker_id": "7",
    "bookmaker_name": "Bookmaker Seven",
    "provider_bet_id": "4",
    "raw_market_label": "Asian Handicap",
    "canonical_market": "ASIAN_HANDICAP",
    "selection": "HOME",
    "line": "-0.5",
    "decimal_odds": "1.91",
    "suspended": False,
    "live": False,
    "provider_last_update": "2026-07-23T01:01:00Z",
    "captured_at": "2026-07-23 01:02:03+00:00",
    "ingested_at": "2026-07-23 01:02:03+00:00",
    "raw_payload_sha256": "a" * 64,
    "source_revision": "legacy-revision",
    "candidate": False,
    "formal_recommendation": False,
}


def _seed_capture(connection: object) -> None:
    """The canonical observation carries a NOT NULL FK to its endpoint capture."""
    connection.execute(  # type: ignore[attr-defined]
        text(
            "insert into matchday_endpoint_captures "
            "(capture_id, endpoint, sanitized_params, params_hash, request_task_key, "
            " attempt, requested_at, provider_captured_at, status_code, elapsed_ms, "
            " response_count, quota_values, raw_payload_sha256, capture_status) "
            "values ('capture-1', 'odds', '{}', :sha, 'task-1', 1, :at, :at, 200, 1, "
            " 1, '{}', :sha, 'CAPTURED')"
        ),
        {"sha": "a" * 64, "at": _CANONICAL_QUOTE["captured_at"]},
    )


def _insert_statement(table: str, row: dict[str, object]) -> str:
    columns = ", ".join(row)
    values = ", ".join(f":{key}" for key in row)
    return f"insert into {table} ({columns}) values ({values})"  # noqa: S608


def _prepare_0040_with_quotes(
    tmp_path: Path,
    name: str,
    legacy_overrides: dict[str, object],
) -> tuple[Path, dict[str, str], str]:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / name}"
    env = _arch_p1_02_env(root, database_url)
    assert _alembic(root, env, "upgrade", "0040_drop_empty_fk_components").returncode == 0

    engine = create_engine(database_url)
    legacy = {**_LEGACY_QUOTE, **legacy_overrides}
    # Column names come from the literal dicts above and values are always bound
    # parameters, so no caller input reaches either statement.
    canonical_insert = _insert_statement("matchday_market_observations", _CANONICAL_QUOTE)
    legacy_insert = _insert_statement("future_market_observation", legacy)
    with engine.begin() as connection:
        _seed_capture(connection)
        connection.execute(text(canonical_insert), _CANONICAL_QUOTE)
        connection.execute(text(legacy_insert), legacy)
    return root, env, database_url


def test_arch_p1_02_guard_blocks_a_legacy_quote_with_no_canonical_match(
    tmp_path: Path,
) -> None:
    root, env, database_url = _prepare_0040_with_quotes(
        tmp_path, "guard-uncovered.db", {"fixture_id": "999", "observation_id": "legacy-orphan"}
    )
    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "ODDS_CONVERGENCE_UNCOVERED_LEGACY_ROWS" in result.stderr
    inspector = inspect(create_engine(database_url))
    assert "future_market_observation" in inspector.get_table_names()
    assert "current_market_projection" not in inspector.get_view_names()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_bet_id", "999"),
        ("raw_market_label", "Asian Handicap 1st Half"),
        ("bookmaker_name", "Some Other Bookmaker"),
        ("provider", "other_provider"),
        ("provider_last_update", "2026-07-23T09:09:09Z"),
        ("suspended", True),
        ("live", True),
    ],
)
def test_arch_p1_02_guard_blocks_a_price_twin_that_differs_semantically(
    tmp_path: Path, field: str, value: object
) -> None:
    """Same fixture, bookmaker, market, selection, line, odds, time and raw hash,
    but a different shared business field: not a duplicate, must not be dropped."""
    root, env, database_url = _prepare_0040_with_quotes(
        tmp_path, f"guard-{field}.db", {field: value}
    )
    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "ODDS_CONVERGENCE_UNCOVERED_LEGACY_ROWS" in result.stderr
    assert "future_market_observation" in inspect(create_engine(database_url)).get_table_names()


@pytest.mark.parametrize("flag", ["candidate", "formal_recommendation"])
def test_arch_p1_02_guard_blocks_flagged_legacy_rows(tmp_path: Path, flag: str) -> None:
    root, env, database_url = _prepare_0040_with_quotes(
        tmp_path, f"guard-{flag}.db", {flag: True}
    )
    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "ODDS_CONVERGENCE_FLAGGED_LEGACY_ROWS" in result.stderr
    assert "future_market_observation" in inspect(create_engine(database_url)).get_table_names()


def test_arch_p1_02_drops_the_legacy_table_when_every_row_is_covered(tmp_path: Path) -> None:
    root, env, database_url = _prepare_0040_with_quotes(tmp_path, "guard-covered.db", {})
    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode == 0, result.stderr
    inspector = inspect(create_engine(database_url))
    assert "future_market_observation" not in inspector.get_table_names()
    assert "current_market_projection" in inspector.get_view_names()
    assert "current_market_projection" not in inspector.get_table_names()
