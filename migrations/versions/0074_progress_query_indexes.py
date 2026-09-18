"""add indexes for progress projection queries

Revision ID: 0074_progress_query_indexes
Revises: 0073_validation_samples

Additive. Only new indexes are created; no existing table's columns,
constraints or data are changed. Two hot queries on the dashboard workspace's
model-forecast progress projection were doing full-table scans with JSON
extraction on every request:

1. ``current_flow_*`` count the T-30m validation-lock candidates by filtering
   ``outcome_ledger`` on ``payload->>'checkpoint'`` (a JSON field). The capture
   rows currently carry a NULL checkpoint, yet the query still seq-scans all
   68k ledger rows and re-parses each JSON document. A partial expression index
   over the extracted checkpoint makes the filter index-backed.

2. ``ever_formed_candidate_count`` filters ``dynamic_prematch_evaluations`` by
   ``official_funnel_eligible`` + state. The state comparison is now done on the
   plain ``original_state`` column; a composite index avoids the full scan.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0074_progress_query_indexes"
down_revision: str | None = "0073_validation_samples"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # current_flow_*：只索引 capture 记录里已写入 checkpoint 的行（未来 T-30m
    # 数据；当前全 NULL，索引极小，查询不再扫全表解析 JSON）。
    op.execute(
        "CREATE INDEX ix_outcome_ledger_capture_checkpoint "
        "ON outcome_ledger ((payload ->> 'checkpoint')) "
        "WHERE record_type = 'capture' AND source_artifact = 'db:forward_outcome_ledger'"
    )
    # ever_formed_candidate_count：official_funnel_eligible + original_state 过滤。
    op.create_index(
        "ix_dynamic_prematch_evaluation_eligible_state",
        "dynamic_prematch_evaluations",
        ["official_funnel_eligible", "original_state"],
    )
    # funnel 的 row_number 窗口：排序键与窗口 partition/order 对齐，避免每次
    # 对 12k 行 evaluations 全量排序。
    op.execute(
        "CREATE INDEX ix_dynamic_prematch_evaluation_funnel_window "
        "ON dynamic_prematch_evaluations (model_forecast_capture_identity_hash, "
        "evaluation_policy_version, evaluation_slot_id, market, "
        "evaluated_at DESC, evaluation_id DESC)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "outcome_ledger" in inspector.get_table_names():
        op.execute("DROP INDEX IF EXISTS ix_outcome_ledger_capture_checkpoint")
    if "dynamic_prematch_evaluations" in inspector.get_table_names():
        op.execute("DROP INDEX IF EXISTS ix_dynamic_prematch_evaluation_funnel_window")
        op.drop_index(
            "ix_dynamic_prematch_evaluation_eligible_state",
            table_name="dynamic_prematch_evaluations",
        )
