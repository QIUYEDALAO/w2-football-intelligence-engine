"""F1R-B: wire the accepted offline recorder to real production sources.

The recorder accepted at `db0f2c21` takes a caller-supplied `FactorProvenance`
and trusts it. That was correct for an offline exercise and is not correct for
production: a caller could name any version, any capture id and any source
time. This module closes that gap without re-implementing anything the
accepted recorder already decides.

What it adds, and only this:

* **Version.** `factor_version` must equal what `w2.domain.factor_versions`
  declares for that factor. A caller that names anything else -- including a
  plausible one, a commit SHA or a bare `v1` -- is refused, and the refusal is
  batch-wide.
* **Capture identity.** `source_capture_id` and `source_capture_sha256` are
  computed from the source records the factor actually consumed, never
  supplied. A synthetic record cannot reach the production branch.
* **Source time.** A result-derived factor's evidence time is the maximum of
  the real observed times of the sources it consumed, and the consumed set is
  cross-checked against what the contribution itself reports having read.

What it does not touch: eligibility, participation, applied weight, the
weight-sum invariant and the all-or-nothing commit all remain the accepted
recorder's, reached by delegation rather than by copy.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.domain.factor_versions import (
    FactorVersionError,
    factor_builder_binding,
    factor_computation_version,
)

_HERE = Path(__file__).resolve().parent


def _load(module_name: str, filename: str) -> Any:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, _HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


recorder = _load("w2_f1r_a0_offline_factor_recorder", "f1r_a0_offline_factor_recorder.py")
capture = _load("w2_f1r_b_source_capture", "f1r_b_source_capture.py")
ports = _load("w2_f1r_b_production_ports", "f1r_b_production_ports.py")
contract = recorder.contract

INTEGRATION_ID = "w2.f1r_b_production_recording_integration.v1"
ABSENCE_LOOKUP = "SOURCE_QUERIED_AT_AS_OF"

#: How many source records each factor must have consumed when it participated.
#: F6 is variable and is checked against the contribution's own meeting count.
EXPECTED_CONSUMED_COUNT = {"F3_REST_FITNESS": 2, "F9_TRUE_XG": 2}


class IntegrationError(recorder.BatchError):
    """A batch-level refusal from the production wiring."""


@dataclass(frozen=True, kw_only=True)
class FactorSourceBinding:
    """What a caller supplies per factor. The version is declared, not chosen.

    `factor_version` is here so the caller has to state which computation it
    believes it ran; it is then checked against the builder authority rather
    than trusted. `records` are the source rows the factor actually consumed.
    """

    factor_version: str
    records: list[Any]


def absence_records(
    factor_id: str, *, query_identity: str, as_of_utc: str, reason: str
) -> list[Any]:
    """The consumed set for a factor that found nothing.

    An absent factor still consumed something: a lookup that returned no usable
    rows. Hashing that lookup is honest; inventing a source record would not
    be, and refusing to record the factor at all would break the all-or-nothing
    batch the contract requires.
    """
    content = {
        "schema_version": "w2.f1r_b_absence_lookup.v1",
        "factor_id": factor_id,
        "query_identity": query_identity,
        "queried_at_utc": as_of_utc,
        "reason": reason,
        "rows_returned": 0,
    }
    return [capture.ConsumedSourceRecord(
        record_id=f"absence:{factor_id}:{query_identity}",
        content_sha256=capture.content_sha256(content),
        source_version="w2.f1r_b_absence_lookup.v1",
        observed_at_utc=as_of_utc,
        observed_time_semantics=ABSENCE_LOOKUP,
    )]


def _parse(value: object, *, field_name: str) -> datetime:
    return contract.parse_aware_utc(recorder._text(value), field_name=field_name)


def _check_version(factor_id: str, declared: str) -> str:
    try:
        authority = factor_computation_version(factor_id)
    except FactorVersionError as exc:
        raise IntegrationError("FACTOR_VERSION_AUTHORITY_MISSING", factor_id) from exc
    if not declared or not str(declared).strip():
        raise IntegrationError("FACTOR_VERSION_MISSING", factor_id)
    if declared != authority:
        raise IntegrationError(
            "FACTOR_VERSION_DISAGREES_WITH_BUILDER_AUTHORITY",
            f"{factor_id}:{declared}!={authority}")
    return authority


#: Factors whose latest consumed source time is exactly the instant the builder
#: reports. F6 is excluded on purpose: its observed_at is the meeting kickoff,
#: which is precisely what its source time may not be.
LATEST_SOURCE_IS_OBSERVED_AT = frozenset({"F3_REST_FITNESS", "F9_TRUE_XG"})


def _check_consumed_set(factor_id: str, contribution: Any, records: list[Any]) -> None:
    """The consumed set must match what the contribution says it read.

    This is the guard against a caller passing a source set that is not the one
    the factor scored: too few rows, too many, or somebody else's. Counts are
    checked against the builder's own report, and where the builder publishes
    the instant of its latest input, that instant is checked too -- a set with
    the right size but the wrong rows fails there.
    """
    expected = EXPECTED_CONSUMED_COUNT.get(factor_id)
    if expected is not None and len(records) != expected:
        raise IntegrationError(
            "CONSUMED_SOURCE_COUNT_DISAGREES_WITH_BUILDER",
            f"{factor_id}:{len(records)}!={expected}")
    if factor_id == "F6_H2H":
        declared = (contribution.inputs or {}).get("meeting_count")
        if declared is None:
            raise IntegrationError("F6_MEETING_COUNT_MISSING", factor_id)
        if int(declared) != len(records):
            raise IntegrationError(
                "CONSUMED_SOURCE_COUNT_DISAGREES_WITH_BUILDER",
                f"{factor_id}:{len(records)}!={declared}")
    if factor_id not in LATEST_SOURCE_IS_OBSERVED_AT:
        return
    observed_at = getattr(contribution, "observed_at", None)
    if observed_at is None:
        raise IntegrationError("PARTICIPATED_WITHOUT_OBSERVED_AT", factor_id)
    times = [record.observed_at_utc for record in records if record.observed_at_utc]
    if len(times) != len(records):
        raise IntegrationError("SOURCE_OBSERVED_TIME_MISSING", factor_id)
    latest = max(_parse(value, field_name=f"{factor_id}.source_observed_at")
                 for value in times)
    if latest != _parse(observed_at, field_name=f"{factor_id}.observed_at"):
        raise IntegrationError(
            "CONSUMED_SOURCE_SET_DISAGREES_WITH_BUILDER",
            f"{factor_id}:{latest.isoformat()}!={observed_at}")


def provenance_for(
    factor_id: str,
    binding: FactorSourceBinding,
    *,
    contribution: Any,
    participated: bool,
) -> tuple[Any, dict[str, str]]:
    """Turn a caller's binding into provenance the accepted recorder accepts."""
    version = _check_version(factor_id, binding.factor_version)
    identity = capture.capture_identity(factor_id, binding.records)
    if identity.synthetic:
        # The production branch must never carry a fixture capture, even one
        # that is honestly labelled.
        raise IntegrationError("SYNTHETIC_SOURCE_IN_PRODUCTION_BRANCH", factor_id)

    source_observed_at: str | None = None
    if participated:
        if any(record.observed_time_semantics == ABSENCE_LOOKUP
               for record in binding.records):
            # A factor that scored read something. Letting the "we looked and
            # found nothing" record stand in for its sources would hand it an
            # evidence time equal to the query time -- the exact substitution
            # this task exists to prevent.
            raise IntegrationError(
                "PARTICIPATED_FACTOR_BOUND_TO_ABSENCE_LOOKUP", factor_id)
        _check_consumed_set(factor_id, contribution, binding.records)
        if factor_id in recorder.RESULT_DERIVED_FACTORS:
            if not identity.observed_times:
                raise IntegrationError("SOURCE_OBSERVED_TIME_MISSING", factor_id)
            # The factor is only knowable once every source it consumed was.
            source_observed_at = max(
                _parse(value, field_name=f"{factor_id}.source_observed_at")
                for value in identity.observed_times
            ).isoformat()

    binding_spec = factor_builder_binding(factor_id)
    extra_inputs = {
        "source_record_ids": ",".join(identity.record_ids),
        "source_observed_times": ",".join(sorted(identity.observed_times)),
        "source_observed_time_semantics": ",".join(sorted({
            record.observed_time_semantics for record in binding.records})),
        "consumed_source_count": str(len(identity.record_ids)),
        "factor_builder": f"{binding_spec.module}:{binding_spec.builder}",
        "factor_builder_source_sha256": binding_spec.builder_source_sha256,
        "integration": INTEGRATION_ID,
    }
    provenance = recorder.FactorProvenance(
        factor_version=version,
        source_capture_id=identity.source_capture_id,
        source_capture_sha256=identity.source_capture_sha256,
        source_version=identity.source_version,
        source_observed_at=source_observed_at,
    )
    return provenance, extra_inputs


