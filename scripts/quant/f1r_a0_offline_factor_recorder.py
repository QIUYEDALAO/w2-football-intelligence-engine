"""F1R-A0: record a complete four-factor AH observation batch, offline.

Freeze A0 scope. This turns the live `FeatureContribution` objects an evaluation
already produces into F1P forward observations. It reads objects, never a
network or a database, and the production chain does not import it.

Why this can carry what F1 could not: F1 was trying to rebuild history from
serialised analysis cards, which never carried a per-factor evidence time. The
contribution object does -- `observed_at` is set and UTC-validated on every
factor's ready branch -- and it carries the weight that actually entered the
aggregation. Recording at evaluation time therefore has what recording after
the fact never could.

A batch is all four factors or nothing. Validation runs over the whole batch
before a single line is written, so a partially recorded evaluation cannot exist.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

_CONTRACT_PATH = Path(__file__).resolve().parent / "f1p_forward_factor_contract.py"
_MODULE_NAME = "w2_f1p_forward_factor_contract"
if _MODULE_NAME in sys.modules:
    contract = sys.modules[_MODULE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_MODULE_NAME, _CONTRACT_PATH)
    assert _spec is not None and _spec.loader is not None
    contract = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE_NAME] = contract
    _spec.loader.exec_module(contract)

RECORDER_ID = "w2.f1r_a0_offline_factor_recorder.v1"
REQUIRED_FACTORS = contract.ALLOWED_FACTOR_IDS

# How a live FeatureStatus becomes a contract status. DEGRADED, NOT_WHITELISTED
# and LEAKAGE_BLOCKED are refusals the feature layer reached on purpose, so they
# map to the contract's refusal, not to "no data".
STATUS_MAP = {
    "READY": contract.PARTICIPATED,
    "INSUFFICIENT_DATA": contract.INSUFFICIENT_DATA,
    "UNAVAILABLE": contract.SOURCE_UNAVAILABLE,
    "DEGRADED": contract.FACTOR_ADMISSION_FAILED,
    "NOT_WHITELISTED": contract.FACTOR_ADMISSION_FAILED,
    "LEAKAGE_BLOCKED": contract.FACTOR_ADMISSION_FAILED,
}

# Two different facts, both real, and the batch records which one it used.
EVIDENCE_FROM_OBSERVATION = "LATEST_UNDERLYING_OBSERVATION"
EVIDENCE_FROM_LOOKUP = "SOURCE_QUERIED_AT_AS_OF"


class BatchError(contract.ContractError):
    """A batch-level refusal. Nothing is written when one is raised."""


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return contract.parse_aware_utc(
            value.isoformat(), field_name="timestamp").isoformat()
    return str(value)


def observation_from_contribution(
    contribution: Any,
    *,
    evaluation_id: str,
    attempt_id: str,
    fixture_id: str,
    evaluated_at_utc: str,
    created_at_utc: str,
    as_of_utc: str,
    factor_version: str,
    source_capture_id: str,
    source_capture_sha256: str,
    source_version: str,
) -> Any:
    """One contribution becomes one forward observation. Nothing is invented.

    An absent factor keeps its absence: no score is supplied, and its evidence
    time is the instant the source was queried, which is a real fact about when
    we looked and found nothing -- not a stand-in for data that never existed.
    """
    status_name = getattr(contribution.status, "value", str(contribution.status))
    mapped = STATUS_MAP.get(status_name)
    if mapped is None:
        raise BatchError("FEATURE_STATUS_UNMAPPED", status_name)
    participated = mapped == contract.PARTICIPATED
    if participated and contribution.score is None:
        raise BatchError("READY_CONTRIBUTION_WITHOUT_SCORE", contribution.feature_id)

    observed_at = _text(getattr(contribution, "observed_at", None))
    if observed_at is not None:
        evidence_time, semantics = observed_at, EVIDENCE_FROM_OBSERVATION
    elif participated:
        # A participating factor must say when its evidence was observed; the
        # look-up instant is not an acceptable substitute for a real score.
        raise BatchError(
            "PARTICIPATED_WITHOUT_OBSERVED_AT", contribution.feature_id)
    else:
        evidence_time, semantics = as_of_utc, EVIDENCE_FROM_LOOKUP

    inputs = {
        str(key): _text(value) for key, value in (contribution.inputs or {}).items()
    }
    leaked = sorted(contract.POST_EVENT_FIELDS & set(inputs))
    if leaked:
        raise BatchError("POST_EVENT_FIELD_IN_FACTOR_INPUT", ",".join(leaked))
    inputs.update({
        "evidence_time_semantics": semantics,
        "feature_status": status_name,
        "feature_reason": _text(getattr(contribution, "reason", None)),
        "collection_status": _text(getattr(contribution, "collection_status", None)),
        # A non-participating factor carries a declared weight that never
        # entered weight_sum_used. Recording the flag keeps the difference
        # visible instead of implying the weight was applied.
        "weight_entered_weight_sum_used": "true" if participated else "false",
        "recorder": RECORDER_ID,
    })
    return contract.ForwardFactorObservation(
        evaluation_id=evaluation_id,
        attempt_id=attempt_id,
        fixture_id=fixture_id,
        factor_id=contribution.feature_id,
        factor_version=factor_version,
        factor_status=mapped,
        participated=participated,
        applied_weight=contribution.weight,
        factor_inputs=inputs,
        evidence_time_utc=evidence_time,
        evaluated_at_utc=evaluated_at_utc,
        created_at_utc=created_at_utc,
        source_capture_id=source_capture_id,
        source_capture_sha256=source_capture_sha256,
        source_version=source_version,
        signed_score=contribution.score if participated else None,
    )


def build_batch(
    *,
    feature_set: Any,
    context: Any,
    evaluation_id: str,
    attempt_id: str,
    evaluated_at_utc: str,
    created_at_utc: str,
    factor_versions: dict[str, str],
    source_capture_id: str,
    source_capture_sha256: str,
    source_version: str,
    market: str = contract.AH_MARKET,
) -> list[Any]:
    """Exactly the four AH factors, in a fixed order, or a refusal."""
    if market != contract.AH_MARKET:
        raise BatchError("MARKET_OUT_OF_CONTRACT", market)
    fixture_id = str(feature_set.fixture_id)
    if str(context.fixture_id) != fixture_id:
        raise BatchError("FIXTURE_ID_MISMATCH",
                         f"{context.fixture_id}!={fixture_id}")
    as_of_utc = contract.parse_aware_utc(
        _text(context.as_of), field_name="as_of").isoformat()

    seen: dict[str, Any] = {}
    for contribution in feature_set.contributions:
        factor_id = contribution.feature_id
        if factor_id not in REQUIRED_FACTORS:
            continue
        if factor_id in seen:
            raise BatchError("DUPLICATE_FACTOR_ID", factor_id)
        seen[factor_id] = contribution
    missing = [factor_id for factor_id in REQUIRED_FACTORS if factor_id not in seen]
    if missing:
        raise BatchError("INCOMPLETE_BATCH_MISSING_FACTOR", ",".join(missing))

    batch = []
    for factor_id in REQUIRED_FACTORS:
        version = factor_versions.get(factor_id)
        if not version:
            raise BatchError("FACTOR_VERSION_MISSING", factor_id)
        batch.append(observation_from_contribution(
            seen[factor_id],
            evaluation_id=evaluation_id, attempt_id=attempt_id,
            fixture_id=fixture_id, evaluated_at_utc=evaluated_at_utc,
            created_at_utc=created_at_utc, as_of_utc=as_of_utc,
            factor_version=version, source_capture_id=source_capture_id,
            source_capture_sha256=source_capture_sha256,
            source_version=source_version))
    return batch


def _batch_coherence(sealed: list[Any]) -> None:
    """One evaluation, one attempt, one fixture, one evaluated_at, four factors."""
    for field_name in ("evaluation_id", "attempt_id", "fixture_id",
                       "evaluated_at_utc", "market"):
        values = {getattr(record, field_name) for record in sealed}
        if len(values) != 1:
            raise BatchError("BATCH_FIELD_NOT_UNIFORM",
                             f"{field_name}={sorted(map(str, values))}")
    factor_ids = [record.factor_id for record in sealed]
    if sorted(factor_ids) != sorted(REQUIRED_FACTORS):
        raise BatchError("BATCH_FACTOR_SET_INVALID", ",".join(sorted(factor_ids)))
    if len(set(factor_ids)) != len(factor_ids):
        raise BatchError("DUPLICATE_FACTOR_ID", ",".join(sorted(factor_ids)))


def append_batch(ledger: Any, batch: list[Any]) -> dict[str, Any]:
    """All four or none.

    Every record is validated and every conflict resolved before the file is
    opened, so a refusal leaves the ledger byte-identical rather than half
    written. F1P's own validate and identity rules do the work; this only
    guarantees the batch is atomic.
    """
    sealed = [contract.validate(record) for record in batch]
    _batch_coherence(sealed)

    existing = ledger.by_id()
    to_write: list[dict[str, Any]] = []
    idempotent = 0
    for record in sealed:
        payload = contract.as_dict(record)
        stored = existing.get(record.observation_id or "")
        if stored is not None:
            differing = sorted(
                name for name in contract.BUSINESS_FIELDS
                if stored.get(name) != payload.get(name))
            if differing:
                raise BatchError(
                    "OBSERVATION_ID_BUSINESS_CONFLICT", ",".join(differing))
            idempotent += 1
            continue
        if record.supersedes_observation_id is not None:
            if record.supersedes_observation_id not in existing:
                raise BatchError("SUPERSEDES_TARGET_NOT_FOUND",
                                 record.supersedes_observation_id)
            if record.revision_reason is None:
                raise BatchError("REVISION_REASON_MISSING",
                                 record.supersedes_observation_id)
            ledger._assert_no_cycle(record, existing)
        to_write.append(payload)

    if to_write:
        with ledger.path.open("a", encoding="utf-8") as handle:
            for payload in to_write:
                handle.write(json.dumps(
                    payload, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")) + "\n")
    return {
        "observation_ids": [record.observation_id for record in sealed],
        "appended": len(to_write),
        "idempotent_no_ops": idempotent,
        "batch_size": len(sealed),
    }


def revise(record: Any, *, supersedes: str, reason: str, **changes: Any) -> Any:
    """A correction is a new observation that points at the one it replaces."""
    return replace(
        record, observation_id=None, factor_input_hash=None,
        factor_verdict_hash=None, supersedes_observation_id=supersedes,
        revision_reason=reason, **changes)
