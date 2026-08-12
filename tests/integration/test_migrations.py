from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from w2.factor_model.remediation import canonical_team_payload, provider_crosswalk_payload
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.matchday.intake_v2 import stable_hash


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


def test_0052_drops_and_restores_empty_retired_checkpoint_plan(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'retired-checkpoint-plan.db'}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }
    assert _alembic(root, env, "upgrade", "0051_apply_seven_day_collection_policy").returncode == 0
    engine = create_engine(database_url)
    assert "future_refresh_checkpoint_plan" in inspect(engine).get_table_names()

    assert _alembic(root, env, "upgrade", "head").returncode == 0
    assert "future_refresh_checkpoint_plan" not in inspect(engine).get_table_names()

    assert (
        _alembic(root, env, "downgrade", "0051_apply_seven_day_collection_policy").returncode
        == 0
    )
    assert "future_refresh_checkpoint_plan" in inspect(engine).get_table_names()


def test_0052_refuses_nonempty_retired_checkpoint_plan(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'nonempty-retired-checkpoint-plan.db'}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }
    assert _alembic(root, env, "upgrade", "0051_apply_seven_day_collection_policy").returncode == 0
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into future_refresh_checkpoint_plan "
                "(id, fixture_id, checkpoint, kickoff_utc, due_at, endpoints, source, status) "
                "values ('fixture:T24', 'fixture', 'T24', '2026-08-13 00:00:00', "
                "'2026-08-12 00:00:00', '[\"odds\"]', 'retired', 'PENDING')"
            )
        )

    result = _alembic(root, env, "upgrade", "head")
    assert result.returncode != 0
    assert "RETIRED_CHECKPOINT_PLAN_TABLE_NONEMPTY:1" in result.stderr
    assert "future_refresh_checkpoint_plan" in inspect(engine).get_table_names()


def test_0053_backfills_reviewed_team_identity_and_retains_it(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'team-identity.db'}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }
    assert (
        _alembic(
            root, env, "upgrade", "0052_drop_retired_future_refresh_checkpoint_plan"
        ).returncode
        == 0
    )
    engine = create_engine(database_url)
    _seed_0053_authority_and_fixtures(engine)

    assert _alembic(root, env, "upgrade", "head").returncode == 0
    with Session(engine) as session:
        fixtures = list(
            session.query(MatchdayFixtureIdentityModel).order_by(
                MatchdayFixtureIdentityModel.provider_fixture_id
            )
        )
        assert len(fixtures) == 3
        assert all(row.team_identity_status == "PROVIDER_PRIMARY_READY" for row in fixtures)
        assert all(row.home_w2_team_id and row.away_w2_team_id for row in fixtures)
        assert session.query(CanonicalTeamModel).count() == 11
        approved = session.query(ProviderTeamIdentityCrosswalkModel).filter_by(
            review_status="APPROVED"
        )
        assert approved.count() == 6

    assert (
        _alembic(root, env, "downgrade", "0052_drop_retired_future_refresh_checkpoint_plan")
        .returncode
        == 0
    )
    with Session(engine) as session:
        fixtures = list(session.query(MatchdayFixtureIdentityModel))
        assert all(row.team_identity_status == "PROVIDER_PRIMARY_READY" for row in fixtures)
        assert all(row.home_w2_team_id and row.away_w2_team_id for row in fixtures)
        assert session.query(CanonicalTeamModel).count() == 11
        assert (
            session.query(ProviderTeamIdentityCrosswalkModel)
            .filter_by(review_status="APPROVED")
            .count()
            == 6
        )


def test_0053_rejects_partial_fixture_scope(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'partial-team-identity.db'}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }
    assert (
        _alembic(
            root, env, "upgrade", "0052_drop_retired_future_refresh_checkpoint_plan"
        ).returncode
        == 0
    )
    engine = create_engine(database_url)
    _seed_0053_authority_and_fixtures(engine)
    with engine.begin() as connection:
        connection.execute(
            text("delete from matchday_fixture_identities where provider_fixture_id='1493061'")
        )

    result = _alembic(root, env, "upgrade", "head")
    assert result.returncode != 0
    assert "TEAM_IDENTITY_FIXTURE_SCOPE_PARTIAL:2" in result.stderr


