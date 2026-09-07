"""Task 3 capture-fix integration test: real ANALYSIS_READY chain.

Proves the real production chain (not a hand-written ``READY`` fixture) produces a
capture:

    _empirical_xg_lambda_uncertainty()  -> ANALYSIS_READY + sigma
        -> run_simulation(SimulationInputs)
        -> day_view/card
        -> _build_capture() -> payload persistence
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from w2.prematch import analysis_calculator as api_repository
from w2.prematch.analysis_calculator import ReadModelService
from w2.strategy.simulate import SimulationInputs, run_simulation
from w2.tracking.model_forecast_ledger import (
    ModelForecastLedgerRepository,
    run_model_forecast_capture,
)

NOW = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=12)


class _FixtureRepository:
    def release_counts(self) -> dict[str, int]:
        return {
            "read_model_fixture_count": 1,
            "matchday_card_count": 0,
            "future_fixture_count": 1,
            "result_event_count": 0,
        }

    def staging_seed_dashboard(self) -> dict[str, Any] | None:
        return None

    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        return []

    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return None

    def result_events(self) -> list[dict[str, Any]]:
        return []

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "id": "fixture-xg",
                    "date": KICKOFF.isoformat().replace("+00:00", "Z"),
                    "status": {"short": "NS"},
                },
                "league": {"id": 1, "name": "World Cup"},
                "teams": {
                    "home": {"id": 10, "name": "Strong"},
                    "away": {"id": 20, "name": "Weak"},
                },
            }
        ]

    def future_market_observations(self) -> list[dict[str, Any]]:
        return []


class _XgStore:
    """Provides rolling xg matches with real xg_for/xg_against variance so the
    empirical lambda uncertainty computes a positive sigma and ANALYSIS_READY."""

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        return []

    def team_xg_rolling_snapshots(self, *, fixture_id: str | None = None) -> list[dict[str, Any]]:
        return [
            {
                "team_id": "10",
                "match_count": 4,
                "as_of_time": (KICKOFF - timedelta(hours=1)).isoformat(),
                "rolling_xg_for": 1.9,
                "rolling_xg_against": 0.7,
                "rolling_goals_for": 2.0,
                "rolling_goals_against": 0.8,
            },
            {
                "team_id": "20",
                "match_count": 4,
                "as_of_time": (KICKOFF - timedelta(hours=1)).isoformat(),
                "rolling_xg_for": 0.8,
                "rolling_xg_against": 1.5,
                "rolling_goals_for": 0.8,
                "rolling_goals_against": 1.6,
            },
        ]

    def team_xg_matches(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for team_id, base_for, base_against in (("10", 1.0, 0.6), ("20", 0.8, 1.2)):
            for index in range(4):
                rows.append(
                    {
                        "team_id": team_id,
                        "fixture_id": f"hist-{team_id}-{index}",
                        "kickoff_at": (NOW - timedelta(days=6 - index)).isoformat(),
                        "captured_at": (NOW - timedelta(days=5 - index)).isoformat(),
                        "xg_for": base_for + index * 0.3,
                        "xg_against": base_against + index * 0.1,
                        "raw_payload_sha256": f"{index + 1}" * 64,
                        "source_system": "api_football_statistics",
                    }
                )
        return rows


def _ledger_repository(tmp_path) -> ModelForecastLedgerRepository:
    from sqlalchemy import create_engine

    from w2.infrastructure.persistence.future_refresh_models import (
        TeamXgMatchModel,
        TeamXgRollingSnapshotModel,
    )
    from w2.infrastructure.persistence.model_forecast_models import (
        ModelForecastCaptureDataVersionModel,
        ModelForecastCaptureModel,
        ModelForecastOutcomeModel,
    )
    from w2.infrastructure.persistence.models import ResultModel

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'integration.db'}")
    for model in (
        TeamXgMatchModel,
        TeamXgRollingSnapshotModel,
        ModelForecastCaptureModel,
        ModelForecastCaptureDataVersionModel,
        ModelForecastOutcomeModel,
        ResultModel,
    ):
        model.__table__.create(engine)
    return ModelForecastLedgerRepository(engine)


def _seed_xg(repository: ModelForecastLedgerRepository) -> None:
    from sqlalchemy.orm import Session

    from w2.infrastructure.persistence.future_refresh_models import (
        TeamXgMatchModel,
        TeamXgRollingSnapshotModel,
    )

    with Session(repository.engine) as session:
        for team_id, opponent, xg_for, xg_against in (
            ("10", "20", 1.9, 0.7),
            ("20", "10", 0.8, 1.5),
        ):
            for index in range(4):
                session.add(
                    TeamXgMatchModel(
                        id=f"history-{index}:{team_id}",
                        fixture_id=f"history-{index}",
                        team_id=team_id,
                        opponent_team_id=opponent,
                        kickoff_at=NOW - timedelta(days=4 - index),
                        captured_at=NOW - timedelta(days=3 - index),
                        xg_for=xg_for,
                        xg_against=xg_against,
                        goals_for=1,
                        goals_against=0,
                        raw_payload_sha256=f"{index + 1}" * 64,
                        source_system="api_football_statistics",
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
            session.add(
                TeamXgRollingSnapshotModel(
                    snapshot_id=f"{team_id}:fixture-1",
                    team_id=team_id,
                    as_of_fixture_id="fixture-1",
                    as_of_time=KICKOFF,
                    match_count=4,
                    rolling_xg_for=xg_for,
                    rolling_xg_against=xg_against,
                    rolling_goals_for=1.0,
                    rolling_goals_against=0.0,
                    regression_index=0.0,
                    source_system="team_xg_match",
                    candidate=False,
                    formal_recommendation=False,
                )
            )
        session.commit()


def test_real_analysis_ready_chain_produces_capture(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real chain: empirical lambda uncertainty -> ANALYSIS_READY -> capture."""
    monkeypatch.setattr(
        api_repository, "future_refresh_db_repository", lambda: _XgStore()
    )
    service = ReadModelService(repository=cast(Any, _FixtureRepository()))

    uncertainty = service._empirical_xg_lambda_uncertainty(
        fixture_id="fixture-xg",
        as_of=NOW,
        home_team_id="10",
        away_team_id="20",
    )

    # 真实计算必须返回 ANALYSIS_READY + 非零 sigma
    assert uncertainty["lambda_uncertainty_status"] == "ANALYSIS_READY"
    assert uncertainty["lambda_sigma_home"] is not None
    assert uncertainty["lambda_sigma_home"] > 0
    assert uncertainty["lambda_sigma_away"] is not None
    assert uncertainty["lambda_sigma_away"] > 0

    # 用真实 sigma 走 run_simulation
    simulation = run_simulation(
        SimulationInputs(
            fixture_id="fixture-1",
            home_team_id="10",
            away_team_id="20",
            home_xg_for=1.9,
            home_xg_against=0.7,
            away_xg_for=0.8,
            away_xg_against=1.5,
            lambda_sigma_home=float(uncertainty["lambda_sigma_home"]),
            lambda_sigma_away=float(uncertainty["lambda_sigma_away"]),
            lambda_uncertainty_method=str(uncertainty["lambda_uncertainty_method"]),
            lambda_uncertainty_status=str(uncertainty["lambda_uncertainty_status"]),
            lambda_uncertainty_audit=dict(uncertainty["lambda_uncertainty_audit"]),
            neutral_site=False,
            input_readiness={
                "lambda_uncertainty_input_hash": str(uncertainty["lambda_uncertainty_input_hash"]),
            },
        )
    )

    repository = _ledger_repository(tmp_path)
    _seed_xg(repository)

    day_view = {
        "cards": [
            {
                "fixture_id": "fixture-1",
                "competition_id": "premier_league",
                "kickoff_utc": KICKOFF.isoformat(),
                "decision_tier": "NOT_READY",
                "outcome_tracked": False,
                "neutral_site_resolution": {
                    "neutral_site": False,
                    "neutral_site_resolution_source": "DEFAULT_NON_NEUTRAL_POLICY",
                    "neutral_site_policy_version": "w2.neutral_site_policy.v1",
                    "neutral_site_as_of": NOW.isoformat(),
                    "neutral_site_status": "READY",
                },
                "frozen_artifact_provenance": {
                    "artifact_hash": "c" * 64,
                    "source_hash": "d" * 64,
                    "fixture_identity": {
                        "fixture_id": "fixture-1",
                        "competition_id": "premier_league",
                        "kickoff_utc": KICKOFF.isoformat(),
                        "home_team_id": "10",
                        "away_team_id": "20",
                    },
                    "input_manifest": {"simulation_sha256": "e" * 64},
                },
                "simulation": {"status": "READY", "simulation": simulation.as_dict()},
            }
        ]
    }

    result = run_model_forecast_capture(
        day_view,
        repository=repository,
        captured_at=NOW,
        dry_run=False,
        write_db=True,
    )

    assert result["model_eligible_count"] == 1
    assert result["model_forecast_capture_count"] == 1
    assert result["no_neutral_site_or_lambda_count"] == 0

    from sqlalchemy.orm import Session

    from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel

    with Session(repository.engine) as session:
        capture = session.query(ModelForecastCaptureModel).one()
        payload = capture.payload

    assert payload["lambda_uncertainty_status"] == "ANALYSIS_READY"
    assert payload["lambda_sigma_home"] > 0
    assert payload["lambda_sigma_away"] > 0
    assert payload["neutral_site"] is False
    assert payload["neutral_site_resolution_source"] == "DEFAULT_NON_NEUTRAL_POLICY"
