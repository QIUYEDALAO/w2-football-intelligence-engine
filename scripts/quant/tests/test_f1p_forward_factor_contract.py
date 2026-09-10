"""F1P forward factor contract: every rule that has to fail closed.

The contract exists so that a future F2 has inputs it can trust. These tests
are therefore mostly about refusal: a record that cannot prove when its evidence
became knowable, or whose declared identity does not match its contents, must
never reach the ledger.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO / "scripts/quant/f1p_forward_factor_contract.py"
RUNNER_PATH = REPO / "scripts/quant/run_f1p_forward_factor_contract.py"
OUTPUT = REPO / "docs/review_packages/W2_AH_FACTOR_ACCURACY_F1P_20260910"


def _load(name: str, path: Path):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = _load("w2_f1p_contract", MODULE_PATH)
ContractError = contract.ContractError

EVIDENCE = "2026-09-07T17:30:00+00:00"
EVALUATED = "2026-09-07T18:32:34.722346+00:00"
CREATED = "2026-09-07T18:32:35+00:00"
CAPTURE_SHA = "a" * 64


def _record(**overrides):  # type: ignore[no-untyped-def]
    base = dict(
        evaluation_id="dqe-" + "e" * 64,
        attempt_id="att-" + "1" * 60,
        fixture_id="1570366",
        factor_id="F3_REST_FITNESS",
        factor_version="v1",
        factor_status=contract.PARTICIPATED,
        participated=True,
        applied_weight="0.10",
        factor_inputs={"home_rest_days": "5.0", "away_rest_days": "4.0"},
        evidence_time_utc=EVIDENCE,
        evaluated_at_utc=EVALUATED,
        created_at_utc=CREATED,
        source_capture_id="capture-1",
        source_capture_sha256=CAPTURE_SHA,
        source_version="w2.analysis_card.v1",
        signed_score="0.25",
    )
    base.update(overrides)
    return contract.ForwardFactorObservation(**base)


def _ledger(tmp_path: Path):  # type: ignore[no-untyped-def]
    return contract.ForwardFactorLedger(tmp_path / "observations.jsonl")


def _codes(excinfo) -> str:  # type: ignore[no-untyped-def]
    return excinfo.value.code


# --- a complete legal record round-trips --------------------------------
def test_a_complete_record_is_written_and_reads_back(tmp_path) -> None:
    ledger = _ledger(tmp_path)

    result = ledger.append(_record())
    stored = ledger.readback(result.observation_id)

    assert result.created is True
    assert stored["observation_id"] == result.observation_id
    assert stored["factor_status"] == contract.PARTICIPATED
    assert stored["applied_weight"] == "0.10"
    assert stored["signed_score"] == "0.25"
    for name in ("observation_id", "factor_input_hash", "factor_verdict_hash"):
        contract.require_hex64(stored[name], field_name=name)


# --- PIT ----------------------------------------------------------------
@pytest.mark.parametrize(("value", "code"), [
    (None, "EVIDENCE_TIME_MISSING"),
    ("", "EVIDENCE_TIME_MISSING"),
    ("   ", "EVIDENCE_TIME_MISSING"),
    ("not-a-timestamp", "TIMESTAMP_UNPARSEABLE"),
    ("2026-13-45T00:00:00+00:00", "TIMESTAMP_UNPARSEABLE"),
    ("2026-09-07T17:30:00", "TIMESTAMP_NOT_TIMEZONE_AWARE"),
])
def test_an_unusable_evidence_time_fails_closed(tmp_path, value, code) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(evidence_time_utc=value))

    assert _codes(excinfo) == code
    assert not (tmp_path / "observations.jsonl").exists()


def test_evidence_time_equal_to_evaluated_at_fails(tmp_path) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(
            _record(evidence_time_utc=EVALUATED, evaluated_at_utc=EVALUATED))

    assert _codes(excinfo) == "PIT_EVIDENCE_TIME_EQUALS_EVALUATED_AT"


def test_evidence_time_after_evaluated_at_fails(tmp_path) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(
            _record(evidence_time_utc="2026-09-07T19:00:00+00:00"))

    assert _codes(excinfo) == "PIT_EVIDENCE_TIME_AFTER_EVALUATED_AT"


def test_the_same_instant_in_another_zone_normalises_correctly(tmp_path) -> None:
    """+09:00 and Z describe one instant; the contract must see one instant."""
    ledger = _ledger(tmp_path)

    first = ledger.append(_record())
    same = ledger.append(_record(evidence_time_utc="2026-09-08T02:30:00+09:00"))

    assert contract.parse_aware_utc(
        "2026-09-08T02:30:00+09:00", field_name="t").isoformat() == EVIDENCE
    assert same.observation_id == first.observation_id
    assert same.created is False


def test_a_zone_shifted_instant_that_is_late_still_fails(tmp_path) -> None:
    # 2026-09-08T04:00+09:00 is 19:00Z, after the evaluation
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(
            _record(evidence_time_utc="2026-09-08T04:00:00+09:00"))

    assert _codes(excinfo) == "PIT_EVIDENCE_TIME_AFTER_EVALUATED_AT"


def test_text_ordering_cannot_smuggle_a_late_evidence_time(tmp_path) -> None:
    """' ' sorts before 'T', so a text comparison would admit this pair."""
    late = "2026-09-07 19:30:00+00"
    assert str(late) < str(EVALUATED), "text comparison would have accepted it"

    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(evidence_time_utc=late))

    assert _codes(excinfo) == "PIT_EVIDENCE_TIME_AFTER_EVALUATED_AT"


def test_created_at_can_never_stand_in_for_evidence_time(tmp_path) -> None:
    """created_at is after the evaluation and is not in the identity at all."""
    ledger = _ledger(tmp_path)
    first = ledger.append(_record())

    later = ledger.append(_record(created_at_utc="2026-09-09T00:00:00+00:00"))

    assert later.observation_id == first.observation_id
    assert "created_at_utc" not in contract.PROTECTED_FIELDS


# --- weight -------------------------------------------------------------
def test_a_missing_applied_weight_fails(tmp_path) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(applied_weight=None))

    assert _codes(excinfo) == "APPLIED_WEIGHT_MISSING"


def test_no_registry_default_is_ever_filled_in() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    for default in ("0.10\"", "0.05\"", "= 0.10", "= 0.05", "0.3333", "16.67"):
        assert default not in source, default
    assert "DEFAULT_WEIGHT" not in source


# --- hashes -------------------------------------------------------------
def test_a_missing_factor_input_hash_is_computed_not_required(tmp_path) -> None:
    """Omitting it is fine; supplying a wrong one is not."""
    sealed = contract.validate(_record())

    assert sealed.factor_input_hash is not None
    assert len(sealed.factor_input_hash) == 64


@pytest.mark.parametrize(("value", "code"), [
    ("", "HASH_MISSING"),
    ("abc", "HASH_LENGTH_INVALID"),
    ("A" * 64, "HASH_NOT_LOWERCASE_HEX"),
    ("z" * 64, "HASH_NOT_LOWERCASE_HEX"),
    ("a" * 63, "HASH_LENGTH_INVALID"),
])
def test_an_illegal_hash_fails(tmp_path, value, code) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(factor_input_hash=value))

    assert _codes(excinfo) == code


def test_an_uppercase_source_capture_hash_fails(tmp_path) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(source_capture_sha256="A" * 64))

    assert _codes(excinfo) == "HASH_NOT_LOWERCASE_HEX"


def test_a_factor_input_hash_that_disagrees_with_its_preimage_fails(tmp_path) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(factor_input_hash="b" * 64))

    assert _codes(excinfo) == "IDENTITY_MISMATCH"
    assert excinfo.value.detail == "factor_input_hash"


def test_a_factor_verdict_hash_that_disagrees_with_the_verdict_fails(tmp_path) -> None:
    sealed = contract.validate(_record())

    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(replace(
            _record(), factor_verdict_hash=sealed.factor_input_hash))

    assert _codes(excinfo) == "IDENTITY_MISMATCH"
    assert excinfo.value.detail == "factor_verdict_hash"


@pytest.mark.parametrize("field_name", contract.PROTECTED_FIELDS)
def test_changing_any_protected_field_changes_the_identity(field_name) -> None:
    baseline = contract.validate(_record())
    mutation = {
        "evaluation_id": "dqe-" + "f" * 64,
        "attempt_id": "att-" + "2" * 60,
        "fixture_id": "1570367",
        "market": contract.AH_MARKET,
        "factor_id": "F9_TRUE_XG",
        "factor_version": "v2",
        "factor_status": contract.INSUFFICIENT_DATA,
        "participated": False,
        "applied_weight": "0.20",
        "factor_inputs": {"home_rest_days": "6.0"},
        "evidence_time_utc": "2026-09-07T17:00:00+00:00",
        "evaluated_at_utc": "2026-09-07T18:40:00+00:00",
        "source_capture_id": "capture-2",
        "source_capture_sha256": "c" * 64,
        "source_version": "w2.analysis_card.v2",
        "signed_score": "0.30",
        "supersedes_observation_id": "d" * 64,
    }[field_name]
    if field_name == "market":
        pytest.skip("market is pinned to ASIAN_HANDICAP by the contract itself")
    overrides = {field_name: mutation}
    if field_name == "factor_status":
        overrides.update(participated=False, signed_score=None)
    if field_name == "participated":
        overrides.update(factor_status=contract.INSUFFICIENT_DATA, signed_score=None)
    if field_name == "signed_score":
        overrides.update(factor_status=contract.PARTICIPATED, participated=True)

    other = contract.validate(_record(**overrides))

    assert other.observation_id != baseline.observation_id, field_name


# --- append-only --------------------------------------------------------
def test_an_identical_rewrite_is_an_idempotent_no_op(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    first = ledger.append(_record())

    second = ledger.append(_record())

    assert second.created is False
    assert second.reason == "IDEMPOTENT_NO_OP"
    assert second.observation_id == first.observation_id
    assert len(ledger.rows()) == 1


def test_the_same_observation_id_with_different_business_fields_conflicts(
    tmp_path,
) -> None:
    """Forged identity: same id claimed, different content underneath."""
    ledger = _ledger(tmp_path)
    sealed = contract.validate(_record())
    ledger.append(_record())
    forged = replace(
        _record(revision_reason="tampered"),
        observation_id=sealed.observation_id,
        factor_input_hash=sealed.factor_input_hash,
        factor_verdict_hash=sealed.factor_verdict_hash)

    with pytest.raises(ContractError) as excinfo:
        ledger.append(forged)

    assert _codes(excinfo) == "OBSERVATION_ID_BUSINESS_CONFLICT"
    assert "revision_reason" in excinfo.value.detail
    assert len(ledger.rows()) == 1


def test_a_revision_appends_and_leaves_the_old_row_byte_identical(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    original = ledger.append(_record())
    before = ledger.path.read_bytes()

    revised = ledger.append(_record(
        applied_weight="0.12",
        supersedes_observation_id=original.observation_id,
        revision_reason="WEIGHT_CORRECTED_BY_SOURCE"))

    assert revised.created is True
    assert revised.observation_id != original.observation_id
    assert ledger.path.read_bytes().startswith(before)
    rows = ledger.rows()
    assert len(rows) == 2
    assert rows[0]["applied_weight"] == "0.10"
    assert rows[1]["supersedes_observation_id"] == original.observation_id


def test_a_revision_without_a_reason_fails(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    original = ledger.append(_record())

    with pytest.raises(ContractError) as excinfo:
        ledger.append(_record(
            applied_weight="0.12",
            supersedes_observation_id=original.observation_id))

    assert _codes(excinfo) == "REVISION_REASON_MISSING"


def test_superseding_an_unknown_observation_fails(tmp_path) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(
            applied_weight="0.12",
            supersedes_observation_id="e" * 64,
            revision_reason="dangling"))

    assert _codes(excinfo) == "SUPERSEDES_TARGET_NOT_FOUND"


def test_a_supersedes_cycle_fails(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    first = ledger.append(_record())
    second = ledger.append(_record(
        applied_weight="0.12", supersedes_observation_id=first.observation_id,
        revision_reason="r1"))
    # forge a cycle by pointing the first row's successor back into the chain
    rows = ledger.rows()
    rows[0]["supersedes_observation_id"] = second.observation_id
    ledger.path.write_text(
        "\n".join(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows)
        + "\n", encoding="utf-8")

    with pytest.raises(ContractError) as excinfo:
        ledger.append(_record(
            applied_weight="0.13", supersedes_observation_id=second.observation_id,
            revision_reason="r2"))

    assert _codes(excinfo) == "SUPERSEDES_CYCLE"


def test_a_revision_cannot_rewrite_the_original_evidence(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    original = ledger.append(_record())

    ledger.append(_record(
        evidence_time_utc="2026-09-07T16:00:00+00:00",
        supersedes_observation_id=original.observation_id,
        revision_reason="EVIDENCE_TIME_CORRECTED"))

    kept = ledger.readback(original.observation_id)
    assert kept["evidence_time_utc"] == EVIDENCE
    assert kept["applied_weight"] == "0.10"


# --- readback -----------------------------------------------------------
def test_readback_recomputes_the_hash_and_checks_every_field(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    result = ledger.append(_record())

    assert ledger.readback(result.observation_id)["observation_id"] == (
        result.observation_id)


def test_readback_refuses_a_row_tampered_with_on_disk(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    result = ledger.append(_record())
    rows = ledger.rows()
    rows[0]["applied_weight"] = "0.99"
    ledger.path.write_text(
        json.dumps(rows[0], sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8")

    with pytest.raises(ContractError) as excinfo:
        ledger.readback(result.observation_id)

    assert _codes(excinfo) in {"READBACK_FIELD_MISMATCH", "IDENTITY_MISMATCH"}


# --- AS-OF vs post-event ------------------------------------------------
def test_a_result_field_cannot_enter_the_factor_input(tmp_path) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(
            factor_inputs={"home_rest_days": "5.0", "settlement": "LOSS"}))

    assert _codes(excinfo) == "POST_EVENT_FIELD_IN_FACTOR_INPUT"


def test_post_event_enrichment_never_changes_an_as_of_observation(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    result = ledger.append(_record())
    before = ledger.path.read_bytes()
    enrichment = contract.PostEventEnrichmentLedger(tmp_path / "post_event.jsonl")

    enrichment.append(evaluation_id=_record().evaluation_id,
                      payload={"score": "2-3", "settlement": "LOSS",
                               "profit_units": "-1.0"})

    assert ledger.path.read_bytes() == before
    assert ledger.readback(result.observation_id)["observation_id"] == (
        result.observation_id)
    assert enrichment.rows()[0]["record_kind"] == contract.POST_EVENT_ENRICHMENT


def test_the_as_of_view_returns_no_post_event_field(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    result = ledger.append(_record())

    view = ledger.as_of_view(result.observation_id)

    assert not contract.POST_EVENT_FIELDS & set(view)
    assert view["record_kind"] == contract.AS_OF_FACTOR_OBSERVATION


def test_enrichment_refuses_a_field_that_is_not_post_event(tmp_path) -> None:
    enrichment = contract.PostEventEnrichmentLedger(tmp_path / "post_event.jsonl")

    with pytest.raises(ContractError) as excinfo:
        enrichment.append(evaluation_id="dqe-x",
                          payload={"signed_score": "0.9"})

    assert _codes(excinfo) == "POST_EVENT_FIELD_NOT_ALLOWED"


def test_a_snapshot_without_pit_evidence_is_not_an_observation(tmp_path) -> None:
    """F1's unbound archive snapshot must not slip in as a formal observation."""
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(evidence_time_utc=None))

    assert _codes(excinfo) == "EVIDENCE_TIME_MISSING"


