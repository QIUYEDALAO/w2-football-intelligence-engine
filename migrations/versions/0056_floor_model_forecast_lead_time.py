"""floor legacy model forecast lead time to whole elapsed seconds

Revision ID: 0056_floor_model_forecast_lead_time
Revises: 0055_model_forecast_lead_time
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0056_floor_model_forecast_lead_time"
down_revision: str | None = "0055_model_forecast_lead_time"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        capture_update = sa.text(
            "update model_forecast_capture set "
            "lead_time_seconds = cast((julianday(kickoff_utc) - julianday(captured_at)) "
            "* 86400 as integer), lead_time_bucket = case "
            "when cast((julianday(kickoff_utc) - julianday(captured_at)) * 86400 as integer) "
            "< 21600 then 'LT_6H' "
            "when cast((julianday(kickoff_utc) - julianday(captured_at)) * 86400 as integer) "
            "< 86400 then 'H6_TO_LT_24H' "
            "when cast((julianday(kickoff_utc) - julianday(captured_at)) * 86400 as integer) "
            "<= 259200 then 'D1_TO_D3' else 'GT_3D' end"
        )
    else:
        capture_update = sa.text(
            "update model_forecast_capture set "
            "lead_time_seconds = cast(floor(extract(epoch from "
            "(kickoff_utc - captured_at))) as bigint), lead_time_bucket = case "
            "when floor(extract(epoch from (kickoff_utc - captured_at))) < 21600 "
            "then 'LT_6H' "
            "when floor(extract(epoch from (kickoff_utc - captured_at))) < 86400 "
            "then 'H6_TO_LT_24H' "
            "when floor(extract(epoch from (kickoff_utc - captured_at))) <= 259200 "
            "then 'D1_TO_D3' else 'GT_3D' end"
        )
    op.execute(capture_update)
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


def downgrade() -> None:
    pass
