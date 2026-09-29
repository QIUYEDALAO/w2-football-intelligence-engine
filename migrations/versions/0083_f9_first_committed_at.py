"""F9 双层 PIT 来源证明（V7 包2/B）: 分列「组成源首次捕获」与「目标快照首次提交可读」。

Revision ID: 0083_f9_first_committed_at
Revises: 0082_ah_ou_cohort
Create Date: 2026-09-29 00:00:00.000000

``first_captured_at`` 是组成这条滚动快照的历史源首次可得时刻；它不能证明
「这条目标快照行」何时首次持久化并可读。新增 ``first_committed_at``，由真实
写入事务时钟锁定（写入时 server clock），不能从组件时间回填，也不能由
``as_of_time`` 推断。晚物化/回填行该列为 NULL → BACKTEST_LOOKBACK 且
``pit_proven=false``。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0083_f9_first_committed_at"
down_revision: str | None = "0082_ah_ou_cohort"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "team_xg_rolling_snapshot",
        sa.Column("first_committed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("team_xg_rolling_snapshot", "first_committed_at")
