"""F1R-B production wiring: real version, real capture identity, real source time.

The accepted offline recorder trusted whatever provenance a caller handed it.
These tests are about what happens now that it cannot: the version has to be
the builder's, the capture identity has to be derived from the rows the factor
actually read, and a result-derived factor has to prove when its sources
observed the facts. F5 cannot, and the tests say so rather than working around
it.

Numbering follows the F1R-B mandatory matrix.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

REPO = Path(__file__).resolve().parents[3]
QUANT = REPO / "scripts/quant"


def _load(name: str, path: Path):  # type: ignore[no-untyped-def]
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


capture = _load("w2_f1r_b_source_capture", QUANT / "f1r_b_source_capture.py")
ports = _load("w2_f1r_b_production_ports", QUANT / "f1r_b_production_ports.py")
integration = _load(
    "w2_f1r_b_integration", QUANT / "f1r_b_production_recording_integration.py")
store_module = _load("w2_f1r_b_observation_store", QUANT / "f1r_b_observation_store.py")
fixtures = _load("w2_f1r_b_fixtures", QUANT / "f1r_b_fixtures.py")
runner = _load(
    "w2_run_f1r_b", QUANT / "run_f1r_b_production_recording_integration.py")
recorder = integration.recorder
contract = integration.contract

REFUSALS = (
    recorder.BatchError, capture.CaptureIdentityError,
    ports.SourcePortError, contract.ContractError)
FACTORS = contract.ALLOWED_FACTOR_IDS


def _bindings(**overrides):  # type: ignore[no-untyped-def]
    base = runner.bindings(f5_absence_reason=runner.f5_refusal())
    base.update(overrides)
    return base


def _build(**overrides):  # type: ignore[no-untyped-def]
    return integration.build_production_batch(
        feature_set=overrides.pop("feature_set", None) or runner.feature_set(),
        context=overrides.pop("context", None) or runner.context(),
        evaluation_id=overrides.pop("evaluation_id", runner.EVALUATION_ID),
        attempt_id=overrides.pop("attempt_id", runner.ATTEMPT_ID),
        evaluated_at_utc=overrides.pop(
            "evaluated_at_utc", fixtures.EVALUATED_AT.isoformat()),
        created_at_utc=overrides.pop(
            "created_at_utc", fixtures.CREATED_AT.isoformat()),
        bindings=overrides.pop("bindings", _bindings()))


def _ledger(tmp_path: Path):  # type: ignore[no-untyped-def]
    return contract.ForwardFactorLedger(tmp_path / "observations.jsonl")


def _by_factor(batch):  # type: ignore[no-untyped-def]
    return {record.factor_id: record for record in batch}


def _isolated_engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    import w2.infrastructure.persistence  # noqa: F401
    from w2.infrastructure.database import Base

    engine = sa.create_engine(f"sqlite+pysqlite:///{tmp_path / 'observations.db'}")
    Base.metadata.create_all(
        engine,
        tables=[Base.metadata.tables["forward_ah_factor_observations"]])
    return engine


# --- 1: a complete four-factor batch --------------------------------------
def test_01_a_complete_batch_records_all_four_factors(tmp_path) -> None:
    batch = _build()
    result = recorder.append_batch(_ledger(tmp_path), batch)

    assert result["appended"] == 4
    assert sorted(record.factor_id for record in batch) == sorted(FACTORS)


def test_01_each_factor_carries_its_own_version_capture_and_time() -> None:
    from w2.domain.factor_versions import factor_computation_version

    for record in _build():
        assert record.factor_version == factor_computation_version(record.factor_id)
        assert record.source_capture_sha256 != ""
        assert record.source_capture_id.startswith(capture.PRODUCTION_SET_PREFIX)
        assert record.factor_inputs["source_record_ids"]


def test_01_the_four_evidence_semantics_are_distinct_and_correct() -> None:
    semantics = {
        record.factor_id: record.factor_inputs["evidence_time_semantics"]
        for record in _build()
    }
    assert semantics == {
        "F3_REST_FITNESS": ports.FIXTURE_EVENT_TIME,
        "F5_RECENT_AH_COVER": integration.ABSENCE_LOOKUP,
        "F6_H2H": recorder.RESULT_DERIVED,
        "F9_TRUE_XG": recorder.SOURCE_SNAPSHOT_OBSERVED_AT,
    }


# --- 2: a missing factor_version ------------------------------------------
@pytest.mark.parametrize("factor_id", FACTORS)
def test_02_a_missing_factor_version_refuses_the_batch(factor_id) -> None:
    bindings = _bindings()
    bindings[factor_id] = replace(bindings[factor_id], factor_version="")

    with pytest.raises(REFUSALS) as excinfo:
        _build(bindings=bindings)
    assert excinfo.value.code == "FACTOR_VERSION_MISSING"


# --- 3: caller disagrees with the builder authority -----------------------
@pytest.mark.parametrize("factor_id", FACTORS)
@pytest.mark.parametrize(
    "impostor", ["v1", "1", "SYNTHETIC_FIXTURE_v1", "71daa3f5ec17ac3c5484e75a87d6bcac990d4bae"])
def test_03_a_caller_version_that_is_not_the_builders_refuses(factor_id, impostor) -> None:
    bindings = _bindings()
    bindings[factor_id] = replace(bindings[factor_id], factor_version=impostor)

    with pytest.raises(REFUSALS) as excinfo:
        _build(bindings=bindings)
    assert excinfo.value.code == "FACTOR_VERSION_DISAGREES_WITH_BUILDER_AUTHORITY"


def test_03_the_version_authority_matches_the_executed_builder() -> None:
    """The declared version names the algorithm the builder actually runs."""
    import hashlib
    import inspect

    from w2.domain.factor_versions import FACTOR_BUILDER_BINDINGS

    for factor_id, binding in FACTOR_BUILDER_BINDINGS.items():
        module = importlib.import_module(binding.module)
        builder = getattr(module, binding.builder)
        source = inspect.getsource(builder)
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        assert digest == binding.builder_source_sha256, (
            f"{factor_id}: {binding.builder} changed; revise its version")
        assert f'reason="{binding.ready_reason}"' in source, factor_id


def test_03_there_is_exactly_one_version_mapping() -> None:
    """Nobody keeps a second copy of the factor versions."""
    from w2.domain.factor_versions import FACTOR_COMPUTATION_VERSIONS

    declared = set(FACTOR_COMPUTATION_VERSIONS.values())
    others = []
    for path in (*QUANT.glob("*.py"), *(REPO / "src/w2").rglob("*.py")):
        if path.name == "factor_versions.py":
            continue
        text = path.read_text(encoding="utf-8")
        others.extend(version for version in declared if version in text)
    assert others == [], others


# --- 4: a missing capture id, hash or version -----------------------------
@pytest.mark.parametrize("factor_id", FACTORS)
@pytest.mark.parametrize("field_name", ["record_id", "content_sha256", "source_version"])
def test_04_a_missing_capture_field_refuses_the_batch(factor_id, field_name) -> None:
    bindings = _bindings()
    records = [replace(record, **{field_name: ""})
               for record in bindings[factor_id].records]
    bindings[factor_id] = replace(bindings[factor_id], records=records)

    with pytest.raises(REFUSALS) as excinfo:
        _build(bindings=bindings)
    assert excinfo.value.code in {
        "SOURCE_RECORD_ID_MISSING", "SOURCE_HASH_MISSING", "SOURCE_VERSION_MISSING"}


def test_04_an_empty_consumed_set_refuses() -> None:
    bindings = _bindings()
    bindings["F9_TRUE_XG"] = replace(bindings["F9_TRUE_XG"], records=[])

    with pytest.raises(REFUSALS) as excinfo:
        _build(bindings=bindings)
    assert excinfo.value.code == "CONSUMED_SOURCE_SET_EMPTY"


# --- 5: an illegal or tampered capture hash -------------------------------
@pytest.mark.parametrize("bad", ["", "ABC", "3" * 63, "3" * 65, "Z" * 64, ("3" * 63 + "A")])
def test_05_an_illegal_capture_hash_refuses(bad) -> None:
    bindings = _bindings()
    records = [replace(record, content_sha256=bad)
               for record in bindings["F6_H2H"].records]
    bindings["F6_H2H"] = replace(bindings["F6_H2H"], records=records)

    with pytest.raises(REFUSALS):
        _build(bindings=bindings)


def test_05_an_uppercase_hash_is_refused_not_normalised() -> None:
    digest = capture.content_sha256({"a": 1})
    with pytest.raises(capture.CaptureIdentityError) as excinfo:
        capture.require_hex64(digest.upper(), field_name="content_sha256")
    assert excinfo.value.code == "SOURCE_HASH_NOT_LOWERCASE_HEX"


def test_05_tampering_with_consumed_content_changes_the_capture_hash() -> None:
    rows = runner.meeting_rows()
    captures = runner.captures_for(rows)
    original = capture.capture_identity(
        "F6_H2H", ports.h2h_records(rows, captures=captures))

    tampered_rows = [dict(row) for row in rows]
    tampered_rows[0]["goals_for"] = tampered_rows[0]["goals_for"] + 1
    tampered = capture.capture_identity(
        "F6_H2H", ports.h2h_records(tampered_rows, captures=captures))

    assert tampered.source_capture_sha256 != original.source_capture_sha256
    # Same rows, so the set id is unchanged: content moved, identity did not.
    assert tampered.source_capture_id == original.source_capture_id


# --- 6: F5 has a provable source time (F1R-C) ------------------------------
AH_SAMPLE = REPO / "tests/fixtures/ah_settlement/real_production_capture_sample.jsonl"


def _real_fact_row(index: int = 1) -> dict[str, Any]:
    """A real runtime AH settlement fact, built from the committed real sample.

    Nothing is synthesised: the sample rows were extracted read-only from
    production and carry the real quotes, captures and terminal scores.
    """
    from w2.markets.ah_settlement_fact import (
        TerminalSettlementEvidence,
        build_ah_settlement_fact,
    )

    item = json.loads(AH_SAMPLE.read_text(encoding="utf-8").splitlines()[index])
    fixture = item["fixture"]
    cap = item["settlement_capture"]
    fact = build_ah_settlement_fact(
        fixture_id=fixture["fixture_id"],
        provider_fixture_id=str(fixture["provider_fixture_id"]),
        competition_id=fixture["competition_id"],
        season=fixture["season"],
        kickoff=fixture["kickoff_utc"],
        market_observations=item["observations"] or [],
        settlement=TerminalSettlementEvidence(
            provider_fixture_id=str(fixture["provider_fixture_id"]),
            status=fixture["fixture_status"],
            home_goals=fixture["home_goals"],
            away_goals=fixture["away_goals"],
            endpoint_capture_id=cap["capture_id"],
            raw_payload_sha256=cap["raw_payload_sha256"],
            observed_at=cap["provider_captured_at"],
            capture_endpoint=cap["endpoint"],
            capture_status=cap["capture_status"],
        ),
        home_team_provider_id=fixture["home_team_provider_id"],
        away_team_provider_id=fixture["away_team_provider_id"],
    )
    assert fact.status == "READY", fact.refusal_code
    return {
        "fact_id": fact.fact_id,
        "fact_hash": fact.fact_hash,
        "source_set_hash": fact.source_set_hash,
        "policy": fact.policy,
        "fixture_id": fact.fixture_id,
        "provider_fixture_id": fact.provider_fixture_id,
        "competition_id": fact.competition_id,
        "season": fact.season,
        "kickoff_utc": fact.kickoff_utc,
        "selected_line": str(fact.line),
        "selected_bookmakers": list(fact.selected_bookmakers),
        "quote_capture_ids": list(fact.quote_capture_ids),
        "quote_payload_sha256s": list(fact.quote_payload_sha256s),
        "quote_captured_at": fact.quote_captured_at,
        "settlement_capture_id": fact.settlement_capture_id,
        "settlement_payload_sha256": fact.settlement_payload_sha256,
        "settlement_observed_at": fact.settlement_observed_at,
        "settlement_observed_at_semantics": fact.settlement_observed_at_semantics,
        "terminal_status": fact.fixture_status,
        "home_goals": fact.home_goals,
        "away_goals": fact.away_goals,
        "home_settlement": fact.home_settlement,
        "away_settlement": fact.away_settlement,
    }


def test_06_a_real_ah_fact_yields_a_record_carrying_the_capture_instant() -> None:
    """F1R-C: the port serves F5, bound to the settlement capture's own instant."""
    row = _real_fact_row()
    records = ports.ah_fact_records([row])

    assert len(records) == 1
    record = records[0]
    assert record.record_id == row["fact_id"]
    assert record.observed_time_semantics == ports.PROVIDER_CAPTURE_OF_TERMINAL_RESULT
    assert record.observed_at_utc == row["settlement_observed_at"].isoformat()
    # Not the kickoff, not the quote time.
    assert record.observed_at_utc != row["kickoff_utc"].isoformat()
    assert record.observed_at_utc != row["quote_captured_at"].isoformat()
    assert record.source_version == ports.AH_SETTLEMENT_FACT_SCHEMA
    assert len(record.content_sha256) == 64


