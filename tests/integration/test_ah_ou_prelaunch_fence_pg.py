"""One-way AH/OU legacy writer retirement on a 0076 -> current PG migration."""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from w2.infrastructure.persistence.dynamic_prematch_models import CandidateNotificationOutboxModel
from w2.prematch.candidate_notifications import delivery_route


@pytest.fixture
def migrated_database(monkeypatch):
    url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("W2_TEST_POSTGRES_URL required")
    name = "w2_prelaunch_" + uuid.uuid4().hex[:12]
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    db_url = url.rsplit("/", 1)[0] + "/" + name
    monkeypatch.setenv("W2_DATABASE_URL", db_url)
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    from w2.config import get_settings
    get_settings.cache_clear()
    env = os.environ.copy()
    subprocess.run([".venv/bin/alembic", "upgrade", "0076_forward_review_evidence"],
                   check=True, env=env, capture_output=True)
    engine = create_engine(db_url)
    at = datetime(2026, 9, 30, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO dynamic_prematch_evaluations
              (evaluation_id, identity_hash, fixture_id, market, selection, checkpoint,
               evaluated_at, original_state, payload)
            VALUES ('old-ah', :identity, 'old-fixture', 'ASIAN_HANDICAP', 'HOME',
                    'T15_ODDS', :at, 'ANALYSIS_PICK_ACTIVE', CAST(:payload AS json))
        """), {"identity": "a" * 64, "at": at, "payload": '{"old":true}'})
        connection.execute(text("""
            INSERT INTO candidate_notification_outbox
              (notification_event_id, event_type, current_state, payload, created_at,
               delivery_status, delivery_attempt_count)
            VALUES ('old-event', 'VALIDATION_SIGNAL', 'VALIDATION_SIGNAL',
                    CAST(:payload AS json), :at, 'PENDING', 0)
        """), {"at": at, "payload": '{"event_type":"VALIDATION_SIGNAL"}'})
    subprocess.run([".venv/bin/alembic", "upgrade", "head"],
                   check=True, env=env, capture_output=True)
    yield engine
    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


def test_old_ah_rows_preserved_and_new_current_writes_refused(migrated_database):
    engine = migrated_database
    with engine.connect() as connection:
        before = connection.execute(text("""
            SELECT identity_hash, selection, payload FROM dynamic_prematch_evaluations
            WHERE evaluation_id='old-ah'
        """)).one()
        assert before.identity_hash == "a" * 64
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0090_ahou_daily_candidate_list_restore"
        )
    with pytest.raises(DBAPIError, match="LEGACY_AH_OU_WRITER_RETIRED"):
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO dynamic_prematch_evaluations
                  (evaluation_id, identity_hash, fixture_id, market, selection,
                   checkpoint, evaluated_at, original_state, payload)
                VALUES ('new-ah', :identity, 'f', 'ASIAN_HANDICAP', 'HOME',
                        'T15_ODDS', now(), 'ANALYSIS_PICK_ACTIVE', '{}')
            """), {"identity": "b" * 64})
    with pytest.raises(DBAPIError, match="LEGACY_AH_OU_WRITER_RETIRED"):
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE dynamic_prematch_evaluations SET selection='AWAY'
                WHERE evaluation_id='old-ah'
            """))
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO dynamic_prematch_evaluations
              (evaluation_id, identity_hash, fixture_id, market, selection,
               checkpoint, evaluated_at, original_state, payload)
            VALUES ('other-market', :identity, 'f', 'ONE_X_TWO', 'HOME',
                    'T15_ODDS', now(), 'ANALYSIS_PICK_ACTIVE', '{}')
        """), {"identity": "c" * 64})
        connection.execute(text("""
            INSERT INTO dynamic_prematch_evaluations
              (evaluation_id, identity_hash, fixture_id, market, selection,
               checkpoint, evaluated_at, original_state, payload)
            VALUES ('other-btts', :identity, 'f', 'BTTS', 'YES',
                    'T15_ODDS', now(), 'ANALYSIS_PICK_ACTIVE', '{}')
        """), {"identity": "d" * 64})
    with engine.connect() as connection:
        assert connection.execute(text("""
            SELECT identity_hash, selection, payload FROM dynamic_prematch_evaluations
            WHERE evaluation_id='old-ah'
        """)).one() == before
        assert connection.scalar(text("""
            SELECT count(*) FROM dynamic_prematch_evaluations WHERE evaluation_id='new-ah'
        """)) == 0