def _seed_0053_authority_and_fixtures(engine: Engine) -> None:
    captured_at = datetime.fromisoformat("2026-08-11T03:14:22+00:00")
    existing = {
        "124": "brasileirao_serie_a",
        "130": "brasileirao_serie_a",
        "2143": "eliteserien",
        "331": "eliteserien",
        "794": "brasileirao_serie_a",
    }
    fixtures = {
        "1493049": (
            "argentina_primera",
            "128",
            "449",
            "Banfield",
            "440",
            "Belgrano Cordoba",
        ),
        "1493061": (
            "argentina_primera",
            "128",
            "441",
            "Union Santa Fe",
            "1065",
            "Central Cordoba de Santiago",
        ),
        "1575453": ("primeira_liga", "94", "227", "Santa Clara", "225", "Nacional"),
    }
    with Session(engine) as session:
        for team_id, competition in existing.items():
            canonical = canonical_team_payload(
                provider_team_id=team_id,
                display_name=f"team-{team_id}",
                country=None,
                created_at=captured_at,
            )
            session.add(CanonicalTeamModel(**canonical))
            crosswalk = provider_crosswalk_payload(
                provider_team_id=team_id,
                w2_team_id=canonical["w2_team_id"],
                competition_id=competition,
                season="2026",
                evidence_hashes=[stable_hash({"team_id": team_id})],
                valid_from=captured_at,
            )
            session.add(ProviderTeamIdentityCrosswalkModel(**crosswalk))
        for index, (provider_fixture_id, fixture) in enumerate(fixtures.items()):
            competition, league, home_id, home_name, away_id, away_name = fixture
            payload = {
                "fixture": {"id": int(provider_fixture_id)},
                "teams": {
                    "home": {"id": int(home_id), "name": home_name},
                    "away": {"id": int(away_id), "name": away_name},
                },
            }
            session.add(
                MatchdayFixtureIdentityModel(
                    fixture_id=f"api_football:{provider_fixture_id}",
                    provider="api_football",
                    provider_fixture_id=provider_fixture_id,
                    competition_id=competition,
                    provider_league_id=league,
                    season="2026",
                    kickoff_utc=captured_at,
                    fixture_status="FT",
                    home_provider_team_id=home_id,
                    away_provider_team_id=away_id,
                    home_w2_team_id=None,
                    away_w2_team_id=None,
                    team_identity_status="REVIEW_REQUIRED",
                    raw_payload_sha256=f"{'1' + str(index)}".ljust(64, "0"),
                    endpoint_capture_id=None,
                    captured_at=captured_at,
                    identity_hash=f"{'2' + str(index)}".ljust(64, "0"),
                    payload=payload,
                )
            )
        session.commit()


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
    assert "shadow_strategy_run" not in tables
    assert "shadow_strategy_lock" not in tables
    assert "shadow_strategy_evaluation" not in tables
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
    assert "shadow_strategy_run" not in tables
    assert "shadow_strategy_lock" not in tables
    assert "shadow_strategy_evaluation" not in tables
    assert "future_market_observation" not in tables
    assert "matchday_market_observations" in tables


def test_arch_p1_08_drops_and_restores_empty_shadow_strategy_tables(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'arch-p1-08-shadow.db'}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }
    shadow_tables = {
        "shadow_strategy_run",
        "shadow_strategy_lock",
        "shadow_strategy_evaluation",
    }

    assert _alembic(
        root, env, "upgrade", "0043_drop_legacy_identity_crosswalks"
    ).returncode == 0
    engine = create_engine(database_url)
    assert shadow_tables.issubset(inspect(engine).get_table_names())

    assert _alembic(root, env, "upgrade", "head").returncode == 0
    assert shadow_tables.isdisjoint(inspect(engine).get_table_names())

    assert _alembic(
        root, env, "downgrade", "0043_drop_legacy_identity_crosswalks"
    ).returncode == 0
    assert shadow_tables.issubset(inspect(engine).get_table_names())


def test_arch_p1_08_refuses_nonempty_shadow_strategy_tables(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'arch-p1-08-shadow-nonempty.db'}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }
    assert _alembic(
        root, env, "upgrade", "0043_drop_legacy_identity_crosswalks"
    ).returncode == 0
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into shadow_strategy_run "
                "(id, run_id, strategy_version, started_at, status, manifest_sha256, payload) "
                "values ('id', 'run', 'v1', '2026-07-28 00:00:00', 'DONE', :hash, '{}')"
            ),
            {"hash": "a" * 64},
        )

    result = _alembic(root, env, "upgrade", "head")
    assert result.returncode != 0
    assert "SHADOW_STRATEGY_DROP_NONEMPTY" in result.stderr


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


def _assert_migration_left_database_untouched(database_url: str) -> None:
    """A refused drop must leave both objects exactly as 0040 left them."""
    inspector = inspect(create_engine(database_url))
    assert "future_market_observation" in inspector.get_table_names()
    assert "current_market_projection" not in inspector.get_view_names()
    assert "current_market_projection" not in inspector.get_table_names()


def test_arch_p1_02_guard_blocks_a_legacy_quote_with_no_canonical_match(
    tmp_path: Path,
) -> None:
    root, env, database_url = _prepare_0040_with_quotes(
        tmp_path, "guard-uncovered.db", {"fixture_id": "999", "observation_id": "legacy-orphan"}
    )
    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "ODDS_CONVERGENCE_UNCOVERED_LEGACY_ROWS" in result.stderr
    _assert_migration_left_database_untouched(database_url)


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
    _assert_migration_left_database_untouched(database_url)


