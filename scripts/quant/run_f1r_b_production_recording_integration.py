"""F1R-B runner: prove the production wiring, disabled, and publish the result.

Deterministic and entirely local. It builds real `FeatureContribution` objects
through the production feature builders, derives capture identity through the
production read ports from rows shaped exactly like the production
projections, records the batch, and then exercises the migration on an
isolated database it creates and destroys.

Nothing here enables live capture, calls a Provider, reads or writes the
production database, touches a VPS, or changes any decision behaviour.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.competitions.registry import CoverageProfile
from w2.features.framework import FeatureContext, FeatureSet, FeatureStatus
from w2.features.live_factors import TeamXgSnapshot, true_xg_factor
from w2.features.team_factors import (
    TeamMatchHistory,
    h2h_factor,
    recent_ah_cover_factor,
    rest_fitness_factor,
)

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]


def _load(module_name: str, filename: str) -> Any:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, _HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


integration = _load("w2_f1r_b_integration", "f1r_b_production_recording_integration.py")
ports = _load("w2_f1r_b_production_ports", "f1r_b_production_ports.py")
capture = _load("w2_f1r_b_source_capture", "f1r_b_source_capture.py")
fixtures = _load("w2_f1r_b_fixtures", "f1r_b_fixtures.py")
store_module = _load("w2_f1r_b_observation_store", "f1r_b_observation_store.py")
recorder = integration.recorder
contract = integration.contract

TASK_ID = "W2_AH_FACTOR_ACCURACY_F1R_B_PRODUCTION_RECORDING_INTEGRATION_20260911"
PARENT_COMMIT = "71daa3f5ec17ac3c5484e75a87d6bcac990d4bae"
LEDGER_NAME = "F1R_B_REFERENCE_LEDGER.jsonl"
PRE_MIGRATION_REVISION = "0070_notification_delivery_routing"
MIGRATION_REVISION = "0071_forward_ah_factor_observation"

EVALUATION_ID = "dqe-" + "1" * 64
ATTEMPT_ID = "att-" + "2" * 60

COVERAGE = CoverageProfile(
    xg="READY", lineups_injuries="READY", squad_value="READY",
    bookmaker_depth="READY", h2h="READY", settled_ah="READY")

HOME_HISTORY_DAYS = (3, 10, 17)
AWAY_HISTORY_DAYS = (4, 11, 18)
MEETING_DAYS = (200, 400)


# --- production-shaped rows ------------------------------------------------
def history_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    home = [fixtures.history_row(
        team_w2_id=fixtures.HOME_TEAM, opponent_w2_id=f"w2-opp-{n}",
        days_ago=n, goals_for=2, goals_against=1) for n in HOME_HISTORY_DAYS]
    away = [fixtures.history_row(
        team_w2_id=fixtures.AWAY_TEAM, opponent_w2_id=f"w2-opp-{n}",
        days_ago=n, goals_for=1, goals_against=1) for n in AWAY_HISTORY_DAYS]
    return home, away


def meeting_rows() -> list[dict[str, Any]]:
    return [fixtures.history_row(
        team_w2_id=fixtures.HOME_TEAM, opponent_w2_id=fixtures.AWAY_TEAM,
        days_ago=n, goals_for=2, goals_against=0) for n in MEETING_DAYS]


def xg_rows() -> list[dict[str, Any]]:
    return [
        fixtures.xg_snapshot_row(
            team_id=fixtures.HOME_TEAM, days_ago=1, xg_for=1.62, xg_against=1.05),
        fixtures.xg_snapshot_row(
            team_id=fixtures.AWAY_TEAM, days_ago=2, xg_for=1.11, xg_against=1.48),
    ]


def captures_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        row["endpoint_capture_id"]: ports.endpoint_capture_from_row(
            fixtures.capture_row(row))
        for row in rows
    }


# --- contributions, built by the production builders -----------------------
def _to_history(row: dict[str, Any], *, source_group: str) -> TeamMatchHistory:
    """The same projection `_canonical_history_rows_to_features` performs."""
    return TeamMatchHistory(
        team_id=row["team_w2_id"],
        opponent_id=row["opponent_w2_id"],
        kickoff_at=datetime.fromisoformat(row["kickoff_utc"].replace("Z", "+00:00")),
        goals_for=row["goals_for"],
        goals_against=row["goals_against"],
        source="canonical_team_match_history",
        source_group=source_group,
        is_independent_signal=True,
        collection_status="READY",
        result_identity_hash=row["result_identity_hash"],
    )


def context() -> FeatureContext:
    return FeatureContext(
        fixture_id=fixtures.FIXTURE_ID, competition_id=fixtures.COMPETITION,
        home_team_id=fixtures.HOME_TEAM, away_team_id=fixtures.AWAY_TEAM,
        kickoff_at=fixtures.KICKOFF, as_of=fixtures.AS_OF)


def feature_set() -> FeatureSet:
    ctx = context()
    home_rows, away_rows = history_rows()
    home = [_to_history(row, source_group="team_fixture_history") for row in home_rows]
    away = [_to_history(row, source_group="team_fixture_history") for row in away_rows]
    meetings = [_to_history(row, source_group="h2h") for row in meeting_rows()]
    snapshots = xg_rows()

    def snapshot(row: dict[str, Any]) -> TeamXgSnapshot:
        return TeamXgSnapshot(
            team_id=row["team_id"],
            observed_at=datetime.fromisoformat(row["as_of_time"].replace("Z", "+00:00")),
            xg_for=row["rolling_xg_for"], xg_against=row["rolling_xg_against"],
            goals_for=round(row["rolling_goals_for"]),
            goals_against=round(row["rolling_goals_against"]))

    contributions = (
        rest_fitness_factor(context=ctx, home_history=home, away_history=away),
        # No canonical AH fact reaches this builder in production, so the
        # fixture does not manufacture one either.
        recent_ah_cover_factor(
            context=ctx, profile=COVERAGE, home_history=home, away_history=away),
        h2h_factor(context=ctx, profile=COVERAGE, meetings=meetings),
        true_xg_factor(
            context=ctx, profile=COVERAGE,
            home_xg=[snapshot(snapshots[0])], away_xg=[snapshot(snapshots[1])]),
    )
    return FeatureSet(
        fixture_id=fixtures.FIXTURE_ID, competition_id=fixtures.COMPETITION,
        as_of=fixtures.AS_OF, contributions=contributions,
        status=FeatureStatus.READY)


# --- bindings --------------------------------------------------------------
def bindings(*, f5_absence_reason: str) -> dict[str, Any]:
    from w2.domain.factor_versions import factor_computation_version

    home_rows, away_rows = history_rows()
    latest = [home_rows[0], away_rows[0]]
    meetings = meeting_rows()
    return {
        "F3_REST_FITNESS": integration.FactorSourceBinding(
            factor_version=factor_computation_version("F3_REST_FITNESS"),
            records=ports.rest_fitness_records(fixtures.event_time_rows(latest))),
        "F5_RECENT_AH_COVER": integration.FactorSourceBinding(
            factor_version=factor_computation_version("F5_RECENT_AH_COVER"),
            records=integration.absence_records(
                "F5_RECENT_AH_COVER",
                query_identity="canonical_historical_ah_fact:none",
                as_of_utc=fixtures.AS_OF.isoformat(),
                reason=f5_absence_reason)),
        "F6_H2H": integration.FactorSourceBinding(
            factor_version=factor_computation_version("F6_H2H"),
            records=ports.h2h_records(meetings, captures=captures_for(meetings))),
        "F9_TRUE_XG": integration.FactorSourceBinding(
            factor_version=factor_computation_version("F9_TRUE_XG"),
            records=ports.true_xg_records(xg_rows())),
    }


def f5_refusal() -> str:
    try:
        ports.ah_fact_records([])
    except ports.SourcePortError as exc:
        return exc.code
    raise SystemExit("F5_PORT_DID_NOT_REFUSE")


def build(**overrides: Any) -> list[Any]:
    return integration.build_production_batch(
        feature_set=feature_set(), context=context(),
        evaluation_id=overrides.pop("evaluation_id", EVALUATION_ID),
        attempt_id=overrides.pop("attempt_id", ATTEMPT_ID),
        evaluated_at_utc=fixtures.EVALUATED_AT.isoformat(),
        created_at_utc=fixtures.CREATED_AT.isoformat(),
        bindings=overrides.pop("bindings", bindings(f5_absence_reason=f5_refusal())))


def _refusal(fn: Any) -> str | None:
    try:
        fn()
    except (recorder.BatchError, capture.CaptureIdentityError,
            ports.SourcePortError, contract.ContractError) as exc:
        return exc.code
    return None


# --- isolated migration replay --------------------------------------------
def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ, W2_DATABASE_URL=database_url)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_ROOT, env=environment, capture_output=True, text=True, check=False)


def isolated_replay(batch: list[Any]) -> dict[str, Any]:
    """upgrade -> write -> readback -> rollback, on a database created here.

    PostgreSQL is not installed in this environment, so the isolated database is
    a file-backed SQLite created in a temporary directory and deleted at the
    end. It is a real database with real DDL, real constraints and real
    transactions; what it is not is the production one, which is the point.
    """
    import sqlalchemy as sa

    with tempfile.TemporaryDirectory(prefix="w2-f1r-b-isolated-") as directory:
        database = Path(directory) / "f1r_b_isolated.db"
        url = f"sqlite+pysqlite:///{database}"
        environment = dict(os.environ, W2_DATABASE_URL=url)

        # The pre-migration state: every table except the one 0071 adds.
        prepare = subprocess.run(
            [sys.executable, "-c",
             "from w2.infrastructure.database import Base, create_engine\n"
             "import w2.infrastructure.persistence  # noqa: F401\n"
             "engine = create_engine()\n"
             "tables = [table for name, table in Base.metadata.tables.items()\n"
             "          if name != 'forward_ah_factor_observations']\n"
             "Base.metadata.create_all(engine, tables=tables)\n"
             "print(len(tables))\n"],
            cwd=_ROOT, env=environment, capture_output=True, text=True, check=True)
        pre_migration_tables = int(prepare.stdout.strip())

        stamped = _alembic(url, "stamp", PRE_MIGRATION_REVISION)
        upgraded = _alembic(url, "upgrade", "head")
        repeat_upgrade = _alembic(url, "upgrade", "head")

        engine = sa.create_engine(url)
        inspector = sa.inspect(engine)
        table_after_upgrade = "forward_ah_factor_observations" in inspector.get_table_names()
        other_tables_after_upgrade = len(
            [name for name in inspector.get_table_names()
             if name not in {"forward_ah_factor_observations", "alembic_version"}])

        store = store_module.ForwardFactorObservationStore(engine)
        appended = store.append_batch(batch)
        replayed = store.append_batch(batch)
        readback = store.by_id()
        payload_matches = all(
            readback[record.observation_id][name] == contract.as_dict(record)[name]
            for record in (contract.validate(item) for item in batch)
            for name in contract.BUSINESS_FIELDS)

        # A populated table refuses to be dropped: append-only facts survive a
        # rollback attempt rather than being destroyed by it.
        blocked = _alembic(url, "downgrade", PRE_MIGRATION_REVISION)
        rows_after_blocked_rollback = len(store.by_id())

        # An empty table rolls back cleanly. Removing the rows here is a
        # property of this replay -- production rollback uses the documented
        # forward-compatible disable path instead.
        with sa.orm.Session(engine) as session:
            session.execute(sa.delete(
                sa.table("forward_ah_factor_observations",
                         sa.column("observation_id"))))
            session.commit()
        rolled_back = _alembic(url, "downgrade", PRE_MIGRATION_REVISION)
        repeat_rollback = _alembic(url, "downgrade", PRE_MIGRATION_REVISION)
        inspector = sa.inspect(engine)
        table_after_rollback = "forward_ah_factor_observations" in inspector.get_table_names()
        other_tables_after_rollback = len(
            [name for name in inspector.get_table_names()
             if name not in {"forward_ah_factor_observations", "alembic_version"}])
        engine.dispose()

        return {
            "schema_version": "w2.f1r_b_isolated_replay.v1",
            "database_kind": "SQLITE_FILE_ISOLATED_TEMPORARY",
            "database_note": (
                "PostgreSQL is not installed in this environment; the isolated "
                "database is a file-backed SQLite created and destroyed by this "
                "run. Real DDL, real constraints, real transactions, and not the "
                "production database."),
            "pre_migration_tables": pre_migration_tables,
            "stamp_returncode": stamped.returncode,
            "upgrade_returncode": upgraded.returncode,
            "repeat_upgrade_returncode": repeat_upgrade.returncode,
            "table_present_after_upgrade": table_after_upgrade,
            "other_tables_after_upgrade": other_tables_after_upgrade,
            "rows_appended": appended["appended"],
            "replay_appended": replayed["appended"],
            "replay_idempotent_no_ops": replayed["idempotent_no_ops"],
            "readback_rows": len(readback),
            "readback_payload_matches_contract": payload_matches,
            "populated_rollback_returncode": blocked.returncode,
            "populated_rollback_refused": blocked.returncode != 0,
            "populated_rollback_reason": (
                "FORWARD_AH_FACTOR_OBSERVATION_DOWNGRADE_WOULD_DESTROY_FACTS"
                if "WOULD_DESTROY_FACTS" in blocked.stderr else blocked.stderr[-200:]),
            "rows_after_blocked_rollback": rows_after_blocked_rollback,
            "empty_rollback_returncode": rolled_back.returncode,
            "repeat_rollback_returncode": repeat_rollback.returncode,
            "table_present_after_rollback": table_after_rollback,
            "other_tables_after_rollback": other_tables_after_rollback,
            "unrelated_tables_untouched": (
                other_tables_after_upgrade == other_tables_after_rollback
                == pre_migration_tables),
        }


# --- report ---------------------------------------------------------------
def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "factor_ids": sorted(row["factor_id"] for row in rows),
        "factor_versions": {row["factor_id"]: row["factor_version"] for row in rows},
        "statuses": {row["factor_id"]: row["factor_status"] for row in rows},
        "applied_weights": {row["factor_id"]: row["applied_weight"] for row in rows},
        "declared_weights": {
            row["factor_id"]: row["factor_inputs"]["declared_weight"] for row in rows},
        "signed_scores": {row["factor_id"]: row["signed_score"] for row in rows},
        "evidence_time_semantics": {
            row["factor_id"]: row["factor_inputs"]["evidence_time_semantics"]
            for row in rows},
        "evidence_time_utc": {
            row["factor_id"]: row["evidence_time_utc"] for row in rows},
        "source_capture_ids": {
            row["factor_id"]: row["source_capture_id"] for row in rows},
        "source_capture_sha256": {
            row["factor_id"]: row["source_capture_sha256"] for row in rows},
        "source_record_ids": {
            row["factor_id"]: row["factor_inputs"]["source_record_ids"] for row in rows},
        "source_observed_times": {
            row["factor_id"]: row["factor_inputs"]["source_observed_times"]
            for row in rows},
        "applied_weight_sum": str(sum(
            (Decimal(row["applied_weight"]) for row in rows), Decimal(0))),
        "every_evidence_time_strictly_before_evaluated_at": all(
            contract.parse_aware_utc(row["evidence_time_utc"], field_name="e")
            < contract.parse_aware_utc(row["evaluated_at_utc"], field_name="v")
            for row in rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    ledger_path = output / LEDGER_NAME
    if ledger_path.exists():
        ledger_path.unlink()
    ledger = contract.ForwardFactorLedger(ledger_path)

    batch = build()
    appended = recorder.append_batch(ledger, batch)
    replayed = recorder.append_batch(ledger, batch)

    # Refusals, demonstrated rather than asserted.
    wrong_version = dict(bindings(f5_absence_reason=f5_refusal()))
    wrong_version["F3_REST_FITNESS"] = replace(
        wrong_version["F3_REST_FITNESS"], factor_version="v1")
    version_refusal = _refusal(lambda: build(bindings=wrong_version))

    synthetic = dict(bindings(f5_absence_reason=f5_refusal()))
    synthetic["F9_TRUE_XG"] = replace(
        synthetic["F9_TRUE_XG"],
        records=[replace(record, synthetic=True)
                 for record in synthetic["F9_TRUE_XG"].records])
    synthetic_refusal = _refusal(lambda: build(bindings=synthetic))

    meetings = meeting_rows()
    echoed = captures_for(meetings)
    for row in meetings:
        echoed[row["endpoint_capture_id"]] = replace(
            echoed[row["endpoint_capture_id"]],
            provider_captured_at=row["kickoff_utc"].replace("Z", "+00:00"))
    kickoff_refusal = _refusal(
        lambda: ports.h2h_records(meetings, captures=echoed))

    uncaptured = [dict(row, endpoint_capture_id=None) for row in meetings]
    uncaptured_refusal = _refusal(
        lambda: ports.h2h_records(uncaptured, captures={}))

    leaked = _refusal(lambda: ports.rest_fitness_records(meetings))

    before = ledger_path.read_bytes()
    incomplete_refusal = _refusal(
        lambda: recorder.append_batch(
            ledger, [record for record in batch if record.factor_id != "F6_H2H"]))
    unchanged_after_refusal = ledger_path.read_bytes() == before

    rows = ledger.rows()
    for row in rows:
        ledger.readback(row["observation_id"])

    replay = isolated_replay(batch)

    result = {
        "schema_version": "w2.f1r_b_production_recording_result.v1",
        "task_id": TASK_ID,
        "parent_commit": PARENT_COMMIT,
        "integration_id": integration.INTEGRATION_ID,
        "recorder_id": recorder.RECORDER_ID,
        "contract_id": contract.CONTRACT_ID,
        "capture_contract": capture.CAPTURE_CONTRACT,
        "fixture_kind": fixtures.FIXTURE_KIND,
        "fixture_note": (
            "Offline rows shaped as the production projections. Not production "
            "data and not evidence about any match. The capture identities are "
            "computed from this content by the production ports, not fabricated."),
        "live_capture_enabled": ports.PRODUCTION_CAPTURE_ENABLED,
        "complete_batch": {
            "appended": appended["appended"], "batch_size": appended["batch_size"],
            **summarise(rows)},
        "idempotent_replay": {
            "appended": replayed["appended"],
            "idempotent_no_ops": replayed["idempotent_no_ops"]},
        "caller_version_disagrees_refused_with": version_refusal,
        "synthetic_source_in_production_refused_with": synthetic_refusal,
        "f6_kickoff_as_source_time_refused_with": kickoff_refusal,
        "f6_row_without_capture_refused_with": uncaptured_refusal,
        "f3_result_field_leak_refused_with": leaked,
        "incomplete_batch_refused_with": incomplete_refusal,
        "ledger_unchanged_after_refusal": unchanged_after_refusal,
        "f5_source_port_refused_with": f5_refusal(),
        "f5_blocking_evidence": list(ports.F5_BLOCKING_EVIDENCE),
        "f6_source_time_proven": True,
        "f6_source_time_authority": (
            "canonical_team_match_history.endpoint_capture_id -> "
            "matchday_endpoint_captures.provider_captured_at"),
        "f9_source_time_proven": True,
        "f9_source_time_authority": (
            "team_xg_rolling_snapshot.as_of_time, set by materialize_rolling_xg "
            "to max(max(component.kickoff_at, component.captured_at))"),
        "f5_source_time_proven": False,
        "isolated_replay": replay,
        "ledger_rows": len(rows),
        "readback_verified_rows": len(rows),
        "provider_calls": 0,
        "public_http_fetch": 0,
        "production_db_reads": 0,
        "production_db_writes": 0,
        "deployment_executed": False,
        "scheduler_modified": False,
        "dashboard_modified": False,
        "v4_decision_behavior_changed": False,
        "historical_148_backfilled": False,
        "obsidian_writes": 0,
        "final_state": "BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE",
    }
    (output / "F1R_B_RESULT.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    (output / "ISOLATED_REPLAY_RESULT.json").write_text(
        json.dumps(replay, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    # The manifests the capture hashes were taken over, published so an
    # independent oracle can re-derive those hashes without importing any of
    # this code.
    manifests = {
        factor_id: capture.capture_identity(factor_id, binding.records).manifest
        for factor_id, binding in sorted(
            bindings(f5_absence_reason=f5_refusal()).items())
    }
    (output / "F1R_B_SOURCE_MANIFESTS.json").write_text(
        json.dumps(manifests, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "final_state": result["final_state"],
        "ledger_rows": result["ledger_rows"],
        "statuses": result["complete_batch"]["statuses"],
        "evidence_time_semantics": result["complete_batch"]["evidence_time_semantics"],
        "applied_weight_sum": result["complete_batch"]["applied_weight_sum"],
        "caller_version_disagrees_refused_with": version_refusal,
        "f6_kickoff_as_source_time_refused_with": kickoff_refusal,
        "f5_source_port_refused_with": result["f5_source_port_refused_with"],
        "isolated_replay_ok": (
            replay["upgrade_returncode"] == 0
            and replay["populated_rollback_refused"]
            and replay["empty_rollback_returncode"] == 0
            and replay["unrelated_tables_untouched"]),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
