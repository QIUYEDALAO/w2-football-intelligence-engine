from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository


def test_streaming_retains_latest_payload_and_filters_league(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "raw.db"}')
    RawPayloadModel.__table__.create(engine)
    now = datetime(2026, 9, 8, tzinfo=UTC)
    with Session(engine) as s:
        for i in range(40):
            s.add(RawPayloadModel(
                sha256=f'{i:064x}', endpoint='fixtures', captured_at=now+timedelta(seconds=i),
                storage_uri='test', payload={'response': [
                    {'fixture': {'id': 1, 'date': '2026-09-09'},
                     'league': {'id': 39}, 'revision': i},
                    {'fixture': {'id': 2, 'date': '2026-09-10'}, 'league': {'id': 40}},
                ]},
            ))
        s.commit()
    queries = []
    @event.listens_for(engine, 'before_cursor_execute')
    def check(conn, cursor, statement, parameters, context, many):
        queries.append(context.execution_options.get('yield_per'))
    repository = FutureRefreshDbRepository(engine=engine)
    assert repository.fixture_payloads(provider_league_id='39') == [
        {'fixture': {'id': 1, 'date': '2026-09-09'}, 'league': {'id': 39}, 'revision': 39}
    ]
    assert len(repository.fixture_payloads()) == 2
    assert queries == [16, 16]