@pytest.mark.parametrize("flag", ["candidate", "formal_recommendation"])
def test_arch_p1_02_guard_blocks_flagged_legacy_rows(tmp_path: Path, flag: str) -> None:
    root, env, database_url = _prepare_0040_with_quotes(tmp_path, f"guard-{flag}.db", {flag: True})
    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "ODDS_CONVERGENCE_FLAGGED_LEGACY_ROWS" in result.stderr
    _assert_migration_left_database_untouched(database_url)


def test_arch_p1_02_drops_the_legacy_table_when_every_row_is_covered(tmp_path: Path) -> None:
    root, env, database_url = _prepare_0040_with_quotes(tmp_path, "guard-covered.db", {})
    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode == 0, result.stderr
    inspector = inspect(create_engine(database_url))
    assert "future_market_observation" not in inspector.get_table_names()
    assert "current_market_projection" in inspector.get_view_names()
    assert "current_market_projection" not in inspector.get_table_names()


def test_0042_team_identity_provider_review_provenance(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'arch-p1-03-m2a.db'}"
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

    migrate("upgrade", "0041_converge_odds_history_and_projection")
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into canonical_teams (w2_team_id, display_name, country, "
                "active_status, created_at, identity_hash, payload) values "
                "('w2:team:api_football:100','T100','SE','ACTIVE',"
                "'2026-01-01T00:00:00+00:00','h100','{}')"
            )
        )
        conn.execute(
            text(
                "insert into provider_team_identity_crosswalks (id, provider, "
                "provider_team_id, w2_team_id, competition_id, season, valid_from, "
                "identity_status, evidence_hashes, identity_hash) values "
                "('api_football:100:allsvenskan:2026','api_football','100',"
                "'w2:team:api_football:100','allsvenskan','2026',"
                "'2026-01-01T00:00:00+00:00','PROVIDER_PRIMARY_READY','[]','ih100')"
            )
        )
        conn.execute(
            text(
                "insert into team_identity_crosswalks (id, api_football_team_id, "
                "transfermarkt_club_id, competition_id, valid_from, review_status, "
                "crosswalk_hash, source_sha256, reviewed_by, reviewed_at, payload) values "
                "('tic-1','100','999','allsvenskan','2026-01-01T00:00:00+00:00',"
                "'APPROVED','ch1','abc','analyst','2026-01-02T00:00:00+00:00','{\"k\":\"v\"}')"
            )
        )

    migrate("upgrade", "head")

    cols = {c["name"] for c in inspect(engine).get_columns("provider_team_identity_crosswalks")}
    assert {"review_status", "reviewed_by", "reviewed_at", "source_hashes", "payload"} <= cols

    with engine.begin() as conn:
        tm = (
            conn.execute(
                text(
                    "select w2_team_id, review_status, reviewed_by, source_hashes, identity_status "
                    "from provider_team_identity_crosswalks where provider='transfermarkt' "
                    "and provider_team_id='999'"
                )
            )
            .mappings()
            .all()
        )
        assert len(tm) == 1
        assert tm[0]["w2_team_id"] == "w2:team:api_football:100"
        assert tm[0]["review_status"] == "APPROVED"
        assert tm[0]["reviewed_by"] == "analyst"
        assert tm[0]["source_hashes"] == '["abc"]'
        assert tm[0]["identity_status"] == "PROVIDER_PRIMARY_READY"

        api = (
            conn.execute(
                text(
                    "select review_status, reviewed_by from provider_team_identity_crosswalks "
                    "where provider='api_football' and provider_team_id='100'"
                )
            )
            .mappings()
            .one()
        )
        assert api["review_status"] == "APPROVED"
        assert api["reviewed_by"] == "analyst"