def test_06_the_record_content_binds_both_captures_and_both_payload_hashes() -> None:
    """The content hash must move when either side of the evidence moves."""
    row = _real_fact_row()
    base = ports.ah_fact_records([row])[0].content_sha256
    for field, tampered in (
        ("settlement_payload_sha256", "0" * 64),
        ("settlement_capture_id", "some-other-capture"),
        ("selected_line", "9.25"),
    ):
        moved = ports.ah_fact_records([{**row, field: tampered}])[0].content_sha256
        assert moved != base, field
    # And the quote side, which is a list of real capture ids.
    moved = ports.ah_fact_records(
        [{**row, "quote_payload_sha256s": ["1" * 64]}]
    )[0].content_sha256
    assert moved != base


def test_06_the_port_still_fails_closed_on_every_unprovable_fact() -> None:
    """Removing the refusal did not remove the proof requirements."""
    row = _real_fact_row()
    cases = {
        "no settlement observed time": {**row, "settlement_observed_at": None},
        "settlement not after kickoff": {
            **row, "settlement_observed_at": row["kickoff_utc"]},
        "koffoff pretending to be the source time": {
            **row,
            "settlement_observed_at": row["kickoff_utc"],
            "settlement_observed_at_semantics": "KICKOFF",
        },
        "query time semantics": {
            **row, "settlement_observed_at_semantics": "SOURCE_QUERIED_AT_AS_OF"},
        "wrong policy": {**row, "policy": "some_other_policy_v1"},
        "no settlement capture": {**row, "settlement_capture_id": ""},
        "no settlement payload hash": {**row, "settlement_payload_sha256": ""},
        "no quote capture": {**row, "quote_capture_ids": []},
        "no quote payload hash": {**row, "quote_payload_sha256s": []},
        "unproven fact id": {**row, "fact_id": "not-a-digest"},
    }
    for label, tampered in cases.items():
        with pytest.raises(REFUSALS):
            ports.ah_fact_records([tampered])
        del label


