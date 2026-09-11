"""persist provider quota observation and minute limit

Revision ID: 0057_provider_quota_observation
Revises: 0056_floor_model_forecast_lead_time
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0057_provider_quota_observation"
down_revision: str | None = "0056_floor_model_forecast_lead_time"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("quota_usage")}
    observed_at_added = "observed_at" not in columns
    with op.batch_alter_table("quota_usage") as batch:
        if observed_at_added:
            batch.add_column(sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True))
        if "burst_limit" not in columns:
            batch.add_column(sa.Column("burst_limit", sa.Integer(), nullable=True))
        if "burst_remaining" not in columns:
            batch.add_column(sa.Column("burst_remaining", sa.Integer(), nullable=True))
    if observed_at_added:
        op.execute(
            sa.text(
                "update quota_usage set observed_at = coalesce((select max(completed_at) "
                "from provider_request_logs where provider_request_logs.provider = "
                "quota_usage.provider and provider_request_logs.endpoint = quota_usage.endpoint "
                "and provider_request_logs.completed_at >= quota_usage.window_start and "
                "provider_request_logs.completed_at < quota_usage.window_end), window_start)"
            )
        )
        with op.batch_alter_table("quota_usage") as batch:
            batch.alter_column(
                "observed_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
            )


def downgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("quota_usage")}
    with op.batch_alter_table("quota_usage") as batch:
        if "burst_remaining" in columns:
            batch.drop_column("burst_remaining")
        if "burst_limit" in columns:
            batch.drop_column("burst_limit")
        if "observed_at" in columns:
            batch.drop_column("observed_at")
