"""F1R-B independent oracle: re-derive every published hash from scratch.

Nothing in this file imports the recorder, the integration, the capture module,
the F1P contract or `w2.domain.canonical_serialization`. The serializer is
re-implemented here from the written contract (`w2.canonical-json.v2`: NFC
normalisation, sorted keys, compact separators, no ASCII escaping, reserved
`$w2_` keys refused, UTF-8) and the preimages are transcribed from the frozen
`F1P_SCHEMA_CONTRACT.json` field lists rather than from the code that computes
them.

It lives under `tests/` rather than beside the other F1R-B tests on purpose.
`scripts/` is a canonical-serialization production root, and an independent
oracle necessarily re-implements the serializer it is checking; putting it here
keeps `check_canonical_serialization_authority` reporting one authority and no
unauthorised writer, without registering a test file in a registry meant for
legacy production sites.

If the production implementation and this transcription ever disagree, one of
them is wrong and the difference is visible here instead of being hidden by a
shared import.
"""
from __future__ import annotations

import ast
import hashlib
import json
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "docs/review_packages/W2_AH_FACTOR_ACCURACY_F1R_B_20260911"
F1P_CONTRACT = (REPO / "docs/review_packages/W2_AH_FACTOR_ACCURACY_F1P_20260910"
                / "F1P_SCHEMA_CONTRACT.json")

CONTRACT_ID = "w2.forward_ah_factor_observation.v1"
HASH_DOMAIN = "future_refresh.evidence"
SERIALIZER_VERSION = "w2.canonical-json.v2"


# --- an independent w2.canonical-json.v2 ----------------------------------
def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            assert isinstance(key, str), key
            normalized = unicodedata.normalize("NFC", key)
            assert not normalized.startswith("$w2_"), normalized
            assert normalized not in out, normalized
            out[normalized] = _normalize(item)
        return out
    if isinstance(value, list | tuple):
        return [_normalize(item) for item in value]
    raise AssertionError(f"the oracle refuses {type(value).__name__}")