def test_06_an_empty_row_set_yields_no_records_rather_than_a_fake_one() -> None:
    """No facts consumed means no records -- and the caller then binds absence."""
    assert ports.ah_fact_records([]) == []


def test_06_f5_blocking_evidence_names_all_four_findings() -> None:
    """The F1R-B findings are kept: the successor package answers them."""
    assert len(ports.F5_BLOCKING_EVIDENCE) == 4
    assert any("NO_PRODUCTION_WRITER" in reason for reason in ports.F5_BLOCKING_EVIDENCE)
    assert any("CONFIRMED_AT" in reason for reason in ports.F5_BLOCKING_EVIDENCE)


def test_06_the_marker_now_has_a_production_writer() -> None:
    """F1R-B's finding, re-derived: nothing produced the marker. Now one does.

    The two readers and the new writer are the whole population, so the marker
    still cannot be produced anywhere else.
    """
    hits = sorted(
        path.relative_to(REPO).as_posix()
        for path in (REPO / "src").rglob("*.py")
        if "CANONICAL_AH_FACT_COLLECTION_STATUS = " in path.read_text(encoding="utf-8")
    )
    assert hits == ["src/w2/historical/runtime_ah_settlement.py"], hits


def test_06_f5_participating_without_a_source_time_refuses_the_batch() -> None:
    """An F5 that claims to have scored fails closed, it does not get a default."""
    contributions = list(runner.feature_set().contributions)
    for index, contribution in enumerate(contributions):
        if contribution.feature_id == "F5_RECENT_AH_COVER":
            contributions[index] = replace(
                contribution, status=type(contribution.status).READY, score=0.25,
                is_independent_signal=True, source_group="team_fixture_history",
                collection_status="READY")
    from w2.features.framework import FeatureSet, FeatureStatus

    feature_set = FeatureSet(
        fixture_id=fixtures.FIXTURE_ID, competition_id=fixtures.COMPETITION,
        as_of=fixtures.AS_OF, contributions=tuple(contributions),
        status=FeatureStatus.READY)

    with pytest.raises(REFUSALS) as excinfo:
        _build(feature_set=feature_set)
    assert excinfo.value.code == "PARTICIPATED_FACTOR_BOUND_TO_ABSENCE_LOOKUP"


# --- 7: F6 missing its result time ----------------------------------------
def test_07_an_f6_row_with_no_endpoint_capture_refuses() -> None:
    rows = [dict(row, endpoint_capture_id=None) for row in runner.meeting_rows()]
    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.h2h_records(rows, captures={})
    assert excinfo.value.code == "F6_HISTORY_ROW_HAS_NO_ENDPOINT_CAPTURE"


def test_07_an_unresolvable_capture_refuses() -> None:
    rows = runner.meeting_rows()
    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.h2h_records(rows, captures={})
    assert excinfo.value.code == "F6_ENDPOINT_CAPTURE_NOT_RESOLVED"


@pytest.mark.parametrize("status", ["FAILED", "PROVIDER_EMPTY"])
def test_07_an_unsuccessful_capture_is_not_evidence(status) -> None:
    rows = runner.meeting_rows()
    captures = {
        row["endpoint_capture_id"]: ports.endpoint_capture_from_row(
            fixtures.capture_row(row, status=status))
        for row in rows
    }
    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.h2h_records(rows, captures=captures)
    assert excinfo.value.code == "F6_ENDPOINT_CAPTURE_NOT_SUCCESSFUL"


def test_07_the_materialisation_clock_is_never_used_as_the_source_time() -> None:
    """`captured_at` on the history row is the run clock, not the provider read."""
    rows = runner.meeting_rows()
    records = ports.h2h_records(rows, captures=runner.captures_for(rows))
    row_clocks = {row["captured_at"].replace("Z", "+00:00") for row in rows}
    assert {record.observed_at_utc for record in records}.isdisjoint(row_clocks)


# --- 8: kickoff masquerading as a source time -----------------------------
def test_08_a_capture_time_equal_to_kickoff_refuses() -> None:
    rows = runner.meeting_rows()
    captures = runner.captures_for(rows)
    for row in rows:
        captures[row["endpoint_capture_id"]] = replace(
            captures[row["endpoint_capture_id"]],
            provider_captured_at=row["kickoff_utc"].replace("Z", "+00:00"))

    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.h2h_records(rows, captures=captures)
    assert excinfo.value.code == "F6_SOURCE_TIME_NOT_AFTER_KICKOFF"


