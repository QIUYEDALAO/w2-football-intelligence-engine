from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.competitions.seed import _hash as stable_hash
from w2.infrastructure.persistence.future_refresh_models import TeamXgMatchModel
from w2.infrastructure.persistence.league_models import (
    LeagueProfileModel,
    LeagueReadinessAuditModel,
    LeagueSeasonModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayFixtureIdentityModel,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "reenable_competition_after_xg_recovery",
    ROOT / "scripts/reenable_competition_after_xg_recovery.py",
)
assert SPEC is not None and SPEC.loader is not None
RECOVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOVERY)
NOW = datetime(2026, 8, 24, 10, tzinfo=UTC)


def _plan(plan_id: str, window_end: datetime, blockers: list[str]):
    return MatchdayCheckpointPlanModel(
        plan_id=plan_id,
        fixture_id="allsvenskan:fixture-1",
        competition_id="allsvenskan",
        season="2026",
        policy_version=f"test-{plan_id}",
        checkpoint="T30_VALIDATION_LOCK",
        kickoff_utc=NOW + timedelta(hours=2),
        scheduled_at=NOW + timedelta(hours=1),
        window_start=NOW,
        window_end=window_end,
        endpoints=["fixtures/statistics"],
        status="SKIPPED_POLICY",
        attempt_count=0,
        test_only=False,
        blockers=blockers,
        plan_hash="d" * 64,
    )


def _engine():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    LeagueProfileModel.__table__.create(engine)
    LeagueSeasonModel.__table__.create(engine)
    LeagueReadinessAuditModel.__table__.create(engine)
    MatchdayFixtureIdentityModel.__table__.create(engine)
    MatchdayCheckpointPlanModel.__table__.create(engine)
    TeamXgMatchModel.__table__.create(engine)
    with Session(engine) as session:
        session.add_all(
            [
                LeagueSeasonModel(
                    id="season-allsvenskan-2026",
                    competition_id="allsvenskan",
                    season="2026",
                    lifecycle="DISABLED",
                    payload={"enabled": False},
                ),
                LeagueSeasonModel(
                    id="season-csl-2026",
                    competition_id="chinese_super_league",
                    season="2026",
                    lifecycle="DISABLED",
                    payload={"enabled": False},
                ),
                LeagueProfileModel(
                    id="profile-allsvenskan",
                    competition_id="allsvenskan",
                    name="Allsvenskan",
                    country="Sweden",
                    payload={"current_season": "2026"},
                ),
                LeagueProfileModel(
                    id="profile-csl",
                    competition_id="chinese_super_league",
                    name="Chinese Super League",
                    country="China",
                    payload={"current_season": "2026"},
                ),
                MatchdayFixtureIdentityModel(
                    fixture_id="allsvenskan:fixture-1",
                    provider="api-football",
                    provider_fixture_id="1494246",
                    competition_id="allsvenskan",
                    provider_league_id="113",
                    season="2026",
                    kickoff_utc=NOW - timedelta(days=2),
                    fixture_status="FT",
                    home_provider_team_id="home",
                    away_provider_team_id="away",
                    home_w2_team_id="home",
                    away_w2_team_id="away",
                    team_identity_status="RESOLVED",
                    raw_payload_sha256="a" * 64,
                    captured_at=NOW - timedelta(days=2),
                    identity_hash="b" * 64,
                    payload={},
                ),
            ]
        )
        for team_id, opponent_id, xg_for, xg_against in (
            ("home", "away", 1.2, 0.8),
            ("away", "home", 0.8, 1.2),
        ):
            session.add(
                TeamXgMatchModel(
                    id=f"1494246:{team_id}",
                    fixture_id="1494246",
                    team_id=team_id,
                    opponent_team_id=opponent_id,
                    kickoff_at=NOW - timedelta(days=2),
                    captured_at=NOW - timedelta(days=1),
                    xg_for=xg_for,
                    xg_against=xg_against,
                    goals_for=1,
                    goals_against=1,
                    raw_payload_sha256="c" * 64,
                    source_system="api-football",
                )
            )
        session.add_all(
            [
                _plan("eligible", NOW + timedelta(hours=2), [RECOVERY.DISABLED_BLOCKER]),
                _plan("expired", NOW - timedelta(seconds=1), [RECOVERY.DISABLED_BLOCKER]),
                _plan(
                    "extra-blocker",
                    NOW + timedelta(hours=2),
                    [RECOVERY.DISABLED_BLOCKER, "OTHER"],
                ),
            ]
        )
        session.commit()
    return engine