def test_0042_fails_closed_when_authority_mapping_missing(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'arch-p1-03-m2a-block.db'}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }

    def migrate(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    assert migrate("upgrade", "0041_converge_odds_history_and_projection").returncode == 0
    engine = create_engine(database_url)
    with engine.begin() as conn:
        # APPROVED legacy row with NO matching api_football authority row -> fail closed.
        conn.execute(
            text(
                "insert into team_identity_crosswalks (id, api_football_team_id, "
                "transfermarkt_club_id, competition_id, valid_from, review_status, "
                "crosswalk_hash, payload) values "
                "('tic-x','777','888','allsvenskan','2026-01-01T00:00:00+00:00',"
                "'APPROVED','chx','{}')"
            )
        )

    result = migrate("upgrade", "head")
    assert result.returncode != 0
    assert "team identity migration blocked" in (result.stderr + result.stdout)


def _m2a_env(tmp_path: Path, name: str) -> tuple[Path, str, dict[str, str]]:
    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite+pysqlite:///{tmp_path / name}"
    env = {
        **os.environ,
        "PYTHONPATH": f"{root / 'src'}:{root}",
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": "test",
    }
    return root, database_url, env


def _alembic(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_0043_drops_and_downgrade_recreates_legacy_identity_schema(
    tmp_path: Path,
) -> None:
    root, database_url, env = _m2a_env(tmp_path, "m4-roundtrip.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    assert (
        _alembic(root, env, "upgrade", "0042_team_identity_provider_review_provenance").returncode
        == 0
    )

    targets = {
        "team_identity_crosswalks",
        "football_data_team_crosswalks",
        "player_identity_crosswalks",
    }
    before = inspect(engine)
    expected = {
        table: {
            "columns": {column["name"] for column in before.get_columns(table)},
            "indexes": {index["name"] for index in before.get_indexes(table)},
            "unique": {constraint["name"] for constraint in before.get_unique_constraints(table)},
        }
        for table in targets
    }

    result = _alembic(root, env, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    assert targets.isdisjoint(inspect(engine).get_table_names())

    result = _alembic(root, env, "downgrade", "0042_team_identity_provider_review_provenance")
    assert result.returncode == 0, result.stderr
    restored = inspect(engine)
    for table in targets:
        assert {column["name"] for column in restored.get_columns(table)} == expected[table][
            "columns"
        ]
        assert {index["name"] for index in restored.get_indexes(table)} == expected[table][
            "indexes"
        ]
        assert {
            constraint["name"] for constraint in restored.get_unique_constraints(table)
        } == expected[table]["unique"]
        with engine.begin() as conn:
            assert conn.execute(text(f"select count(*) from {table}")).scalar_one() == 0  # noqa: S608


def test_0043_fails_closed_on_legacy_database_dependency(tmp_path: Path) -> None:
    root, database_url, env = _m2a_env(tmp_path, "m4-dependency.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    assert (
        _alembic(root, env, "upgrade", "0042_team_identity_provider_review_provenance").returncode
        == 0
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "create table legacy_consumer ("
                "id varchar(36) primary key, crosswalk_id varchar(36), "
                "foreign key(crosswalk_id) references team_identity_crosswalks(id))"
            )
        )

    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "LEGACY_IDENTITY_M4_DEPENDENCIES" in (result.stdout + result.stderr)


@pytest.mark.parametrize(
    "dependency_sql",
    [
        ("create view legacy_identity_view as select id from team_identity_crosswalks"),
        (
            "create trigger legacy_identity_trigger after insert on canonical_teams "
            "begin select count(*) from team_identity_crosswalks; end"
        ),
    ],
)
def test_0043_fails_closed_on_sqlite_view_or_trigger_dependency(
    tmp_path: Path,
    dependency_sql: str,
) -> None:
    root, database_url, env = _m2a_env(tmp_path, "m4-sqlite-object-dependency.db")
    assert (
        _alembic(
            root,
            env,
            "upgrade",
            "0041_converge_odds_history_and_projection",
        ).returncode
        == 0
    )
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    assert (
        _alembic(root, env, "upgrade", "0042_team_identity_provider_review_provenance").returncode
        == 0
    )
    with engine.begin() as conn:
        conn.execute(text(dependency_sql))

    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "LEGACY_IDENTITY_M4_DEPENDENCIES" in (result.stdout + result.stderr)


@pytest.mark.parametrize(
    "dependency_sql",
    [
        (
            "create function legacy_identity_function() returns bigint language sql "
            "as $$ select count(*) from team_identity_crosswalks $$"
        ),
        (
            "create function legacy_identity_trigger_function() returns trigger "
            "language plpgsql as $$ begin return new; end $$; "
            "create trigger legacy_identity_trigger before insert "
            "on team_identity_crosswalks for each row "
            "execute function legacy_identity_trigger_function()"
        ),
        (
            "create materialized view legacy_identity_materialized_view as "
            "select id from team_identity_crosswalks"
        ),
    ],
)
def test_0043_fails_closed_on_postgres_catalog_dependency(dependency_sql: str) -> None:
    database_url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("W2_TEST_POSTGRES_URL is required for PostgreSQL dependency mutation")
    root = Path(__file__).resolve().parents[2]
    env = _arch_p1_02_env(root, database_url)
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("drop schema public cascade"))
        conn.execute(text("create schema public"))
    assert (
        _alembic(
            root,
            env,
            "upgrade",
            "0041_converge_odds_history_and_projection",
        ).returncode
        == 0
    )
    _seed_m2a_baseline(engine)
    assert (
        _alembic(root, env, "upgrade", "0042_team_identity_provider_review_provenance").returncode
        == 0
    )
    with engine.begin() as conn:
        conn.execute(text(dependency_sql))

    result = _alembic(root, env, "upgrade", "head")
    with engine.begin() as conn:
        conn.execute(text("drop schema public cascade"))
        conn.execute(text("create schema public"))

    assert result.returncode != 0
    assert "LEGACY_IDENTITY_M4_DEPENDENCIES" in (result.stdout + result.stderr)


def test_0043_fails_closed_on_unreconciled_team_identity(tmp_path: Path) -> None:
    root, database_url, env = _m2a_env(tmp_path, "m4-unreconciled.db")
    assert (
        _alembic(root, env, "upgrade", "0042_team_identity_provider_review_provenance").returncode
        == 0
    )
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into team_identity_crosswalks (id, api_football_team_id, "
                "transfermarkt_club_id, competition_id, valid_from, review_status, "
                "crosswalk_hash, payload) values "
                "('unreconciled','100','999','allsvenskan',"
                "'2026-01-01T00:00:00+00:00','CANDIDATE','unreconciled','{}')"
            )
        )

    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "LEGACY_IDENTITY_M4_TEAM_AUTHORITY_UNRECONCILED" in (result.stdout + result.stderr)