def test_08_a_capture_time_before_kickoff_refuses() -> None:
    rows = runner.meeting_rows()
    captures = runner.captures_for(rows)
    for row in rows:
        kickoff = datetime.fromisoformat(row["kickoff_utc"].replace("Z", "+00:00"))
        captures[row["endpoint_capture_id"]] = replace(
            captures[row["endpoint_capture_id"]],
            provider_captured_at=(kickoff - timedelta(minutes=1)).isoformat())

    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.h2h_records(rows, captures=captures)
    assert excinfo.value.code == "F6_SOURCE_TIME_NOT_AFTER_KICKOFF"


def test_08_f6_evidence_time_is_not_the_contributions_observed_at() -> None:
    record = _by_factor(_build())["F6_H2H"]
    contribution = next(
        item for item in runner.feature_set().contributions
        if item.feature_id == "F6_H2H")
    assert record.evidence_time_utc != contribution.observed_at.isoformat()


def test_08_f3_may_not_read_a_result_field() -> None:
    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.rest_fitness_records(runner.meeting_rows())
    assert excinfo.value.code == "F3_RESULT_FIELD_IN_EVENT_TIME_INPUT"


# --- 9: evidence_time is the max of the consumed source times -------------
def test_09_evidence_time_is_the_latest_consumed_source_time() -> None:
    record = _by_factor(_build())["F6_H2H"]
    times = record.factor_inputs["source_observed_times"].split(",")

    assert record.evidence_time_utc == max(times)
    assert len(times) == 2


def test_09_a_later_consumed_source_moves_the_evidence_time() -> None:
    rows = runner.meeting_rows()
    captures = runner.captures_for(rows)
    baseline = ports.h2h_records(rows, captures=captures)

    later = dict(captures)
    key = rows[0]["endpoint_capture_id"]
    moved = datetime.fromisoformat(
        captures[key].provider_captured_at) + timedelta(hours=5)
    later[key] = replace(captures[key], provider_captured_at=moved.isoformat())
    shifted = ports.h2h_records(rows, captures=later)

    assert max(record.observed_at_utc for record in shifted) > max(
        record.observed_at_utc for record in baseline)


def test_09_f9_uses_the_latest_of_both_team_snapshots() -> None:
    record = _by_factor(_build())["F9_TRUE_XG"]
    times = record.factor_inputs["source_observed_times"].split(",")
    assert record.evidence_time_utc == max(times)


# --- 10: identity moves with consumed sources only ------------------------
def test_10_reordering_the_consumed_set_does_not_change_identity() -> None:
    rows = runner.meeting_rows()
    captures = runner.captures_for(rows)
    forward = capture.capture_identity("F6_H2H", ports.h2h_records(rows, captures=captures))
    backward = capture.capture_identity(
        "F6_H2H", list(reversed(ports.h2h_records(rows, captures=captures))))

    assert forward.source_capture_sha256 == backward.source_capture_sha256
    assert forward.source_capture_id == backward.source_capture_id


def test_10_changing_a_consumed_source_changes_the_observation_identity() -> None:
    baseline = _by_factor(_build())["F6_H2H"]
    rows = runner.meeting_rows()
    captures = runner.captures_for(rows)
    key = rows[0]["endpoint_capture_id"]
    captures[key] = replace(
        captures[key],
        raw_payload_sha256=capture.content_sha256({"different": "payload"}))
    bindings = _bindings()
    bindings["F6_H2H"] = replace(
        bindings["F6_H2H"], records=ports.h2h_records(rows, captures=captures))
    changed = _by_factor(_build(bindings=bindings))["F6_H2H"]

    sealed = [contract.validate(record) for record in (baseline, changed)]
    assert sealed[0].observation_id != sealed[1].observation_id


def test_10_a_source_the_factor_never_consumed_changes_nothing() -> None:
    baseline = capture.capture_identity(
        "F6_H2H", ports.h2h_records(
            runner.meeting_rows(), captures=runner.captures_for(runner.meeting_rows())))

    # A row that exists in the database but that this factor did not read.
    unconsumed = fixtures.history_row(
        team_w2_id=fixtures.HOME_TEAM, opponent_w2_id="w2-someone-else",
        days_ago=999, goals_for=5, goals_against=0)
    assert unconsumed["history_id"] not in baseline.record_ids

    again = capture.capture_identity(
        "F6_H2H", ports.h2h_records(
            runner.meeting_rows(), captures=runner.captures_for(runner.meeting_rows())))
    assert again.source_capture_sha256 == baseline.source_capture_sha256


def test_10_a_wrong_sized_consumed_set_refuses() -> None:
    bindings = _bindings()
    bindings["F9_TRUE_XG"] = replace(
        bindings["F9_TRUE_XG"], records=bindings["F9_TRUE_XG"].records[:1])

    with pytest.raises(REFUSALS) as excinfo:
        _build(bindings=bindings)
    assert excinfo.value.code == "CONSUMED_SOURCE_COUNT_DISAGREES_WITH_BUILDER"


def test_10_a_right_sized_but_wrong_consumed_set_refuses() -> None:
    """Two rows, the correct count, but not the rows the builder read."""
    home_rows, away_rows = runner.history_rows()
    wrong = fixtures.event_time_rows([home_rows[1], away_rows[1]])
    bindings = _bindings()
    bindings["F3_REST_FITNESS"] = replace(
        bindings["F3_REST_FITNESS"], records=ports.rest_fitness_records(wrong))

    with pytest.raises(REFUSALS) as excinfo:
        _build(bindings=bindings)
    assert excinfo.value.code == "CONSUMED_SOURCE_SET_DISAGREES_WITH_BUILDER"


def test_10_a_synthetic_record_cannot_reach_the_production_branch() -> None:
    bindings = _bindings()
    bindings["F9_TRUE_XG"] = replace(
        bindings["F9_TRUE_XG"],
        records=[replace(record, synthetic=True)
                 for record in bindings["F9_TRUE_XG"].records])

    with pytest.raises(REFUSALS) as excinfo:
        _build(bindings=bindings)
    assert excinfo.value.code == "SYNTHETIC_SOURCE_IN_PRODUCTION_BRANCH"


