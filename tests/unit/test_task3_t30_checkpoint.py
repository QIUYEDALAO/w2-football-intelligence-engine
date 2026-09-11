from datetime import timedelta

from apps.worker import celery_app as worker
from test_analysis_card_xg_materialized import (
    KICKOFF,
    FakeCanonicalDbRepository,
    FakeReadRepository,
)

from w2.prematch import analysis_calculator as analysis
from w2.tracking import model_forecast_ledger as ledger


def test_checkpoint_adapter_binds_evaluation_time(monkeypatch):
    now = KICKOFF - timedelta(minutes=30)
    class ReadRepository(FakeReadRepository):
        def fixture_payloads(self):
            return [{**item, 'league': {'id': 39, 'name': 'Synthetic League 39', 'season': 2026}}
                    for item in super().fixture_payloads()]
        def future_market_observations(self):
            return [{**r, 'captured_at': now.isoformat(),
                     'provider_last_update': now.isoformat()}
                    for r in super().future_market_observations() if 'ah-' in r['observation_id']
                    and '-1-' in r['observation_id']]
    monkeypatch.setenv('W2_TASK3_T30_CAPTURE_ENABLED', '1')
    monkeypatch.setattr(analysis, 'ReadModelRepository', ReadRepository)
    monkeypatch.setattr(analysis, 'future_refresh_db_repository', FakeCanonicalDbRepository)
    captured = []
    def freeze(day_view, **kwargs):
        captured.append((day_view, kwargs))
        return {'db_writes': 0}
    monkeypatch.setattr(ledger, 'freeze_t30_capture', freeze)
    worker._freeze_t30_checkpoint_captures(
        [{'fixture_id': '1489410', 'checkpoint': ledger.T30_CHECKPOINT}], evaluated_at=now,
    )
    assert captured and captured[0][0]['cards']
    card = captured[0][0]['cards'][0]
    assert card['fixture_id'] == '1489410'
    assert captured[0][1]['captured_at'] == now


def test_checkpoint_disabled_does_not_read(monkeypatch):
    monkeypatch.delenv('W2_TASK3_T30_CAPTURE_ENABLED', raising=False)
    def forbidden():
        raise AssertionError('disabled path must not read')
    monkeypatch.setattr(analysis, 'ReadModelRepository', forbidden)
    result = worker._freeze_t30_checkpoint_captures(
        [{'fixture_id': '1489410', 'checkpoint': ledger.T30_CHECKPOINT}],
        evaluated_at=KICKOFF - timedelta(minutes=30),
    )
    assert result == {'status': 'DISABLED', 'provider_calls': 0, 'db_writes': 0}


