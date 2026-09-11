"""F1P: the forward AH factor observation contract, offline reference implementation.

This is a data contract for factor observations captured *from now on*. It is
not a backfill of the frozen 148: F1 established that those cannot be rebuilt,
and nothing here changes that. It produces no weight, no direction and no
recommendation, and it is never imported by the production chain.

The whole point is that a factor observation is only usable if it can prove it
was knowable before the evaluation it fed. So every rule here fails closed: a
missing, naive, unparseable, equal or later evidence time is refused, and so is
a record whose declared identity does not match its own contents.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HashDomain,
    canonical_sha256,
)

CONTRACT_ID = "w2.forward_ah_factor_observation.v1"
SCHEMA_VERSION = CONTRACT_ID
SERIALIZER_VERSION = str(CURRENT_SERIALIZER_VERSION)
# No quant-specific HashDomain exists yet and adding one would edit a production
# module, so an existing offline-evidence domain is reused and the domain string
# is written into the preimage explicitly. A future quant domain would therefore
# be a visible identity change, not a silent one.
HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE

AH_MARKET = "ASIAN_HANDICAP"
ALLOWED_FACTOR_IDS = ("F3_REST_FITNESS", "F5_RECENT_AH_COVER", "F6_H2H", "F9_TRUE_XG")

PARTICIPATED = "PARTICIPATED"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
FACTOR_ADMISSION_FAILED = "FACTOR_ADMISSION_FAILED"
HISTORICAL_NO_FACTOR_VERDICT_IDENTITY = "HISTORICAL_NO_FACTOR_VERDICT_IDENTITY"
ALLOWED_FACTOR_STATUSES = (
    PARTICIPATED, INSUFFICIENT_DATA, SOURCE_UNAVAILABLE,
    FACTOR_ADMISSION_FAILED, HISTORICAL_NO_FACTOR_VERDICT_IDENTITY,
)
# A status that carries no number. None of these is a zero score and none of
# them is a neutral factor; they are absences, and the contract keeps them so.
SCORELESS_STATUSES = frozenset({
    INSUFFICIENT_DATA, SOURCE_UNAVAILABLE, FACTOR_ADMISSION_FAILED,
    HISTORICAL_NO_FACTOR_VERDICT_IDENTITY,
})

AS_OF_FACTOR_OBSERVATION = "AS_OF_FACTOR_OBSERVATION"
POST_EVENT_ENRICHMENT = "POST_EVENT_ENRICHMENT"
# Anything decided by the result. None of it may reach an as-of observation.
POST_EVENT_FIELDS = frozenset({
    "score", "settlement", "profit_units", "result_available_at",
    "result_status", "home_goals", "away_goals", "graded", "payout",
})

_HEX64_DIGITS = frozenset("0123456789abcdef")


class ContractError(ValueError):
    """A refusal, carrying the machine-readable code that caused it."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