def oracle_sha256(value: Any) -> str:
    encoded = json.dumps(
        _normalize(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text)


@pytest.fixture(scope="module")
def published() -> dict[str, Any]:
    """Read the delivered review package.

    The oracle checks what was actually published, not a fresh run of the code
    that published it. Determinism of the runner is a separate claim, proven by
    `test_22_two_runs_in_different_directories_are_byte_identical`.
    """
    output = PACKAGE
    ledger = [json.loads(line) for line
              in (output / "F1R_B_REFERENCE_LEDGER.jsonl").read_text(
                  encoding="utf-8").splitlines() if line.strip()]
    return {
        "ledger": ledger,
        "manifests": json.loads(
            (output / "F1R_B_SOURCE_MANIFESTS.json").read_text(encoding="utf-8")),
        "result": json.loads(
            (output / "F1R_B_RESULT.json").read_text(encoding="utf-8")),
    }


# --- the oracle does not import what it is checking ------------------------
def test_the_oracle_imports_no_production_implementation() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    banned = ("w2.domain.canonical_serialization", "w2_f1p", "w2_f1r",
              "f1p_forward_factor_contract", "f1r_b_", "f1r_a0_")
    for name in imported:
        assert not any(name.startswith(prefix) for prefix in banned), name
    # ...and does not side-load one by path either.
    called = {node.func.attr for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert "spec_from_file_location" not in called
    assert "module_from_spec" not in called


def test_the_oracle_agrees_with_the_serializer_contract() -> None:
    """Spot-check the re-implementation against the written v2 rules."""
    assert oracle_sha256({"b": 1, "a": 2}) == oracle_sha256({"a": 2, "b": 1})
    assert oracle_sha256({"k": "é"}) == oracle_sha256({"k": "é"})
    with pytest.raises(AssertionError):
        oracle_sha256({"$w2_float": "00"})
    assert oracle_sha256({"k": "é"}) == hashlib.sha256(
        '{"k":"é"}'.encode()).hexdigest()


# --- 21: re-derive the capture hashes -------------------------------------
def test_the_capture_hash_is_the_hash_of_the_published_manifest(published) -> None:
    by_factor = {row["factor_id"]: row for row in published["ledger"]}
    assert set(by_factor) == set(published["manifests"])
    for factor_id, manifest in published["manifests"].items():
        assert manifest["contract"] == "w2.f1r_b_source_capture.v1"
        assert manifest["hash_domain"] == HASH_DOMAIN
        assert manifest["serializer_version"] == SERIALIZER_VERSION
        assert oracle_sha256(manifest) == by_factor[factor_id]["source_capture_sha256"]


def test_the_capture_id_is_the_hash_of_the_consumed_record_ids(published) -> None:
    by_factor = {row["factor_id"]: row for row in published["ledger"]}
    for factor_id, manifest in published["manifests"].items():
        record_ids = [entry["record_id"] for entry in manifest["records"]]
        assert record_ids == sorted(record_ids)
        digest = oracle_sha256({
            "contract": "w2.f1r_b_source_capture.v1",
            "factor_id": factor_id,
            "record_ids": record_ids,
        })
        assert by_factor[factor_id]["source_capture_id"] == (
            f"w2.consumed_source_set.v1:{digest}")
        assert by_factor[factor_id]["factor_inputs"]["source_record_ids"] == (
            ",".join(record_ids))


# --- 21: re-derive the observation identity -------------------------------
def _preimages() -> dict[str, list[str]]:
    identity = json.loads(F1P_CONTRACT.read_text(encoding="utf-8"))["identity"]
    return {
        "input": identity["factor_input_hash_preimage"],
        "verdict": identity["factor_verdict_hash_preimage"],
        "observation": identity["observation_id_preimage"],
    }


def test_the_three_identity_hashes_re_derive_from_the_stored_row(published) -> None:
    fields = _preimages()
    constants = {
        "contract": CONTRACT_ID,
        "hash_domain": HASH_DOMAIN,
        "serializer_version": SERIALIZER_VERSION,
    }
    for row in published["ledger"]:
        def value(name: str, row: dict[str, Any] = row) -> Any:
            if name in constants:
                return constants[name]
            if name == "evidence_time_utc":
                return _instant(row[name]).isoformat()
            return row[name]

        input_hash = oracle_sha256({name: value(name) for name in fields["input"]})
        assert input_hash == row["factor_input_hash"], row["factor_id"]

        verdict_source = dict(row, factor_input_hash=input_hash)
        verdict_hash = oracle_sha256(
            {name: (constants.get(name, verdict_source.get(name)))
             for name in fields["verdict"]})
        assert verdict_hash == row["factor_verdict_hash"], row["factor_id"]

        observation_source = dict(
            row, factor_input_hash=input_hash, factor_verdict_hash=verdict_hash)
        observation_id = oracle_sha256({
            name: (constants[name] if name in constants
                   else _instant(observation_source[name]).isoformat()
                   if name == "evaluated_at_utc"
                   else observation_source[name])
            for name in fields["observation"]})
        assert observation_id == row["observation_id"], row["factor_id"]


def test_created_at_is_not_in_any_identity_preimage() -> None:
    fields = _preimages()
    for names in fields.values():
        assert "created_at_utc" not in names


# --- 21: re-derive the batch facts ----------------------------------------
def test_the_batch_is_exactly_four_factors_of_one_attempt(published) -> None:
    rows = published["ledger"]
    assert sorted(row["factor_id"] for row in rows) == [
        "F3_REST_FITNESS", "F5_RECENT_AH_COVER", "F6_H2H", "F9_TRUE_XG"]
    for name in ("evaluation_id", "attempt_id", "fixture_id", "evaluated_at_utc"):
        assert len({row[name] for row in rows}) == 1, name


def test_every_evidence_time_is_strictly_before_the_evaluation(published) -> None:
    for row in published["ledger"]:
        assert _instant(row["evidence_time_utc"]) < _instant(row["evaluated_at_utc"])
        assert _instant(row["evidence_time_utc"]).utcoffset() is not None


def test_a_result_derived_factor_never_uses_a_kickoff(published) -> None:
    """F6's evidence time is a provider capture, strictly after every kickoff."""
    manifest = published["manifests"]["F6_H2H"]
    row = next(r for r in published["ledger"] if r["factor_id"] == "F6_H2H")
    observed = [_instant(entry["observed_at_utc"]) for entry in manifest["records"]]
    assert _instant(row["evidence_time_utc"]) == max(observed)
    assert all(entry["observed_time_semantics"] == "PROVIDER_CAPTURE_OF_FINISHED_FIXTURE"
               for entry in manifest["records"])


def test_the_absent_factor_carries_no_weight_and_no_score(published) -> None:
    row = next(r for r in published["ledger"] if r["factor_id"] == "F5_RECENT_AH_COVER")
    assert row["participated"] is False
    assert row["applied_weight"] == "0"
    assert row["signed_score"] is None
    assert row["factor_status"] == "INSUFFICIENT_DATA"
    assert row["factor_inputs"]["declared_weight"] == "0.05"


def test_the_applied_weights_sum_to_the_published_authority_total(published) -> None:
    from decimal import Decimal

    total = sum((Decimal(row["applied_weight"]) for row in published["ledger"]),
                Decimal(0))
    assert str(total) == published["result"]["complete_batch"]["applied_weight_sum"]


def test_the_versions_are_per_factor_and_none_is_a_bare_v1(published) -> None:
    versions = {row["factor_id"]: row["factor_version"] for row in published["ledger"]}
    assert len(set(versions.values())) == 4
    for factor_id, version in versions.items():
        assert version not in {"v1", "1", "SYNTHETIC_FIXTURE_v1"}, factor_id
        assert version.startswith("w2.factor."), factor_id
        assert len(version) != 40, factor_id  # not a git sha