@pytest.mark.parametrize(
    ("case", "mutation_sql"),
    [
        (
            "missing_transfermarkt",
            "delete from provider_team_identity_crosswalks where provider='transfermarkt'",
        ),
        (
            "ambiguous_api",
            "insert into provider_team_identity_crosswalks "
            "(id,provider,provider_team_id,w2_team_id,competition_id,season,valid_from,"
            "identity_status,evidence_hashes,identity_hash,review_status,reviewed_by,"
            "reviewed_at,source_hashes,payload) "
            "select 'api_football:100:allsvenskan:overlap',provider,provider_team_id,"
            "w2_team_id,competition_id,'2027',valid_from,identity_status,evidence_hashes,"
            "'overlap-hash',review_status,reviewed_by,reviewed_at,source_hashes,payload "
            "from provider_team_identity_crosswalks where provider='api_football'",
        ),
        (
            "expired_api",
            "update provider_team_identity_crosswalks "
            "set valid_to='2026-01-01T00:00:00+00:00' where provider='api_football'",
        ),
        (
            "future_api",
            "update provider_team_identity_crosswalks "
            "set valid_from='2026-01-02T00:00:00+00:00' where provider='api_football'",
        ),
        (
            "expired_transfermarkt",
            "update provider_team_identity_crosswalks "
            "set valid_to='2026-01-01T00:00:00+00:00' where provider='transfermarkt'",
        ),
        (
            "future_transfermarkt",
            "update provider_team_identity_crosswalks "
            "set valid_from='2026-01-02T00:00:00+00:00' where provider='transfermarkt'",
        ),
        (
            "other_season",
            "update provider_team_identity_crosswalks "
            "set season='2025' where provider='transfermarkt'",
        ),
        (
            "identity_hash",
            "update provider_team_identity_crosswalks "
            "set identity_hash='drift' where provider='transfermarkt'",
        ),
        (
            "valid_from",
            "update provider_team_identity_crosswalks "
            "set valid_from='2025-12-31T00:00:00+00:00' where provider='transfermarkt'",
        ),
        (
            "valid_to",
            "update provider_team_identity_crosswalks "
            "set valid_to='2027-01-01T00:00:00+00:00' where provider='transfermarkt'",
        ),
        (
            "reviewed_by",
            "update provider_team_identity_crosswalks "
            "set reviewed_by='other' where provider='transfermarkt'",
        ),
        (
            "reviewed_at",
            "update provider_team_identity_crosswalks "
            "set reviewed_at='2026-02-01T00:00:00+00:00' where provider='transfermarkt'",
        ),
        (
            "source_hashes",
            "update provider_team_identity_crosswalks "
            "set source_hashes='[\"drift\"]' where provider='transfermarkt'",
        ),
        (
            "evidence_hashes",
            "update provider_team_identity_crosswalks "
            "set evidence_hashes='[\"drift\"]' where provider='transfermarkt'",
        ),
        (
            "payload",
            "update provider_team_identity_crosswalks "
            "set payload='[]' where provider='transfermarkt'",
        ),
        (
            "api_review_provenance",
            "update provider_team_identity_crosswalks "
            "set reviewed_by='other' where provider='api_football'",
        ),
        (
            "api_source_hashes",
            "update provider_team_identity_crosswalks "
            "set source_hashes='[\"drift\"]' where provider='api_football'",
        ),
    ],
)
def test_0043_fails_closed_on_reconciliation_mutation(
    tmp_path: Path,
    case: str,
    mutation_sql: str,
) -> None:
    root, database_url, env = _m2a_env(tmp_path, f"m4-reconcile-{case}.db")
    assert (
        _alembic(
            root,
            env,
            "upgrade",
            "0041_converge_odds_history_and_projection",
        ).returncode
        == 0
    )
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    assert (
        _alembic(root, env, "upgrade", "0042_team_identity_provider_review_provenance").returncode
        == 0
    )
    with engine.begin() as conn:
        conn.execute(text(mutation_sql))

    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "LEGACY_IDENTITY_M4_TEAM_AUTHORITY_UNRECONCILED" in (result.stdout + result.stderr)