def test_10_a_synthetic_capture_id_is_labelled() -> None:
    identity = capture.capture_identity("F9_TRUE_XG", [
        capture.ConsumedSourceRecord(
            record_id="fixture-1", content_sha256="3" * 64,
            source_version="fixture", observed_at_utc="2026-01-01T00:00:00+00:00",
            synthetic=True)])
    assert identity.source_capture_id.startswith(capture.SYNTHETIC_SET_PREFIX)
    assert identity.synthetic is True


# --- 11: PIT ---------------------------------------------------------------
def test_11_evidence_time_equal_to_evaluated_at_refuses() -> None:
    record = _by_factor(_build())["F9_TRUE_XG"]
    with pytest.raises(contract.ContractError) as excinfo:
        contract.validate(replace(record, evaluated_at_utc=record.evidence_time_utc))
    assert excinfo.value.code == "PIT_EVIDENCE_TIME_EQUALS_EVALUATED_AT"


def test_11_evidence_time_after_evaluated_at_refuses() -> None:
    record = _by_factor(_build())["F9_TRUE_XG"]
    earlier = (contract.parse_aware_utc(record.evidence_time_utc, field_name="e")
               - timedelta(minutes=1)).isoformat()
    with pytest.raises(contract.ContractError) as excinfo:
        contract.validate(replace(record, evaluated_at_utc=earlier))
    assert excinfo.value.code == "PIT_EVIDENCE_TIME_AFTER_EVALUATED_AT"


def test_11_a_naive_source_time_refuses() -> None:
    rows = runner.meeting_rows()
    captures = runner.captures_for(rows)
    key = rows[0]["endpoint_capture_id"]
    naive = datetime.fromisoformat(
        captures[key].provider_captured_at).replace(tzinfo=None).isoformat()
    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.endpoint_capture_from_row({
            "capture_id": key, "provider_captured_at": naive,
            "raw_payload_sha256": rows[0]["source_raw_hash"],
            "capture_status": "CAPTURED"})
    assert excinfo.value.code == "SOURCE_TIME_NOT_TIMEZONE_AWARE"


def test_11_mixed_zones_are_the_same_instant_and_the_same_identity() -> None:
    rows = runner.meeting_rows()
    captures = runner.captures_for(rows)
    shifted = dict(captures)
    for key, value in captures.items():
        instant = datetime.fromisoformat(value.provider_captured_at)
        shifted[key] = replace(
            value,
            provider_captured_at=instant.astimezone(
                timezone(timedelta(hours=9))).isoformat())

    assert (capture.capture_identity("F6_H2H", ports.h2h_records(rows, captures=shifted))
            .source_capture_sha256
            == capture.capture_identity(
                "F6_H2H", ports.h2h_records(rows, captures=captures)
            ).source_capture_sha256)


# --- 12: participation and applied weight ---------------------------------
def test_12_participation_is_the_scoring_authoritys_verdict() -> None:
    authority = recorder.scoring_authority_view(runner.feature_set().contributions)
    for record in _build():
        assert record.participated is (record.factor_id in authority["scoring_factors"])


def test_12_a_non_participating_factor_applies_no_weight_and_carries_no_score() -> None:
    record = _by_factor(_build())["F5_RECENT_AH_COVER"]
    assert Decimal(str(record.applied_weight)) == Decimal(0)
    assert record.signed_score is None
    assert record.factor_inputs["declared_weight"] == "0.05"


def test_12_a_participating_factors_applied_weight_is_the_authoritys() -> None:
    authority = recorder.scoring_authority_view(runner.feature_set().contributions)
    for record in _build():
        if not record.participated:
            continue
        expected = authority["scoring_factors"][record.factor_id]["weight"]
        assert Decimal(str(record.applied_weight)) == Decimal(str(expected))


# --- 13: batch weight closure ---------------------------------------------
def test_13_applied_weights_sum_to_what_the_authority_used() -> None:
    authority = recorder.scoring_authority_view(runner.feature_set().contributions)
    total = sum((Decimal(str(record.applied_weight)) for record in _build()), Decimal(0))
    assert total == Decimal(str(authority["weight_sum_used"]))


def test_13_a_tampered_applied_weight_refuses_the_batch() -> None:
    batch = _build()
    tampered = [replace(record, applied_weight=Decimal("0.99"))
                if record.factor_id == "F3_REST_FITNESS" else record
                for record in batch]
    with pytest.raises(REFUSALS):
        recorder._batch_coherence(
            [contract.validate(record) for record in tampered],
            recorder.scoring_authority_view(
                runner.feature_set().contributions)["weight_sum_used"])


# --- 14: batch shape -------------------------------------------------------
@pytest.mark.parametrize("dropped", FACTORS)
def test_14_a_missing_factor_binding_refuses(dropped) -> None:
    bindings = _bindings()
    del bindings[dropped]
    with pytest.raises(REFUSALS) as excinfo:
        _build(bindings=bindings)
    assert excinfo.value.code == "FACTOR_SOURCE_BINDING_MISSING"


def test_14_a_missing_contribution_refuses() -> None:
    from w2.features.framework import FeatureSet, FeatureStatus

    contributions = tuple(
        item for item in runner.feature_set().contributions
        if item.feature_id != "F6_H2H")
    feature_set = FeatureSet(
        fixture_id=fixtures.FIXTURE_ID, competition_id=fixtures.COMPETITION,
        as_of=fixtures.AS_OF, contributions=contributions,
        status=FeatureStatus.READY)
    with pytest.raises(REFUSALS) as excinfo:
        _build(feature_set=feature_set)
    assert excinfo.value.code == "INCOMPLETE_BATCH_MISSING_FACTOR"


@pytest.mark.parametrize(
    "field_name,value",
    [("evaluation_id", "dqe-" + "9" * 64), ("attempt_id", "att-" + "9" * 60),
     ("fixture_id", "9000009"), ("evaluated_at_utc", "2026-10-01T18:40:00+00:00")])
def test_14_a_batch_may_not_mix_identities(tmp_path, field_name, value) -> None:
    batch = _build()
    mixed = [replace(record, **{field_name: value}) if index == 0 else record
             for index, record in enumerate(batch)]
    with pytest.raises(REFUSALS) as excinfo:
        recorder.append_batch(_ledger(tmp_path), mixed)
    assert excinfo.value.code == "BATCH_FIELD_NOT_UNIFORM"


def test_14_a_duplicated_factor_refuses(tmp_path) -> None:
    batch = _build()
    duplicated = [*batch, batch[0]]
    with pytest.raises(REFUSALS) as excinfo:
        recorder.append_batch(_ledger(tmp_path), duplicated)
    assert excinfo.value.code == "BATCH_FACTOR_SET_INVALID"


