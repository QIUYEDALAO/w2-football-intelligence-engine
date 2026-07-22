"""create matchday evidence authority

Revision ID: 0028_create_matchday_evidence_authority
Revises: 0027_finalize_fah_authority_constraints
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0028_create_matchday_evidence_authority"
down_revision: str | None = "0027_finalize_fah_authority_constraints"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "matchday_endpoint_captures",
        sa.Column("capture_id", sa.String(64), primary_key=True),
        sa.Column("endpoint", sa.String(64), nullable=False),
        sa.Column("sanitized_params", sa.JSON(), nullable=False),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("request_task_key", sa.String(255), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("response_count", sa.Integer(), nullable=False),
        sa.Column("quota_values", sa.JSON(), nullable=False),
        sa.Column("raw_payload_sha256", sa.String(64), nullable=False),
        sa.Column("provider_event_time", sa.String(64), nullable=True),
        sa.Column("capture_status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.UniqueConstraint(
            "endpoint",
            "params_hash",
            "provider_captured_at",
            "raw_payload_sha256",
            name="uq_matchday_endpoint_capture_identity",
        ),
    )
    op.create_index(
        "ix_matchday_endpoint_capture_endpoint",
        "matchday_endpoint_captures",
        ["endpoint", "provider_captured_at"],
    )
    op.create_index(
        "ix_matchday_endpoint_capture_raw_payload",
        "matchday_endpoint_captures",
        ["raw_payload_sha256"],
    )

    op.create_table(
        "matchday_checkpoint_plans",
        sa.Column("plan_id", sa.String(128), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("season", sa.String(32), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("checkpoint", sa.String(64), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("missed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capture_id", sa.String(64), nullable=True),
        sa.Column("current_unscheduled_capture_id", sa.String(64), nullable=True),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("plan_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "competition_id",
            "season",
            "checkpoint",
            "policy_version",
            name="uq_matchday_checkpoint_plan_identity",
        ),
    )
    op.create_index(
        "ix_matchday_checkpoint_plan_status",
        "matchday_checkpoint_plans",
        ["status", "scheduled_at"],
    )
    op.create_index(
        "ix_matchday_checkpoint_plan_fixture",
        "matchday_checkpoint_plans",
        ["fixture_id"],
    )

    op.create_table(
        "matchday_evidence_manifests",
        sa.Column("manifest_id", sa.String(64), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(128), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("input_manifest_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "as_of",
            "manifest_hash",
            name="uq_matchday_manifest_hash",
        ),
    )
    op.create_index(
        "ix_matchday_evidence_manifest_fixture",
        "matchday_evidence_manifests",
        ["fixture_id", "as_of"],
    )


def downgrade() -> None:
    op.drop_index("ix_matchday_evidence_manifest_fixture", table_name="matchday_evidence_manifests")
    op.drop_table("matchday_evidence_manifests")
    op.drop_index("ix_matchday_checkpoint_plan_fixture", table_name="matchday_checkpoint_plans")
    op.drop_index("ix_matchday_checkpoint_plan_status", table_name="matchday_checkpoint_plans")
    op.drop_table("matchday_checkpoint_plans")
    op.drop_index(
        "ix_matchday_endpoint_capture_raw_payload",
        table_name="matchday_endpoint_captures",
    )
    op.drop_index("ix_matchday_endpoint_capture_endpoint", table_name="matchday_endpoint_captures")
    op.drop_table("matchday_endpoint_captures")
