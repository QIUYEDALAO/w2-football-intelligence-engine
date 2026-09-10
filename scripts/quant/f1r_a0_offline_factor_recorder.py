"""F1R-A0: record a complete four-factor AH observation batch, offline.

Freeze A0 scope. Reads live `FeatureContribution` objects, writes F1P forward
observations. No network, no database, and the production chain does not import
it.

Three things this module refuses to do, each of which the first version got
wrong:

1. It will not treat a fixture kickoff as the time a *result* was observed.
   F5 reads settled AH outcomes and F6 reads historical goals; neither fact is
   knowable at kickoff. Those two factors may only participate when an explicit
   per-factor source-observed time is supplied, and a supplied time that merely
   echoes the kickoff is refused.
2. It will not call a contribution "participated" because its status is READY.
   Participation is whatever `w2.pricing.team_score` actually scored, and the
   applied weight is the weight that authority actually summed.
3. It will not append row by row. The whole ledger is rebuilt in a sibling
   temporary file, flushed and fsynced, and committed with one atomic replace,
   so a failure part way through leaves the original file untouched.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.pricing.team_score import independent_team_scores_from_contributions

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

RECORDER_ID = "w2.f1r_a0_offline_factor_recorder.v3"
# F1P freezes applied_weight as "the weight this evaluation actually applied".
# A factor the scoring authority excluded applied none of its declared weight,
# so it records a canonical zero and its builder-declared value is kept in an
# audit field instead. Anything else would make the batch's applied weights sum
# to something the authority never used.
NO_WEIGHT_APPLIED = Decimal(0)
REQUIRED_FACTORS = contract.ALLOWED_FACTOR_IDS

STATUS_MAP = {
    "READY": contract.PARTICIPATED,
    "INSUFFICIENT_DATA": contract.INSUFFICIENT_DATA,
    "UNAVAILABLE": contract.SOURCE_UNAVAILABLE,
    "DEGRADED": contract.FACTOR_ADMISSION_FAILED,
    "NOT_WHITELISTED": contract.FACTOR_ADMISSION_FAILED,
    "LEAKAGE_BLOCKED": contract.FACTOR_ADMISSION_FAILED,
}

# What each factor's evidence time is allowed to be.
#
# FIXTURE_EVENT_TIME  the fact is "a match kicked off at T", which is observable
#                     at T and needs no result. F3 reads only kickoff spacing.
# SOURCE_SNAPSHOT     the source itself carries when it was observed. F9 reads
#                     TeamXgSnapshot.observed_at, which is a real capture time.
# RESULT_DERIVED      the fact is a result or a settlement, which cannot be
#                     known at kickoff. F5 reads settled AH outcomes and F6
#                     reads historical goals, so both need an explicit
#                     source-observed time from the caller.
FIXTURE_EVENT_TIME = "FIXTURE_EVENT_TIME"
SOURCE_SNAPSHOT_OBSERVED_AT = "SOURCE_SNAPSHOT_OBSERVED_AT"
RESULT_DERIVED = "RESULT_DERIVED_REQUIRES_EXPLICIT_SOURCE_OBSERVED_TIME"
EVIDENCE_FROM_LOOKUP = "SOURCE_QUERIED_AT_AS_OF"

EVIDENCE_RULES = {
    "F3_REST_FITNESS": FIXTURE_EVENT_TIME,
    "F5_RECENT_AH_COVER": RESULT_DERIVED,
    "F6_H2H": RESULT_DERIVED,
    "F9_TRUE_XG": SOURCE_SNAPSHOT_OBSERVED_AT,
}
RESULT_DERIVED_FACTORS = frozenset(
    factor_id for factor_id, rule in EVIDENCE_RULES.items() if rule == RESULT_DERIVED)


class BatchError(contract.ContractError):
    """A batch-level refusal. Nothing is written when one is raised."""


@dataclass(frozen=True, kw_only=True)
class FactorProvenance:
    """Per-factor provenance the caller must supply. Nothing here is defaulted.

    `source_observed_at` is the instant the underlying source observed the fact.
    It is required for a result-derived factor and must not be the fixture
    kickoff; there is no default and the recorder will not infer one.
    """

    factor_version: str
    source_capture_id: str
    source_capture_sha256: str
    source_version: str
    source_observed_at: str | None = None


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return contract.parse_aware_utc(
            value.isoformat(), field_name="timestamp").isoformat()
    return str(value)


def scoring_authority_view(contributions: Any) -> dict[str, Any]:
    """What `team_score` actually scored, straight from that authority.

    The eligibility rules -- READY, scoring factor, independent signal,
    authoritative source group, non-zero weight -- live there and are not
    re-implemented here, so the two cannot drift apart.
    """
    scores = independent_team_scores_from_contributions(contributions)
    breakdown = {
        str(row["id"]): row for row in scores.get("scoring_factors") or []
    }
    return {
        "scoring_factors": breakdown,
        "weight_sum_used": float(scores.get("weight_sum_used") or 0.0),
    }


def observation_from_contribution(
    contribution: Any,
    provenance: FactorProvenance,
    *,
    scored: dict[str, Any] | None,
    evaluation_id: str,
    attempt_id: str,
    fixture_id: str,
    evaluated_at_utc: str,
    created_at_utc: str,
    as_of_utc: str,
) -> Any:
    """One contribution becomes one forward observation. Nothing is invented."""
    factor_id = contribution.feature_id
    rule = EVIDENCE_RULES.get(factor_id)
    if rule is None:
        raise BatchError("FACTOR_ID_NOT_ALLOWED", str(factor_id))
    status_name = getattr(contribution.status, "value", str(contribution.status))
    if status_name not in STATUS_MAP:
        raise BatchError("FEATURE_STATUS_UNMAPPED", status_name)

    # Participation is the scoring authority's verdict, never the raw status.
    participated = scored is not None
    if participated and status_name != "READY":
        raise BatchError("SCORED_FACTOR_IS_NOT_READY", factor_id)
    if participated:
        mapped = contract.PARTICIPATED
    elif status_name == "READY":
        # READY but excluded by the authority: a real refusal, not missing data.
        mapped = contract.FACTOR_ADMISSION_FAILED
    else:
        mapped = STATUS_MAP[status_name]

    if participated and contribution.score is None:
        raise BatchError("SCORED_CONTRIBUTION_WITHOUT_SCORE", factor_id)

    contribution_observed_at = _text(getattr(contribution, "observed_at", None))
    supplied = provenance.source_observed_at
    if not participated:
        evidence_time, semantics = as_of_utc, EVIDENCE_FROM_LOOKUP
    elif rule is RESULT_DERIVED:
        if not supplied:
            raise BatchError(
                "RESULT_DERIVED_FACTOR_WITHOUT_SOURCE_OBSERVED_TIME", factor_id)
        if contribution_observed_at is not None and (
            contract.parse_aware_utc(supplied, field_name="source_observed_at")
            == contract.parse_aware_utc(
                contribution_observed_at, field_name="observed_at")
        ):
            # observed_at on these rows is the fixture kickoff; a "source time"
            # equal to it is the kickoff wearing a different name.
            raise BatchError("SOURCE_OBSERVED_TIME_IS_KICKOFF_DERIVED", factor_id)
        evidence_time, semantics = supplied, rule
    else:
        if supplied:
            raise BatchError("SOURCE_OBSERVED_TIME_NOT_APPLICABLE", factor_id)
        if contribution_observed_at is None:
            raise BatchError("PARTICIPATED_WITHOUT_OBSERVED_AT", factor_id)
        evidence_time, semantics = contribution_observed_at, rule

    declared_weight = contribution.weight
    if participated:
        authority_weight = float(scored["weight"])
        if float(declared_weight) != authority_weight:
            raise BatchError(
                "APPLIED_WEIGHT_DISAGREES_WITH_SCORING_AUTHORITY",
                f"{factor_id}:{declared_weight}!={authority_weight}")
        applied_weight: Any = Decimal(str(scored["weight"]))
    else:
        applied_weight = NO_WEIGHT_APPLIED

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
        "is_independent_signal": str(
            bool(getattr(contribution, "is_independent_signal", False))).lower(),
        "source_group": _text(getattr(contribution, "source_group", None)),
        "weight_entered_weight_sum_used": "true" if participated else "false",
        # What the builder declared, kept for audit. It is not the applied
        # weight and must never be read as one.
        "declared_weight": _text(declared_weight),
        "scoring_authority_share": (
            _text(scored.get("share")) if participated else None),
        "recorder": RECORDER_ID,
    })
    return contract.ForwardFactorObservation(
        evaluation_id=evaluation_id,
        attempt_id=attempt_id,
        fixture_id=fixture_id,
        factor_id=factor_id,
        factor_version=provenance.factor_version,
        factor_status=mapped,
        participated=participated,
        applied_weight=applied_weight,
        factor_inputs=inputs,
        evidence_time_utc=evidence_time,
        evaluated_at_utc=evaluated_at_utc,
        created_at_utc=created_at_utc,
        source_capture_id=provenance.source_capture_id,
        source_capture_sha256=provenance.source_capture_sha256,
        source_version=provenance.source_version,
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
    provenance: dict[str, FactorProvenance],
    market: str = contract.AH_MARKET,
) -> list[Any]:
    """Exactly the four AH factors, in a fixed order, or a refusal."""
    if market != contract.AH_MARKET:
        raise BatchError("MARKET_OUT_OF_CONTRACT", market)
    fixture_id = str(feature_set.fixture_id)
    if str(context.fixture_id) != fixture_id:
        raise BatchError("FIXTURE_ID_MISMATCH", f"{context.fixture_id}!={fixture_id}")
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

    authority = scoring_authority_view(feature_set.contributions)
    batch = []

    for factor_id in REQUIRED_FACTORS:
        factor_provenance = provenance.get(factor_id)
        if factor_provenance is None:
            raise BatchError("FACTOR_PROVENANCE_MISSING", factor_id)
        if not factor_provenance.factor_version:
            raise BatchError("FACTOR_VERSION_MISSING", factor_id)
        batch.append(observation_from_contribution(
            seen[factor_id], factor_provenance,
            scored=authority["scoring_factors"].get(factor_id),
            evaluation_id=evaluation_id, attempt_id=attempt_id,
            fixture_id=fixture_id, evaluated_at_utc=evaluated_at_utc,
            created_at_utc=created_at_utc, as_of_utc=as_of_utc))
    # Checked here as well as at append time, so a caller that never appends
    # still cannot build a batch whose weights disagree with the authority.
    _batch_coherence([contract.validate(record) for record in batch],
                     authority["weight_sum_used"])
    return batch


def _batch_coherence(sealed: list[Any], weight_sum_used: float | None = None) -> None:
    for field_name in ("evaluation_id", "attempt_id", "fixture_id",
                       "evaluated_at_utc", "market"):
        values = {getattr(record, field_name) for record in sealed}
        if len(values) != 1:
            raise BatchError("BATCH_FIELD_NOT_UNIFORM",
                             f"{field_name}={sorted(map(str, values))}")
    factor_ids = [record.factor_id for record in sealed]
    if sorted(factor_ids) != sorted(REQUIRED_FACTORS):
        raise BatchError("BATCH_FACTOR_SET_INVALID", ",".join(sorted(factor_ids)))
    for record in sealed:
        if record.participated:
            continue
        if Decimal(str(record.applied_weight)) != NO_WEIGHT_APPLIED:
            raise BatchError("NON_PARTICIPATING_FACTOR_CARRIES_APPLIED_WEIGHT",
                             f"{record.factor_id}={record.applied_weight}")
        if record.signed_score is not None:
            raise BatchError("NON_PARTICIPATING_FACTOR_CARRIES_SCORE",
                             record.factor_id)
    if weight_sum_used is None:
        return
    # The mechanical invariant: what the batch says was applied is exactly what
    # the scoring authority summed.
    total = sum((Decimal(str(record.applied_weight)) for record in sealed),
                Decimal(0))
    if total != Decimal(str(weight_sum_used)):
        raise BatchError("BATCH_APPLIED_WEIGHT_SUM_DISAGREES_WITH_AUTHORITY",
                         f"{total}!={weight_sum_used}")


def _atomic_replace(path: Path, lines: list[str]) -> None:
    """Rebuild the ledger in a sibling temp file and commit with one replace.

    The commit point is `os.replace`. Everything before it -- serialising,
    writing, flushing, fsyncing -- happens on a file the readers never see, so
    an exception at any earlier point leaves the original ledger exactly as it
    was. `os.replace` is atomic within a filesystem, which is why the temp file
    is created in the same directory rather than in the system temp dir.
    """
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory,
        prefix=f".{path.name}.", suffix=".tmp", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            for line in lines:
                handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)          # <- commit point
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def append_batch(ledger: Any, batch: list[Any]) -> dict[str, Any]:
    """All four or none.

    Validation, conflict resolution and serialisation all complete before the
    commit point, and the commit itself is a single atomic replace, so neither a
    refusal nor an I/O failure part way through can leave a partial batch.
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
        # Append-only is preserved by rewriting the prior rows verbatim ahead of
        # the new ones; the existing bytes are re-emitted, never edited.
        previous = (
            ledger.path.read_text(encoding="utf-8") if ledger.path.exists() else "")
        lines = [previous] if previous else []
        lines.extend(
            json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n"
            for payload in to_write)
        _atomic_replace(ledger.path, lines)
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
