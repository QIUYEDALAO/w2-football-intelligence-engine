from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[2]
HEAD = "0045_eval_01a_results_outcome_ledger"


def test_0045_schema_and_fixture_identity_constraints(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'schema.db'}"
    _migrate(database_url, "upgrade", "head")
    engine = create_engine(database_url)
    inspector = inspect(engine)

    assert "outcome_ledger" in inspector.get_table_names()
    result_columns = {column["name"]: column for column in inspector.get_columns("results")}
    assert {
        "fixture_id",
        "home_goals",
        "away_goals",
        "result_status",
        "confirmed_at",
        "source_payload_sha256",
        "source_capture_id",
        "result_hash",
    } <= result_columns.keys()
    assert result_columns["fixture_id"]["type"].length == 128
    assert all(
        foreign_key["referred_table"] != "fixtures"
        for foreign_key in inspector.get_foreign_keys("results")
    )
    assert {"ix_results_confirmed_at"} <= {
        index["name"] for index in inspector.get_indexes("results")
    }
    assert {
        "ix_outcome_ledger_fixture_type_time",
        "ix_outcome_ledger_capture_identity",
        "ix_outcome_ledger_decision_hash",
    } <= {index["name"] for index in inspector.get_indexes("outcome_ledger")}

    values = {
        "id": "result-1",
        "fixture_id": "api_football:" + "1" * 64,
        "home_goals": 2,
        "away_goals": 1,
        "result_status": "FT",
        "confirmed_at": "2026-07-28T00:00:00Z",
        "source_payload_sha256": "a" * 64,
        "source_capture_id": None,
        "result_hash": "b" * 64,
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into results (
                    id, fixture_id, home_goals, away_goals, result_status,
                    confirmed_at, source_payload_sha256, source_capture_id, result_hash
                ) values (
                    :id, :fixture_id, :home_goals, :away_goals, :result_status,
                    :confirmed_at, :source_payload_sha256, :source_capture_id, :result_hash
                )
                """
            ),
            values,
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    insert into results (
                        id, fixture_id, home_goals, away_goals, result_status,
                        confirmed_at, source_payload_sha256, source_capture_id, result_hash
                    ) values (
                        'result-2', :fixture_id, 3, 1, 'FT',
                        :confirmed_at, :source_payload_sha256, null, :result_hash
                    )
                    """
                ),
                {
                    **values,
                    "result_hash": "c" * 64,
                },
            )


def test_0045_empty_downgrade_and_reupgrade(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'roundtrip.db'}"
    _migrate(database_url, "upgrade", "head")
    _migrate(database_url, "downgrade", "0044_drop_retired_shadow_strategy")
    inspector = inspect(create_engine(database_url))

    assert "outcome_ledger" not in inspector.get_table_names()
    assert "result_status" not in {
        column["name"] for column in inspector.get_columns("results")
    }
    assert any(
        foreign_key["referred_table"] == "fixtures"
        for foreign_key in inspector.get_foreign_keys("results")
    )

    _migrate(database_url, "upgrade", "head")
    assert "outcome_ledger" in inspect(create_engine(database_url)).get_table_names()


def test_0045_nonempty_downgrade_fails_closed(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'protected.db'}"
    _migrate(database_url, "upgrade", "head")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into outcome_ledger (
                    business_key, record_type, fixture_id, occurred_at,
                    schema_version, payload, payload_sha256, source_artifact, imported_at
                ) values (
                    :business_key, 'capture', 'fixture-1', :occurred_at,
                    'v1', '{}', :payload_sha256, 'test', :imported_at
                )
                """
            ),
            {
                "business_key": "a" * 64,
                "occurred_at": "2026-07-28T00:00:00Z",
                "payload_sha256": "b" * 64,
                "imported_at": "2026-07-28T00:00:00Z",
            },
        )

    result = _migrate(
        database_url,
        "downgrade",
        "0044_drop_retired_shadow_strategy",
        check=False,
    )

    assert result.returncode != 0
    assert "OUTCOME_LEDGER_DOWNGRADE_NONEMPTY" in result.stderr
    assert "outcome_ledger" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        version = connection.execute(
            text("select version_num from alembic_version")
        ).scalar_one()
    assert version == HEAD


def _migrate(
    database_url: str,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}",
            "W2_DATABASE_URL": database_url,
            "W2_ENVIRONMENT": "test",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result
