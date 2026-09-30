"""V9 production chain on isolated PostgreSQL, synthetic upstream, network=0."""
from datetime import UTC, datetime, timedelta
from copy import deepcopy
from types import SimpleNamespace
import uuid
import pytest
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import Session
from w2.config import get_settings
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.ingestion.xg_backfill import XgHistoryBackfillService, XgBackfillConfig
from w2.ingestion.h2h_capture import capture_h2h_for_pair
from w2.ingestion.future_refresh import sha256_payload
from w2.domain.canonical_serialization import HashDomain
from w2.infrastructure.persistence.factor_model_models import CanonicalTeamModel, ProviderTeamIdentityCrosswalkModel
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.providers.api_football import LiveApiFootballResponse
from w2.prematch.analysis_calculator import ReadModelService
from tests.integration import test_future_refresh_db_persistence as harness
from tests.integration.test_ah_ou_v3_real_chain import PinnacleAhOuClient

def _build_chain(tmp_path, monkeypatch):
    import os, subprocess
    url=os.environ.get('W2_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('W2_TEST_POSTGRES_URL required')
    admin=create_engine(url,isolation_level='AUTOCOMMIT'); name='w2_v9chain_'+uuid.uuid4().hex[:12]
    with admin.connect() as c: c.execute(text(f'CREATE DATABASE "{name}"'))
    db=url.rsplit('/',1)[0]+'/'+name
    monkeypatch.setenv('W2_DATABASE_URL',db); monkeypatch.setenv('W2_ENVIRONMENT','test')
    monkeypatch.setenv('W2_FUTURE_REFRESH_PERSISTENCE','db'); get_settings.cache_clear()
    # The public router is imported once per pytest process. Bind its read
    # service to this case's isolated database before the first API request.
    from w2.api import routers
    from w2.api.repository import ReadModelService as ApiReadModelService
    monkeypatch.setattr(routers, 'service', ApiReadModelService())
    subprocess.run(['.venv/bin/alembic','upgrade','head'],check=True,env=os.environ.copy(),capture_output=True)
    now=datetime.now(UTC).replace(microsecond=0); kickoff=now+timedelta(hours=7)
    monkeypatch.setattr(harness,'NOW',now)
    from w2.competitions.seed import seed_competition_runtime_authority, apply_collection_policy_update
    repo=FutureRefreshDbRepository()
    seed_competition_runtime_authority(repo.engine,environment='test',now=now)
    apply_collection_policy_update(repo.engine,updated_by='v9-isolated',now=now)
    harness.seed_odds_checkpoint('1489404',with_identity=True)
    from w2.matchday.repository import MatchdayRuntimeRepository
    plans=MatchdayRuntimeRepository().claim_due_checkpoint_plans(now=now,worker_id='v9')
    class Odds(PinnacleAhOuClient):
        def payload(self, endpoint, params):
            raw=super().payload(endpoint,params)
            if endpoint=='fixtures':
                for observed in raw.get('response',[]):
                    if str((observed.get('fixture') or {}).get('id'))=='1489404':
                        observed['fixture']['date']=kickoff.isoformat()
            if endpoint=='odds':
                values=raw['response'][0]['bookmakers'][0]['bets'][0]['values']
                values[0]['odd']='1.25'; values[1]['odd']='4.50'
            return raw
        def request_live(self,endpoint,params):
            response=super().request_live(endpoint,params)
            return LiveApiFootballResponse(**{**response.__dict__, 'captured_at':now, 'requested_at':now})
    harness.run_direct_checkpoint(tmp_path,Odds(),*plans)
    with Session(repo.engine) as session, session.begin():
        for pid,w2 in [('10','H'),('20','A')]:
            session.add(CanonicalTeamModel(w2_team_id=w2,display_name=w2,active_status='ACTIVE',created_at=now,identity_hash=pid*32,payload={}))
            session.add(ProviderTeamIdentityCrosswalkModel(id='v9-'+pid,provider='api_football',provider_team_id=pid,w2_team_id=w2,
                competition_id='allsvenskan',season='2026',valid_from=now-timedelta(days=400),identity_status='PROVIDER_PRIMARY_READY',evidence_hashes=[],identity_hash=pid*32))
        identity=session.get(MatchdayFixtureIdentityModel,'api_football:1489404')
        identity.kickoff_utc=kickoff
        identity.home_w2_team_id='H'; identity.away_w2_team_id='A'; identity.team_identity_status='READY'
    def fixture(fid,date,status):
        return {'fixture':{'id':fid,'date':date.isoformat(),'status':{'short':status}},
                'league':{'id':113,'season':2026},'teams':{'home':{'id':10,'name':'H'},'away':{'id':20,'name':'A'}},
                'goals':{'home':4,'away':0}}
    future=fixture(1489404,kickoff,'NS')
    past=[fixture(9100+i,now-timedelta(days=30-i),'FT') for i in range(3)]
    raw={'response':[future,*past]}
    repo.save_raw_payload(sha256=sha256_payload(raw,domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD),endpoint='fixtures',captured_at=now,payload=raw)
    for item in past:
        payload={'parameters':{'fixture':str(item['fixture']['id'])},'response':[
            {'team':{'id':10},'statistics':[{'type':'expected_goals','value':'3.8'}]},
            {'team':{'id':20},'statistics':[{'type':'expected_goals','value':'0.4'}]}]}
        repo.save_raw_payload(sha256=sha256_payload(payload,domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD),endpoint='statistics',captured_at=now,payload=payload)
    producer=XgHistoryBackfillService(repository=repo,client=object(),now=now,config=XgBackfillConfig(competition_ids=('allsvenskan',)))
    plan=producer.build_saved_raw_plan()
    result=producer.run_saved_raw()
    assert result.rolling_snapshot_rows==2, result.as_dict()
    class H2H:
        def request_live(self,endpoint,params):
            assert endpoint=='h2h'
            return LiveApiFootballResponse(endpoint=endpoint,params=params,status_code=200,elapsed_ms=1,
                payload={'response':past},headers={},captured_at=now,requested_at=now)
    assert capture_h2h_for_pair(home_provider_team_id='10',away_provider_team_id='20',competition_id='allsvenskan',season='2026',client=H2H())==6
    repo._v9_h2h_client=H2H()
    yield repo, future, plan, producer


@pytest.fixture
def chain(tmp_path, monkeypatch):
    yield from _build_chain(tmp_path, monkeypatch)


def test_selected_full_chain_and_source_four_steps(chain):
    repo,item,plan,producer=chain
    frozen=repo.team_xg_rolling_snapshots(fixture_id='1489404')
    assert all(r['first_committed_at'] and r['pit_proven'] for r in frozen), frozen
    # Same original input, then new Session read-back/reconstruction.
    repo.upsert_team_xg_rolling_snapshots(list(plan.rolling_snapshots))
    repo.upsert_team_xg_rolling_snapshots(frozen)
    changed=deepcopy(frozen[0]); changed['rolling_xg_for']+=.1
    with pytest.raises(RuntimeError,match='FIELD_CONFLICT'):
        repo.upsert_team_xg_rolling_snapshots([changed])
    changed=deepcopy(frozen[0]); changed['source_matches'][0]['raw_serializer_version']='w2.canonical-json.v2'
    with pytest.raises(RuntimeError,match='FIELD_CONFLICT'):
        repo.upsert_team_xg_rolling_snapshots([changed])
    service=ReadModelService()
    card=service.public_analysis_card_bounded('1489404',use_frozen_canary=False)
    assert card is not None
    with Session(repo.engine) as session:
        rows=list(session.scalars(select(AhOuDecisionLedgerModel)))
        assert len(rows)==2
        assert all(row.selected for row in rows), [(r.market,r.selected,r.skip_reason,r.full_distribution) for r in rows]
        public={m['market']:m for m in card['markets']}
        for row in rows:
            assert public[row.market]['selected']==row.selected
            assert public[row.market]['direction']==row.direction
            assert public[row.market]['tendency']==(row.direction+'_AH' if row.market=='ASIAN_HANDICAP' else row.direction)
            assert public[row.market]['score']==row.score
            assert public[row.market]['decision_hash']==row.decision_id
    assert card['ah_ou_result']['recording']['status']=='COMMITTED'
    repeat=ReadModelService().public_analysis_card_bounded('1489404',use_frozen_canary=False)
    assert repeat is not None
    markets={'ASIAN_HANDICAP','TOTALS'}
    assert {m['market']:m['decision_hash'] for m in repeat['markets'] if m['market'] in markets} == {
        market: value['decision_hash'] for market,value in public.items() if market in markets}
    with Session(repo.engine) as session:
        assert len(list(session.scalars(select(AhOuDecisionLedgerModel))))==2


def test_actual_producer_after_decision_is_false(chain):
    repo,item,plan,producer=chain
    producer.now=datetime.fromisoformat(item['fixture']['date'])-timedelta(hours=1)
    rebuilt=producer.build_saved_raw_plan()
    assert all(not r['pit_proven'] for r in rebuilt.rolling_snapshots)


def test_database_proof_never_accepts_injected_first_commit(chain):
    repo,item,plan,producer=chain
    row=deepcopy(plan.rolling_snapshots[0]); row['snapshot_id']='injected-first'; row['as_of_fixture_id']='injected-target'
    row['first_committed_at']=(datetime.now(UTC)-timedelta(days=5)).isoformat()
    row['decision_at']=(datetime.now(UTC)-timedelta(seconds=1)).isoformat()
    repo.upsert_team_xg_rolling_snapshots([row])
    stored=repo.team_xg_rolling_snapshots(fixture_id='injected-target')[0]
    assert stored['first_committed_at'] is None  # target identity/cutoff is not proven
    assert not stored['pit_proven']


def test_database_first_visibility_after_late_commit(chain):
    """An INSERT before the cutoff is not evidence if it commits afterward."""
    import time
    from w2.infrastructure.persistence.future_refresh_models import TeamXgRollingSnapshotModel
    repo, item, _, _ = chain
    control = repo.team_xg_rolling_snapshots(fixture_id='1489404')[0]
    assert control['pit_proven'] and control['first_committed_at']
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    values = {key: control[key] for key in (
        'team_id', 'as_of_fixture_id', 'match_count', 'rolling_xg_for', 'rolling_xg_against',
        'rolling_goals_for', 'rolling_goals_against', 'regression_index', 'source_system',
        'source_matches', 'source_pit_requested', 'candidate', 'formal_recommendation')}
    target_id = 'late-commit-'+uuid.uuid4().hex
    values.update(snapshot_id=values['team_id']+':'+target_id,
                  as_of_fixture_id=target_id,
                  as_of_time=datetime.fromisoformat(control['as_of_time']),
                  first_captured_at=datetime.fromisoformat(control['first_captured_at']),
                  decision_at=cutoff, first_committed_at=cutoff-timedelta(days=1),
                  pit_proven=True, proof_pending=True)
    with Session(repo.engine) as session:
        inserted = TeamXgRollingSnapshotModel(**values)
        session.add(inserted)
        session.flush()
        session.refresh(inserted)
        assert inserted.first_committed_at is None
        time.sleep(max(0, (cutoff-datetime.now(UTC)).total_seconds())+.1)
        session.commit()
    with Session(repo.engine) as session, session.begin():
        frozen = session.get(TeamXgRollingSnapshotModel, values['snapshot_id'])
        assert frozen.first_committed_at is None and not frozen.pit_proven
        frozen.proof_pending = False
    with Session(repo.engine) as session:
        frozen = session.get(TeamXgRollingSnapshotModel, values['snapshot_id'])
        assert frozen.first_committed_at >= cutoff
        assert not frozen.pit_proven


@pytest.mark.parametrize('attack,reason',[
    ('late','F6_H2H_CAPTURED_AFTER_DECISION'),('failed','F6_H2H_CAPTURE_FAILED'),
    ('missing_raw','F6_H2H_RAW_MISSING'),('score','F6_H2H_CAPTURE_SCORE_MISMATCH'),
    ('fixture','F6_H2H_CAPTURE_FIXTURE_MISMATCH'),
    ('raw_time','F6_H2H_RAW_CAPTURE_TIME_MISMATCH'),
    ('raw_hash','F6_H2H_CAPTURE_RAW_HASH_MISMATCH'),
    ('team','F6_H2H_CAPTURE_TEAM_MISMATCH'),
    ('not_ft','F6_H2H_STATUS_NOT_FT'),
    ('ft_visible_late','F6_H2H_STATUS_NOT_VISIBLE'),
])
def test_f6_actual_source_attacks_have_ready_controls(chain,attack,reason):
    from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
    from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel
    from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
    from w2.strategy.ah_ou_decision import build_ah_ou_selections
    repo,item,_,_=chain
    kwargs=dict(fixture_id='1489404',home_team_id='H',away_team_id='A',kickoff=datetime.fromisoformat(item['fixture']['date']),
                competition_id='allsvenskan',season='2026',ah_line=-.5,ah_home_odds=1.25,ah_away_odds=4.5,
                ou_line=2.5,ou_over_odds=1.9,ou_under_odds=1.9)
    assert build_ah_ou_selections(repo,**kwargs)['status']=='READY'
    with Session(repo.engine) as session, session.begin():
        h=session.scalar(select(CanonicalTeamMatchHistoryModel).where(CanonicalTeamMatchHistoryModel.team_w2_id=='H'))
        cap=session.get(MatchdayEndpointCaptureModel,h.endpoint_capture_id)
        if attack=='late': cap.provider_captured_at=kwargs['kickoff']-timedelta(hours=1)
        elif attack=='failed': cap.capture_status='FAILED'; cap.status_code=500
        elif attack=='missing_raw': session.delete(session.get(RawPayloadModel,cap.raw_payload_sha256))
        elif attack=='score': h.goals_for+=1
        elif attack=='team': h.team_provider_id='999'
        elif attack=='not_ft':
            # Keep the frozen FT row queryable while changing the genuinely
            # bound raw capture. Rebind its hashes so the status check, rather
            # than a preceding hash check, owns this negative case.
            from w2.matchday.intake_v2 import stable_hash
            source=session.get(RawPayloadModel,cap.raw_payload_sha256)
            payload=deepcopy(source.payload)
            item=next(row for row in payload['response'] if str(row['fixture']['id'])==str(h.provider_fixture_id))
            item['fixture']['status']['short']='NS'
            replacement_hash=sha256_payload(payload,domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
            session.add(RawPayloadModel(sha256=replacement_hash,endpoint=source.endpoint,
                captured_at=source.captured_at,inserted_at=source.inserted_at,
                storage_uri=source.storage_uri,payload=payload))
            cap.raw_payload_sha256=replacement_hash
            for bound in session.scalars(select(CanonicalTeamMatchHistoryModel).where(
                    CanonicalTeamMatchHistoryModel.provider_fixture_id==h.provider_fixture_id)):
                bound.source_raw_hash=stable_hash(item)
        elif attack=='ft_visible_late': h.status_first_visible_at=kwargs['kickoff']-timedelta(hours=1)
        elif attack=='fixture': cap.fixture_id='api_football:foreign'
        elif attack=='raw_time': session.get(RawPayloadModel,cap.raw_payload_sha256).captured_at+=timedelta(seconds=1)
        elif attack=='raw_hash':
            source=session.get(RawPayloadModel,cap.raw_payload_sha256)
            source.payload={**source.payload,'tampered':True}
    result=build_ah_ou_selections(repo,**kwargs)
    assert result['status']==reason
    assert result['ah'] is None and result['ou'] is None


@pytest.mark.parametrize('attack,ah_reason,ou_reason',[
    ('ah_late','ASIAN_HANDICAP_QUOTE_CAPTURED_AFTER_DECISION','DEPENDENCY_BLOCKED'),
    ('ou_late','DEPENDENCY_BLOCKED','TOTALS_QUOTE_CAPTURED_AFTER_DECISION'),
    ('different','ASIAN_HANDICAP_QUOTE_CAPTURED_AFTER_DECISION','TOTALS_QUOTE_NOT_PINNACLE'),
])
def test_market_reason_selector_public_and_new_session(chain,tmp_path,monkeypatch,attack,ah_reason,ou_reason):
    from w2.infrastructure.persistence.matchday_intake_models import MatchdayMarketObservationModel
    from w2.strategy.ah_ou_quote_selector import select_v3_ah_ou_quotes
    repo,item,_,_=chain
    # Commit the legal public control, then use a fresh isolated PG database for
    # the attack. Frozen decision rows must never be deleted to reset a test.
    control=ReadModelService().public_analysis_card_bounded('1489404',use_frozen_canary=False)
    assert control['ah_ou_result']['recording']['status']=='COMMITTED'
    assert all(m['selected'] for m in control['markets'] if m['market'] in ('ASIAN_HANDICAP','TOTALS'))
    attack_root=tmp_path/'market_reason_attack'
    attack_root.mkdir()
    attack_chain=_build_chain(attack_root,monkeypatch)
    repo,item,_,_=next(attack_chain)
    decision=datetime.fromisoformat(item['fixture']['date'])-timedelta(hours=2)
    with Session(repo.engine) as session, session.begin():
        rows=list(session.scalars(select(MatchdayMarketObservationModel)))
        for row in rows:
            if (row.canonical_market=='ASIAN_HANDICAP' and attack in {'ah_late','different'}) or (row.canonical_market=='TOTALS' and attack=='ou_late'):
                row.captured_at=decision+timedelta(seconds=1)
            if row.canonical_market=='TOTALS' and attack=='different': row.bookmaker_id='8'
    observations=repo.latest_market_observations_for_fixtures(['1489404'])
    captures=list({r['capture_id'] for r in observations})
    selector=select_v3_ah_ou_quotes(observations,fixture_id='1489404',decision_at=decision,raw_payloads=repo.raw_payloads_for_captures(captures))
    card=ReadModelService().public_analysis_card_bounded('1489404',use_frozen_canary=False)
    assert card['ah_ou_result']['recording']['status']=='COMMITTED'
    with Session(repo.engine) as session:
        ledger={row.market:row for row in session.scalars(select(AhOuDecisionLedgerModel))}
        public={m['market']:m for m in card['markets']}
        for market,reason,key in [('ASIAN_HANDICAP',ah_reason,'ah'),('TOTALS',ou_reason,'ou')]:
            assert public[market]['reason']==ledger[market].skip_reason==reason
            assert not public[market]['selected'] and not ledger[market].selected
            assert selector[key]['status']==('READY' if reason=='DEPENDENCY_BLOCKED' else reason)


def test_f6_source_freeze_four_steps(chain):
    from w2.ingestion.h2h_capture import _freeze_h2h_history_row
    from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel
    repo,_,_,_=chain
    assert capture_h2h_for_pair(home_provider_team_id='10',away_provider_team_id='20',competition_id='allsvenskan',season='2026',client=repo._v9_h2h_client)==0
    with Session(repo.engine) as session:
        rows=list(session.scalars(select(CanonicalTeamMatchHistoryModel)))
        payloads=[{c.name:getattr(row,c.name) for c in row.__table__.columns} for row in rows]
    with Session(repo.engine) as session, session.begin():
        assert all(not _freeze_h2h_history_row(session,row) for row in payloads)
    changed=deepcopy(payloads[0]); changed['goals_for']+=1
    with Session(repo.engine) as session, pytest.raises(RuntimeError,match='F6_HISTORY_FIELD_CONFLICT:goals_for'):
        _freeze_h2h_history_row(session,changed)
    with Session(repo.engine) as session:
        stored=[{c.name:getattr(row,c.name) for c in row.__table__.columns} for row in session.scalars(select(CanonicalTeamMatchHistoryModel))]
    assert stored==payloads