# --- 15: idempotency, conflict, revision, dangling, cycle -----------------
def test_15_replaying_a_batch_into_the_store_is_a_no_op(tmp_path) -> None:
    store = store_module.ForwardFactorObservationStore(_isolated_engine(tmp_path))
    batch = _build()
    first = store.append_batch(batch)
    second = store.append_batch(batch)

    assert (first["appended"], second["appended"]) == (4, 0)
    assert second["idempotent_no_ops"] == 4


def test_15_the_same_identity_with_different_content_conflicts(tmp_path) -> None:
    store = store_module.ForwardFactorObservationStore(_isolated_engine(tmp_path))
    batch = _build()
    store.append_batch(batch)
    sealed = [contract.validate(record) for record in batch]
    forged = [replace(record, factor_inputs={**record.factor_inputs, "extra": "x"},
                      observation_id=record.observation_id,
                      factor_input_hash=None, factor_verdict_hash=None)
              for record in sealed]
    with pytest.raises(REFUSALS):
        store.append_batch(forged)
    assert len(store.by_id()) == 4


def test_15_a_revision_chain_appends_and_leaves_the_old_rows(tmp_path) -> None:
    store = store_module.ForwardFactorObservationStore(_isolated_engine(tmp_path))
    batch = [contract.validate(record) for record in _build()]
    store.append_batch(batch)
    before = store.by_id()

    revised = [recorder.revise(record, supersedes=record.observation_id,
                               reason="F1R_B_SOURCE_RESTATEMENT",
                               created_at_utc=fixtures.CREATED_AT.isoformat(),
                               factor_inputs={**record.factor_inputs,
                                              "restated": "true"})
               for record in batch]
    store.append_batch(revised)
    after = store.by_id()

    assert len(after) == 8
    for observation_id, payload in before.items():
        assert after[observation_id] == payload


def test_15_a_dangling_supersedes_refuses(tmp_path) -> None:
    store = store_module.ForwardFactorObservationStore(_isolated_engine(tmp_path))
    batch = [contract.validate(record) for record in _build()]
    dangling = [recorder.revise(record, supersedes="a" * 64, reason="nope",
                                created_at_utc=fixtures.CREATED_AT.isoformat())
                for record in batch]
    with pytest.raises(REFUSALS) as excinfo:
        store.append_batch(dangling)
    assert excinfo.value.code == "SUPERSEDES_TARGET_NOT_FOUND"
    assert store.by_id() == {}


def test_15_a_supersedes_cycle_refuses(tmp_path) -> None:
    store = store_module.ForwardFactorObservationStore(_isolated_engine(tmp_path))
    batch = [contract.validate(record) for record in _build()]
    store.append_batch(batch)
    first = [contract.validate(
        recorder.revise(record, supersedes=record.observation_id, reason="one",
                        created_at_utc=fixtures.CREATED_AT.isoformat(),
                        factor_inputs={**record.factor_inputs, "step": "1"}))
        for record in batch]
    store.append_batch(first)

    existing = store.by_id()
    cycle = replace(batch[0], observation_id=None, factor_input_hash=None,
                    factor_verdict_hash=None,
                    supersedes_observation_id=first[0].observation_id,
                    revision_reason="cycle")
    sealed = contract.validate(cycle)
    # Point the chain back at the record we are about to write.
    existing[first[0].observation_id]["supersedes_observation_id"] = sealed.observation_id
    with pytest.raises(REFUSALS) as excinfo:
        store_module.ForwardFactorObservationStore._assert_no_cycle(
            sealed.observation_id, first[0].observation_id, existing)
    assert excinfo.value.code == "SUPERSEDES_CYCLE"


# --- 16: nothing is written when anything fails ---------------------------
def test_16_a_refused_batch_adds_zero_rows_to_the_store(tmp_path) -> None:
    store = store_module.ForwardFactorObservationStore(_isolated_engine(tmp_path))
    incomplete = [record for record in _build() if record.factor_id != "F6_H2H"]
    with pytest.raises(REFUSALS):
        store.append_batch(incomplete)
    assert store.by_id() == {}


def test_16_a_database_failure_midway_adds_zero_rows(tmp_path, monkeypatch) -> None:
    engine = _isolated_engine(tmp_path)
    store = store_module.ForwardFactorObservationStore(engine)
    real_to_row = store_module._to_row
    calls = {"n": 0}

    def exploding(payload):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disk went away mid-batch")
        return real_to_row(payload)

    monkeypatch.setattr(store_module, "_to_row", exploding)
    with pytest.raises(OSError):
        store.append_batch(_build())
    monkeypatch.undo()
    assert calls["n"] == 3
    assert store.by_id() == {}


def test_16_a_database_failure_on_the_first_row_adds_zero_rows(tmp_path, monkeypatch) -> None:
    engine = _isolated_engine(tmp_path)
    store = store_module.ForwardFactorObservationStore(engine)

    def exploding(payload):  # type: ignore[no-untyped-def]
        raise OSError("disk went away before the first row")

    monkeypatch.setattr(store_module, "_to_row", exploding)
    with pytest.raises(OSError):
        store.append_batch(_build())
    monkeypatch.undo()
    assert store.by_id() == {}


def test_16_a_failure_at_the_database_commit_point_adds_zero_rows(
    tmp_path, monkeypatch
) -> None:
    """The commit itself fails after every row is staged.

    `with session.begin()` commits through the transaction object, so that is
    what has to fail: patching `Session.commit` would leave the real commit
    path untouched and the test would pass without proving anything.
    """
    engine = _isolated_engine(tmp_path)
    store = store_module.ForwardFactorObservationStore(engine)

    def exploding(self):  # type: ignore[no-untyped-def]
        raise OSError("commit failed")

    monkeypatch.setattr(sa.orm.session.SessionTransaction, "commit", exploding)
    with pytest.raises(OSError):
        store.append_batch(_build())
    monkeypatch.undo()
    assert store.by_id() == {}


def test_16_zero_rows_survive_a_second_attempt_after_a_failure(tmp_path, monkeypatch) -> None:
    """A failed batch is not half-remembered: retrying writes all four."""
    engine = _isolated_engine(tmp_path)
    store = store_module.ForwardFactorObservationStore(engine)
    real_to_row = store_module._to_row
    calls = {"n": 0}

    def exploding(payload):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("transient")
        return real_to_row(payload)

    monkeypatch.setattr(store_module, "_to_row", exploding)
    with pytest.raises(OSError):
        store.append_batch(_build())
    monkeypatch.undo()
    assert store.by_id() == {}
    assert store.append_batch(_build())["appended"] == 4


