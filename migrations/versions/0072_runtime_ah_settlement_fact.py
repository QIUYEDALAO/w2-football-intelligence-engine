"""create runtime_ah_settlement_facts

Revision ID: 0072_runtime_ah_settlement_fact
Revises: 0071_forward_ah_factor_observation

Additive. A new table only: no existing table, column, index or constraint is
touched, so every historical row keeps its identity and its hashes.

Not a backfill. This table is populated only by the natural capture writer, from
a pre-kickoff odds quote paired with the terminal-result capture that observed
the fixture finish. No existing history is reinterpreted into it, and the
pre-existing `canonical_historical_ah_facts` chain is left exactly as it was --
those rows have no capture identity and no source-observed time, so they keep
producing F5 absence rather than being promoted by inference.

Every column that carries meaning is NOT NULL, and the point-in-time ordering is
a database constraint: `quote_captured_at < kickoff_utc < settlement_observed_at`.
A row whose source-observed time is not strictly after kickoff is precisely the
fabrication this table exists to prevent, so the database refuses it rather than
accepting a default.

Rollback is not an unconditional drop. These are immutable business facts, so
`downgrade` drops the table only when it is empty. If rows exist it refuses and
the documented path is the forward-compatible one: stop the writer and roll the
application back without the schema.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0072_runtime_ah_settlement_fact"
down_revision: str | None = "0071_forward_ah_factor_observation"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "runtime_ah_settlement_facts"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("fact_id", sa.String(64), primary_key=True),
        sa.Column("fact_hash", sa.String(64), nullable=False),
        sa.Column("source_set_hash", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("hash_contract", sa.String(64), nullable=False),
        sa.Column("record_kind", sa.String(64), nullable=False),
        sa.Column("policy", sa.String(64), nullable=False),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("provider_fixture_id", sa.String(128), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("season", sa.String(32), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_provider_id", sa.String(128), nullable=False),
        sa.Column("away_team_provider_id", sa.String(128), nullable=False),
        sa.Column("home_w2_team_id", sa.String(128), nullable=True),
        sa.Column("away_w2_team_id", sa.String(128), nullable=True),
        sa.Column("selected_line", sa.String(32), nullable=False),
        sa.Column("home_price", sa.Float(), nullable=True),
        sa.Column("away_price", sa.Float(), nullable=True),
        sa.Column("selected_bookmakers", sa.JSON(), nullable=False),
        sa.Column("quote_capture_ids", sa.JSON(), nullable=False),
        sa.Column("quote_payload_sha256s", sa.JSON(), nullable=False),
        sa.Column("quote_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quote_identity_hash", sa.String(64), nullable=False),
        sa.Column("settlement_capture_id", sa.String(255), nullable=False),
        sa.Column("settlement_payload_sha256", sa.String(64), nullable=False),
        sa.Column("settlement_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settlement_observed_at_semantics", sa.String(64), nullable=False),
        sa.Column("terminal_status", sa.String(8), nullable=False),
        sa.Column("home_goals", sa.Integer(), nullable=False),
        sa.Column("away_goals", sa.Integer(), nullable=False),
        sa.Column("home_settlement", sa.String(16), nullable=False),
        sa.Column("away_settlement", sa.String(16), nullable=False),
        sa.Column("result_identity_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("fact_hash", name="uq_runtime_ah_settlement_fact_hash"),
        sa.UniqueConstraint(
            "fixture_id",
            "policy",
            "selected_line",
            "quote_identity_hash",
            "settlement_capture_id",
            name="uq_runtime_ah_settlement_fact_natural",
        ),
        sa.CheckConstraint(
            "terminal_status in ('FT', 'AET', 'PEN')",
            name="ck_runtime_ah_settlement_terminal_status",
        ),
        sa.CheckConstraint(
            "quote_captured_at < kickoff_utc and kickoff_utc < settlement_observed_at",
            name="ck_runtime_ah_settlement_point_in_time",
        ),
        sa.CheckConstraint(
            "settlement_observed_at_semantics = 'PROVIDER_CAPTURE_OF_TERMINAL_RESULT'",
            name="ck_runtime_ah_settlement_observed_semantics",
        ),
        sa.CheckConstraint(
            "policy = 'canonical_bookmaker_mainline_majority_v1'",
            name="ck_runtime_ah_settlement_policy",
        ),
        sa.CheckConstraint(
            "quote_identity_hash <> '' and source_set_hash <> '' and "
            "settlement_capture_id <> '' and settlement_payload_sha256 <> ''",
            name="ck_runtime_ah_settlement_identities_present",
        ),
    )
    op.create_index(
        "ix_runtime_ah_settlement_fixture", _TABLE, ["provider_fixture_id", "kickoff_utc"]
    )
    op.create_index("ix_runtime_ah_settlement_kickoff", _TABLE, ["kickoff_utc"])
    op.create_index(
        "ix_runtime_ah_settlement_home_team", _TABLE, ["home_w2_team_id", "kickoff_utc"]
    )
    op.create_index(
        "ix_runtime_ah_settlement_away_team", _TABLE, ["away_w2_team_id", "kickoff_utc"]
    )
    op.create_index(
        "ix_runtime_ah_settlement_settlement_capture", _TABLE, ["settlement_capture_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        # Already absent: a repeated downgrade is a no-op, not a failure.
        return
    table = sa.table(_TABLE, sa.column("fact_id"))
    rows = bind.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
    if rows:
        raise RuntimeError(
            "RUNTIME_AH_SETTLEMENT_FACT_DOWNGRADE_WOULD_DESTROY_FACTS:"
            f"rows={rows}; use the forward-compatible disable path instead"
        )
    op.drop_index("ix_runtime_ah_settlement_settlement_capture", table_name=_TABLE)
    op.drop_index("ix_runtime_ah_settlement_away_team", table_name=_TABLE)
    op.drop_index("ix_runtime_ah_settlement_home_team", table_name=_TABLE)
    op.drop_index("ix_runtime_ah_settlement_kickoff", table_name=_TABLE)
    op.drop_index("ix_runtime_ah_settlement_fixture", table_name=_TABLE)
    op.drop_table(_TABLE)
