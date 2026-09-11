"""add immutable data-version metadata for model forecast captures

Revision ID: 0061_model_forecast_data_version
Revises: 0060_model_forecast_canonical_fixture_view
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0061_model_forecast_data_version"
down_revision: str | None = "0060_model_forecast_canonical_fixture_view"
branch_labels: str | None = None
depends_on: str | None = None

def upgrade() -> None:
    op.create_table(
        "model_forecast_capture_data_version",
        sa.Column("capture_identity_hash", sa.String(64), nullable=False),
        sa.Column("data_version", sa.String(128), nullable=False),
        sa.Column("team_xg_match_count", sa.BigInteger(), nullable=True),
        sa.Column("evidence_source", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["capture_identity_hash"],
            ["model_forecast_capture.capture_identity_hash"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("capture_identity_hash"),
    )
    op.execute(
        sa.text(
            """
            insert into model_forecast_capture_data_version
            (capture_identity_hash,data_version,team_xg_match_count,evidence_source,recorded_at)
            select capture_identity_hash,
                case when
                    (select count(*) from model_forecast_capture) = 45 and
                    (select count(*) from model_forecast_capture
                     where captured_at < '2026-08-17 05:56:53.022663+00:00') = 13
                then case when captured_at < '2026-08-17 05:56:53.022663+00:00'
                    then 'TEAM_XG_MATCH_ROWS_1868' else 'TEAM_XG_MATCH_ROWS_18686' end
                else 'LEGACY_UNVERSIONED' end,
                case when
                    (select count(*) from model_forecast_capture) = 45 and
                    (select count(*) from model_forecast_capture
                     where captured_at < '2026-08-17 05:56:53.022663+00:00') = 13
                then case when captured_at < '2026-08-17 05:56:53.022663+00:00'
                    then 1868 else 18686 end
                else null end,
                case when
                    (select count(*) from model_forecast_capture) = 45 and
                    (select count(*) from model_forecast_capture
                     where captured_at < '2026-08-17 05:56:53.022663+00:00') = 13
                then 'OWNER_VERIFIED_RECONSTRUCTION' else 'LEGACY_UNVERSIONED' end,
                captured_at
            from model_forecast_capture
            """
        )
    )
    _replace_canonical_view(include_data_version=True)


def downgrade() -> None:
    _replace_canonical_view(include_data_version=False)
    op.drop_table("model_forecast_capture_data_version")


def _replace_canonical_view(*, include_data_version: bool) -> None:
    op.execute("DROP VIEW model_forecast_capture_canonical")
    if include_data_version:
        op.execute(
            """
        CREATE VIEW model_forecast_capture_canonical AS
        SELECT
            capture.capture_identity_hash,
            CASE
                WHEN capture.fixture_id LIKE 'api_football:%' THEN capture.fixture_id
                ELSE 'api_football:' || capture.fixture_id
            END AS canonical_fixture_id,
            capture.fixture_id AS stored_fixture_id,
            capture.competition_id,
            capture.kickoff_utc,
            capture.captured_at,
            capture.lead_time_seconds,
            capture.lead_time_bucket,
            capture.model_family,
            capture.model_version,
            capture.four_field_xg_identity_hash,
            capture.payload_sha256,
            version.data_version,
            version.team_xg_match_count,
            version.evidence_source
        FROM model_forecast_capture AS capture
        LEFT JOIN model_forecast_capture_data_version AS version
          ON version.capture_identity_hash = capture.capture_identity_hash
            """
        )
        return
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