# --- status semantics ---------------------------------------------------
def test_insufficient_data_is_not_a_zero_score(tmp_path) -> None:
    ledger = _ledger(tmp_path)

    result = ledger.append(_record(
        factor_status=contract.INSUFFICIENT_DATA, participated=False,
        signed_score=None))

    stored = ledger.readback(result.observation_id)
    assert stored["signed_score"] is None
    assert stored["participated"] is False


@pytest.mark.parametrize("status", [
    contract.INSUFFICIENT_DATA, contract.SOURCE_UNAVAILABLE,
    contract.FACTOR_ADMISSION_FAILED,
])
def test_a_scoreless_status_may_not_carry_a_score(tmp_path, status) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(
            factor_status=status, participated=False, signed_score="0.0"))

    assert _codes(excinfo) == "SCORELESS_STATUS_CARRIES_A_SCORE"


def test_only_participation_counts_as_admitted() -> None:
    assert contract.is_factor_admitted(contract.PARTICIPATED) is True
    for status in (contract.INSUFFICIENT_DATA, contract.SOURCE_UNAVAILABLE,
                   contract.FACTOR_ADMISSION_FAILED,
                   contract.HISTORICAL_NO_FACTOR_VERDICT_IDENTITY):
        assert contract.is_factor_admitted(status) is False