def test_old_pending_event_can_only_be_suppressed(migrated_database):
    engine = migrated_database
    with engine.connect() as connection:
        row = connection.execute(text("""
            SELECT event_type, payload, delivery_status FROM candidate_notification_outbox
            WHERE notification_event_id='old-event'
        """)).one()
        assert delivery_route(CandidateNotificationOutboxModel(
            notification_event_id="old-event", event_type=row.event_type,
            delivery_status=row.delivery_status, payload=row.payload,
        )) == ("SUPPRESS", "HISTORICAL_AH_OU_EVENT")
    # ① 每日候选名单恢复写入（0090 恢复）；② 验证样本确认仍退休。
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO candidate_notification_outbox
              (notification_event_id, event_type, current_state, payload,
               created_at, delivery_status, delivery_attempt_count)
            VALUES ('late-candidate', 'DAILY_CANDIDATE_LIST', 'PLANNED', '{}',
                    now(), 'PENDING', 0)
        """))
    with pytest.raises(DBAPIError, match="LEGACY_AH_OU_EVENT_RETIRED"):
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO candidate_notification_outbox
                  (notification_event_id, event_type, current_state, payload,
                   created_at, delivery_status, delivery_attempt_count)
                VALUES ('late-confirm', 'VALIDATION_SAMPLE_CONFIRMED', 'CONFIRMED', '{}',
                        now(), 'PENDING', 0)
            """))
    with engine.begin() as connection:
        connection.execute(text("""
            UPDATE candidate_notification_outbox
            SET delivery_status='SUPPRESSED', last_error='HISTORICAL_AH_OU_EVENT'
            WHERE notification_event_id='old-event'
        """))
    with pytest.raises(DBAPIError, match="LEGACY_AH_OU_EVENT_IMMUTABLE"):
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE candidate_notification_outbox SET payload='{}'
                WHERE notification_event_id='old-event'
            """))
    with engine.connect() as connection:
        stored = connection.execute(text("""
            SELECT event_type, payload, delivery_status FROM candidate_notification_outbox
            WHERE notification_event_id='old-event'
        """)).one()
        assert stored.event_type == row.event_type
        assert stored.payload == row.payload
        assert stored.delivery_status == "SUPPRESSED"


def test_alembic_down_up_keeps_legacy_writer_fence(migrated_database):
    engine = migrated_database
    env = os.environ.copy()
    subprocess.run([".venv/bin/alembic", "downgrade", "0086_ahou_v3_postmatch"],
                   check=True, env=env, capture_output=True)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0086_ahou_v3_postmatch"
        )
    with pytest.raises(DBAPIError, match="LEGACY_AH_OU_WRITER_RETIRED"):
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO dynamic_prematch_evaluations
                  (evaluation_id, identity_hash, fixture_id, market, selection,
                   checkpoint, evaluated_at, original_state, payload)
                VALUES ('downgraded-ah', :identity, 'f', 'ASIAN_HANDICAP', 'HOME',
                        'T15_ODDS', now(), 'ANALYSIS_PICK_ACTIVE', '{}')
            """), {"identity": "d" * 64})
    subprocess.run([".venv/bin/alembic", "upgrade", "head"],
                   check=True, env=env, capture_output=True)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0090_ahou_daily_candidate_list_restore"
        )
        assert connection.scalar(text("""
            SELECT count(*) FROM dynamic_prematch_evaluations
            WHERE evaluation_id='downgraded-ah'
        """)) == 0


def test_asof_role_can_read_source_but_not_postmatch_result(migrated_database):
    engine = migrated_database
    with engine.connect() as connection:
        connection.execute(text("SET ROLE quant_asof_reader_role"))
        assert connection.scalar(text("SELECT count(*) FROM ah_ou_history_capture_sources")) == 0
        with pytest.raises(DBAPIError, match="permission denied"):
            connection.execute(text("SELECT count(*) FROM results"))
        connection.rollback()
