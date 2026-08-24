from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from w2.api.repository import ANALYSIS_CARD_SHADOW_PREFIX, ReadModelRepository, ReadModelService
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.league_models import LeagueProfileModel, LeagueSeasonModel
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel


def _engine() -> Any:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _profile(competition_id: str) -> LeagueProfileModel:
    return LeagueProfileModel(
        id=f"profile-{competition_id}",
        competition_id=competition_id,
        name=competition_id,
        country="test",
        payload={
            "current_season": "2026",
            "coverage_profile": {
                "xg": "AVAILABLE",
                "lineups_injuries": "AVAILABLE",
                "squad_value": "AVAILABLE",
                "bookmaker_depth": "AVAILABLE",
                "h2h": "AVAILABLE",
                "settled_ah": "AVAILABLE",
            },
            "install_seed": {"source": "tests"},
            "scope_group": "national_leagues",
            "audit_cohort": "IN_SEASON",
            "audit_order": 1,
            "competition_profile": {},
        },
    )


def _season(competition_id: str, *, enabled: bool) -> LeagueSeasonModel:
    return LeagueSeasonModel(
        id=f"season-{competition_id}",
        competition_id=competition_id,
        season="2026",
        lifecycle="ACTIVE",
        payload={
            "environment": "local",
            "enabled": enabled,
            "provider": "api_football",
            "provider_league_id": competition_id,
            "provider_season": "2026",
        },
    )


def _fixture(competition_id: str, fixture_id: str) -> MatchdayFixtureIdentityModel:
    kickoff = datetime(2026, 8, 24, 17, tzinfo=UTC)
    return MatchdayFixtureIdentityModel(
        fixture_id=f"api_football:{fixture_id}",
        provider="api_football",
        provider_fixture_id=fixture_id,
        competition_id=competition_id,
        provider_league_id=competition_id,
        season="2026",
        kickoff_utc=kickoff,
        fixture_status="NS",
        home_provider_team_id=f"home-{fixture_id}",
        away_provider_team_id=f"away-{fixture_id}",
        home_w2_team_id=None,
        away_w2_team_id=None,
        team_identity_status="REVIEW_REQUIRED",
        raw_payload_sha256=fixture_id.rjust(64, "0"),
        captured_at=kickoff,
        identity_hash=fixture_id.rjust(64, "1"),
        payload={"home_team_name": "Home", "away_team_name": "Away"},
    )


def _seed_scope(engine: Any) -> None:
    with Session(engine) as session:
        for competition_id, enabled, fixture_id in (
            ("enabled_league", True, "1001"),
            ("disabled_league", False, "1002"),
        ):
            session.add(_profile(competition_id))
            session.add(_season(competition_id, enabled=enabled))
            session.add(_fixture(competition_id, fixture_id))
            session.add(
                ReadModelCheckpointModel(
                    id=f"checkpoint-{fixture_id}",
                    checkpoint_key=f"{ANALYSIS_CARD_SHADOW_PREFIX}{fixture_id}",
                    source_hash=fixture_id.rjust(64, "2"),
                    created_at=datetime(2026, 8, 24, 8, tzinfo=UTC),
                    payload={"analysis_card": {"status": "NS"}},
                )
            )
        session.commit()


def test_public_projection_scope_comes_from_enabled_league_season(monkeypatch: Any) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "local")
    engine = _engine()
    _seed_scope(engine)
    repository = ReadModelRepository(engine=engine)
    monkeypatch.setattr(
        repository,
        "_analysis_card_from_checkpoint",
        lambda _row, fixture_id: {
            "fixture_id": fixture_id,
            "competition_id": "enabled_league",
            "kickoff_utc": "2026-08-24T17:00:00Z",
            "status": "NS",
            "home_team_name": "Home",
            "away_team_name": "Away",
        },
    )

    assert repository._dashboard_competition_ids() == ("enabled_league",)
    assert [row["fixture_id"] for row in repository.dashboard_latest_fixtures()] == ["1001"]
    assert repository.analysis_card_projection("1002") is None
    assert repository.dashboard_fixture("1002") is None
    assert repository.release_counts() == {
        "read_model_fixture_count": 1,
        "matchday_card_count": 1,
        "future_fixture_count": 1,
        "result_event_count": 0,
    }
    assert repository.persisted_date_strip(
        datetime(2026, 8, 24, tzinfo=UTC).date(),
        now=datetime(2026, 8, 24, 8, tzinfo=UTC),
    )[7]["active_whitelist_count"] == 1


def test_matchday_cannot_reintroduce_a_disabled_projection(monkeypatch: Any) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "local")
    engine = _engine()
    _seed_scope(engine)
    repository = ReadModelRepository(engine=engine)
    monkeypatch.setattr(
        repository,
        "_analysis_card_from_checkpoint",
        lambda _row, fixture_id: {
            "fixture_id": fixture_id,
            "competition_id": "enabled_league",
            "kickoff_utc": "2026-08-24T17:00:00Z",
            "status": "NS",
        },
    )
    service = ReadModelService(repository=repository)
    monkeypatch.setattr(
        service,
        "_project_dashboard_card",
        lambda row: {
            "fixture_id": row["fixture_id"],
            "competition_id": row["competition_id"],
            "kickoff_utc": row["kickoff_utc"],
            "status": "SCHEDULED",
        },
    )

    payload = service.matchday(target_date="2026-08-24")

    assert payload["total"] == 1
    assert [row["fixture_id"] for row in payload["items"]] == ["1001"]


def test_release_sync_preflight_rejects_mixed_image_revisions(tmp_path: Path) -> None:
    fake_docker = tmp_path / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$3\" in\n"
        "  python-image) echo python-sha ;;\n"
        "  web-image) echo web-sha ;;\n"
        "  synced-web-image) echo python-sha ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    script = Path("ops/host/w2-release-sync-preflight").resolve()
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}

    mismatch = subprocess.run(
        [script, "python-image", "web-image"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    synced = subprocess.run(
        [script, "python-image", "synced-web-image", "python-sha"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert mismatch.returncode == 2
    assert "RELEASE_BLOCKED_WEB_PYTHON_REVISION_MISMATCH" in mismatch.stderr
    assert synced.returncode == 0
    assert "RELEASE_SYNC_PREFLIGHT_OK" in synced.stdout


def test_web_scope_check_rejects_single_field_mutation(tmp_path: Path) -> None:
    evidence = Path(
        "docs/review_packages/WEB_SCOPE_01/WEB_SCOPE_01_EVIDENCE.json"
    ).resolve()
    mutated = json.loads(evidence.read_text(encoding="utf-8"))
    mutated["scope_retention_ratio"] += 0.000001
    mutated_path = tmp_path / "mutated.json"
    mutated_path.write_text(json.dumps(mutated), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_web_scope_01.py",
            "--check",
            "--evidence",
            str(mutated_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "WEB_SCOPE_01_CHECK_FAILED" in result.stderr
