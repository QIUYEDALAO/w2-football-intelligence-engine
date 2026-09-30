"""Protect v3 notification business envelopes while allowing delivery audit.

Revision ID: 0088_ahou_v3_outbox
Revises: 0087_ahou_legacy_fence
"""

from alembic import op

revision = "0088_ahou_v3_outbox"
down_revision = "0087_ahou_legacy_fence"
branch_labels = depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    CREATE OR REPLACE FUNCTION w2_ahou_v3_outbox_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.event_type IN ('AH_OU_V3_RECOMMENDATION_CONFIRMED', 'AH_OU_V3_DAILY_SETTLEMENT') THEN
        IF TG_OP = 'DELETE' THEN
          RAISE EXCEPTION 'V3_OUTBOX_BUSINESS_IMMUTABLE';
        END IF;
        IF (to_jsonb(OLD) - ARRAY[
              'payload', 'delivery_status', 'delivery_attempt_count', 'delivered_at', 'last_error'
            ]) IS DISTINCT FROM (to_jsonb(NEW) - ARRAY[
              'payload', 'delivery_status', 'delivery_attempt_count', 'delivered_at', 'last_error'
            ]) OR (OLD.payload::jsonb - '_delivery') IS DISTINCT FROM
                  (NEW.payload::jsonb - '_delivery') THEN
          RAISE EXCEPTION 'V3_OUTBOX_BUSINESS_IMMUTABLE';
        END IF;
      ELSIF TG_OP = 'UPDATE' AND NEW.event_type IN (
        'AH_OU_V3_RECOMMENDATION_CONFIRMED', 'AH_OU_V3_DAILY_SETTLEMENT'
      ) THEN
        RAISE EXCEPTION 'V3_OUTBOX_BUSINESS_IMMUTABLE';
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$;
    DROP TRIGGER IF EXISTS w2_ahou_v3_outbox_immutable ON candidate_notification_outbox;
    CREATE TRIGGER w2_ahou_v3_outbox_immutable BEFORE UPDATE OR DELETE
      ON candidate_notification_outbox FOR EACH ROW
      EXECUTE FUNCTION w2_ahou_v3_outbox_immutable();
    """)


def downgrade() -> None:
    # Rollback cannot reopen the mutable business envelope of an existing event.
    # The idempotent upgrade reinstalls the same trigger on the next promotion.
    return
