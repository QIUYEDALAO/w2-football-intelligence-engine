"""bind runtime-selected Gate A fixtures to the reservation

Revision ID: 0050_gate_a_runtime_selection
Revises: 0049_gate_a_signed_fixture_scope
"""

import sqlalchemy as sa
from alembic import op

revision = "0050_gate_a_runtime_selection"
down_revision = "0049_gate_a_signed_fixture_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("gate_a_run_reservations") as batch:
        batch.alter_column("fixture_id", existing_type=sa.String(length=128), nullable=True)
        batch.add_column(sa.Column("provider_league_id", sa.String(length=64)))
        batch.add_column(sa.Column("fixture_scope_mode", sa.String(length=32)))
        batch.add_column(sa.Column("kickoff_window_start_utc", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("kickoff_window_end_utc", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("selection_policy_version", sa.String(length=64)))
        batch.add_column(sa.Column("policy_config_hash", sa.String(length=64)))
        batch.add_column(sa.Column("selected_fixture_id", sa.String(length=128)))
        batch.add_column(sa.Column("fixture_candidate_set_sha256", sa.String(length=64)))
        batch.add_column(sa.Column("fixture_discovery_capture_id", sa.String(length=64)))
        batch.add_column(sa.Column("eligible_candidate_count", sa.Integer()))
        batch.add_column(sa.Column("fixture_selected_at", sa.DateTime(timezone=True)))
    op.execute(
        sa.text(
            "UPDATE gate_a_run_reservations SET "
            "provider_league_id = 'LEGACY_UNBOUND_REJECTED', "
            "fixture_scope_mode = 'EXACT_FIXTURE_ID', "
            "selection_policy_version = 'LEGACY_UNBOUND_REJECTED', "
            "policy_config_hash = 'LEGACY_UNBOUND_REJECTED', "
            "selected_fixture_id = fixture_id, fixture_selected_at = reserved_at"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE gate_a_run_reservations SET fixture_id = "
            "COALESCE(fixture_id, selected_fixture_id, 'LEGACY_UNSCOPED_REJECTED')"
        )
    )
    with op.batch_alter_table("gate_a_run_reservations") as batch:
        batch.drop_column("fixture_selected_at")
        batch.drop_column("eligible_candidate_count")
        batch.drop_column("fixture_discovery_capture_id")
        batch.drop_column("fixture_candidate_set_sha256")
        batch.drop_column("selected_fixture_id")
        batch.drop_column("policy_config_hash")
        batch.drop_column("selection_policy_version")
        batch.drop_column("kickoff_window_end_utc")
        batch.drop_column("kickoff_window_start_utc")
        batch.drop_column("fixture_scope_mode")
        batch.drop_column("provider_league_id")
        batch.alter_column("fixture_id", existing_type=sa.String(length=128), nullable=False)
