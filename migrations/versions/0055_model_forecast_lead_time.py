"""stratify model forecast validation by immutable capture lead time

Revision ID: 0055_model_forecast_lead_time
Revises: 0054_model_forecast_validation_ledger
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0055_model_forecast_lead_time"
down_revision: str | None = "0054_model_forecast_validation_ledger"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("model_forecast_capture") as batch:
        batch.add_column(sa.Column("lead_time_seconds", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("lead_time_bucket", sa.String(32), nullable=True))
    with op.batch_alter_table("model_forecast_outcome") as batch:
        batch.add_column(sa.Column("lead_time_seconds", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("lead_time_bucket", sa.String(32), nullable=True))

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        lead_time_update = sa.text(
            "update model_forecast_capture set lead_time_seconds = "
            "cast((julianday(kickoff_utc) - julianday(captured_at)) * 86400 as integer)"
        )
    else:
        lead_time_update = sa.text(
            "update model_forecast_capture set lead_time_seconds = "
            "cast(floor(extract(epoch from (kickoff_utc - captured_at))) as bigint)"
        )
    op.execute(lead_time_update)
    op.execute(
        sa.text(
            "update model_forecast_capture set lead_time_bucket = case "
            "when lead_time_seconds < 21600 then 'LT_6H' "
            "when lead_time_seconds < 86400 then 'H6_TO_LT_24H' "
            "when lead_time_seconds <= 259200 then 'D1_TO_D3' "
            "else 'GT_3D' end"
        )
    )
    op.execute(
        sa.text(
            "update model_forecast_outcome set "
            "lead_time_seconds = (select lead_time_seconds from model_forecast_capture "
            "where model_forecast_capture.capture_identity_hash = "
            "model_forecast_outcome.capture_identity_hash), "
            "lead_time_bucket = (select lead_time_bucket from model_forecast_capture "
            "where model_forecast_capture.capture_identity_hash = "
            "model_forecast_outcome.capture_identity_hash)"
        )
    )
    with op.batch_alter_table("model_forecast_capture") as batch:
        batch.alter_column("lead_time_seconds", existing_type=sa.BigInteger(), nullable=False)
        batch.alter_column("lead_time_bucket", existing_type=sa.String(32), nullable=False)
    with op.batch_alter_table("model_forecast_outcome") as batch:
        batch.alter_column("lead_time_seconds", existing_type=sa.BigInteger(), nullable=False)
        batch.alter_column("lead_time_bucket", existing_type=sa.String(32), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("model_forecast_outcome") as batch:
        batch.drop_column("lead_time_bucket")
        batch.drop_column("lead_time_seconds")
    with op.batch_alter_table("model_forecast_capture") as batch:
        batch.drop_column("lead_time_bucket")
        batch.drop_column("lead_time_seconds")