def test_16_a_refused_batch_leaves_the_file_ledger_byte_identical(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    recorder.append_batch(ledger, _build())
    before = ledger.path.read_bytes()

    with pytest.raises(REFUSALS):
        recorder.append_batch(
            ledger, [record for record in _build() if record.factor_id != "F9_TRUE_XG"])
    assert ledger.path.read_bytes() == before


def test_16_an_fsync_failure_adds_no_lines(tmp_path, monkeypatch) -> None:
    ledger = _ledger(tmp_path)
    recorder.append_batch(ledger, _build())
    before = ledger.path.read_bytes()

    monkeypatch.setattr(
        recorder.os, "fsync",
        lambda handle: (_ for _ in ()).throw(OSError("fsync failed")))
    other = _build(evaluation_id="dqe-" + "7" * 64, attempt_id="att-" + "8" * 60)
    with pytest.raises(OSError):
        recorder.append_batch(ledger, other)
    monkeypatch.undo()
    assert ledger.path.read_bytes() == before


# --- 17: migration ---------------------------------------------------------
def test_17_the_isolated_replay_upgrades_writes_reads_back_and_rolls_back() -> None:
    replay = runner.isolated_replay(_build())

    assert replay["upgrade_returncode"] == 0
    assert replay["repeat_upgrade_returncode"] == 0
    assert replay["table_present_after_upgrade"] is True
    # F1R-C's additive table arrives with the same upgrade, unchanged otherwise.
    assert replay["ah_fact_table_present_after_upgrade"] is True
    assert replay["rows_appended"] == 4
    assert replay["replay_appended"] == 0
    assert replay["replay_idempotent_no_ops"] == 4
    assert replay["readback_rows"] == 4
    assert replay["readback_payload_matches_contract"] is True
    assert replay["populated_rollback_refused"] is True
    assert replay["rows_after_blocked_rollback"] == 4
    assert replay["empty_rollback_returncode"] == 0
    assert replay["repeat_rollback_returncode"] == 0
    assert replay["table_present_after_rollback"] is False
    assert replay["unrelated_tables_untouched"] is True


def test_17_the_migration_is_additive_only() -> None:
    text = (REPO / "migrations/versions/0071_forward_ah_factor_observation.py").read_text(
        encoding="utf-8")
    tree = ast.parse(text)
    upgrade = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == "upgrade")
    calls = {
        node.func.attr for node in ast.walk(upgrade)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "op"
    }
    assert calls == {"create_table", "create_index"}
    assert "drop_column" not in text
    assert "alter_column" not in text


def test_17_a_populated_downgrade_refuses_rather_than_destroying_facts() -> None:
    text = (REPO / "migrations/versions/0071_forward_ah_factor_observation.py").read_text(
        encoding="utf-8")
    assert "WOULD_DESTROY_FACTS" in text


def test_17_every_meaningful_column_is_not_null() -> None:
    from w2.infrastructure.persistence import ForwardAhFactorObservationModel

    nullable = {column.name for column in
                ForwardAhFactorObservationModel.__table__.columns if column.nullable}
    assert nullable == {"signed_score", "supersedes_observation_id", "revision_reason"}


# --- 18: history is untouched ---------------------------------------------
def test_18_the_migration_touches_no_existing_table() -> None:
    """Every DDL call in the migration names the one table it adds."""
    path = REPO / "migrations/versions/0071_forward_ah_factor_observation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    named: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "op"):
            continue
        arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
        for argument in arguments:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                named.add(argument.value)
            if isinstance(argument, ast.Name) and argument.id == "_TABLE":
                named.add("forward_ah_factor_observations")
    tables = {name for name in named if not name.startswith(("ix_", "uq_"))}
    assert tables == {"forward_ah_factor_observations"}, tables


def test_18_historical_no_factor_verdict_identity_still_means_what_it_meant() -> None:
    assert contract.HISTORICAL_NO_FACTOR_VERDICT_IDENTITY in contract.ALLOWED_FACTOR_STATUSES
    assert (contract.HISTORICAL_NO_FACTOR_VERDICT_IDENTITY
            in contract.SCORELESS_STATUSES)