def test_real_checkpoint_to_sqlite_ledger(monkeypatch, tmp_path):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from test_task3_t30_freeze import _repository, _seed_xg

    from w2.competitions.registry import CompetitionRegistry
    from w2.infrastructure.persistence.future_refresh_models import (
        TeamXgMatchModel,
        TeamXgRollingSnapshotModel,
    )
    from w2.infrastructure.persistence.league_models import LeagueSeasonModel
    from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
    store = _repository(tmp_path)
    _seed_xg(store)
    now = KICKOFF - timedelta(minutes=30)
    # Only the temporary pytest authority DB: the seed disables league id 39.
    authority = CompetitionRegistry().engine
    with Session(authority) as session:
        season = session.scalars(select(LeagueSeasonModel).where(
            LeagueSeasonModel.competition_id == 'premier_league',
        )).first()
        original = dict(season.payload)
        season.payload = {**original, 'enabled': True}
        session.commit()
    with Session(store.engine) as session:
        for row in session.scalars(select(TeamXgRollingSnapshotModel)):
            row.as_of_fixture_id = '1489410'
            row.as_of_time = now - timedelta(hours=1)
        for row in session.scalars(select(TeamXgMatchModel)):
            row.kickoff_at = now - timedelta(days=10)
            row.captured_at = now - timedelta(days=9)
            delta = (int(row.fixture_id.rsplit('-', 1)[1]) - 1) * 0.1
            row.xg_for += delta
            row.xg_against += delta
        session.commit()

    class Inputs(FakeCanonicalDbRepository):
        def matchday_fixture_identity(self, fixture_id):
            return {**super().matchday_fixture_identity(fixture_id),
                    'competition_id': 'premier_league',
                    'identity_hash': 'a' * 64, 'raw_payload_sha256': 'b' * 64}

        def team_xg_rolling_snapshots_for_w2_teams(self, team_ids, **kwargs):
            with Session(store.engine) as session:
                return [{
                    'team_id': 'w2:team:home' if r.team_id == '10' else 'w2:team:away',
                    'provider_team_id': r.team_id, 'snapshot_id': r.snapshot_id,
                    'as_of_fixture_id': r.as_of_fixture_id,
                    'as_of_time': r.as_of_time.isoformat() + '+00:00',
                    'match_count': r.match_count, 'rolling_xg_for': r.rolling_xg_for,
                    'rolling_xg_against': r.rolling_xg_against,
                    'rolling_goals_for': 1, 'rolling_goals_against': 0, 'regression_index': 0,
                } for r in session.scalars(select(TeamXgRollingSnapshotModel))]

        def team_xg_matches_for_w2_teams(self, team_ids, **kwargs):
            with Session(store.engine) as session:
                return [{
                    'fixture_id': r.fixture_id,
                    'team_id': 'w2:team:home' if r.team_id == '10' else 'w2:team:away',
                    'provider_team_id': r.team_id,
                    'kickoff_at': r.kickoff_at.isoformat() + '+00:00',
                    'captured_at': r.captured_at.isoformat() + '+00:00',
                    'xg_for': r.xg_for, 'xg_against': r.xg_against,
                    'source_system': 'api_football_statistics',
                    'raw_payload_sha256': r.raw_payload_sha256,
                } for r in session.scalars(select(TeamXgMatchModel))]

    class ReadRepository(FakeReadRepository):
        def fixture_payloads(self):
            return [{**item, 'league': {'id': 39, 'name': 'Synthetic League 39', 'season': 2026}}
                    for item in super().fixture_payloads()]

        def future_market_observations(self):
            return [{**r, 'captured_at': now.isoformat(),
                     'provider_last_update': now.isoformat()}
                    for r in super().future_market_observations()
                    if 'ah-' in r['observation_id'] and '-1-' in r['observation_id']]
    inputs = Inputs()
    monkeypatch.setenv('W2_TASK3_T30_CAPTURE_ENABLED', '1')
    monkeypatch.setattr(analysis, 'ReadModelRepository', ReadRepository)
    monkeypatch.setattr(analysis, 'future_refresh_db_repository', lambda: inputs)
    monkeypatch.setattr(
        store.xg_repository, 'matchday_fixture_identity', inputs.matchday_fixture_identity,
    )
    monkeypatch.setattr(ledger, 'create_engine', lambda: store.engine)
    monkeypatch.setattr(ledger, 'FutureRefreshDbRepository', lambda **kwargs: store.xg_repository)
    try:
        result = worker._freeze_t30_checkpoint_captures(
            [{'fixture_id': '1489410', 'checkpoint': ledger.T30_CHECKPOINT}], evaluated_at=now,
        )
        assert result['db_writes'] == 1, result
        with Session(store.engine) as session:
            row = session.scalars(select(ModelForecastCaptureModel)).one()
            assert row.payload['lambda_uncertainty_status'] == 'ANALYSIS_READY'
            assert row.payload['t30_market_reference']['bookmaker'] == 'Pinnacle'
            from w2.strategy.simulate import replay_simulation
            saved = row.payload['simulation_replay']['simulation']
            assert row.payload['simulation_replay']['status'] == 'RECORDED_PENDING_REPLAY'
            replayed = replay_simulation(saved).as_dict()
            assert replayed['score_matrix_summary'] == saved['score_matrix_summary']
            assert replayed['ah_probabilities'] == saved['ah_probabilities']
            assert (row.payload['score_matrix_distribution']
                    == saved['score_matrix_summary']['distribution'])
    finally:
        with Session(authority) as session:
            season = session.scalars(select(LeagueSeasonModel).where(
                LeagueSeasonModel.competition_id == 'premier_league',
            )).first()
            season.payload = original
            session.commit()
