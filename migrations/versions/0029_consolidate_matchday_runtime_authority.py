"""consolidate matchday runtime authority

Revision ID: 0029_consolidate_matchday_runtime_authority
Revises: 0028_create_matchday_evidence_authority
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0029_consolidate_matchday_runtime_authority"
down_revision: str | None = "0028_create_matchday_evidence_authority"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "matchday_endpoint_captures", sa.Column("fixture_id", sa.String(128), nullable=True)
    )
    op.add_column(
        "matchday_endpoint_captures", sa.Column("checkpoint", sa.String(64), nullable=True)
    )
    op.add_column(
        "matchday_checkpoint_plans",
        sa.Column("endpoints", sa.JSON(), nullable=False, server_default="[]"),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "uq_matchday_endpoint_capture_identity",
            "matchday_endpoint_captures",
            type_="unique",
        )
        op.create_unique_constraint(
            "uq_matchday_endpoint_capture_identity",
            "matchday_endpoint_captures",
            ["endpoint", "params_hash", "checkpoint", "provider_captured_at", "raw_payload_sha256"],
        )

    op.create_table(
        "matchday_market_observations",
        sa.Column("observation_id", sa.String(64), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("provider_fixture_id", sa.String(64), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("bookmaker_id", sa.String(64), nullable=False),
        sa.Column("bookmaker_name", sa.String(255), nullable=False),
        sa.Column(
            "capture_id",
            sa.String(64),
            sa.ForeignKey("matchday_endpoint_captures.capture_id"),
            nullable=False,
        ),
        sa.Column("provider_bet_id", sa.String(64), nullable=False),
        sa.Column("raw_market_label", sa.String(255), nullable=False),
        sa.Column("canonical_market", sa.String(64), nullable=False),
        sa.Column("canonical_selection", sa.String(128), nullable=False),
        sa.Column("provider_selection", sa.String(128), nullable=False),
        sa.Column("line", sa.String(64), nullable=True),
        sa.Column("decimal_odds", sa.String(32), nullable=False),
        sa.Column("suspended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("live", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider_updated_at", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload_sha256", sa.String(64), nullable=False),
        sa.Column("source_revision", sa.String(128), nullable=False),
        sa.UniqueConstraint("observation_id", name="uq_matchday_market_observation_identity"),
    )
    op.create_index(
        "ix_matchday_market_observation_fixture",
        "matchday_market_observations",
        ["fixture_id", "captured_at"],
    )
    op.create_index(
        "ix_matchday_market_observation_capture",
        "matchday_market_observations",
        ["capture_id"],
    )

    op.add_column(
        "matchday_evidence_manifests", sa.Column("decision_hash", sa.String(64), nullable=True)
    )
    op.add_column(
        "matchday_evidence_manifests",
        sa.Column(
            "manifest_integrity_status", sa.String(64), nullable=False, server_default="PASS"
        ),
    )
    op.add_column(
        "matchday_evidence_manifests", sa.Column("natural_key_hash", sa.String(64), nullable=True)
    )
    if op.get_bind().dialect.name != "sqlite":
        op.create_unique_constraint(
            "uq_matchday_manifest_natural_key",
            "matchday_evidence_manifests",
            ["fixture_id", "as_of", "natural_key_hash"],
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "uq_matchday_manifest_natural_key",
            "matchday_evidence_manifests",
            type_="unique",
        )
    op.drop_column("matchday_evidence_manifests", "natural_key_hash")
    op.drop_column("matchday_evidence_manifests", "manifest_integrity_status")
    op.drop_column("matchday_evidence_manifests", "decision_hash")
    op.drop_index(
        "ix_matchday_market_observation_capture", table_name="matchday_market_observations"
    )
    op.drop_index(
        "ix_matchday_market_observation_fixture", table_name="matchday_market_observations"
    )
    op.drop_table("matchday_market_observations")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "uq_matchday_endpoint_capture_identity",
            "matchday_endpoint_captures",
            type_="unique",
        )
        op.create_unique_constraint(
            "uq_matchday_endpoint_capture_identity",
            "matchday_endpoint_captures",
            ["endpoint", "params_hash", "provider_captured_at", "raw_payload_sha256"],
        )
    op.drop_column("matchday_checkpoint_plans", "endpoints")
    op.drop_column("matchday_endpoint_captures", "checkpoint")
    op.drop_column("matchday_endpoint_captures", "fixture_id")
