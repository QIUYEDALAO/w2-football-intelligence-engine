"""Provider 不确定副作用栅栏（V7 包5/E）: 调用前持久化 task+stage+attempt，调用后落状态。

Revision ID: 0084_provider_side_effect_fence
Revises: 0083_f9_first_committed_at
Create Date: 2026-09-29 00:00:00.000000

在发起任何可能有外部副作用的 Provider 阶段前先落一行 ``ATTEMPTING``；外部调用
后任何异常/进程中断只允许把该行置为 ``SIDE_EFFECT_UNCERTAIN`` 或 ``BLOCKED``，
禁止同 task 自动重发该阶段或进入后续阶段。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0084_provider_side_effect_fence"
down_revision: str | None = "0083_f9_first_committed_at"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "provider_side_effect_fence",
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="ATTEMPTING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.String(512), nullable=True),
        sa.PrimaryKeyConstraint("task_id", "stage", "attempt"),
    )


def downgrade() -> None:
    op.drop_table("provider_side_effect_fence")