def _seed_m2a_baseline(engine, *, api_id: str = "100", tm_id: str = "999") -> None:
    params = {
        "api_id": api_id,
        "tm_id": tm_id,
        "w2": f"w2:team:api_football:{api_id}",
        "ptic_id": f"api_football:{api_id}:allsvenskan:2026",
        "team_hash": f"h{api_id}",
        "identity_hash": f"ih{api_id}",
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into canonical_teams (w2_team_id, display_name, country, "
                "active_status, created_at, identity_hash, payload) values "
                "(:w2,'T','SE','ACTIVE','2026-01-01T00:00:00+00:00',:team_hash,'{}')"
            ),
            params,
        )
        conn.execute(
            text(
                "insert into provider_team_identity_crosswalks (id, provider, "
                "provider_team_id, w2_team_id, competition_id, season, valid_from, "
                "identity_status, evidence_hashes, identity_hash) values "
                "(:ptic_id,'api_football',:api_id,:w2,'allsvenskan','2026',"
                "'2026-01-01T00:00:00+00:00','PROVIDER_PRIMARY_READY','[]',:identity_hash)"
            ),
            params,
        )
        conn.execute(
            text(
                "insert into team_identity_crosswalks (id, api_football_team_id, "
                "transfermarkt_club_id, competition_id, valid_from, review_status, "
                "crosswalk_hash, source_sha256, reviewed_by, reviewed_at, payload) values "
                "('tic-1',:api_id,:tm_id,'allsvenskan','2026-01-01T00:00:00+00:00',"
                "'APPROVED','ch1','abc','analyst','2026-01-02T00:00:00+00:00','{}')"
            ),
            params,
        )


def test_0042_blocks_on_divergent_existing_transfermarkt_row(tmp_path: Path) -> None:
    root, database_url, env = _m2a_env(tmp_path, "m2a-divergent.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    with engine.begin() as conn:
        # A pre-existing transfermarkt target row pointing at a DIFFERENT canonical team.
        conn.execute(
            text(
                "insert into canonical_teams (w2_team_id, display_name, country, "
                "active_status, created_at, identity_hash, payload) values "
                "('w2:team:api_football:777','X','SE','ACTIVE',"
                "'2026-01-01T00:00:00+00:00','h777','{}')"
            )
        )
        conn.execute(
            text(
                "insert into provider_team_identity_crosswalks (id, provider, "
                "provider_team_id, w2_team_id, competition_id, season, valid_from, "
                "identity_status, evidence_hashes, identity_hash) values "
                "('transfermarkt:999:allsvenskan:2026','transfermarkt','999',"
                "'w2:team:api_football:777','allsvenskan','2026',"
                "'2026-01-01T00:00:00+00:00','PROVIDER_PRIMARY_READY','[]','other-hash')"
            )
        )

    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "TRANSFERMARKT_TARGET_DIVERGENT" in (result.stderr + result.stdout)


def test_0042_downgrade_keeps_transfermarkt_rows_it_does_not_own(tmp_path: Path) -> None:
    root, database_url, env = _m2a_env(tmp_path, "m2a-downgrade.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    assert _alembic(root, env, "upgrade", "head").returncode == 0

    with engine.begin() as conn:
        # A transfermarkt row owned by something else (foreign id + foreign hash).
        conn.execute(
            text(
                "insert into provider_team_identity_crosswalks (id, provider, "
                "provider_team_id, w2_team_id, competition_id, season, valid_from, "
                "identity_status, evidence_hashes, identity_hash) values "
                "('other-source:555','transfermarkt','555',"
                "'w2:team:api_football:100','allsvenskan','2026',"
                "'2026-01-01T00:00:00+00:00','PROVIDER_PRIMARY_READY','[]','foreign-hash')"
            )
        )

    assert _alembic(root, env, "downgrade", baseline).returncode == 0

    with engine.begin() as conn:
        remaining = (
            conn.execute(
                text(
                    "select id from provider_team_identity_crosswalks "
                    "where provider='transfermarkt'"
                )
            )
            .scalars()
            .all()
        )
    # The migration-owned row is gone; the foreign row survives.
    assert remaining == ["other-source:555"]


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("reviewed_at", "2020-01-01T00:00:00+00:00"),
        ("source_hashes", '["tampered"]'),
        ("valid_from", "2020-01-01T00:00:00+00:00"),
        ("payload", '{"k": "tampered"}'),
    ],
)
def test_0042_blocks_on_provenance_divergence(tmp_path: Path, field: str, tampered: str) -> None:
    """A pre-existing target row diverging on any provenance/validity field blocks."""
    root, database_url, env = _m2a_env(tmp_path, f"m2a-div-{field}.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    assert (
        _alembic(
            root,
            env,
            "upgrade",
            "0042_team_identity_provider_review_provenance",
        ).returncode
        == 0
    )

    with engine.begin() as conn:
        # Tamper one field on the migrated row, then rewind only the alembic
        # version pointer so the migration re-runs against a partially-migrated
        # database whose target row now diverges.
        # Column name comes from this test's own parametrize list, not input.
        where = "where provider='transfermarkt' and provider_team_id='999'"
        update_sql = f"update provider_team_identity_crosswalks set {field} = :value {where}"  # noqa: S608
        conn.execute(text(update_sql), {"value": tampered})
        conn.execute(text("update alembic_version set version_num=:v"), {"v": baseline})

    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert "TRANSFERMARKT_TARGET_DIVERGENT" in output
    assert field in output


