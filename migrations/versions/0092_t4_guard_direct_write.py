"""Guard against direct writes that bypass the AH/OU ledger / F9 snapshot writers.

T4 测试数据污染：生产账本出现过 fx1/fx2（decision_contract=''、input_hash='hhhh…'）
和 snap-H/A（source_system='sys'）——绕过四步写入器手插。写入器本会强制
decision_contract='w2.ah_ou_decision.v3.1' 和 source_system='team_xg_match'，直写
绕过校验。本迁移加 DB 级 CHECK constraint 堵住直写路径：任何绕过写入器的 INSERT 带
这些非法值会被数据库拒绝。

``NOT VALID``：不校验既有行（既有污染由 scripts/cleanup_t4_test_pollution.py 清理），
只约束新写入——正是「堵直写」需要的语义。

Revision ID: 0092_t4_guard_direct_write
Revises: 0091_ahou_decision_skip_reevaluate
"""

from alembic import op

revision = "0092_t4_guard_direct_write"
down_revision = "0091_ahou_decision_skip_reevaluate"
branch_labels = depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # 账本：decision_contract 不能是空字符串（历史 v3 行为 NULL 合法，当前为
    # 'w2.ah_ou_decision.v3.1'）；空字符串是直写 fx1/fx2 的特征。
    op.execute(
        "ALTER TABLE ah_ou_decision_ledger "
        "ADD CONSTRAINT ck_ahou_decision_contract_not_empty "
        "CHECK (decision_contract IS NULL OR decision_contract <> '') NOT VALID"
    )
    # 快照：source_system 不能是 'sys'（直写 snap-H/A 的特征；合法值如
    # 'team_xg_match' / 'api_football_statistics'）。
    op.execute(
        "ALTER TABLE team_xg_rolling_snapshot "
        "ADD CONSTRAINT ck_team_xg_snapshot_source_system_not_sys "
        "CHECK (source_system <> 'sys') NOT VALID"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE ah_ou_decision_ledger "
        "DROP CONSTRAINT IF EXISTS ck_ahou_decision_contract_not_empty"
    )
    op.execute(
        "ALTER TABLE team_xg_rolling_snapshot "
        "DROP CONSTRAINT IF EXISTS ck_team_xg_snapshot_source_system_not_sys"
    )