def build_production_batch(
    *,
    feature_set: Any,
    context: Any,
    evaluation_id: str,
    attempt_id: str,
    evaluated_at_utc: str,
    created_at_utc: str,
    bindings: dict[str, FactorSourceBinding],
) -> list[Any]:
    """The four AH factors, bound to real sources, or a refusal.

    Participation is resolved first -- by the scoring authority, through the
    accepted recorder -- because whether a factor participated decides whether
    it needs a source-observed time at all.
    """
    contributions = {
        contribution.feature_id: contribution
        for contribution in feature_set.contributions
        if contribution.feature_id in recorder.REQUIRED_FACTORS
    }
    authority = recorder.scoring_authority_view(feature_set.contributions)
    scoring = authority["scoring_factors"]

    provenance: dict[str, Any] = {}
    extras: dict[str, dict[str, str]] = {}
    for factor_id in recorder.REQUIRED_FACTORS:
        binding = bindings.get(factor_id)
        if binding is None:
            raise IntegrationError("FACTOR_SOURCE_BINDING_MISSING", factor_id)
        contribution = contributions.get(factor_id)
        if contribution is None:
            raise IntegrationError("INCOMPLETE_BATCH_MISSING_FACTOR", factor_id)
        provenance[factor_id], extras[factor_id] = provenance_for(
            factor_id, binding,
            contribution=contribution,
            participated=factor_id in scoring)

    batch = recorder.build_batch(
        feature_set=feature_set, context=context,
        evaluation_id=evaluation_id, attempt_id=attempt_id,
        evaluated_at_utc=evaluated_at_utc, created_at_utc=created_at_utc,
        provenance=provenance)

    bound = [
        replace(record, factor_inputs={**record.factor_inputs, **extras[record.factor_id]})
        for record in batch
    ]
    # Re-checked after enrichment so the delivered batch, not an intermediate
    # one, is what the weight-sum invariant was proven against.
    recorder._batch_coherence(
        [contract.validate(record) for record in bound], authority["weight_sum_used"])
    return bound


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
