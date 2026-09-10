"""F1R-A0 offline recorder: a batch is all four factors or nothing.

The recorder's job is to turn the live contribution objects into F1P
observations without inventing anything, and to make a partially recorded
evaluation impossible. Most of what follows is therefore refusal, and every
refusal asserts the ledger is byte-identical afterwards.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from w2.competitions.registry import CoverageProfile
from w2.features.framework import FeatureContext, FeatureSet, FeatureStatus
from w2.features.live_factors import TeamXgSnapshot, true_xg_factor
from w2.features.team_factors import (
    TeamMatchHistory,
    h2h_factor,
    recent_ah_cover_factor,
    rest_fitness_factor,
)

REPO = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO / "scripts/quant/f1p_forward_factor_contract.py"
RECORDER_PATH = REPO / "scripts/quant/f1r_a0_offline_factor_recorder.py"
RUNNER_PATH = REPO / "scripts/quant/run_f1r_a0_offline_factor_recorder.py"
OUTPUT = REPO / "docs/review_packages/W2_AH_FACTOR_ACCURACY_F1R_A0_20260910"


def _load(name: str, path: Path):  # type: ignore[no-untyped-def]
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = _load("w2_f1p_forward_factor_contract", CONTRACT_PATH)
recorder = _load("w2_f1r_a0_recorder", RECORDER_PATH)
ContractError = contract.ContractError

KICKOFF = datetime(2026, 10, 1, 19, 30, tzinfo=UTC)
AS_OF = KICKOFF - timedelta(hours=1)
EVALUATED_AT = (KICKOFF - timedelta(minutes=55)).isoformat()
CREATED_AT = (KICKOFF - timedelta(minutes=54)).isoformat()
CAPTURE_SHA = "3" * 64
SOURCE_OBSERVED = (AS_OF - timedelta(hours=6)).isoformat()


def _provenance(**per_factor):  # type: ignore[no-untyped-def]
    """Synthetic provenance. Result-derived factors get an explicit source time."""
    base = {
        factor_id: recorder.FactorProvenance(
            factor_version="SYNTHETIC_FIXTURE_v1",
            source_capture_id=f"capture-{factor_id.lower()}",
            source_capture_sha256=CAPTURE_SHA,
            source_version="w2.features.v1",
            source_observed_at=(SOURCE_OBSERVED
                                if factor_id in recorder.RESULT_DERIVED_FACTORS
                                else None))
        for factor_id in contract.ALLOWED_FACTOR_IDS
    }
    base.update(per_factor)
    return base
COVERAGE = CoverageProfile(
    xg="READY", lineups_injuries="READY", squad_value="READY",
    bookmaker_depth="READY", h2h="READY", settled_ah="READY")


def _context(fixture_id: str = "9000001") -> FeatureContext:
    return FeatureContext(
        fixture_id=fixture_id, competition_id="synthetic_league",
        home_team_id="home-1", away_team_id="away-1",
        kickoff_at=KICKOFF, as_of=AS_OF)


def _fact(team_id: str, *, days_ago: int, settlement: str) -> TeamMatchHistory:
    return TeamMatchHistory(
        team_id=team_id, opponent_id=f"opp-{days_ago}",
        kickoff_at=KICKOFF - timedelta(days=days_ago),
        goals_for=1, goals_against=1, ah_line=-0.25,
        source="canonical_historical_ah_fact",
        source_group="canonical_historical_ah_fact",
        collection_status="CANONICAL_AH_FACT",
        ah_fact_id=f"fact-{team_id}-{days_ago}",
        ah_fact_hash=f"hash-{team_id}-{days_ago}",
        settlement_outcome=settlement)


def _complete_contributions(context: FeatureContext) -> tuple:
    home = [_fact("home-1", days_ago=n, settlement="WIN") for n in (3, 10, 17, 24, 31)]
    away = [_fact("away-1", days_ago=n, settlement="LOSS") for n in (4, 11, 18, 25, 32)]
    meetings = [_fact("home-1", days_ago=n, settlement="WIN") for n in (200, 400)]
    return (
        rest_fitness_factor(context=context, home_history=home, away_history=away),
        recent_ah_cover_factor(
            context=context, profile=COVERAGE, home_history=home, away_history=away),
        h2h_factor(context=context, profile=COVERAGE, meetings=meetings),
        true_xg_factor(
            context=context, profile=COVERAGE,
            home_xg=[TeamXgSnapshot(team_id="home-1", observed_at=AS_OF - timedelta(days=1),
                                    xg_for=1.62, xg_against=1.05, goals_for=8,
                                    goals_against=5)],
            away_xg=[TeamXgSnapshot(team_id="away-1", observed_at=AS_OF - timedelta(days=2),
                                    xg_for=1.11, xg_against=1.48, goals_for=5,
                                    goals_against=9)]),
    )


def _feature_set(contributions: tuple, fixture_id: str = "9000001") -> FeatureSet:
    return FeatureSet(
        fixture_id=fixture_id, competition_id="synthetic_league", as_of=AS_OF,
        contributions=contributions, status=FeatureStatus.READY)


def _build(feature_set: FeatureSet | None = None, **overrides):  # type: ignore[no-untyped-def]
    context = overrides.pop("context", None) or _context()
    base = dict(
        feature_set=feature_set or _feature_set(_complete_contributions(context)),
        context=context,
        evaluation_id="dqe-" + "1" * 64, attempt_id="att-" + "2" * 60,
        evaluated_at_utc=EVALUATED_AT, created_at_utc=CREATED_AT,
        provenance=_provenance())
    base.update(overrides)
    return recorder.build_batch(**base)


def _ledger(tmp_path: Path):  # type: ignore[no-untyped-def]
    return contract.ForwardFactorLedger(tmp_path / "observations.jsonl")


def _bytes(ledger) -> bytes:  # type: ignore[no-untyped-def]
    return ledger.path.read_bytes() if ledger.path.exists() else b""


# --- 1: a complete batch records ----------------------------------------
def test_01_a_complete_four_factor_batch_is_recorded(tmp_path) -> None:
    ledger = _ledger(tmp_path)

    result = recorder.append_batch(ledger, _build())

    assert result["appended"] == 4
    assert result["batch_size"] == 4
    rows = ledger.rows()
    assert sorted(row["factor_id"] for row in rows) == sorted(
        contract.ALLOWED_FACTOR_IDS)
    for row in rows:
        # a participant carries the authority's weight, an excluded factor zero
        assert row["applied_weight"] in {"0.1", "0.05", "0"}
        assert contract.parse_aware_utc(row["evidence_time_utc"], field_name="e") < (
            contract.parse_aware_utc(row["evaluated_at_utc"], field_name="v"))
        if row["participated"]:
            assert row["signed_score"] is not None
            assert row["factor_inputs"]["weight_entered_weight_sum_used"] == "true"
        else:
            assert row["signed_score"] is None
            assert row["factor_inputs"]["weight_entered_weight_sum_used"] == "false"


def test_01_each_factor_gets_its_own_evidence_time(tmp_path) -> None:
    """One shared timestamp would defeat the point of a per-factor contract."""
    recorder.append_batch(_ledger(tmp_path), _build())

    times = {row["factor_id"]: row["evidence_time_utc"]
             for row in _ledger(tmp_path).rows()}

    assert len(set(times.values())) > 1, times


# --- P0: a kickoff is not the time a result was observed ----------------
@pytest.mark.parametrize("factor_id", sorted(recorder.RESULT_DERIVED_FACTORS))
def test_p0_a_result_derived_factor_needs_an_explicit_source_time(
    tmp_path, factor_id
) -> None:
    """F5 reads settled outcomes and F6 reads goals; neither is known at kickoff."""
    provenance = _provenance(**{
        factor_id: replace(_provenance()[factor_id], source_observed_at=None)})
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, _build(provenance=provenance))

    assert excinfo.value.code == "RESULT_DERIVED_FACTOR_WITHOUT_SOURCE_OBSERVED_TIME"
    assert excinfo.value.detail == factor_id
    assert _bytes(ledger) == b""


@pytest.mark.parametrize("factor_id", sorted(recorder.RESULT_DERIVED_FACTORS))
def test_p0_a_kickoff_derived_timestamp_is_refused_as_a_source_time(
    tmp_path, factor_id
) -> None:
    """TeamMatchHistory.observed_at *is* kickoff_at, so echoing it is the bug."""
    context = _context()
    contribution = next(c for c in _complete_contributions(context)
                        if c.feature_id == factor_id)
    provenance = _provenance(**{
        factor_id: replace(_provenance()[factor_id],
                           source_observed_at=contribution.observed_at.isoformat())})
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, _build(provenance=provenance, context=context))

    assert excinfo.value.code == "SOURCE_OBSERVED_TIME_IS_KICKOFF_DERIVED"
    assert _bytes(ledger) == b""


def test_p0_the_underlying_history_row_really_does_return_kickoff(tmp_path) -> None:
    """The premise of the whole P0 fix, asserted against the live type."""
    row = _fact("home-1", days_ago=3, settlement="WIN")

    assert row.observed_at == row.kickoff_at


def test_p0_a_source_time_later_than_evaluated_at_is_refused(tmp_path) -> None:
    late = (KICKOFF - timedelta(minutes=10)).isoformat()
    provenance = _provenance(**{
        factor_id: replace(_provenance()[factor_id], source_observed_at=late)
        for factor_id in recorder.RESULT_DERIVED_FACTORS})
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, _build(provenance=provenance))

    assert excinfo.value.code == "PIT_EVIDENCE_TIME_AFTER_EVALUATED_AT"
    assert _bytes(ledger) == b""


def test_p0_f3_and_f9_use_their_own_semantics_not_the_result_derived_one(
    tmp_path,
) -> None:
    """The four factors are not treated alike; each rule is checked separately."""
    assert recorder.EVIDENCE_RULES["F3_REST_FITNESS"] == recorder.FIXTURE_EVENT_TIME
    assert recorder.EVIDENCE_RULES["F9_TRUE_XG"] == (
        recorder.SOURCE_SNAPSHOT_OBSERVED_AT)
    assert recorder.RESULT_DERIVED_FACTORS == {"F5_RECENT_AH_COVER", "F6_H2H"}

    ledger = _ledger(tmp_path)
    recorder.append_batch(ledger, _build())
    rows = {row["factor_id"]: row for row in ledger.rows()}

    assert rows["F9_TRUE_XG"]["factor_inputs"]["evidence_time_semantics"] == (
        recorder.SOURCE_SNAPSHOT_OBSERVED_AT)
    for factor_id in recorder.RESULT_DERIVED_FACTORS:
        assert rows[factor_id]["factor_inputs"]["evidence_time_semantics"] == (
            recorder.RESULT_DERIVED)
        assert rows[factor_id]["evidence_time_utc"] == SOURCE_OBSERVED


def test_p0_a_non_result_factor_may_not_be_handed_a_source_time() -> None:
    """F9 has a real capture time of its own; overriding it would hide a swap."""
    provenance = _provenance(**{
        "F9_TRUE_XG": replace(_provenance()["F9_TRUE_XG"],
                              source_observed_at=SOURCE_OBSERVED)})

    with pytest.raises(ContractError) as excinfo:
        _build(provenance=provenance)

    assert excinfo.value.code == "SOURCE_OBSERVED_TIME_NOT_APPLICABLE"


# --- 2, 3, 4, 5: batch shape --------------------------------------------
@pytest.mark.parametrize("dropped", list(contract.ALLOWED_FACTOR_IDS))
def test_02_a_missing_factor_refuses_the_whole_batch(tmp_path, dropped) -> None:
    context = _context()
    kept = tuple(c for c in _complete_contributions(context)
                 if c.feature_id != dropped)

    with pytest.raises(ContractError) as excinfo:
        _build(_feature_set(kept), context=context)

    assert excinfo.value.code == "INCOMPLETE_BATCH_MISSING_FACTOR"
    assert dropped in excinfo.value.detail


def test_03_a_duplicated_factor_id_refuses_the_batch(tmp_path) -> None:
    context = _context()
    contributions = _complete_contributions(context)

    with pytest.raises(ContractError) as excinfo:
        _build(_feature_set((*contributions, contributions[0])), context=context)

    assert excinfo.value.code == "DUPLICATE_FACTOR_ID"


@pytest.mark.parametrize("field_name", ["evaluation_id", "attempt_id"])
def test_04_a_batch_must_share_one_evaluation_and_attempt(tmp_path, field_name) -> None:
    batch = _build()
    mixed = [*batch[:-1], replace(batch[-1], **{field_name: "dqe-" + "9" * 64
                                                if field_name == "evaluation_id"
                                                else "att-" + "9" * 60})]
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, mixed)

    assert excinfo.value.code == "BATCH_FIELD_NOT_UNIFORM"
    assert _bytes(ledger) == b""


def test_04_a_context_for_another_fixture_is_refused() -> None:
    with pytest.raises(ContractError) as excinfo:
        _build(context=_context("9000002"))

    assert excinfo.value.code == "FIXTURE_ID_MISMATCH"


def test_05_a_batch_must_share_one_evaluated_at(tmp_path) -> None:
    batch = _build()
    later = (KICKOFF - timedelta(minutes=50)).isoformat()
    mixed = [*batch[:-1], replace(batch[-1], evaluated_at_utc=later)]
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, mixed)

    assert excinfo.value.code == "BATCH_FIELD_NOT_UNIFORM"
    assert _bytes(ledger) == b""


# --- 6, 7, 8, 9, 10, 11: weight and PIT ---------------------------------
def test_06_a_missing_applied_weight_refuses_the_batch(tmp_path) -> None:
    batch = _build()
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, [*batch[:-1],
                                       replace(batch[-1], applied_weight=None)])

    assert excinfo.value.code == "APPLIED_WEIGHT_MISSING"
    assert _bytes(ledger) == b""


def test_06_the_recorder_never_supplies_a_weight_of_its_own() -> None:
    source = RECORDER_PATH.read_text(encoding="utf-8")

    for invented in ("0.10", "0.05", "DEFAULT_WEIGHT"):
        assert invented not in source, invented


# --- P1: participation is the scoring authority's verdict ---------------
def _non_scoring(contribution, **changes):  # type: ignore[no-untyped-def]
    return replace(contribution, **changes)


@pytest.mark.parametrize(("label", "changes"), [
    ("not an independent signal", {"is_independent_signal": False}),
    ("non authoritative source group", {"source_group": "match_importance"}),
    ("unknown source group", {"source_group": "some_other_group"}),
    ("zero weight", {"weight": 0.0}),
])
def test_p1_a_ready_factor_the_authority_excludes_does_not_participate(
    tmp_path, label, changes
) -> None:
    """READY is not participation; team_score decides, and it is reused, not copied."""
    context = _context()
    contributions = _complete_contributions(context)
    target = "F9_TRUE_XG"
    adjusted = tuple(
        _non_scoring(c, **changes) if c.feature_id == target else c
        for c in contributions)
    ledger = _ledger(tmp_path)

    recorder.append_batch(
        ledger, _build(_feature_set(adjusted), context=context))

    row = next(r for r in ledger.rows() if r["factor_id"] == target)
    assert row["participated"] is False, label
    assert row["factor_status"] == contract.FACTOR_ADMISSION_FAILED, label
    assert row["signed_score"] is None, label
    assert row["factor_inputs"]["weight_entered_weight_sum_used"] == "false", label
    assert row["factor_inputs"]["feature_status"] == "READY", label
    # applied_weight means the weight this evaluation actually applied, and an
    # excluded factor applied none of it
    assert Decimal(row["applied_weight"]) == Decimal(0), label
    assert row["factor_inputs"]["declared_weight"] not in (None, "0"), label


def test_p1_the_recorder_reuses_team_score_rather_than_reimplementing_it() -> None:
    source = RECORDER_PATH.read_text(encoding="utf-8")

    assert "independent_team_scores_from_contributions" in source
    for copied in ("AUTHORITATIVE_SIGNAL_GROUPS", "NON_SCORING_GROUPS",
                   "is_scoring_factor"):
        assert copied not in source, copied


def test_p1_recorded_weights_match_the_authority_row_for_row(tmp_path) -> None:
    context = _context()
    feature_set = _feature_set(_complete_contributions(context))
    authority = recorder.scoring_authority_view(feature_set.contributions)
    ledger = _ledger(tmp_path)

    recorder.append_batch(ledger, _build(feature_set, context=context))

    rows = {row["factor_id"]: row for row in ledger.rows()}
    scored = authority["scoring_factors"]
    assert scored, "the fixture must actually score something"
    for factor_id, row in rows.items():
        assert row["participated"] is (factor_id in scored), factor_id
        if factor_id in scored:
            assert float(row["applied_weight"]) == float(scored[factor_id]["weight"])
    total = sum(float(rows[f]["applied_weight"]) for f in scored)
    assert abs(total - authority["weight_sum_used"]) < 1e-9


def test_p1_a_weight_disagreeing_with_the_authority_refuses_the_batch() -> None:
    context = _context()
    ready = next(c for c in _complete_contributions(context)
                 if c.feature_id == "F9_TRUE_XG")

    with pytest.raises(ContractError) as excinfo:
        recorder.observation_from_contribution(
            ready, _provenance()["F9_TRUE_XG"],
            scored={"weight": 0.99, "share": 1.0},
            evaluation_id="dqe-" + "1" * 64, attempt_id="att-" + "2" * 60,
            fixture_id="9000001", evaluated_at_utc=EVALUATED_AT,
            created_at_utc=CREATED_AT, as_of_utc=AS_OF.isoformat())

    assert excinfo.value.code == "APPLIED_WEIGHT_DISAGREES_WITH_SCORING_AUTHORITY"


def test_07_a_missing_evidence_time_refuses_the_batch(tmp_path) -> None:
    batch = _build()
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, [*batch[:-1],
                                       replace(batch[-1], evidence_time_utc=None)])

    assert excinfo.value.code == "EVIDENCE_TIME_MISSING"
    assert _bytes(ledger) == b""


def test_07_a_scored_factor_without_observed_at_is_refused() -> None:
    """The look-up instant may stand in for an absence, never for a real score."""
    context = _context()
    ready = next(c for c in _complete_contributions(context)
                 if c.feature_id == "F9_TRUE_XG")
    stripped = replace(ready, observed_at=None)

    with pytest.raises(ContractError) as excinfo:
        recorder.observation_from_contribution(
            stripped, _provenance()["F9_TRUE_XG"],
            scored={"weight": stripped.weight, "share": 1.0},
            evaluation_id="dqe-" + "1" * 64, attempt_id="att-" + "2" * 60,
            fixture_id="9000001", evaluated_at_utc=EVALUATED_AT,
            created_at_utc=CREATED_AT, as_of_utc=AS_OF.isoformat())

    assert excinfo.value.code == "PARTICIPATED_WITHOUT_OBSERVED_AT"


def test_08_evidence_time_equal_to_evaluated_at_refuses(tmp_path) -> None:
    batch = _build()
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(
            ledger, [*batch[:-1], replace(batch[-1], evidence_time_utc=EVALUATED_AT)])

    assert excinfo.value.code == "PIT_EVIDENCE_TIME_EQUALS_EVALUATED_AT"
    assert _bytes(ledger) == b""


def test_09_evidence_time_after_evaluated_at_refuses(tmp_path) -> None:
    batch = _build()
    later = (KICKOFF - timedelta(minutes=10)).isoformat()
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger,
                              [*batch[:-1], replace(batch[-1], evidence_time_utc=later)])

    assert excinfo.value.code == "PIT_EVIDENCE_TIME_AFTER_EVALUATED_AT"
    assert _bytes(ledger) == b""


@pytest.mark.parametrize("spelling", [
    "2026-10-01 19:20:00+00",      # space separated, later than evaluated_at
    "2026-10-01T19:20:00Z",
    "2026-10-01T19:20:00+00:00",
    "2026-10-02T04:20:00+09:00",   # same instant in another zone
])
def test_10_no_timestamp_spelling_smuggles_a_late_evidence_time(
    tmp_path, spelling
) -> None:
    batch = _build()
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(
            ledger, [*batch[:-1], replace(batch[-1], evidence_time_utc=spelling)])

    assert excinfo.value.code == "PIT_EVIDENCE_TIME_AFTER_EVALUATED_AT"
    assert _bytes(ledger) == b""


def test_10_a_naive_evidence_time_refuses(tmp_path) -> None:
    batch = _build()
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(
            ledger, [*batch[:-1],
                     replace(batch[-1], evidence_time_utc="2026-10-01T17:00:00")])

    assert excinfo.value.code == "TIMESTAMP_NOT_TIMEZONE_AWARE"


def test_11_created_at_cannot_prove_pit(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    first = recorder.append_batch(ledger, _build())

    again = recorder.append_batch(
        ledger, [replace(record, created_at_utc="2026-11-01T00:00:00+00:00")
                 for record in _build()])

    assert again["appended"] == 0
    assert again["observation_ids"] == first["observation_ids"]
    assert "created_at_utc" not in contract.PROTECTED_FIELDS


# --- 12, 13: status semantics ------------------------------------------
def _degraded_set(context: FeatureContext) -> FeatureSet:
    home = [TeamMatchHistory(team_id="home-1", opponent_id="o", goals_for=1,
                             goals_against=1,
                             kickoff_at=KICKOFF - timedelta(days=n)) for n in (3, 10)]
    away = [TeamMatchHistory(team_id="away-1", opponent_id="o", goals_for=1,
                             goals_against=1,
                             kickoff_at=KICKOFF - timedelta(days=n)) for n in (4, 11)]
    return _feature_set((
        rest_fitness_factor(context=context, home_history=home, away_history=away),
        recent_ah_cover_factor(context=context, profile=COVERAGE,
                               home_history=home, away_history=away),
        h2h_factor(context=context, profile=COVERAGE, meetings=[]),
        true_xg_factor(context=context, profile=COVERAGE, home_xg=[], away_xg=[]),
    ))


def test_12_an_absent_factor_is_still_recorded_and_carries_no_score(tmp_path) -> None:
    context = _context()
    ledger = _ledger(tmp_path)

    recorder.append_batch(ledger, _build(_degraded_set(context), context=context))

    rows = {row["factor_id"]: row for row in ledger.rows()}
    assert len(rows) == 4
    assert rows["F5_RECENT_AH_COVER"]["factor_status"] == contract.INSUFFICIENT_DATA
    assert rows["F6_H2H"]["factor_status"] == contract.SOURCE_UNAVAILABLE
    assert rows["F9_TRUE_XG"]["factor_status"] == contract.SOURCE_UNAVAILABLE
    for factor_id in ("F5_RECENT_AH_COVER", "F6_H2H", "F9_TRUE_XG"):
        row = rows[factor_id]
        assert row["signed_score"] is None
        assert row["participated"] is False
        assert row["factor_inputs"]["weight_entered_weight_sum_used"] == "false"
        assert row["factor_inputs"]["evidence_time_semantics"] == (
            recorder.EVIDENCE_FROM_LOOKUP)


def test_12_a_scoreless_status_may_not_carry_a_score(tmp_path) -> None:
    batch = _build()
    ledger = _ledger(tmp_path)
    tampered = replace(batch[-1], factor_status=contract.INSUFFICIENT_DATA,
                       participated=False)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, [*batch[:-1], tampered])

    assert excinfo.value.code == "SCORELESS_STATUS_CARRIES_A_SCORE"
    assert _bytes(ledger) == b""


def test_13_participated_without_a_score_is_refused(tmp_path) -> None:
    batch = _build()
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, [*batch[:-1],
                                       replace(batch[-1], signed_score=None)])

    assert excinfo.value.code == "SIGNED_SCORE_MISSING_FOR_PARTICIPATED"
    assert _bytes(ledger) == b""


# --- 14, 15: identity ---------------------------------------------------
@pytest.mark.parametrize("bad", ["", "abc", "A" * 64, "z" * 64])
def test_14_an_illegal_source_capture_hash_refuses(tmp_path, bad) -> None:
    ledger = _ledger(tmp_path)
    provenance = {
        factor_id: replace(entry, source_capture_sha256=bad)
        for factor_id, entry in _provenance().items()}

    with pytest.raises(ContractError):
        recorder.append_batch(ledger, _build(provenance=provenance))

    assert _bytes(ledger) == b""


def test_15_a_tampered_identity_refuses(tmp_path) -> None:
    batch = _build()
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, [*batch[:-1],
                                       replace(batch[-1], observation_id="d" * 64)])

    assert excinfo.value.code == "IDENTITY_MISMATCH"
    assert _bytes(ledger) == b""


# --- 16, 17, 18, 19, 20, 21: append-only -------------------------------
def test_16_replaying_the_same_batch_is_an_idempotent_no_op(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    recorder.append_batch(ledger, _build())
    before = _bytes(ledger)

    again = recorder.append_batch(ledger, _build())

    assert again["appended"] == 0
    assert again["idempotent_no_ops"] == 4
    assert _bytes(ledger) == before


def test_17_the_same_identity_with_different_content_conflicts(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    sealed = [contract.validate(record) for record in _build()]
    recorder.append_batch(ledger, _build())
    before = _bytes(ledger)
    forged = [replace(record, revision_reason="tampered") for record in sealed]

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, forged)

    assert excinfo.value.code == "OBSERVATION_ID_BUSINESS_CONFLICT"
    assert _bytes(ledger) == before


def test_18_a_revision_appends_and_leaves_the_old_rows_byte_identical(
    tmp_path,
) -> None:
    ledger = _ledger(tmp_path)
    first = recorder.append_batch(ledger, _build())
    before = _bytes(ledger)
    batch = [contract.validate(record) for record in _build()]
    revised = [
        recorder.revise(record, supersedes=observation_id,
                        reason="FACTOR_VERSION_CORRECTED_BY_SOURCE",
                        factor_version="SYNTHETIC_FIXTURE_v2")
        for record, observation_id in zip(batch, first["observation_ids"], strict=True)
    ]

    result = recorder.append_batch(ledger, revised)

    assert result["appended"] == 4
    assert _bytes(ledger).startswith(before)
    rows = ledger.rows()
    assert len(rows) == 8
    for observation_id in first["observation_ids"]:
        assert ledger.readback(observation_id)["factor_version"] == (
            "SYNTHETIC_FIXTURE_v1")


def test_19_a_dangling_supersedes_refuses_the_batch(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    batch = [contract.validate(record) for record in _build()]
    dangling = [recorder.revise(record, supersedes="e" * 64, reason="r",
                                factor_version="SYNTHETIC_FIXTURE_v2")
                for record in batch]

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, dangling)

    assert excinfo.value.code == "SUPERSEDES_TARGET_NOT_FOUND"
    assert _bytes(ledger) == b""


def test_20_a_supersedes_cycle_refuses(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    first = recorder.append_batch(ledger, _build())
    batch = [contract.validate(record) for record in _build()]
    revised = [
        recorder.revise(record, supersedes=observation_id, reason="r1",
                        factor_version="SYNTHETIC_FIXTURE_v2")
        for record, observation_id in zip(batch, first["observation_ids"], strict=True)]
    second = recorder.append_batch(ledger, revised)
    rows = ledger.rows()
    by_id = {row["observation_id"]: row for row in rows}
    for original, successor in zip(first["observation_ids"],
                                   second["observation_ids"], strict=True):
        by_id[original]["supersedes_observation_id"] = successor
    ledger.path.write_text("\n".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8")
    batch3 = [contract.validate(record) for record in _build()]
    cyclic = [
        recorder.revise(record, supersedes=observation_id, reason="r2",
                        factor_version="SYNTHETIC_FIXTURE_v3")
        for record, observation_id in zip(batch3, second["observation_ids"],
                                          strict=True)]

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, cyclic)

    assert excinfo.value.code == "SUPERSEDES_CYCLE"


def test_21_a_refused_batch_leaves_zero_new_lines(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    recorder.append_batch(ledger, _build())
    before = _bytes(ledger)
    broken = _build()
    broken = [*broken[:-1], replace(broken[-1], evidence_time_utc=None)]

    with pytest.raises(ContractError):
        recorder.append_batch(ledger, broken)

    assert _bytes(ledger) == before
    assert len(ledger.rows()) == 4


# --- 22, 23: as-of and market ------------------------------------------
def test_22_the_as_of_view_has_no_post_event_field(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    result = recorder.append_batch(ledger, _build())

    for observation_id in result["observation_ids"]:
        view = ledger.as_of_view(observation_id)
        assert not contract.POST_EVENT_FIELDS & set(view)
        assert not contract.POST_EVENT_FIELDS & set(view["factor_inputs"])


def test_22_a_result_field_in_a_contribution_input_is_refused() -> None:
    context = _context()
    contributions = _complete_contributions(context)
    leaked = replace(contributions[0],
                     inputs={**contributions[0].inputs, "settlement": "LOSS"})

    with pytest.raises(ContractError) as excinfo:
        _build(_feature_set((leaked, *contributions[1:])), context=context)

    assert excinfo.value.code == "POST_EVENT_FIELD_IN_FACTOR_INPUT"


def test_23_totals_is_out_of_contract() -> None:
    with pytest.raises(ContractError) as excinfo:
        _build(market="TOTALS")

    assert excinfo.value.code == "MARKET_OUT_OF_CONTRACT"


# --- 24, 25, 26: frozen artifacts and boundaries -----------------------
@pytest.mark.parametrize(("package", "count"), [
    ("W2_AH_FACTOR_ACCURACY_F0_20260910", 5),
    ("W2_AH_FACTOR_ACCURACY_F1_20260910", 6),
    ("W2_AH_FACTOR_ACCURACY_F1P_20260910", 7),
])
def test_24_frozen_packages_still_verify(package, count) -> None:
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/shasum", "-a", "256", "-c", "HASHES.sha256"],
        cwd=REPO / "docs/review_packages" / package,
        capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count(": OK") == count


def test_25_no_second_serializer_or_hash_writer_is_defined() -> None:
    for path in (RECORDER_PATH, RUNNER_PATH):
        source = path.read_text(encoding="utf-8")
        assert "hashlib" not in source, path
        tree = ast.parse(source)
        defined = {node.name for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef)}
        assert not {n for n in defined
                    if "canonical" in n or "sha256" in n or "identity_hash" in n}
    # identities come from F1P only
    recorder_source = RECORDER_PATH.read_text(encoding="utf-8")
    assert "contract.validate" in recorder_source
    assert "canonical_sha256" not in recorder_source


def test_26_nothing_reaches_a_network_or_a_database() -> None:
    banned = {"requests", "httpx", "urllib", "urllib3", "http", "socket", "aiohttp",
              "sqlalchemy", "psycopg", "psycopg2", "alembic"}
    forbidden_w2 = ("w2.prematch", "w2.strategy", "w2.api", "w2.dashboard",
                    "w2.providers", "w2.ingestion", "w2.scheduler",
                    "w2.infrastructure")
    for path in (RECORDER_PATH, RUNNER_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom)
                     else [])
            for name in names:
                assert name.split(".")[0] not in banned, (path, name)
                assert not name.startswith(forbidden_w2), (path, name)


def test_the_runner_is_deterministic(tmp_path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    for target in (first, second):
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(RUNNER_PATH), "--output", str(target)],
            capture_output=True, text=True, check=False, cwd=REPO)
        assert result.returncode == 0, result.stdout + result.stderr

    for name in ("OFFLINE_RECORDER_RESULT.json", "F1R_A0_REFERENCE_LEDGER.jsonl"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_the_published_result_states_what_is_not_done() -> None:
    result = json.loads(
        (OUTPUT / "OFFLINE_RECORDER_RESULT.json").read_text(encoding="utf-8"))

    assert result["final_state"] == "BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE"
    assert result["f5_f6_source_observed_time_exists_in_production"] is False
    assert result["result_derived_without_source_time_refused_with"] == (
        "RESULT_DERIVED_FACTOR_WITHOUT_SOURCE_OBSERVED_TIME")
    assert result["kickoff_echo_as_source_time_refused_with"] == (
        "SOURCE_OBSERVED_TIME_IS_KICKOFF_DERIVED")
    assert result["offline_recorder_implemented"] is True
    assert result["production_wiring_not_started"] is True
    assert result["live_capture_not_started"] is True
    assert result["deployment_not_executed"] is True
    assert result["weight_calibration_not_started"] is True
    assert result["fixture_kind"] == "SYNTHETIC_CONTRACT_FIXTURE"
    assert result["provider_calls"] == 0
    assert result["production_db_reads"] == 0
    assert result["production_db_writes"] == 0
    assert result["f2_allowed"] is False


# --- P1: batch atomicity under injected I/O failure ---------------------
# Validation failures were already covered above. These inject failures *after*
# validation, at each stage of the write, which is where the previous
# row-by-row append could leave a partial batch behind.
class _Boom(OSError):
    """An injected I/O failure."""


def _seeded(tmp_path: Path):  # type: ignore[no-untyped-def]
    """A ledger that already holds one committed batch."""
    ledger = _ledger(tmp_path)
    recorder.append_batch(ledger, _build())
    return ledger


def _second_batch():  # type: ignore[no-untyped-def]
    return _build(evaluation_id="dqe-" + "7" * 64, attempt_id="att-" + "8" * 60)


def test_atomicity_a_failure_on_the_first_write_leaves_the_ledger_untouched(
    tmp_path, monkeypatch
) -> None:
    ledger = _seeded(tmp_path)
    before = _bytes(ledger)
    calls = {"n": 0}
    real_write = recorder.tempfile.NamedTemporaryFile

    def failing(*args, **kwargs):  # type: ignore[no-untyped-def]
        handle = real_write(*args, **kwargs)
        original = handle.write

        def write(payload):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] == 1:
                raise _Boom("first write failed")
            return original(payload)

        handle.write = write  # type: ignore[method-assign]
        return handle

    monkeypatch.setattr(recorder.tempfile, "NamedTemporaryFile", failing)

    with pytest.raises(_Boom):
        recorder.append_batch(ledger, _second_batch())

    assert _bytes(ledger) == before
    assert len(ledger.rows()) == 4


def test_atomicity_a_failure_midway_through_leaves_the_ledger_untouched(
    tmp_path, monkeypatch
) -> None:
    ledger = _seeded(tmp_path)
    before = _bytes(ledger)
    calls = {"n": 0}
    real_write = recorder.tempfile.NamedTemporaryFile

    def failing(*args, **kwargs):  # type: ignore[no-untyped-def]
        handle = real_write(*args, **kwargs)
        original = handle.write

        def write(payload):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] == 3:
                raise _Boom("write failed part way through")
            return original(payload)

        handle.write = write  # type: ignore[method-assign]
        return handle

    monkeypatch.setattr(recorder.tempfile, "NamedTemporaryFile", failing)

    with pytest.raises(_Boom):
        recorder.append_batch(ledger, _second_batch())

    assert _bytes(ledger) == before
    assert len(ledger.rows()) == 4


def test_atomicity_an_fsync_failure_leaves_the_ledger_untouched(
    tmp_path, monkeypatch
) -> None:
    ledger = _seeded(tmp_path)
    before = _bytes(ledger)

    def failing_fsync(_fd):  # type: ignore[no-untyped-def]
        raise _Boom("fsync failed")

    monkeypatch.setattr(recorder.os, "fsync", failing_fsync)

    with pytest.raises(_Boom):
        recorder.append_batch(ledger, _second_batch())

    assert _bytes(ledger) == before
    assert len(ledger.rows()) == 4


def test_atomicity_a_failure_at_the_commit_point_leaves_the_ledger_untouched(
    tmp_path, monkeypatch
) -> None:
    """os.replace is the commit point; failing there must change nothing."""
    ledger = _seeded(tmp_path)
    before = _bytes(ledger)

    def failing_replace(_src, _dst):  # type: ignore[no-untyped-def]
        raise _Boom("replace failed")

    monkeypatch.setattr(recorder.os, "replace", failing_replace)

    with pytest.raises(_Boom):
        recorder.append_batch(ledger, _second_batch())

    assert _bytes(ledger) == before
    assert len(ledger.rows()) == 4


@pytest.mark.parametrize("stage", ["write", "fsync", "replace"])
def test_atomicity_no_temporary_file_survives_a_failure(
    tmp_path, monkeypatch, stage
) -> None:
    """A refusal must not leave litter next to the ledger either."""
    ledger = _seeded(tmp_path)
    if stage == "fsync":
        monkeypatch.setattr(recorder.os, "fsync",
                            lambda _fd: (_ for _ in ()).throw(_Boom("x")))
    elif stage == "replace":
        monkeypatch.setattr(recorder.os, "replace",
                            lambda _s, _d: (_ for _ in ()).throw(_Boom("x")))
    else:
        real = recorder.tempfile.NamedTemporaryFile

        def failing(*args, **kwargs):  # type: ignore[no-untyped-def]
            handle = real(*args, **kwargs)
            handle.write = lambda _p: (_ for _ in ()).throw(_Boom("x"))  # type: ignore[method-assign]
            return handle

        monkeypatch.setattr(recorder.tempfile, "NamedTemporaryFile", failing)

    with pytest.raises(_Boom):
        recorder.append_batch(ledger, _second_batch())

    leftovers = [p.name for p in tmp_path.iterdir() if p.name != ledger.path.name]
    assert leftovers == [], leftovers


def test_atomicity_a_successful_commit_lands_all_four_rows(tmp_path) -> None:
    ledger = _seeded(tmp_path)

    result = recorder.append_batch(ledger, _second_batch())

    assert result["appended"] == 4
    assert len(ledger.rows()) == 8
    for observation_id in result["observation_ids"]:
        ledger.readback(observation_id)


def test_atomicity_recovery_after_a_failure_still_commits(tmp_path, monkeypatch) -> None:
    """A failed batch must not poison the next attempt."""
    ledger = _seeded(tmp_path)
    monkeypatch.setattr(recorder.os, "replace",
                        lambda _s, _d: (_ for _ in ()).throw(_Boom("x")))
    with pytest.raises(_Boom):
        recorder.append_batch(ledger, _second_batch())
    monkeypatch.undo()

    result = recorder.append_batch(ledger, _second_batch())

    assert result["appended"] == 4
    assert len(ledger.rows()) == 8


def test_atomicity_prior_rows_are_re_emitted_verbatim(tmp_path) -> None:
    """Rewriting the file must not reformat or reorder what was already there."""
    ledger = _seeded(tmp_path)
    before = _bytes(ledger)

    recorder.append_batch(ledger, _second_batch())

    assert _bytes(ledger).startswith(before)


def test_atomicity_replay_after_a_rewrite_is_still_idempotent(tmp_path) -> None:
    ledger = _seeded(tmp_path)
    recorder.append_batch(ledger, _second_batch())
    before = _bytes(ledger)

    again = recorder.append_batch(ledger, _second_batch())

    assert again["appended"] == 0
    assert again["idempotent_no_ops"] == 4
    assert _bytes(ledger) == before


# --- applied_weight is the weight actually applied, never the declared one ---
# F1P freezes applied_weight as "the weight this evaluation actually adopted".
# A factor the scoring authority excluded adopted none of it, so it must record
# a canonical zero; the builder's declared value lives in an audit field.
def _authority(feature_set) -> dict:  # type: ignore[no-untyped-def]
    return recorder.scoring_authority_view(feature_set.contributions)


@pytest.mark.parametrize(("label", "changes"), [
    ("ready but not an independent signal", {"is_independent_signal": False}),
    ("ready but a non authoritative source group", {"source_group": "match_importance"}),
    ("ready but an unknown source group", {"source_group": "some_other_group"}),
    ("ready but zero weight", {"weight": 0.0}),
])
def test_w1_an_excluded_ready_factor_records_zero_applied_weight(
    tmp_path, label, changes
) -> None:
    context = _context()
    target = "F9_TRUE_XG"
    adjusted = tuple(
        replace(c, **changes) if c.feature_id == target else c
        for c in _complete_contributions(context))
    feature_set = _feature_set(adjusted)
    ledger = _ledger(tmp_path)

    recorder.append_batch(ledger, _build(feature_set, context=context))

    row = next(r for r in ledger.rows() if r["factor_id"] == target)
    assert row["participated"] is False, label
    assert Decimal(row["applied_weight"]) == Decimal(0), label
    assert row["signed_score"] is None, label
    assert row["factor_inputs"]["weight_entered_weight_sum_used"] == "false", label


@pytest.mark.parametrize(("label", "status_field"), [
    ("insufficient data", contract.INSUFFICIENT_DATA),
    ("source unavailable", contract.SOURCE_UNAVAILABLE),
])
def test_w1_a_missing_data_factor_records_zero_applied_weight(
    tmp_path, label, status_field
) -> None:
    context = _context()
    ledger = _ledger(tmp_path)

    recorder.append_batch(ledger, _build(_degraded_set(context), context=context))

    rows = [r for r in ledger.rows() if r["factor_status"] == status_field]
    assert rows, label
    for row in rows:
        assert Decimal(row["applied_weight"]) == Decimal(0), (label, row["factor_id"])
        assert row["signed_score"] is None
        assert row["factor_inputs"]["declared_weight"] not in (None, "0")


def test_w1_the_admission_failed_case_records_zero_in_all_three_scoreless_states(
    tmp_path,
) -> None:
    """FACTOR_ADMISSION_FAILED, INSUFFICIENT_DATA and SOURCE_UNAVAILABLE alike."""
    context = _context()
    ledger = _ledger(tmp_path)
    recorder.append_batch(ledger, _build(_degraded_set(context), context=context))
    recorder.append_batch(
        ledger,
        _build(_feature_set(tuple(
            replace(c, is_independent_signal=False) if c.feature_id == "F9_TRUE_XG"
            else c for c in _complete_contributions(context))),
            context=context,
            evaluation_id="dqe-" + "6" * 64, attempt_id="att-" + "6" * 60))

    seen = {row["factor_status"] for row in ledger.rows() if not row["participated"]}
    assert {contract.INSUFFICIENT_DATA, contract.SOURCE_UNAVAILABLE,
            contract.FACTOR_ADMISSION_FAILED} <= seen
    for row in ledger.rows():
        if not row["participated"]:
            assert Decimal(row["applied_weight"]) == Decimal(0), row["factor_id"]


def test_w1_every_row_matches_the_authority_and_the_batch_sum_closes(
    tmp_path,
) -> None:
    """The mechanical invariant: what was applied is exactly what was summed."""
    context = _context()
    feature_set = _feature_set(_complete_contributions(context))
    authority = _authority(feature_set)
    ledger = _ledger(tmp_path)

    recorder.append_batch(ledger, _build(feature_set, context=context))

    rows = {row["factor_id"]: row for row in ledger.rows()}
    scored = authority["scoring_factors"]
    assert scored
    for factor_id, row in rows.items():
        assert row["participated"] is (factor_id in scored), factor_id
        expected = (Decimal(str(scored[factor_id]["weight"])) if factor_id in scored
                    else Decimal(0))
        assert Decimal(row["applied_weight"]) == expected, factor_id
    total = sum((Decimal(row["applied_weight"]) for row in rows.values()), Decimal(0))
    assert total == Decimal(str(authority["weight_sum_used"]))


def test_w1_the_degraded_batch_sum_also_closes(tmp_path) -> None:
    context = _context()
    feature_set = _degraded_set(context)
    authority = _authority(feature_set)
    ledger = _ledger(tmp_path)

    recorder.append_batch(ledger, _build(feature_set, context=context))

    total = sum((Decimal(row["applied_weight"]) for row in ledger.rows()), Decimal(0))
    assert total == Decimal(str(authority["weight_sum_used"]))


def test_w1_a_batch_whose_weights_do_not_close_is_refused() -> None:
    """The invariant must be capable of failing, or it proves nothing."""
    context = _context()
    batch = _build(_feature_set(_complete_contributions(context)), context=context)
    excluded = next(r for r in batch if not r.participated)
    tampered = [
        replace(r, applied_weight="0.1") if r.factor_id == excluded.factor_id else r
        for r in batch]

    with pytest.raises(ContractError) as excinfo:
        recorder._batch_coherence(
            [contract.validate(r) for r in tampered],
            _authority(_feature_set(_complete_contributions(context)))[
                "weight_sum_used"])

    assert excinfo.value.code in {
        "NON_PARTICIPATING_FACTOR_CARRIES_APPLIED_WEIGHT",
        "BATCH_APPLIED_WEIGHT_SUM_DISAGREES_WITH_AUTHORITY"}


def test_w1_the_published_ledger_has_zero_weight_on_every_admission_failed_row(
) -> None:
    """The shipped artifact, not just a fixture."""
    rows = [json.loads(line) for line in
            (OUTPUT / "F1R_A0_REFERENCE_LEDGER.jsonl").read_text(
                encoding="utf-8").splitlines() if line.strip()]
    failed = [r for r in rows
              if r["factor_status"] == contract.FACTOR_ADMISSION_FAILED]

    assert failed, "the reference ledger must exercise this case"
    for row in failed:
        assert Decimal(row["applied_weight"]) == Decimal(0), row["factor_id"]


def test_w1_the_published_result_closes_against_its_own_authority_block() -> None:
    result = json.loads(
        (OUTPUT / "OFFLINE_RECORDER_RESULT.json").read_text(encoding="utf-8"))

    for name in ("complete_batch", "absent_factor_batch"):
        closure = result["scoring_authority_closure"][name]
        assert Decimal(result[name]["applied_weight_sum"]) == Decimal(
            str(closure["weight_sum_used"])), name


# --- delivery identity is consistent across the package -------------------
def test_w2_the_published_parent_commit_is_this_rounds_parent() -> None:
    result = json.loads(
        (OUTPUT / "OFFLINE_RECORDER_RESULT.json").read_text(encoding="utf-8"))
    index = (OUTPUT / "INDEX.md").read_text(encoding="utf-8")

    assert result["parent_commit"] == "7e8b07f77bf0638692aea9e4bf30b9d0107fd8bd"
    assert result["task_id"] == (
        "W2_AH_FACTOR_ACCURACY_F1R_A0_NARROW_REMEDIATION_2_20260910")
    assert result["final_state"] == "BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE"
    assert result["parent_commit"] in index
    assert result["task_id"] in index
    assert result["final_state"] in index
    # the superseded parents must not linger anywhere in the package identity
    for stale in ("d8c8bf8259b30cd9fd81dfbf7be8555aa42680aa",
                  "0821f472115ca2d1aabf0d0c51248057de9c5693"):
        assert result["parent_commit"] != stale