def test_only_allsvenskan_is_owner_approved() -> None:
    with pytest.raises(ValueError, match="COMPETITION_NOT_OWNER_APPROVED"):
        RECOVERY.recover_competition(
            competition_id="chinese_super_league",
            apply=False,
            updated_by="test",
            now=NOW,
            engine=_engine(),
        )


def test_dry_run_selects_only_exact_unexpired_blocker() -> None:
    result = RECOVERY.recover_competition(
        competition_id="allsvenskan",
        apply=False,
        updated_by="test",
        now=NOW,
        engine=_engine(),
    )

    assert result["coverage_30d"] == {"covered": 1, "finished": 1, "percent": 100.0}
    assert result["reopen_plan_count"] == 1
    assert result["reopen_plan_set_sha256"] == stable_hash(["eligible"])


def test_allsvenskan_recovery_fails_if_csl_is_enabled() -> None:
    engine = _engine()
    with Session(engine) as session:
        csl = session.scalar(
            select(LeagueSeasonModel).where(
                LeagueSeasonModel.competition_id == "chinese_super_league"
            )
        )
        assert csl is not None
        csl.payload = {"enabled": True}
        session.commit()

    with pytest.raises(ValueError, match="PROTECTED_COMPETITION_MUST_REMAIN_DISABLED"):
        RECOVERY.recover_competition(
            competition_id="allsvenskan",
            apply=False,
            updated_by="test",
            now=NOW,
            engine=engine,
        )


def test_apply_requires_all_three_evidence_gates() -> None:
    engine = _engine()
    with pytest.raises(ValueError, match="PRODUCTION_DECISION_ID_REQUIRED"):
        RECOVERY.recover_competition(
            competition_id="allsvenskan",
            apply=True,
            updated_by="test",
            now=NOW,
            engine=engine,
        )

    with Session(engine) as session:
        season = session.scalar(
            select(LeagueSeasonModel).where(LeagueSeasonModel.competition_id == "allsvenskan")
        )
        assert season is not None and season.payload["enabled"] is False


def test_apply_reopens_exact_frozen_set_and_audits_authority() -> None:
    engine = _engine()
    plan_set_hash = stable_hash(["eligible"])
    result = RECOVERY.recover_competition(
        competition_id="allsvenskan",
        apply=True,
        updated_by="owner-approved-runner",
        now=NOW,
        engine=engine,
        production_decision_id="ALLSV-RESTORE-01-DECISION-C",
        deployment_evidence_sha256="1" * 64,
        backfill_evidence_sha256="2" * 64,
        capacity_evidence_sha256="3" * 64,
        expected_reopen_plan_count=1,
        expected_reopen_plan_set_sha256=plan_set_hash,
    )

    assert result["audit_sha256"]
    with Session(engine) as session:
        seasons = {row.competition_id: row for row in session.scalars(select(LeagueSeasonModel))}
        plans = {row.plan_id: row for row in session.scalars(select(MatchdayCheckpointPlanModel))}
        audit = session.scalar(select(LeagueReadinessAuditModel))

    assert seasons["allsvenskan"].payload["enabled"] is True
    assert seasons["chinese_super_league"].payload["enabled"] is False
    assert plans["eligible"].status == "PLANNED"
    assert plans["eligible"].blockers == []
    assert plans["expired"].status == "SKIPPED_POLICY"
    assert plans["extra-blocker"].status == "SKIPPED_POLICY"
    assert audit is not None
    assert audit.payload["reopened_plan_ids"] == ["eligible"]
    assert audit.payload["capacity_evidence_sha256"] == "3" * 64


def test_plan_set_drift_fails_before_write() -> None:
    engine = _engine()
    with pytest.raises(ValueError, match="REOPEN_PLAN_SET_DRIFT"):
        RECOVERY.recover_competition(
            competition_id="allsvenskan",
            apply=True,
            updated_by="test",
            now=NOW,
            engine=engine,
            production_decision_id="decision",
            deployment_evidence_sha256="1" * 64,
            backfill_evidence_sha256="2" * 64,
            capacity_evidence_sha256="3" * 64,
            expected_reopen_plan_count=1,
            expected_reopen_plan_set_sha256="4" * 64,
        )


def test_xg_refresh_reads_dynamic_enabled_scope() -> None:
    source = (ROOT / "ops/host/w2-xg-refresh").read_text()

    assert "FROM league_season s" in source
    assert "JOIN league_profile p" in source
    assert "(s.payload->>'enabled')::boolean IS TRUE" in source
    assert "s.season = p.payload->>'current_season'" in source
    assert "chinese_super_league allsvenskan" not in source
    assert '"${COMPOSE[@]}" run --rm --no-deps --entrypoint python' in source
    assert "docker exec -e W2_XG_BACKFILL_COMPETITION_ID" not in source
