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
VERSIONS = dict.fromkeys(contract.ALLOWED_FACTOR_IDS, "v1")
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
        factor_versions=dict(VERSIONS), source_capture_id="capture-a",
        source_capture_sha256=CAPTURE_SHA, source_version="w2.features.v1")
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
        assert row["factor_status"] == contract.PARTICIPATED
        assert row["signed_score"] is not None
        assert row["applied_weight"] in {"0.1", "0.05"}
        assert contract.parse_aware_utc(row["evidence_time_utc"], field_name="e") < (
            contract.parse_aware_utc(row["evaluated_at_utc"], field_name="v"))
        assert row["factor_inputs"]["evidence_time_semantics"] == (
            recorder.EVIDENCE_FROM_OBSERVATION)


def test_01_each_factor_gets_its_own_evidence_time(tmp_path) -> None:
    """One shared timestamp would defeat the point of a per-factor contract."""
    recorder.append_batch(_ledger(tmp_path), _build())

    times = {row["factor_id"]: row["evidence_time_utc"]
             for row in _ledger(tmp_path).rows()}

    assert len(set(times.values())) > 1, times


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

    assert "applied_weight=contribution.weight" in source
    for invented in ("0.10", "0.05", "DEFAULT_WEIGHT", "registry"):
        assert invented not in source, invented


def test_07_a_missing_evidence_time_refuses_the_batch(tmp_path) -> None:
    batch = _build()
    ledger = _ledger(tmp_path)

    with pytest.raises(ContractError) as excinfo:
        recorder.append_batch(ledger, [*batch[:-1],
                                       replace(batch[-1], evidence_time_utc=None)])

    assert excinfo.value.code == "EVIDENCE_TIME_MISSING"
    assert _bytes(ledger) == b""


def test_07_a_participating_factor_without_observed_at_is_refused() -> None:
    """The look-up instant may stand in for an absence, never for a real score."""
    context = _context()
    ready = _complete_contributions(context)[0]
    stripped = replace(ready, observed_at=None)

    with pytest.raises(ContractError) as excinfo:
        recorder.observation_from_contribution(
            stripped, evaluation_id="dqe-" + "1" * 64, attempt_id="att-" + "2" * 60,
            fixture_id="9000001", evaluated_at_utc=EVALUATED_AT,
            created_at_utc=CREATED_AT, as_of_utc=AS_OF.isoformat(),
            factor_version="v1", source_capture_id="c",
            source_capture_sha256=CAPTURE_SHA, source_version="v")

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

    with pytest.raises(ContractError):
        recorder.append_batch(ledger, _build(source_capture_sha256=bad))

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
                        reason="WEIGHT_CORRECTED_BY_SOURCE", applied_weight="0.12")
        for record, observation_id in zip(batch, first["observation_ids"], strict=True)
    ]

    result = recorder.append_batch(ledger, revised)

    assert result["appended"] == 4
    assert _bytes(ledger).startswith(before)
    rows = ledger.rows()
    assert len(rows) == 8
    for observation_id in first["observation_ids"]:
        assert ledger.readback(observation_id)["applied_weight"] in {"0.1", "0.05"}


def test_19_a_dangling_supersedes_refuses_the_batch(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    batch = [contract.validate(record) for record in _build()]
    dangling = [recorder.revise(record, supersedes="e" * 64, reason="r",
                                applied_weight="0.12") for record in batch]

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
                        applied_weight="0.12")
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
                        applied_weight="0.13")
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

    assert result["final_state"] == "OFFLINE_FACTOR_RECORDER_READY_FOR_R1"
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
