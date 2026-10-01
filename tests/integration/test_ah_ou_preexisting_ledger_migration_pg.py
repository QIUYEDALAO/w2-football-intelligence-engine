"""Recover verified forward-created 0081 objects at stale 0076, never stamp/drop."""

import os
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.parametrize(
    "attack", ["noop", "type", "nullable", "extra", "slot", "index", "trigger"]
)
def test_0076_existing_ledger_preservation_or_exact_structure_rejection(monkeypatch, attack):
    url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("W2_TEST_POSTGRES_URL required")
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    name = "w2_existing_ledger_" + uuid.uuid4().hex[:12]
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    target = url.rsplit("/", 1)[0] + "/" + name
    monkeypatch.setenv("W2_DATABASE_URL", target)
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    engine = create_engine(target)

    def migrate(revision):
        return subprocess.run(
            [".venv/bin/alembic", "upgrade", revision],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )

    def before():
        with engine.connect() as conn:
            return conn.scalar(text("SELECT to_jsonb(t)::text FROM ah_ou_decision_ledger t"))

    try:
        control = migrate("0076_forward_review_evidence")
        assert control.returncode == 0, control.stderr
        with engine.begin() as conn:
            conn.execute(text(Path("tests/fixtures/ah_ou_0076_existing_ledger.sql").read_text()))
            conn.execute(
                text("""
                INSERT INTO ah_ou_decision_ledger VALUES
                  ('old-id','old-fixture','ASIAN_HANDICAP','2026-09-28T18:00Z',
                  'm1','c1',:hash,'{}',:hash,:hash,:hash,'old-source','H','A',
                  true,'HOME','0.1',NULL,'2026-09-28T18:00Z')
            """),
                {"hash": "a" * 64},
            )
        original = before()
        # Every attack first proves the same DB read/write channel is inert.
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE ah_ou_decision_ledger SET score=score WHERE decision_id='old-id'")
            )
        assert before() == original
        faults = {
            "type": (
                "ALTER TABLE ah_ou_decision_ledger ALTER COLUMN score TYPE text",
                "COLUMN_CONFLICT:score",
            ),
            "nullable": (
                "ALTER TABLE ah_ou_decision_ledger ALTER COLUMN score DROP NOT NULL",
                "COLUMN_CONFLICT:score",
            ),
            "extra": (
                "ALTER TABLE ah_ou_decision_ledger ADD COLUMN unknown text",
                "COLUMN_SET_CONFLICT",
            ),
            "slot": ("DROP INDEX uq_ah_ou_decision_ledger_slot", "INDEX_SET_CONFLICT"),
            "index": (
                "DROP INDEX ix_ah_ou_decision_ledger_capture; CREATE INDEX "
                "ix_ah_ou_decision_ledger_capture ON ah_ou_decision_ledger(source_id)",
                "INDEX_CONFLICT:ix_ah_ou_decision_ledger_capture",
            ),
            "trigger": (
                "CREATE FUNCTION unknown_ledger_trigger() RETURNS trigger LANGUAGE plpgsql "
                "AS $$ BEGIN RETURN NEW; END $$; CREATE TRIGGER unknown_ledger_trigger "
                "BEFORE UPDATE ON ah_ou_decision_ledger FOR EACH ROW EXECUTE FUNCTION "
                "unknown_ledger_trigger()",
                "TRIGGER_CONFLICT",
            ),
        }
        if attack != "noop":
            with engine.begin() as conn:
                conn.execute(text(faults[attack][0]))
        stored = before()
        result = migrate("head")
        with engine.connect() as conn:
            revision = conn.scalar(text("SELECT version_num FROM alembic_version"))
            if attack == "noop":
                assert result.returncode == 0, result.stderr
                assert revision == "0089_ahou_v3_monitoring"
                got = conn.scalar(
                    text(
                        "SELECT "
                        "(to_jsonb(t)-ARRAY['decision_contract','frozen_terms','terms_hash'])::te"
                        "xt "
                        "FROM ah_ou_decision_ledger t"
                    )
                )
                assert got == original
                assert (
                    conn.scalar(
                        text(
                            "SELECT count(*) FROM ah_ou_decision_ledger WHERE decision_contract I"
                            "S NOT "
                            "NULL"
                        )
                    )
                    == 0
                )
                assert conn.scalar(text("SELECT count(*) FROM ah_ou_v3_validation_sample")) == 0
                from sqlalchemy.orm import Session

                from w2.tracking.ah_ou_v3_postmatch import v3_validation_snapshot

                with Session(engine) as session:
                    current = v3_validation_snapshot(session)
                assert current["rows"] == []
                assert current["selected"] == current["completed_decisions"] == 0
                assert all(r["selected"] == 0 for r in current["by_market"].values())
                assert (
                    conn.scalar(
                        text(
                            "SELECT count(*) FROM pg_constraint WHERE "
                            "conrelid='ah_ou_decision_ledger'::regclass AND "
                            "conname='uq_ah_ou_decision_ledger_slot'"
                        )
                    )
                    == 1
                )
                assert (
                    conn.scalar(
                        text(
                            "SELECT count(*) FROM team_xg_rolling_snapshot WHERE first_committed_"
                            "at IS "
                            "NOT NULL OR pit_proven"
                        )
                    )
                    == 0
                )
            else:
                assert result.returncode != 0
                assert "PREEXISTING_AH_OU_LEDGER_" + faults[attack][1] in result.stderr, (
                    result.stderr
                )
                assert revision == "0076_forward_review_evidence"
                assert before() == stored
        print(
            {
                "case": attack,
                "schema": revision,
                "migration_exit": result.returncode,
                "preserved": True,
            }
        )
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.mark.parametrize("attack", ["noop", "extra", "type", "dependency"])
def test_minimal_capture_result_archive_keeps_unproven_rows_and_refuses_unknowns(
    monkeypatch, attack
):
    url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("W2_TEST_POSTGRES_URL required")
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    name = "w2_minimal_source_" + uuid.uuid4().hex[:12]
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    db = url.rsplit("/", 1)[0] + "/" + name
    monkeypatch.setenv("W2_DATABASE_URL", db)
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    engine = create_engine(db)

    def migrate(revision):
        return subprocess.run(
            [".venv/bin/alembic", "upgrade", revision],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )

    try:
        result = migrate("0076_forward_review_evidence")
        assert result.returncode == 0, result.stderr
        with engine.begin() as conn:
            # Isolated replica of the read-only observed production shapes.
            # Their real dependencies were absent. Never run this DDL on production.
            conn.execute(
                text("DROP TABLE matchday_endpoint_captures CASCADE; DROP TABLE results CASCADE")
            )
            conn.execute(
                text("""
                CREATE TABLE matchday_endpoint_captures (
                  capture_id varchar(64) PRIMARY KEY, raw_payload_sha256 varchar(64) NOT NULL);
                INSERT INTO matchday_endpoint_captures VALUES ('cap-1',repeat('a',64));
                CREATE TABLE results (fixture_id varchar(128) PRIMARY KEY,
                  home_goals integer, away_goals integer);
                INSERT INTO results VALUES ('f1',2,1);
            """)
            )
            conn.execute(text("UPDATE results SET home_goals=home_goals WHERE fixture_id='f1'"))
            assert conn.scalar(text("SELECT home_goals FROM results")) == 2
            faults = {
                "extra": (
                    "ALTER TABLE results ADD COLUMN unknown text",
                    "LEGACY_0076_SOURCE_SCHEMA_CONFLICT:results",
                ),
                "type": (
                    "ALTER TABLE results ALTER COLUMN home_goals TYPE bigint",
                    "LEGACY_0076_SOURCE_COLUMN_CONFLICT:results:home_goals",
                ),
                "dependency": (
                    "CREATE TABLE unexpected_reference (fixture_id varchar(128) REFERENCES result"
                    "s(fixture_id))",
                    "LEGACY_0076_SOURCE_DEPENDENCY_CONFLICT:results",
                ),
            }
            if attack != "noop":
                conn.execute(text(faults[attack][0]))
        result = migrate("head")
        with engine.connect() as conn:
            if attack == "noop":
                assert result.returncode == 0, result.stderr
                assert (
                    conn.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0089_ahou_v3_monitoring"
                )
                assert conn.execute(
                    text(
                        "SELECT fixture_id,home_goals,away_goals FROM w2_legacy_unproven_results_"
                        "0076"
                    )
                ).one() == ("f1", 2, 1)
                assert conn.execute(
                    text(
                        "SELECT capture_id,raw_payload_sha256 FROM w2_legacy_unproven_matchday_en"
                        "dpoint_captures_0076"
                    )
                ).one() == ("cap-1", "a" * 64)
                assert conn.scalar(text("SELECT count(*) FROM results")) == 0
                assert conn.scalar(text("SELECT count(*) FROM matchday_endpoint_captures")) == 0
                assert conn.scalar(text("SELECT count(*) FROM ah_ou_v3_validation_sample")) == 0
            else:
                assert result.returncode != 0 and faults[attack][1] in result.stderr, result.stderr
                assert (
                    conn.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0076_forward_review_evidence"
                )
                assert conn.scalar(text("SELECT home_goals FROM results")) == 2
                assert (
                    conn.scalar(text("SELECT to_regclass('w2_legacy_unproven_results_0076')"))
                    is None
                )
        if attack == "noop":
            from sqlalchemy.exc import DBAPIError

            with pytest.raises(DBAPIError, match="LEGACY_UNPROVEN_SOURCE_IMMUTABLE"):
                with engine.begin() as conn:
                    conn.execute(text("UPDATE w2_legacy_unproven_results_0076 SET home_goals=999"))
        print(
            {"case": attack, "migration_exit": result.returncode, "unproven_rows_preserved": True}
        )
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