# --- historical payloads ------------------------------------------------
def test_a_pre_verdict_payload_reads_back_as_the_historical_marker() -> None:
    for payload in ({}, {"state": "ANALYSIS_PICK_ACTIVE"},
                    {"factor_direction": None, "factor_veto_code": None}):
        assert contract.classify_historical_payload(payload) == (
            contract.HISTORICAL_NO_FACTOR_VERDICT_IDENTITY)


def test_the_historical_marker_is_never_admitted() -> None:
    status = contract.classify_historical_payload({})

    assert status == contract.HISTORICAL_NO_FACTOR_VERDICT_IDENTITY
    assert contract.is_factor_admitted(status) is False


# --- scope --------------------------------------------------------------
@pytest.mark.parametrize("factor_id", [
    "F1_MARKET_MOVEMENT", "F4_MATCH_IMPORTANCE", "F7_STRENGTH_FORM",
    "F8_SQUAD_VALUE", "", "f3_rest_fitness",
])
def test_a_factor_outside_the_four_fails(tmp_path, factor_id) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(factor_id=factor_id))

    assert _codes(excinfo) == "FACTOR_ID_NOT_ALLOWED"


def test_totals_is_out_of_contract_not_an_ah_factor_failure(tmp_path) -> None:
    with pytest.raises(ContractError) as excinfo:
        _ledger(tmp_path).append(_record(market="TOTALS"))

    assert _codes(excinfo) == "MARKET_OUT_OF_CONTRACT"
    assert "FACTOR" not in _codes(excinfo)