# --- time -----------------------------------------------------------------
def parse_aware_utc(value: object, *, field_name: str) -> datetime:
    """Parse to an aware UTC instant, or refuse.

    Naive is refused rather than assumed: a forward contract can insist on a
    zone, and a value whose zone we guessed cannot prove anything about
    ordering. Timestamps are never compared as text anywhere in this module.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ContractError("EVIDENCE_TIME_MISSING", field_name)
    if not isinstance(value, str):
        raise ContractError("TIMESTAMP_NOT_A_STRING", field_name)
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ContractError("TIMESTAMP_UNPARSEABLE", f"{field_name}={value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError("TIMESTAMP_NOT_TIMEZONE_AWARE", f"{field_name}={value}")
    return parsed.astimezone(UTC)


def check_pit(evidence_time_utc: object, evaluated_at_utc: object) -> tuple[datetime, datetime]:
    """evidence_time_utc must be strictly earlier than evaluated_at_utc.

    Equal fails: a fact that becomes available at the very instant of evaluation
    was not knowledge the evaluation could have used.
    """
    evidence = parse_aware_utc(evidence_time_utc, field_name="evidence_time_utc")
    evaluated = parse_aware_utc(evaluated_at_utc, field_name="evaluated_at_utc")
    if evidence == evaluated:
        raise ContractError("PIT_EVIDENCE_TIME_EQUALS_EVALUATED_AT", str(evidence))
    if evidence > evaluated:
        raise ContractError("PIT_EVIDENCE_TIME_AFTER_EVALUATED_AT", str(evidence))
    return evidence, evaluated


# --- hashes ---------------------------------------------------------------
def require_hex64(value: object, *, field_name: str) -> str:
    """Lowercase 64-hex, or refuse. Uppercase is refused, not normalised."""
    if not isinstance(value, str) or not value:
        raise ContractError("HASH_MISSING", field_name)
    if len(value) != 64:
        raise ContractError("HASH_LENGTH_INVALID", f"{field_name}={len(value)}")
    if not set(value) <= _HEX64_DIGITS:
        raise ContractError("HASH_NOT_LOWERCASE_HEX", f"{field_name}={value}")
    return value


def _decimal_text(value: object, *, field_name: str) -> str:
    """Numbers enter the preimage as canonical decimal text, never as floats."""
    if isinstance(value, bool):
        raise ContractError("NUMBER_IS_BOOLEAN", field_name)
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ContractError("NUMBER_INVALID", f"{field_name}={value!r}") from exc


def factor_input_preimage(record: ForwardFactorObservation) -> dict[str, Any]:
    """Everything about the evidence that fed this factor.

    Deliberately excludes the verdict and the write time, and can never contain
    a result field: the input is what was true before the evaluation.
    """
    return {
        "contract": CONTRACT_ID,
        "hash_domain": str(HASH_DOMAIN),
        "serializer_version": SERIALIZER_VERSION,
        "evaluation_id": record.evaluation_id,
        "attempt_id": record.attempt_id,
        "fixture_id": record.fixture_id,
        "market": record.market,
        "factor_id": record.factor_id,
        "factor_version": record.factor_version,
        "applied_weight": _decimal_text(
            record.applied_weight, field_name="applied_weight"),
        "factor_inputs": record.factor_inputs,
        "evidence_time_utc": parse_aware_utc(
            record.evidence_time_utc, field_name="evidence_time_utc").isoformat(),
        "source_capture_id": record.source_capture_id,
        "source_capture_sha256": record.source_capture_sha256,
        "source_version": record.source_version,
    }


def factor_verdict_preimage(record: ForwardFactorObservation, input_hash: str) -> dict[str, Any]:
    return {
        "contract": CONTRACT_ID,
        "hash_domain": str(HASH_DOMAIN),
        "factor_input_hash": input_hash,
        "factor_status": record.factor_status,
        "participated": record.participated,
        "signed_score": (
            None if record.signed_score is None
            else _decimal_text(record.signed_score, field_name="signed_score")),
    }


def observation_preimage(
    record: ForwardFactorObservation, input_hash: str, verdict_hash: str
) -> dict[str, Any]:
    return {
        "contract": CONTRACT_ID,
        "hash_domain": str(HASH_DOMAIN),
        "factor_input_hash": input_hash,
        "factor_verdict_hash": verdict_hash,
        "evaluated_at_utc": parse_aware_utc(
            record.evaluated_at_utc, field_name="evaluated_at_utc").isoformat(),
        "supersedes_observation_id": record.supersedes_observation_id,
    }


def _hash(payload: dict[str, Any]) -> str:
    return canonical_sha256(payload, domain=HASH_DOMAIN)


def compute_identity(record: ForwardFactorObservation) -> tuple[str, str, str]:
    """(factor_input_hash, factor_verdict_hash, observation_id) for a record."""
    input_hash = _hash(factor_input_preimage(record))
    verdict_hash = _hash(factor_verdict_preimage(record, input_hash))
    observation_id = _hash(observation_preimage(record, input_hash, verdict_hash))
    return input_hash, verdict_hash, observation_id


# --- the record -----------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class ForwardFactorObservation:
    evaluation_id: str
    attempt_id: str
    fixture_id: str
    factor_id: str
    factor_version: str
    factor_status: str
    participated: bool
    applied_weight: object
    factor_inputs: dict[str, Any]
    evidence_time_utc: str
    evaluated_at_utc: str
    created_at_utc: str
    source_capture_id: str
    source_capture_sha256: str
    source_version: str
    signed_score: object | None = None
    market: str = AH_MARKET
    schema_version: str = SCHEMA_VERSION
    observation_id: str | None = None
    factor_input_hash: str | None = None
    factor_verdict_hash: str | None = None
    supersedes_observation_id: str | None = None
    revision_reason: str | None = None
    record_kind: str = AS_OF_FACTOR_OBSERVATION


# Changing any of these must change the identity. created_at_utc is absent on
# purpose: when a row was written says nothing about what was knowable.
PROTECTED_FIELDS = (
    "evaluation_id", "attempt_id", "fixture_id", "market", "factor_id",
    "factor_version", "factor_status", "participated", "applied_weight",
    "factor_inputs", "evidence_time_utc", "evaluated_at_utc",
    "source_capture_id", "source_capture_sha256", "source_version",
    "signed_score", "supersedes_observation_id",
)
BUSINESS_FIELDS = (*PROTECTED_FIELDS, "schema_version", "record_kind",
                   "revision_reason", "factor_input_hash", "factor_verdict_hash")


def validate(record: ForwardFactorObservation) -> ForwardFactorObservation:
    """Refuse anything that cannot prove itself, and return a sealed record."""
    if record.schema_version != SCHEMA_VERSION:
        raise ContractError("SCHEMA_VERSION_UNSUPPORTED", str(record.schema_version))
    if record.market != AH_MARKET:
        # TOTALS is not an AH factor failure; it is simply out of this contract.
        raise ContractError("MARKET_OUT_OF_CONTRACT", str(record.market))
    if record.factor_id not in ALLOWED_FACTOR_IDS:
        raise ContractError("FACTOR_ID_NOT_ALLOWED", str(record.factor_id))
    if record.factor_status not in ALLOWED_FACTOR_STATUSES:
        raise ContractError("FACTOR_STATUS_NOT_ALLOWED", str(record.factor_status))
    for name in ("evaluation_id", "attempt_id", "fixture_id", "factor_version",
                 "source_capture_id", "source_version"):
        if not str(getattr(record, name) or "").strip():
            raise ContractError("REQUIRED_FIELD_MISSING", name)
    require_hex64(record.source_capture_sha256, field_name="source_capture_sha256")

    # An absent weight is absent. Filling it from the current registry would
    # invent the very number F2 is meant to fit.
    if record.applied_weight is None:
        raise ContractError("APPLIED_WEIGHT_MISSING", record.factor_id)
    _decimal_text(record.applied_weight, field_name="applied_weight")

    if record.factor_status == PARTICIPATED:
        if not record.participated:
            raise ContractError("PARTICIPATED_FLAG_CONTRADICTS_STATUS", record.factor_id)
        if record.signed_score is None:
            raise ContractError("SIGNED_SCORE_MISSING_FOR_PARTICIPATED", record.factor_id)
        _decimal_text(record.signed_score, field_name="signed_score")
    else:
        if record.participated:
            raise ContractError("PARTICIPATED_FLAG_CONTRADICTS_STATUS", record.factor_id)
        # INSUFFICIENT_DATA is not a zero and SOURCE_UNAVAILABLE is not neutral.
        if record.signed_score is not None:
            raise ContractError("SCORELESS_STATUS_CARRIES_A_SCORE", record.factor_status)

    if not isinstance(record.factor_inputs, dict):
        raise ContractError("FACTOR_INPUTS_NOT_A_MAPPING", record.factor_id)
    leaked = sorted(POST_EVENT_FIELDS & set(record.factor_inputs))
    if leaked:
        raise ContractError("POST_EVENT_FIELD_IN_FACTOR_INPUT", ",".join(leaked))
    if record.record_kind != AS_OF_FACTOR_OBSERVATION:
        raise ContractError("RECORD_KIND_NOT_AS_OF", str(record.record_kind))

    check_pit(record.evidence_time_utc, record.evaluated_at_utc)
    parse_aware_utc(record.created_at_utc, field_name="created_at_utc")

    input_hash, verdict_hash, observation_id = compute_identity(record)
    for supplied, computed, name in (
        (record.factor_input_hash, input_hash, "factor_input_hash"),
        (record.factor_verdict_hash, verdict_hash, "factor_verdict_hash"),
        (record.observation_id, observation_id, "observation_id"),
    ):
        if supplied is None:
            continue
        require_hex64(supplied, field_name=name)
        if supplied != computed:
            raise ContractError("IDENTITY_MISMATCH", name)
    if record.supersedes_observation_id is not None:
        require_hex64(record.supersedes_observation_id,
                      field_name="supersedes_observation_id")
        if record.supersedes_observation_id == observation_id:
            raise ContractError("SUPERSEDES_CYCLE", observation_id)
    return replace(
        record, factor_input_hash=input_hash, factor_verdict_hash=verdict_hash,
        observation_id=observation_id)


def as_dict(record: ForwardFactorObservation) -> dict[str, Any]:
    """The stored form, canonicalised the same way the preimage is.

    Timestamps are stored as the parsed UTC instant, not as the text that
    happened to be supplied. Identity is decided on the instant, so storage has
    to be too -- otherwise the same moment written as +09:00 and as Z would
    share an observation_id while disagreeing on the field, and a legitimate
    idempotent rewrite would look like a conflict.
    """
    payload = asdict(record)
    payload["applied_weight"] = _decimal_text(
        record.applied_weight, field_name="applied_weight")
    payload["signed_score"] = (
        None if record.signed_score is None
        else _decimal_text(record.signed_score, field_name="signed_score"))
    for name in ("evidence_time_utc", "evaluated_at_utc", "created_at_utc"):
        payload[name] = parse_aware_utc(
            getattr(record, name), field_name=name).isoformat()
    return payload


# --- the append-only ledger ----------------------------------------------
@dataclass
class AppendResult:
    observation_id: str
    created: bool
    reason: str


class ForwardFactorLedger:
    """Append-only JSONL. Nothing already written is ever updated or removed."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def by_id(self) -> dict[str, dict[str, Any]]:
        return {str(row["observation_id"]): row for row in self.rows()}

    def append(self, record: ForwardFactorObservation) -> AppendResult:
        sealed = validate(record)
        payload = as_dict(sealed)
        existing = self.by_id()
        stored = existing.get(sealed.observation_id or "")
        if stored is not None:
            # Idempotent only if every business field agrees, field by field.
            differing = sorted(
                name for name in BUSINESS_FIELDS if stored.get(name) != payload.get(name)
            )
            if differing:
                raise ContractError(
                    "OBSERVATION_ID_BUSINESS_CONFLICT", ",".join(differing))
            return AppendResult(str(sealed.observation_id), False, "IDEMPOTENT_NO_OP")
        if sealed.supersedes_observation_id is not None:
            if sealed.supersedes_observation_id not in existing:
                raise ContractError(
                    "SUPERSEDES_TARGET_NOT_FOUND", sealed.supersedes_observation_id)
            self._assert_no_cycle(sealed, existing)
            if sealed.revision_reason is None:
                raise ContractError("REVISION_REASON_MISSING",
                                    sealed.supersedes_observation_id)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(
                payload, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")) + "\n")
        return AppendResult(str(sealed.observation_id), True, "APPENDED")

    def _assert_no_cycle(
        self, sealed: ForwardFactorObservation, existing: dict[str, dict[str, Any]]
    ) -> None:
        seen = {sealed.observation_id}
        cursor = sealed.supersedes_observation_id
        while cursor is not None:
            if cursor in seen:
                raise ContractError("SUPERSEDES_CYCLE", str(cursor))
            seen.add(cursor)
            cursor = (existing.get(cursor) or {}).get("supersedes_observation_id")

    def readback(self, observation_id: str) -> dict[str, Any]:
        """Re-read a row, recompute its identity and check it field by field."""
        stored = self.by_id().get(observation_id)
        if stored is None:
            raise ContractError("OBSERVATION_NOT_FOUND", observation_id)
        rebuilt = ForwardFactorObservation(**{
            name: stored[name] for name in stored
            if name in ForwardFactorObservation.__dataclass_fields__
        })
        sealed = validate(replace(
            rebuilt, observation_id=None, factor_input_hash=None,
            factor_verdict_hash=None))
        recomputed = as_dict(sealed)
        for name in BUSINESS_FIELDS:
            if stored.get(name) != recomputed.get(name):
                raise ContractError("READBACK_FIELD_MISMATCH", name)
        if stored["observation_id"] != sealed.observation_id:
            raise ContractError("READBACK_IDENTITY_MISMATCH", observation_id)
        return stored

    def as_of_view(self, observation_id: str) -> dict[str, Any]:
        """The as-of projection. A result field can never appear here."""
        row = self.readback(observation_id)
        view = {name: row[name] for name in row if name not in POST_EVENT_FIELDS}
        leaked = sorted(POST_EVENT_FIELDS & set(view.get("factor_inputs") or {}))
        if leaked:
            raise ContractError("POST_EVENT_FIELD_IN_AS_OF_VIEW", ",".join(leaked))
        view["record_kind"] = AS_OF_FACTOR_OBSERVATION
        return view


class PostEventEnrichmentLedger:
    """Results and settlement. Separate file, separate kind, one-way.

    Nothing here is ever consulted when an as-of observation is built, so
    enrichment cannot reach back into an identity that was already sealed.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, *, evaluation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(payload) - POST_EVENT_FIELDS)
        if unknown:
            raise ContractError("POST_EVENT_FIELD_NOT_ALLOWED", ",".join(unknown))
        row = {
            "schema_version": "w2.post_event_enrichment.v1",
            "record_kind": POST_EVENT_ENRICHMENT,
            "evaluation_id": evaluation_id,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(
                row, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")) + "\n")
        return row

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


# --- historical payloads --------------------------------------------------
def classify_historical_payload(payload: dict[str, Any]) -> str:
    """A payload written before the verdict existed is explicitly marked.

    It is never ADMITTED and never a factor pass; it is the absence of a
    verdict, which for an AH candidate must fail closed.
    """
    if not isinstance(payload, dict) or not any(
        key.startswith("factor_") and payload.get(key) for key in payload
    ):
        return HISTORICAL_NO_FACTOR_VERDICT_IDENTITY
    status = str(payload.get("factor_decision_status") or "").strip().upper()
    return status or HISTORICAL_NO_FACTOR_VERDICT_IDENTITY


def is_factor_admitted(status: str) -> bool:
    """Only a real participation is a pass. Everything absent fails closed."""
    return status == PARTICIPATED
