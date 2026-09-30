"""Retire AH/OU legacy current writers while preserving historical reads.

Revision ID: 0087_ahou_legacy_fence
Revises: 0086_ahou_v3_postmatch
"""

from alembic import op

revision = "0087_ahou_legacy_fence"
down_revision = "0086_ahou_v3_postmatch"
branch_labels = depends_on = None


_TABLES = (
    "dynamic_prematch_evaluations",
    "dynamic_prematch_opportunities",
    "validation_samples",
    "validation_samples_calibrated",
    "candidate_notification_outbox",
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    CREATE OR REPLACE FUNCTION w2_ahou_legacy_current_fence() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE old_market text;
    BEGIN
      IF TG_LEVEL = 'STATEMENT' THEN
        RAISE EXCEPTION 'LEGACY_AH_OU_TRUNCATE_FORBIDDEN';
      END IF;
      IF TG_TABLE_NAME = 'candidate_notification_outbox' THEN
        IF TG_OP = 'INSERT' AND NEW.event_type IN (
          'DAILY_CANDIDATE_LIST', 'VALIDATION_SAMPLE_CONFIRMED',
          'VALIDATION_SIGNAL', 'DAILY_SETTLEMENT'
        ) THEN
          RAISE EXCEPTION 'LEGACY_AH_OU_EVENT_RETIRED';
        END IF;
        IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.event_type IN (
          'DAILY_CANDIDATE_LIST', 'VALIDATION_SAMPLE_CONFIRMED',
          'VALIDATION_SIGNAL', 'DAILY_SETTLEMENT'
        ) THEN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'LEGACY_AH_OU_EVENT_IMMUTABLE';
          END IF;
          IF (to_jsonb(OLD) - ARRAY[
                'delivery_status', 'delivery_attempt_count', 'delivered_at', 'last_error'
              ]) IS DISTINCT FROM (to_jsonb(NEW) - ARRAY[
                'delivery_status', 'delivery_attempt_count', 'delivered_at', 'last_error'
              ]) THEN
            RAISE EXCEPTION 'LEGACY_AH_OU_EVENT_IMMUTABLE';
          END IF;
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
      END IF;
      IF TG_OP = 'INSERT' THEN
        old_market := NEW.market;
      ELSE
        old_market := OLD.market;
      END IF;
      IF old_market IN ('ASIAN_HANDICAP', 'TOTALS') THEN
        RAISE EXCEPTION 'LEGACY_AH_OU_WRITER_RETIRED';
      END IF;
      IF TG_OP = 'UPDATE' THEN
        IF NEW.market IN ('ASIAN_HANDICAP', 'TOTALS') THEN
          RAISE EXCEPTION 'LEGACY_AH_OU_WRITER_RETIRED';
        END IF;
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$;
    """)
    for table in _TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS w2_ahou_legacy_current_fence ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS w2_ahou_legacy_no_truncate ON {table}")
        op.execute(
            f"CREATE TRIGGER w2_ahou_legacy_current_fence "
            f"BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION w2_ahou_legacy_current_fence()"
        )
        op.execute(
            f"CREATE TRIGGER w2_ahou_legacy_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION w2_ahou_legacy_current_fence()"
        )


def downgrade() -> None:
    # Keep the independent trigger/function in place when Alembic records
    # 0086. CI's down/up rehearsal must not reopen legacy AH/OU writers, and a
    # service rollback must fail closed even if its code predates this revision.
    # The next upgrade replaces the function and the triggers idempotently.
    return
