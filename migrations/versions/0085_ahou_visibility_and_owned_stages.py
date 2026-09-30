"""Commit visibility confirmation and owned, resumable task stages.

Revision ID: 0085_ahou_visibility_owned
Revises: 0084_provider_side_effect_fence
"""

import sqlalchemy as sa
from alembic import op

revision = "0085_ahou_visibility_owned"
down_revision = "0084_provider_side_effect_fence"
branch_labels = depends_on = None


def upgrade():
    op.add_column("team_xg_rolling_snapshot", sa.Column("decision_at", sa.DateTime(timezone=True)))
    op.add_column("team_xg_rolling_snapshot", sa.Column("source_matches", sa.JSON()))
    op.add_column(
        "team_xg_rolling_snapshot",
        sa.Column("proof_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "team_xg_rolling_snapshot",
        sa.Column("source_pit_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("provider_side_effect_fence", sa.Column("owner_token", sa.String(64)))
    op.add_column("provider_side_effect_fence", sa.Column("stored_result", sa.JSON()))
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    CREATE VIEW ah_ou_history_capture_sources AS
      SELECT c.capture_id, c.fixture_id, c.raw_payload_sha256, c.capture_status,
             c.status_code, c.provider_captured_at, r.payload AS raw_payload,
             r.captured_at AS raw_captured_at
      FROM matchday_endpoint_captures c LEFT JOIN raw_payload r ON r.sha256=c.raw_payload_sha256
      WHERE EXISTS (SELECT 1 FROM canonical_team_match_history h
                    WHERE h.endpoint_capture_id=c.capture_id);
    GRANT SELECT ON ah_ou_history_capture_sources TO quant_asof_reader_role;
    """)
    # Do not backfill historical rows. Only a later transaction can confirm a
    # newly frozen object; INSERT / transaction-start clocks are not commit proof.
    op.execute("""
    CREATE FUNCTION w2_f9_freeze_visibility() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'INSERT' THEN
        NEW.first_committed_at := NULL;
        NEW.pit_proven := false;
        RETURN NEW;
      END IF;
      IF (to_jsonb(OLD) - ARRAY['first_committed_at','pit_proven','proof_pending'])
         IS DISTINCT FROM
            (to_jsonb(NEW) - ARRAY['first_committed_at','pit_proven','proof_pending']) THEN
        RAISE EXCEPTION 'TEAM_XG_SNAPSHOT_FROZEN_CONTENT_CONFLICT';
      END IF;
      IF OLD.proof_pending AND NOT NEW.proof_pending AND OLD.first_committed_at IS NULL
         AND OLD.xmin::text::bigint <> txid_current() THEN
        NEW.first_committed_at := clock_timestamp();
        NEW.pit_proven := OLD.source_pit_requested AND OLD.decision_at IS NOT NULL
            AND OLD.first_captured_at IS NOT NULL
            AND OLD.first_captured_at <= OLD.decision_at
            AND NEW.first_committed_at <= OLD.decision_at;
      ELSIF NEW.first_committed_at IS DISTINCT FROM OLD.first_committed_at
          OR NEW.pit_proven IS DISTINCT FROM OLD.pit_proven
          OR NEW.proof_pending IS DISTINCT FROM OLD.proof_pending THEN
        RAISE EXCEPTION 'TEAM_XG_SNAPSHOT_VISIBILITY_PROOF_CONFLICT';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER w2_f9_freeze_visibility BEFORE INSERT OR UPDATE ON team_xg_rolling_snapshot
      FOR EACH ROW EXECUTE FUNCTION w2_f9_freeze_visibility();
    """)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP VIEW ah_ou_history_capture_sources")
        op.execute("DROP TRIGGER w2_f9_freeze_visibility ON team_xg_rolling_snapshot")
        op.execute("DROP FUNCTION w2_f9_freeze_visibility()")
    for field in ("stored_result", "owner_token"):
        op.drop_column("provider_side_effect_fence", field)
    for field in ("source_pit_requested", "proof_pending", "source_matches", "decision_at"):
        op.drop_column("team_xg_rolling_snapshot", field)
