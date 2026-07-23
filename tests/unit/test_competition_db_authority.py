from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from w2.competitions.registry import CompetitionRegistry
from w2.competitions.seed import seed_competition_runtime_authority, set_competition_enabled
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.league_models import LeagueReadinessAuditModel


def _seeded_engine(environment: str = "production"):  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    report = seed_competition_runtime_authority(
        engine,
        environment=environment,
        updated_by="unit-test-seed",
        now=datetime(2026, 7, 23, tzinfo=UTC),
    )
    assert report.conflicts == ()
    return engine, report


def test_seed_is_idempotent_and_reconciles_all_json_profiles() -> None:
    engine, first = _seeded_engine()
    second = seed_competition_runtime_authority(
        engine,
        environment="production",
        updated_by="unit-test-seed-rerun",
    )

    assert first.inserted_profiles == 14
    assert first.inserted_seasons == 14
    assert first.audits_written == 14
    assert second.inserted_profiles == 0
    assert second.inserted_seasons == 0
    assert second.unchanged == 14
    assert second.audits_written == 0


def test_staging_policy_is_seeded_into_database_without_env_override() -> None:
    engine, _report = _seeded_engine("staging")

    assert CompetitionRegistry(engine).enabled_ids() == {
        "world_cup_2026",
        "brasileirao_serie_a",
        "chinese_super_league",
        "allsvenskan",
        "eliteserien",
    }


def test_enabled_change_is_visible_to_same_registry_without_deploy() -> None:
    engine, _report = _seeded_engine()
    registry = CompetitionRegistry(engine)
    assert registry.is_enabled("allsvenskan") is False

    audit_hash = set_competition_enabled(
        engine,
        competition_id="allsvenskan",
        enabled=True,
        updated_by="unit-test-operator",
        now=datetime(2026, 7, 23, 1, tzinfo=UTC),
    )

    assert registry.is_enabled("allsvenskan") is True
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(LeagueReadinessAuditModel)
                .where(LeagueReadinessAuditModel.audit_sha256 == audit_hash)
            )
            == 1
        )


def test_runtime_authority_modules_do_not_read_install_seed_json() -> None:
    paths = (
        "src/w2/competitions/registry.py",
        "src/w2/ingestion/future_refresh.py",
        "src/w2/matchday/intake_v2.py",
        "apps/scheduler/main.py",
    )
    forbidden = (
        "config/competitions",
        "future_fixture_refresh.v1.json",
        "matchday_intake.v2.json",
        "W2_STAGING_ENABLED_COMPETITIONS",
    )
    for path in paths:
        source = Path(path).read_text(encoding="utf-8")
        assert not any(value in source for value in forbidden), path


def test_production_code_cannot_read_competition_install_seed_files() -> None:
    allowed = {
        Path("src/w2/competitions/seed.py"),
        Path("src/w2/historical/existing_data_inventory.py"),
    }
    for root in (Path("src"), Path("apps")):
        for path in root.rglob("*.py"):
            if path in allowed:
                continue
            source = path.read_text(encoding="utf-8")
            assert "config/competitions" not in source, path
            assert "config_path.read_text" not in source, path
            assert "future_fixture_refresh.v1.json" not in source, path
            assert "matchday_intake.v2.json" not in source, path
