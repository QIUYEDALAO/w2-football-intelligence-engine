"""Allow prematch SKIP ledger rows to be deleted for re-evaluation (override).

决策 forward 幂等过严修复：旧代码留下的 SKIP 行（selected=false，如
``AH_LINE_NOT_HEMISPHERE``）会卡死场次，新代码永远不重新评估。账本表
append-only 的 ``w2_ahou_postmatch_immutable`` 无条件禁止 DELETE，导致「删除旧
SKIP + 重新写入」无法落地。本迁移仅对 ``ah_ou_decision_ledger`` 放行「selected=false
的 SKIP 行 DELETE」（重新评估覆盖），selected=true 的最终决策仍不可变，其它表
（settlement / validation_sample）仍完全不可变。

Revision ID: 0091_ahou_decision_skip_reevaluate
Revises: 0090_ahou_daily_candidate_list_restore
"""

from alembic import op

revision = "0091_ahou_decision_skip_reevaluate"
down_revision = "0090_ahou_daily_candidate_list_restore"
branch_labels = depends_on = None


_UPGRADE_FUNCTION = """
CREATE OR REPLACE FUNCTION w2_ahou_postmatch_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME = 'ah_ou_decision_ledger' THEN
    -- 幂等过严修复：prematch 的旧 SKIP 行（selected=false）允许删除以重新评估覆盖；
    -- selected=true 的最终决策仍不可变（append-only 防线）。
    IF TG_OP = 'DELETE' AND OLD.selected IS FALSE THEN
      RETURN OLD;
    END IF;
  END IF;
  RAISE EXCEPTION 'AH_OU_POSTMATCH_FROZEN_CONTENT_CONFLICT';
END $$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(_UPGRADE_FUNCTION)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    CREATE OR REPLACE FUNCTION w2_ahou_postmatch_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'AH_OU_POSTMATCH_FROZEN_CONTENT_CONFLICT'; END $$;
    """)
