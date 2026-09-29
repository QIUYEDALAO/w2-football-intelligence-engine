"""AH/OU v3 接线真实链正例（S2/S3/S4 接线验收）。

producer（Pinnacle AH/OU 双侧 odds）→ capture（endpoint capture）→ frozen
（raw payload）→ repository（F9 快照 + F6 交锋，正式 upsert）→ 自动 forward
（_db_analysis_card_from_fixture → v3 选择器 → softmax → 新账本）→ commit →
DB 实读。

禁止手工补调 forward：本测试只走 `_db_analysis_card_from_fixture`，账本写入由
`_softmax_ah_ou_selections` 内的 `_write_ah_ou_decision_ledger` 自动触发。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
    AhOuCohortModel,
    AhOuDecisionLedgerModel,
)
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.future_refresh_models import (
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.prematch.analysis_calculator import ReadModelService

from tests.integration.test_future_refresh_db_persistence import (
    FakeApiFootballClient,
    NOW,
    configure_sqlite_db,
    run_direct_checkpoint,
    seed_odds_checkpoint,
)

FIXTURE_ID = "1489404"
KICKOFF = NOW + timedelta(hours=7)
COMPETITION = "allsvenskan"
SEASON = "2026"


class PinnacleAhOuClient(FakeApiFootballClient):
    """Provides Pinnacle (id=4) two-sided AH and OU in one odds capture."""

    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "odds":
            return {
                "response": [
                    {
                        "fixture": {"id": int(params["fixture"])},
                        "bookmakers": [
                            {
                                "id": 4,
                                "name": "Pinnacle",
                                "bets": [
                                    {
                                        "id": 1,
                                        "name": "Asian Handicap",
                                        "values": [
                                            {"value": "Home -0.5", "odd": "1.80"},
                                            {"value": "Away +0.5", "odd": "2.05"},
                                        ],
                                    },
                                    {
                                        "id": 2,
                                        "name": "Goals Over/Under",
                                        "values": [
                                            {"value": "Over 2.5", "odd": "1.90"},
                                            {"value": "Under 2.5", "odd": "1.90"},
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        return super().payload(endpoint, params)


def _seed_identity_and_repository(engine: Any, repository: Any) -> None:
    """Seed canonical teams / crosswalk / F9 snapshot / F6 history (formal upserts)."""
    with Session(engine) as session:
        session.add_all(
            [
                CanonicalTeamModel(
                    w2_team_id="H",
                    display_name="Home W2",
                    active_status="ACTIVE",
                    created_at=NOW,
                    identity_hash="h" * 64,
                    payload={},
                ),
                CanonicalTeamModel(
                    w2_team_id="A",
                    display_name="Away W2",
                    active_status="ACTIVE",
                    created_at=NOW,
                    identity_hash="a" * 64,
                    payload={},
                ),
            ]
        )
        session.add_all(
            [
                ProviderTeamIdentityCrosswalkModel(
                    id="xw-10",
                    provider="api_football",
                    provider_team_id="10",
                    w2_team_id="H",
                    competition_id=COMPETITION,
                    season=SEASON,
                    valid_from=NOW - timedelta(days=1),
                    identity_status="READY",
                    evidence_hashes=[],
                    identity_hash="x" * 64,
                ),
                ProviderTeamIdentityCrosswalkModel(
                    id="xw-20",
                    provider="api_football",
                    provider_team_id="20",
                    w2_team_id="A",
                    competition_id=COMPETITION,
                    season=SEASON,
                    valid_from=NOW - timedelta(days=1),
                    identity_status="READY",
                    evidence_hashes=[],
                    identity_hash="y" * 64,
                ),
            ]
        )
        session.add_all(
            [
                TeamXgRollingSnapshotModel(
                    snapshot_id="snap-10",
                    team_id="10",
                    as_of_fixture_id=FIXTURE_ID,
                    as_of_time=NOW - timedelta(days=1),
                    match_count=8,
                    rolling_xg_for=1.2,
                    rolling_xg_against=0.8,
                    rolling_goals_for=1.1,
                    rolling_goals_against=0.7,
                    regression_index=0.0,
                    source_system="test",
                    first_captured_at=NOW - timedelta(days=1),
                    pit_proven=True,
                ),
                TeamXgRollingSnapshotModel(
                    snapshot_id="snap-20",
                    team_id="20",
                    as_of_fixture_id=FIXTURE_ID,
                    as_of_time=NOW - timedelta(days=1),
                    match_count=8,
                    rolling_xg_for=0.9,
                    rolling_xg_against=1.0,
                    rolling_goals_for=0.8,
                    rolling_goals_against=1.1,
                    regression_index=0.0,
                    source_system="test",
                    first_captured_at=NOW - timedelta(days=1),
                    pit_proven=True,
                ),
            ]
        )
        session.add_all(
            [
                CanonicalTeamMatchHistoryModel(
                    history_id="hist-1",
                    fixture_id="api_football:past-1",
                    provider="api_football",
                    provider_fixture_id="past-1",
                    competition_id=COMPETITION,
                    season=SEASON,
                    kickoff_utc=NOW - timedelta(days=30),
                    fixture_status="FT",
                    team_side="AWAY",
                    team_provider_id="10",
                    opponent_provider_id="20",
                    team_w2_id="H",
                    opponent_w2_id="A",
                    goals_for=1,
                    goals_against=0,
                    result_identity_hash="r" * 64,
                    source_raw_hash="s" * 64,
                    endpoint_capture_id=None,
                    captured_at=NOW - timedelta(days=29),
                    history_hash="hh" * 32,
                    payload={},
                    status_first_visible_at=NOW - timedelta(days=29),
                    pit_proven=True,
                ),
                CanonicalTeamMatchHistoryModel(
                    history_id="hist-2",
                    fixture_id="api_football:past-2",
                    provider="api_football",
                    provider_fixture_id="past-2",
                    competition_id=COMPETITION,
                    season=SEASON,
                    kickoff_utc=NOW - timedelta(days=10),
                    fixture_status="FT",
                    team_side="HOME",
                    team_provider_id="10",
                    opponent_provider_id="20",
                    team_w2_id="H",
                    opponent_w2_id="A",
                    goals_for=2,
                    goals_against=1,
                    result_identity_hash="r2" * 32,
                    source_raw_hash="s2" * 32,
                    endpoint_capture_id=None,
                    captured_at=NOW - timedelta(days=9),
                    history_hash="hh2" * 32,
                    payload={},
                    status_first_visible_at=NOW - timedelta(days=9),
                    pit_proven=True,
                ),
            ]
        )
        session.commit()

    # Bind a READY fixture identity so the canonical (w2) team path is used.
    with Session(engine) as session:
        identity = session.scalar(
            select(MatchdayFixtureIdentityModel).where(
                MatchdayFixtureIdentityModel.fixture_id == f"api_football:{FIXTURE_ID}"
            )
        )
        assert identity is not None
        identity.home_w2_team_id = "H"
        identity.away_w2_team_id = "A"
        identity.team_identity_status = "READY"
        session.commit()


def test_v3_wiring_real_chain_writes_ledger(tmp_path: Any, monkeypatch: Any) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)
    repository = FutureRefreshDbRepositoryForTest()
    seed_odds_checkpoint(FIXTURE_ID, with_identity=True)
    checkpoints = repository_claim_checkpoints()
    client = PinnacleAhOuClient()
    run_direct_checkpoint(tmp_path, client, *checkpoints)

    # repository F9/F6 (formal upsert) + READY fixture identity
    _seed_identity_and_repository(repository.engine, repository)

    # producer fixture payload (item) + the observations captured above
    item = FakeApiFootballClient().payload("fixtures", {})["response"][0]
    item["fixture"]["id"] = int(FIXTURE_ID)
    item["fixture"]["date"] = KICKOFF.isoformat()
    item["league"] = {"id": 113, "name": "Allsvenskan", "season": 2026}

    observations = repository.latest_market_observations_for_fixtures([FIXTURE_ID])

    service = ReadModelService(repository=repository)
    card = service._db_analysis_card_from_fixture(item, observations)  # noqa: SLF001

    # DB 实读：自动 forward 已把 AH + OU 写进新账本（同一 commit）
    with Session(repository.engine) as session:
        rows = list(
            session.scalars(
                select(AhOuDecisionLedgerModel).where(
                    AhOuDecisionLedgerModel.fixture_id == FIXTURE_ID
                )
            )
        )

    assert card is not None
    assert {row.market for row in rows} == {"ASIAN_HANDICAP", "TOTALS"}, [
        (row.market, row.skip_reason) for row in rows
    ]
    for row in rows:
        assert row.home_team_id == "H"
        assert row.away_team_id == "A"
        assert row.capture_id
        assert row.source_capture_sha256
    # R3: cohort is independently persisted (one row per (fixture, decision_at)).
    with Session(repository.engine) as session:
        cohorts = list(
            session.scalars(
                select(AhOuCohortModel).where(
                    AhOuCohortModel.fixture_id == FIXTURE_ID
                )
            )
        )
    assert len(cohorts) == 1
    assert cohorts[0].home_team_id == "H"
    assert cohorts[0].away_team_id == "A"
    assert cohorts[0].ah_capture_id
    assert cohorts[0].ou_capture_id
    assert cohorts[0].frozen_identity


def FutureRefreshDbRepositoryForTest() -> Any:  # noqa: N802
    from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

    return FutureRefreshDbRepository()


def repository_claim_checkpoints() -> list[dict[str, Any]]:  # noqa: N802
    from w2.matchday.repository import MatchdayRuntimeRepository

    return MatchdayRuntimeRepository().claim_due_checkpoint_plans(
        now=NOW, worker_id="v3-real-chain"
    )
