"""Restore DAILY_CANDIDATE_LIST outbox writes while keeping other legacy events retired.

5c248935 误删每日候选名单（NOTIF-04 要求保留的三类之一）。0087 的 PG trigger 把
``DAILY_CANDIDATE_LIST`` 的 INSERT 一并判为 ``LEGACY_AH_OU_EVENT_RETIRED``；本迁移
仅恢复 ① 每日候选名单的写入，② 验证样本确认 / VALIDATION_SIGNAL / ③ 旧每日结算
仍保持退休，历史行仍不可变（UPDATE/DELETE immutable 不变）。

Revision ID: 0090_ahou_daily_candidate_list_restore
Revises: 0089_ahou_v3_monitoring
"""

from alembic import op

revision = "0090_ahou_daily_candidate_list_restore"
down_revision = "0089_ahou_v3_monitoring"
branch_labels = depends_on = None


_UPGRADE_FUNCTION = """
CREATE OR REPLACE FUNCTION w2_ahou_legacy_current_fence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_market text;
BEGIN
  IF TG_LEVEL = 'STATEMENT' THEN
    RAISE EXCEPTION 'LEGACY_AH_OU_TRUNCATE_FORBIDDEN';
  END IF;
  IF TG_TABLE_NAME = 'candidate_notification_outbox' THEN
    IF TG_OP = 'INSERT' AND NEW.event_type IN (
      'VALIDATION_SAMPLE_CONFIRMED', 'VALIDATION_SIGNAL', 'DAILY_SETTLEMENT'
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
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(_UPGRADE_FUNCTION)


def downgrade() -> None:
    # Rollback restores the 0087 fence (re-block DAILY_CANDIDATE_LIST writes).
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(_UPGRADE_FUNCTION.replace(
        "      'VALIDATION_SAMPLE_CONFIRMED', 'VALIDATION_SIGNAL', 'DAILY_SETTLEMENT'\n",
        "      'DAILY_CANDIDATE_LIST', 'VALIDATION_SAMPLE_CONFIRMED',\n"
        "      'VALIDATION_SIGNAL', 'DAILY_SETTLEMENT'\n",
        1,
    ))