def test_18_the_frozen_f1p_reference_ledger_still_validates() -> None:
    path = (REPO / "docs/review_packages/W2_AH_FACTOR_ACCURACY_F1P_20260910"
            / "F1P_REFERENCE_LEDGER.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert rows
    for row in rows:
        record = contract.ForwardFactorObservation(**{
            key: value for key, value in row.items()
            if key in {field.name for field in
                       __import__("dataclasses").fields(contract.ForwardFactorObservation)}})
        assert contract.validate(record).observation_id == row["observation_id"]


# --- 19: frozen packages ---------------------------------------------------
@pytest.mark.parametrize("package", [
    "W2_AH_FACTOR_ACCURACY_F0_20260910",
    "W2_AH_FACTOR_ACCURACY_F1_20260910",
    "W2_AH_FACTOR_ACCURACY_F1P_20260910",
    "W2_AH_FACTOR_ACCURACY_F1R_A0_20260910",
])
def test_19_frozen_package_hashes_are_unchanged(package) -> None:
    import hashlib

    directory = REPO / "docs/review_packages" / package
    manifest = (directory / "HASHES.sha256").read_text(encoding="utf-8")
    checked = 0
    for line in manifest.splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        actual = hashlib.sha256((directory / name.strip()).read_bytes()).hexdigest()
        assert actual == digest, f"{package}/{name.strip()}"
        checked += 1
    assert checked


#: The F1R-B delivery commit. Historical pins are verified against these bytes,
#: not against a working tree a successor was authorised to change.
F1R_B_DELIVERY_COMMIT = "b4285660b091b1270172cfd3b7c226ff8c7fcc62"

#: F1 froze two source files' hashes. F1R-C revised one of them, because the F5
#: builder lives in it. That revision is named here rather than hidden by
#: relaxing the check.
F1R_C_REVISED_F1_PINNED_SOURCES = {
    "src/w2/features/team_factors.py":
        "8d4afae21ced6b4cdc02673a88057899475b0884a4e0787ce3d6f240c57acdfc",
}


def test_19_the_pinned_builder_sources_are_still_the_frozen_f1_evidence() -> None:
    """The F1 freeze is historical evidence, and stays verifiable.

    F1R-B did not change either pinned file, so the pin is verified against the
    F1R-B delivery commit -- where it genuinely held. The working tree is then
    checked separately, with the one F1R-C revision named explicitly. Deleting
    the check would lose the history; asserting the working tree still matches
    F1 byte-for-byte would simply be false.
    """
    import hashlib
    import subprocess

    inventory = (REPO / "docs/review_packages/W2_AH_FACTOR_ACCURACY_F1_20260910"
                 / "F1_SOURCE_INVENTORY.jsonl")
    pinned = {}
    for line in inventory.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["source_type"] == "SOURCE_CODE_DEFAULT":
            pinned[row["source_path"]] = row["source_sha256"]
    assert pinned

    for path, digest in pinned.items():
        delivered = subprocess.run(  # noqa: S603
            ["/usr/bin/git", "show", f"{F1R_B_DELIVERY_COMMIT}:{path}"],
            cwd=REPO, capture_output=True, check=True).stdout
        assert hashlib.sha256(delivered).hexdigest() == digest, path

    for path, digest in pinned.items():
        expected = F1R_C_REVISED_F1_PINNED_SOURCES.get(path, digest)
        assert hashlib.sha256((REPO / path).read_bytes()).hexdigest() == expected, path

    revised = {
        path for path, digest in pinned.items()
        if digest != F1R_C_REVISED_F1_PINNED_SOURCES.get(path, digest)
    }
    assert revised == set(F1R_C_REVISED_F1_PINNED_SOURCES), sorted(revised)


# --- 20: no side effects ---------------------------------------------------
@pytest.mark.parametrize("module_path", [
    "f1r_b_source_capture.py", "f1r_b_production_ports.py",
    "f1r_b_production_recording_integration.py", "f1r_b_fixtures.py",
    "run_f1r_b_production_recording_integration.py",
])
def test_20_no_network_provider_or_vps_reference(module_path) -> None:
    text = (QUANT / module_path).read_text(encoding="utf-8")
    for banned in ("requests", "httpx", "urllib.request", "socket",
                   "api-football", "ssh ", "paramiko"):
        assert banned not in text, f"{module_path}: {banned}"
    # No host address of any kind. Written as a pattern rather than as the
    # literal it is looking for: the repository's own infrastructure-literal
    # guard scans this tree, and a test that spells out a public address to
    # forbid it would itself be the violation.
    assert re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) is None, module_path


def test_20_the_live_capture_switch_is_off() -> None:
    assert ports.PRODUCTION_CAPTURE_ENABLED is False
    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.LiveSourceReadPort().read("select 1")
    assert excinfo.value.code == "LIVE_CAPTURE_DISABLED"


def test_20_enabling_the_port_is_still_not_authorised() -> None:
    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.LiveSourceReadPort(enabled=True).read("select 1")
    assert excinfo.value.code == "LIVE_CAPTURE_NOT_AUTHORISED"


def test_20_the_production_chain_does_not_import_this_wiring() -> None:
    """Nothing imports the wiring statically, and only one module names it.

    F1R-B asserted that `src/` never mentioned these modules at all, because no
    production path reached them. The successor commit that persists the four
    factors necessarily changes that, so the invariant is narrowed to the one
    that still has to hold: the modules are reached by *file path*, from exactly
    one module, and are never pulled into another module's import graph. A
    static import would drag the F1R-B sources into every read-only caller.
    """
    allowed = {"src/w2/quant_research/forward_factor_modules.py"}
    hits = {
        path.relative_to(REPO).as_posix()
        for path in (REPO / "src").rglob("*.py")
        if "f1r_b_" in path.read_text(encoding="utf-8")
    }
    assert hits == allowed, sorted(hits)
    text = (REPO / "src/w2/quant_research/forward_factor_modules.py").read_text(
        encoding="utf-8")
    assert "import f1r_b_" not in text
    assert "from f1r_b_" not in text
    assert "from w2.quant_research._f1r_b" not in text
    assert "spec_from_file_location" in text


def test_20_no_scheduler_dashboard_or_v4_module_was_modified() -> None:
    """F1R-B itself touched no protected path.

    The range is pinned to F1R-B's own commit rather than "the working tree as
    it stands now". What this test exists to prove is a property of this task's
    delivery, and diffing against a moving HEAD made it re-judge every later,
    separately authorised change as if it belonged to F1R-B.
    """
    changed = subprocess.run(
        ["git", "diff", "--name-only",
         "71daa3f5ec17ac3c5484e75a87d6bcac990d4bae",
         "c482ccf92804cea8f92ef3d24aa158346495370d"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    for path in changed:
        assert not path.startswith("src/w2/scheduler/"), path
        assert not path.startswith("src/w2/dashboard/"), path
        assert not path.startswith("src/w2/strategy/"), path
        assert not path.startswith("src/w2/prematch/"), path


def test_20_no_second_serializer_or_hash_writer_is_defined() -> None:
    for name in ("f1r_b_source_capture.py", "f1r_b_production_ports.py",
                 "f1r_b_production_recording_integration.py"):
        text = (QUANT / name).read_text(encoding="utf-8")
        assert "def canonical_json" not in text
        assert "hashlib" not in text


# --- 22: the runner is deterministic --------------------------------------
def test_22_two_runs_in_different_directories_are_byte_identical(tmp_path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    for output in (first, second):
        subprocess.run(
            [sys.executable, str(QUANT / "run_f1r_b_production_recording_integration.py"),
             "--output", str(output)],
            cwd=REPO, check=True, capture_output=True, text=True)
    assert ((first / runner.LEDGER_NAME).read_bytes()
            == (second / runner.LEDGER_NAME).read_bytes())


def test_22_the_published_result_states_what_is_not_done(tmp_path) -> None:
    subprocess.run(
        [sys.executable, str(QUANT / "run_f1r_b_production_recording_integration.py"),
         "--output", str(tmp_path)],
        cwd=REPO, check=True, capture_output=True, text=True)
    result = json.loads((tmp_path / "F1R_B_RESULT.json").read_text(encoding="utf-8"))

    assert result["final_state"] == "BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE"
    assert result["f5_source_time_proven"] is False
    assert result["f6_source_time_proven"] is True
    assert result["f9_source_time_proven"] is True
    assert result["live_capture_enabled"] is False
    assert result["provider_calls"] == 0
    assert result["production_db_reads"] == 0
    assert result["production_db_writes"] == 0
    assert result["deployment_executed"] is False
    assert result["historical_148_backfilled"] is False
    assert result["obsidian_writes"] == 0
