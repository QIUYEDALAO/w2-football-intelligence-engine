"""extend ModelForecast capture identity with freeze policy and horizon

Revision ID: 0063_model_forecast_capture_policy_identity
Revises: 0062_dynamic_evaluation_denominator

Frozen payloads and capture_identity_hash values are never rewritten. Both new
columns are derived from what each row already froze in its payload, so the
ledger stays byte-identical while the relational key gains the two dimensions a
parallel fixed-horizon track needs.

``horizon_id`` is deliberately *not* added to the hashed core: ``capture_policy``
already lives there, so registering one horizon per policy keeps the two tracks
distinguishable without opening a third capture-schema generation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0063_model_forecast_capture_policy_identity"
down_revision: str | None = "0062_dynamic_evaluation_denominator"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "model_forecast_capture"
CANONICAL_VIEW = "model_forecast_capture_canonical"
LEGACY_CAPTURE_POLICY = "FIRST_ELIGIBLE_FREEZE_IMMUTABLE"
NO_HORIZON = "NONE"
OLD_UNIQUE = "uq_model_forecast_capture_fixture_model"
NEW_UNIQUE = "uq_model_forecast_capture_identity_scope"

# The canonical view is the sanctioned entry point for cross-table analysis, so
# the new identity dimensions have to surface there; otherwise every stratified
# report keeps reaching into the base table with a bare fixture_id join.
CANONICAL_VIEW_SQL = """
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
    {policy_columns}capture.four_field_xg_identity_hash,
    capture.payload_sha256,
    version.data_version,
    version.team_xg_match_count,
    version.evidence_source
FROM model_forecast_capture AS capture
LEFT JOIN model_forecast_capture_data_version AS version
  ON version.capture_identity_hash = capture.capture_identity_hash
"""


def _recreate_canonical_view(*, with_policy: bool) -> None:
    """SQLite's batch mode rebuilds the table, which would orphan the view."""

    op.execute(f"DROP VIEW IF EXISTS {CANONICAL_VIEW}")
    columns = "capture.capture_policy,\n    capture.horizon_id,\n    " if with_policy else ""
    op.execute(CANONICAL_VIEW_SQL.format(policy_columns=columns))


# Written out per dialect rather than interpolated: PostgreSQL and SQLite
# disagree on JSON extraction, and a literal statement keeps the UPDATE auditable.
_BACKFILL_POSTGRESQL = sa.text(
    """
    UPDATE model_forecast_capture
    SET capture_policy = COALESCE(NULLIF(payload ->> 'capture_policy', ''), :legacy_policy),
        horizon_id = COALESCE(NULLIF(payload ->> 'horizon_id', ''), :no_horizon)
    """
).bindparams(legacy_policy=LEGACY_CAPTURE_POLICY, no_horizon=NO_HORIZON)

_BACKFILL_SQLITE = sa.text(
    """
    UPDATE model_forecast_capture
    SET capture_policy = COALESCE(
            NULLIF(json_extract(payload, '$.capture_policy'), ''), :legacy_policy
        ),
        horizon_id = COALESCE(
            NULLIF(json_extract(payload, '$.horizon_id'), ''), :no_horizon
        )
    """
).bindparams(legacy_policy=LEGACY_CAPTURE_POLICY, no_horizon=NO_HORIZON)


def _backfill_sql() -> sa.TextClause:
    if op.get_bind().dialect.name == "postgresql":
        return _BACKFILL_POSTGRESQL
    return _BACKFILL_SQLITE


def upgrade() -> None:
    _recreate_canonical_view(with_policy=False)

    op.add_column(TABLE, sa.Column("capture_policy", sa.String(64), nullable=True))
    op.add_column(TABLE, sa.Column("horizon_id", sa.String(32), nullable=True))
    op.execute(_backfill_sql())

    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(TABLE, "capture_policy", existing_type=sa.String(64), nullable=False)
        op.alter_column(TABLE, "horizon_id", existing_type=sa.String(32), nullable=False)
        op.drop_constraint(OLD_UNIQUE, TABLE, type_="unique")
        op.create_unique_constraint(
            NEW_UNIQUE,
            TABLE,
            [
                "fixture_id",
                "model_family",
                "model_version",
                "capture_policy",
                "horizon_id",
            ],
        )
    # SQLite cannot alter a constraint in place, and rebuilding the table via
    # batch mode breaks the RESTRICT foreign key that the data-version sidecar
    # holds on this exact table.  Test databases are built from ORM metadata,
    # which already declares the widened constraint, so the swap is only needed
    # on the deployed PostgreSQL instance.

    _recreate_canonical_view(with_policy=True)


def downgrade() -> None:
    _recreate_canonical_view(with_policy=False)

    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(NEW_UNIQUE, TABLE, type_="unique")
        op.create_unique_constraint(
            OLD_UNIQUE, TABLE, ["fixture_id", "model_family", "model_version"]
        )

    op.drop_column(TABLE, "horizon_id")
    op.drop_column(TABLE, "capture_policy")

    _recreate_canonical_view(with_policy=False)