# --- the runner ---------------------------------------------------------
def test_the_runner_is_deterministic(tmp_path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    for target in (first, second):
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(RUNNER_PATH), "--output", str(target)],
            capture_output=True, text=True, check=False, cwd=REPO)
        assert result.returncode == 0, result.stdout + result.stderr

    for name in ("F1P_RESULT.json", "F1P_SCHEMA_CONTRACT.json",
                 "F1P_REFERENCE_LEDGER.jsonl"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_the_runner_reaches_no_provider_database_or_production_module() -> None:
    import ast

    banned = {"requests", "httpx", "urllib", "urllib3", "http", "socket", "aiohttp",
              "sqlalchemy", "psycopg", "psycopg2", "alembic"}
    forbidden_w2 = ("w2.prematch", "w2.strategy", "w2.api", "w2.dashboard",
                    "w2.providers", "w2.ingestion", "w2.scheduler")
    for path in (MODULE_PATH, RUNNER_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = (
                [alias.name for alias in node.names] if isinstance(node, ast.Import)
                else [node.module or ""] if isinstance(node, ast.ImportFrom)
                else []
            )
            for name in names:
                assert name.split(".")[0] not in banned, (path, name)
                assert not name.startswith(forbidden_w2), (path, name)


def test_the_contract_reuses_the_single_canonical_serializer() -> None:
    import ast

    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    sources = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and any(a.name == "canonical_sha256" for a in node.names)
    }

    assert sources == {"w2.domain.canonical_serialization"}
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "hashlib.sha256" not in source
    assert contract.SERIALIZER_VERSION == "w2.canonical-json.v2"


def test_the_published_result_is_a_finite_terminal_state() -> None:
    result = json.loads((OUTPUT / "F1P_RESULT.json").read_text(encoding="utf-8"))

    assert result["final_state"] in {
        "FORWARD_CONTRACT_READY", "BLOCKED_BY_AUTHORITY", "FAILED"}
    assert result["f2_allowed"] is False
    assert result["f3_allowed"] is False
    assert result["provider_calls"] == 0
    assert result["production_db_reads"] == 0
    assert result["production_db_writes"] == 0
    assert result["deployment_executed"] is False
    assert result["obsidian_writes"] == 0
    assert result["produces_model_weights"] is False
    assert result["produces_recommendation_direction"] is False
    assert result["is_historical_backfill_of_the_148"] is False
