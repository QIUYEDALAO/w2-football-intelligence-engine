"""F1R-A0 runner: prove the offline recorder end to end and publish the result.

Deterministic and entirely local. It builds real `FeatureContribution` objects
through the production feature builders -- so the mapping is exercised against
the actual types, not a mock of them -- feeds them to the recorder, and records
what happened.

The fixtures are synthetic and labelled as such. They are a contract
demonstration, not evidence about any match, and nothing here wires the
production chain, starts a capture or touches a database.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
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
for _name, _file in (("w2_f1p_forward_factor_contract", "f1p_forward_factor_contract.py"),
                     ("w2_f1r_a0_recorder", "f1r_a0_offline_factor_recorder.py")):
    if _name not in sys.modules:
        _spec = importlib.util.spec_from_file_location(_name, _HERE / _file)
        assert _spec is not None and _spec.loader is not None
        _module = importlib.util.module_from_spec(_spec)
        sys.modules[_name] = _module
        _spec.loader.exec_module(_module)
contract = sys.modules["w2_f1p_forward_factor_contract"]
recorder = sys.modules["w2_f1r_a0_recorder"]

TASK_ID = "W2_AH_FACTOR_ACCURACY_F1R_A0_NARROW_REMEDIATION_2_20260910"
PARENT_COMMIT = "7e8b07f77bf0638692aea9e4bf30b9d0107fd8bd"
FIXTURE_KIND = "SYNTHETIC_CONTRACT_FIXTURE"
LEDGER_NAME = "F1R_A0_REFERENCE_LEDGER.jsonl"

# Fixed instants so two runs are byte-identical. Obviously synthetic ids.
KICKOFF = datetime(2026, 10, 1, 19, 30, tzinfo=UTC)
AS_OF = KICKOFF - timedelta(hours=1)
EVALUATED_AT = (KICKOFF - timedelta(minutes=55)).isoformat()
CREATED_AT = (KICKOFF - timedelta(minutes=54)).isoformat()
EVALUATION_ID = "dqe-" + "1" * 64
ATTEMPT_ID = "att-" + "2" * 60
FIXTURE_ID = "9000001"
CAPTURE_SHA = "3" * 64
# Synthetic provenance for a synthetic fixture. "SYNTHETIC_FIXTURE_v1" is a
# fixture value, not a production factor version: no builder emits one, and
# F1R-B must supply a real source before anything is wired.
SYNTHETIC_PROVENANCE = {
    factor_id: recorder.FactorProvenance(
        factor_version="SYNTHETIC_FIXTURE_v1",
        source_capture_id=f"synthetic-capture-{factor_id.lower()}",
        source_capture_sha256=CAPTURE_SHA,
        source_version="w2.feature_engine.synthetic.v1")
    for factor_id in contract.ALLOWED_FACTOR_IDS
}


# The canonical AH path only accepts rows that carry a settled AH fact identity,
# so the fixture supplies one rather than a looser shape the builder would drop.
def _history(team_id: str, *, days_ago: int, settlement: str) -> TeamMatchHistory:
    return TeamMatchHistory(
        team_id=team_id,
        opponent_id=f"opp-{days_ago}",
        kickoff_at=KICKOFF - timedelta(days=days_ago),
        goals_for=1,
        goals_against=1,
        ah_line=-0.25,
        source="canonical_historical_ah_fact",
        source_group="canonical_historical_ah_fact",
        collection_status="CANONICAL_AH_FACT",
        ah_fact_id=f"fact-{team_id}-{days_ago}",
        ah_fact_hash=f"hash-{team_id}-{days_ago}",
        settlement_outcome=settlement,
    )


def _plain_history(team_id: str, *, days_ago: int) -> TeamMatchHistory:
    """Enough for rest days, deliberately without a canonical AH fact."""
    return TeamMatchHistory(
        team_id=team_id,
        opponent_id=f"opp-{days_ago}",
        kickoff_at=KICKOFF - timedelta(days=days_ago),
        goals_for=1,
        goals_against=1,
    )


COVERAGE = CoverageProfile(
    xg="READY", lineups_injuries="READY", squad_value="READY",
    bookmaker_depth="READY", h2h="READY", settled_ah="READY")


def _context() -> FeatureContext:
    return FeatureContext(
        fixture_id=FIXTURE_ID, competition_id="synthetic_league",
        home_team_id="home-1", away_team_id="away-1",
        kickoff_at=KICKOFF, as_of=AS_OF)


def complete_feature_set() -> FeatureSet:
    """All four factors with real evidence, built by the production builders."""
    context = _context()
    home = [_history("home-1", days_ago=n, settlement="WIN") for n in (3, 10, 17, 24, 31)]
    away = [_history("away-1", days_ago=n, settlement="LOSS") for n in (4, 11, 18, 25, 32)]
    meetings = [_history("home-1", days_ago=n, settlement="WIN") for n in (200, 400)]
    contributions = (
        rest_fitness_factor(context=context, home_history=home, away_history=away),
        recent_ah_cover_factor(
            context=context, profile=COVERAGE, home_history=home, away_history=away),
        h2h_factor(context=context, profile=COVERAGE, meetings=meetings),
        true_xg_factor(
            context=context, profile=COVERAGE,
            home_xg=[TeamXgSnapshot(
                team_id="home-1", observed_at=AS_OF - timedelta(days=1),
                xg_for=1.62, xg_against=1.05, goals_for=8, goals_against=5)],
            away_xg=[TeamXgSnapshot(
                team_id="away-1", observed_at=AS_OF - timedelta(days=2),
                xg_for=1.11, xg_against=1.48, goals_for=5, goals_against=9)]),
    )
    return FeatureSet(
        fixture_id=FIXTURE_ID, competition_id="synthetic_league", as_of=AS_OF,
        contributions=contributions, status=FeatureStatus.READY)


def degraded_feature_set() -> FeatureSet:
    """Two factors with no evidence at all: absences must still be recorded."""
    context = _context()
    home = [_plain_history("home-1", days_ago=n) for n in (3, 10)]
    away = [_plain_history("away-1", days_ago=n) for n in (4, 11)]
    contributions = (
        rest_fitness_factor(context=context, home_history=home, away_history=away),
        recent_ah_cover_factor(
            context=context, profile=COVERAGE, home_history=home, away_history=away),
        h2h_factor(context=context, profile=COVERAGE, meetings=[]),
        true_xg_factor(context=context, profile=COVERAGE, home_xg=[], away_xg=[]),
    )
    return FeatureSet(
        fixture_id=FIXTURE_ID, competition_id="synthetic_league", as_of=AS_OF,
        contributions=contributions, status=FeatureStatus.DEGRADED)


def build(feature_set: FeatureSet, *, suffix: str,
          provenance: dict | None = None) -> list[Any]:
    return recorder.build_batch(
        feature_set=feature_set, context=_context(),
        evaluation_id=EVALUATION_ID if suffix == "a" else "dqe-" + "4" * 64,
        attempt_id=ATTEMPT_ID if suffix == "a" else "att-" + "5" * 60,
        evaluated_at_utc=EVALUATED_AT, created_at_utc=CREATED_AT,
        provenance=provenance or SYNTHETIC_PROVENANCE)


def _authority_closure(feature_set: FeatureSet) -> dict[str, Any]:
    """What team_score scored, so the applied-weight semantics are auditable."""
    authority = recorder.scoring_authority_view(feature_set.contributions)
    return {
        "scoring_factors": {
            factor_id: {"weight": row["weight"], "share": row["share"]}
            for factor_id, row in sorted(authority["scoring_factors"].items())},
        "weight_sum_used": authority["weight_sum_used"],
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

    # A batch whose F5/F6 have no explicit source-observed time is refused.
    # This is the blocking finding, demonstrated rather than merely asserted.
    result_derived_refusal = None
    try:
        build(complete_feature_set(), suffix="a")
    except contract.ContractError as exc:
        result_derived_refusal = exc.code

    # A supplied time that merely echoes the fixture kickoff is refused too.
    kickoff_echo = dict(SYNTHETIC_PROVENANCE)
    for factor_id in recorder.RESULT_DERIVED_FACTORS:
        contribution = next(c for c in complete_feature_set().contributions
                            if c.feature_id == factor_id)
        kickoff_echo[factor_id] = replace(
            SYNTHETIC_PROVENANCE[factor_id],
            source_observed_at=contribution.observed_at.isoformat())
    kickoff_echo_refusal = None
    try:
        build(complete_feature_set(), suffix="a", provenance=kickoff_echo)
    except contract.ContractError as exc:
        kickoff_echo_refusal = exc.code

    # With a synthetic explicit source-observed time the batch records, which
    # shows the port works. It is not evidence that such a time exists in
    # production: it does not.
    with_source_time = dict(SYNTHETIC_PROVENANCE)
    for factor_id in recorder.RESULT_DERIVED_FACTORS:
        with_source_time[factor_id] = replace(
            SYNTHETIC_PROVENANCE[factor_id],
            source_observed_at=(AS_OF - timedelta(hours=6)).isoformat())
    complete = build(complete_feature_set(), suffix="a",
                     provenance=with_source_time)
    first = recorder.append_batch(ledger, complete)
    repeat = recorder.append_batch(ledger, complete)

    degraded = build(degraded_feature_set(), suffix="b")
    absent = recorder.append_batch(ledger, degraded)

    # a refused batch must leave the file byte-identical
    before = ledger_path.read_bytes()
    incomplete = [record for record in complete if record.factor_id != "F6_H2H"]
    refusal = None
    try:
        recorder.append_batch(ledger, incomplete)
    except contract.ContractError as exc:
        refusal = exc.code
    unchanged_after_refusal = ledger_path.read_bytes() == before

    rows = ledger.rows()
    for row in rows:
        ledger.readback(row["observation_id"])
        view = ledger.as_of_view(row["observation_id"])
        if contract.POST_EVENT_FIELDS & set(view):
            raise SystemExit("AS_OF_VIEW_LEAKED_POST_EVENT_FIELD")

    def summarise(observation_ids: list[str]) -> dict[str, Any]:
        stored = {row["observation_id"]: row for row in rows}
        seen = [stored[observation_id] for observation_id in observation_ids]
        return {
            "factor_ids": sorted(row["factor_id"] for row in seen),
            "statuses": {row["factor_id"]: row["factor_status"] for row in seen},
            "applied_weights": {
                row["factor_id"]: row["applied_weight"] for row in seen},
            "signed_scores": {
                row["factor_id"]: row["signed_score"] for row in seen},
            "evidence_time_semantics": {
                row["factor_id"]: row["factor_inputs"]["evidence_time_semantics"]
                for row in seen},
            "evidence_time_utc": {
                row["factor_id"]: row["evidence_time_utc"] for row in seen},
            "declared_weights": {
                row["factor_id"]: row["factor_inputs"]["declared_weight"]
                for row in seen},
            "applied_weight_sum": str(sum(
                (Decimal(row["applied_weight"]) for row in seen), Decimal(0))),
            "every_evidence_time_strictly_before_evaluated_at": all(
                contract.parse_aware_utc(row["evidence_time_utc"], field_name="e")
                < contract.parse_aware_utc(row["evaluated_at_utc"], field_name="v")
                for row in seen),
        }

    result = {
        "schema_version": "w2.f1r_a0_offline_recorder_result.v1",
        "task_id": TASK_ID,
        "parent_commit": PARENT_COMMIT,
        "recorder_id": recorder.RECORDER_ID,
        "contract_id": contract.CONTRACT_ID,
        "fixture_kind": FIXTURE_KIND,
        "fixture_note": (
            "Synthetic contract fixture. Not a real match, not evidence about any "
            "match, and not proof that the production chain is wired."),
        "complete_batch": {
            "appended": first["appended"], "batch_size": first["batch_size"],
            **summarise(first["observation_ids"])},
        "idempotent_replay": {
            "appended": repeat["appended"],
            "idempotent_no_ops": repeat["idempotent_no_ops"]},
        "absent_factor_batch": {
            "appended": absent["appended"], **summarise(absent["observation_ids"])},
        "incomplete_batch_refused_with": refusal,
        "result_derived_without_source_time_refused_with": result_derived_refusal,
        "kickoff_echo_as_source_time_refused_with": kickoff_echo_refusal,
        "f5_f6_source_observed_time_exists_in_production": False,
        "f5_f6_blocking_reason": (
            "TeamMatchHistory carries no source-observed timestamp and its "
            "observed_at property returns kickoff_at. results.confirmed_at exists "
            "in the database but is never carried onto the object the factor "
            "builders consume, so F5 and F6 have no bindable per-factor source "
            "time. Wiring one would change src/w2/features and src/w2/prematch, "
            "both out of scope for A0."),
        "ledger_unchanged_after_refusal": unchanged_after_refusal,
        "scoring_authority_closure": {
            "complete_batch": _authority_closure(complete_feature_set()),
            "absent_factor_batch": _authority_closure(degraded_feature_set()),
        },
        "ledger_rows": len(rows),
        "readback_verified_rows": len(rows),
        "offline_recorder_implemented": True,
        "production_wiring_not_started": True,
        "live_capture_not_started": True,
        "deployment_not_executed": True,
        "weight_calibration_not_started": True,
        "provider_calls": 0,
        "public_http_fetch": 0,
        "production_db_reads": 0,
        "production_db_writes": 0,
        "obsidian_writes": 0,
        "f2_allowed": False,
        "f3_allowed": False,
        "final_state": "BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE",
    }
    (output / "OFFLINE_RECORDER_RESULT.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "final_state": result["final_state"],
        "ledger_rows": result["ledger_rows"],
        "complete_batch_appended": first["appended"],
        "idempotent_replay_appended": repeat["appended"],
        "incomplete_batch_refused_with": refusal,
        "result_derived_without_source_time_refused_with": result_derived_refusal,
        "kickoff_echo_as_source_time_refused_with": kickoff_echo_refusal,
        "ledger_unchanged_after_refusal": unchanged_after_refusal,
        "complete_batch_semantics": result["complete_batch"][
            "evidence_time_semantics"],
        "absent_batch_statuses": result["absent_factor_batch"]["statuses"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
