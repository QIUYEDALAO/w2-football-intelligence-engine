"""add canonical fixture projection for model forecast captures

Revision ID: 0060_model_forecast_canonical_fixture_view
Revises: 0059_free_plan_fixture_scope_observation
"""

from __future__ import annotations

from alembic import op

revision: str = "0060_model_forecast_canonical_fixture_view"
down_revision: str | None = "0059_free_plan_fixture_scope_observation"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW model_forecast_capture_canonical AS
        SELECT
            capture_identity_hash,
            CASE
                WHEN fixture_id LIKE 'api_football:%' THEN fixture_id
                ELSE 'api_football:' || fixture_id
            END AS canonical_fixture_id,
            fixture_id AS stored_fixture_id,
            competition_id,
            kickoff_utc,
            captured_at,
            lead_time_seconds,
            lead_time_bucket,
            model_family,
            model_version,
            four_field_xg_identity_hash,
            payload_sha256
        FROM model_forecast_capture
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW model_forecast_capture_canonical")