def test_0042_downgrade_keeps_foreign_row_that_existed_before_upgrade(tmp_path: Path) -> None:
    """A foreign transfermarkt row present BEFORE upgrade must survive downgrade."""
    root, database_url, env = _m2a_env(tmp_path, "m2a-pre-existing-foreign.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    with engine.begin() as conn:
        # Foreign transfermarkt row for a DIFFERENT provider team id, written
        # before this migration ever ran (no provenance columns yet).
        conn.execute(
            text(
                "insert into provider_team_identity_crosswalks (id, provider, "
                "provider_team_id, w2_team_id, competition_id, season, valid_from, "
                "identity_status, evidence_hashes, identity_hash) values "
                "('legacy-import:555','transfermarkt','555',"
                "'w2:team:api_football:100','allsvenskan','2026',"
                "'2026-01-01T00:00:00+00:00','PROVIDER_PRIMARY_READY','[]','pre-existing')"
            )
        )

    assert _alembic(root, env, "upgrade", "head").returncode == 0
    assert _alembic(root, env, "downgrade", baseline).returncode == 0

    with engine.begin() as conn:
        remaining = (
            conn.execute(
                text(
                    "select id from provider_team_identity_crosswalks "
                    "where provider='transfermarkt'"
                )
            )
            .scalars()
            .all()
        )
    assert remaining == ["legacy-import:555"]


def _transfermarkt_hash(
    tm_id: str, w2: str, comp: str = "allsvenskan", season: str = "2026"
) -> str:
    from w2.matchday.intake_v2 import stable_hash

    return stable_hash(
        {
            "schema_version": "ProviderTeamIdentityCrosswalkV1",
            "provider": "transfermarkt",
            "provider_team_id": tm_id,
            "w2_team_id": w2,
            "competition_id": comp,
            "season": season,
            "identity_status": "PROVIDER_PRIMARY_READY",
            "scope_note": (
                "Transfermarkt provider identity migrated from team_identity_crosswalks."
            ),
        }
    )


def test_0042_downgrade_keeps_unowned_row_with_matching_id_and_hash(tmp_path: Path) -> None:
    """Ownership is the persisted marker, not an inferred id/hash shape.

    A pre-existing row whose id format and identity_hash are exactly what this
    migration would produce must still survive downgrade, because it does not
    carry the persisted ownership marker.
    """
    root, database_url, env = _m2a_env(tmp_path, "m2a-unowned-lookalike.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    assert _alembic(root, env, "upgrade", "head").returncode == 0

    w2 = "w2:team:api_football:100"
    with engine.begin() as conn:
        # Look-alike row: correct id format, correct identity_hash, no marker.
        conn.execute(
            text(
                "insert into provider_team_identity_crosswalks (id, provider, "
                "provider_team_id, w2_team_id, competition_id, season, valid_from, "
                "identity_status, evidence_hashes, identity_hash, payload) values "
                "('transfermarkt:888:allsvenskan:2026','transfermarkt','888',:w2,"
                "'allsvenskan','2026','2026-01-01T00:00:00+00:00',"
                "'PROVIDER_PRIMARY_READY','[]',:h,:payload)"
            ),
            {"w2": w2, "h": _transfermarkt_hash("888", w2), "payload": '{"unrelated": true}'},
        )

    assert _alembic(root, env, "downgrade", baseline).returncode == 0

    with engine.begin() as conn:
        remaining = (
            conn.execute(
                text(
                    "select id from provider_team_identity_crosswalks "
                    "where provider='transfermarkt' order by id"
                )
            )
            .scalars()
            .all()
        )
    # Migration-owned row removed; the unowned look-alike survives.
    assert remaining == ["transfermarkt:888:allsvenskan:2026"]


def test_0042_blocks_when_api_football_authority_is_not_ready(tmp_path: Path) -> None:
    root, database_url, env = _m2a_env(tmp_path, "m2a-authority-not-ready.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "update provider_team_identity_crosswalks set identity_status='CANDIDATE' "
                "where provider='api_football' and provider_team_id='100'"
            )
        )

    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "AUTHORITY_CANONICAL_TARGETS=0" in (result.stderr + result.stdout)


def test_0042_blocks_when_api_football_authority_is_outside_validity(tmp_path: Path) -> None:
    root, database_url, env = _m2a_env(tmp_path, "m2a-authority-expired.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    with engine.begin() as conn:
        # Authority row expires before the legacy row's effective time.
        conn.execute(
            text(
                "update provider_team_identity_crosswalks "
                "set valid_to='2025-01-01T00:00:00+00:00' "
                "where provider='api_football' and provider_team_id='100'"
            )
        )

    result = _alembic(root, env, "upgrade", "head")

    assert result.returncode != 0
    assert "AUTHORITY_CANONICAL_TARGETS=0" in (result.stderr + result.stdout)


def test_0042_accepts_multiple_authority_rows_agreeing_on_one_canonical_team(
    tmp_path: Path,
) -> None:
    """Unique canonical target, not a single row: agreement must not block."""
    root, database_url, env = _m2a_env(tmp_path, "m2a-authority-agree.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)
    with engine.begin() as conn:
        # A second READY authority row for the same provider team and the same
        # canonical target, differing only by valid_from.
        conn.execute(
            text(
                "insert into provider_team_identity_crosswalks (id, provider, "
                "provider_team_id, w2_team_id, competition_id, season, valid_from, "
                "identity_status, evidence_hashes, identity_hash) values "
                "('api_football:100:allsvenskan:2026:b','api_football','100',"
                "'w2:team:api_football:100','allsvenskan','2026',"
                "'2025-06-01T00:00:00+00:00','PROVIDER_PRIMARY_READY','[]','ih100b')"
            )
        )

    # 0042 resolves a unique canonical target/season even when several valid
    # rows agree. The destructive 0043 gate is intentionally stricter and
    # rejects that overlap until the authority rows are de-duplicated.
    assert (
        _alembic(root, env, "upgrade", "0042_team_identity_provider_review_provenance").returncode
        == 0
    )

    with engine.begin() as conn:
        created = (
            conn.execute(
                text(
                    "select w2_team_id from provider_team_identity_crosswalks "
                    "where provider='transfermarkt' and provider_team_id='999'"
                )
            )
            .scalars()
            .all()
        )
    assert created == ["w2:team:api_football:100"]


def test_0042_backfills_only_the_selected_valid_ready_authority_rows(tmp_path: Path) -> None:
    """Mixed authority rows: only the selected valid READY row gains provenance."""
    root, database_url, env = _m2a_env(tmp_path, "m2a-mixed-authority.db")
    baseline = "0041_converge_odds_history_and_projection"
    assert _alembic(root, env, "upgrade", baseline).returncode == 0
    engine = create_engine(database_url)
    _seed_m2a_baseline(engine)  # row A: READY, valid, season 2026 -> selected

    unselected = (
        # (id, season, valid_from, valid_to, identity_status, identity_hash)
        ("candidate", "2026", "2026-02-01T00:00:00+00:00", None, "CANDIDATE", "ihc"),
        (
            "expired",
            "2025",
            "2024-01-01T00:00:00+00:00",
            "2025-01-01T00:00:00+00:00",
            "PROVIDER_PRIMARY_READY",
            "ihe",
        ),
        ("future", "2026", "2027-01-01T00:00:00+00:00", None, "PROVIDER_PRIMARY_READY", "ihf"),
    )
    with engine.begin() as conn:
        for row_id, season, valid_from, valid_to, status, identity_hash in unselected:
            conn.execute(
                text(
                    "insert into provider_team_identity_crosswalks (id, provider, "
                    "provider_team_id, w2_team_id, competition_id, season, valid_from, "
                    "valid_to, identity_status, evidence_hashes, identity_hash) values "
                    "(:id,'api_football','100','w2:team:api_football:100','allsvenskan',"
                    ":season,:valid_from,:valid_to,:status,'[]',:identity_hash)"
                ),
                {
                    "id": f"api_football:100:allsvenskan:{row_id}",
                    "season": season,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "status": status,
                    "identity_hash": identity_hash,
                },
            )

    assert _alembic(root, env, "upgrade", "head").returncode == 0

    with engine.begin() as conn:
        provenance = dict(
            conn.execute(
                text(
                    "select id, review_status from provider_team_identity_crosswalks "
                    "where provider='api_football'"
                )
            ).all()
        )
    # Only the selected valid READY row carries review provenance.
    assert provenance["api_football:100:allsvenskan:2026"] == "APPROVED"
    for row_id, *_ in unselected:
        assert provenance[f"api_football:100:allsvenskan:{row_id}"] is None
