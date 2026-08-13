from __future__ import annotations

import hmac
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HashDomain,
    SerializerVersion,
    canonical_sha256,
)
from w2.domain.five_state_pricing import (
    MIN_CASHFLOW_PRICE_EDGE,
    SettlementDistribution,
    cashflow_price_edge,
    expected_value,
    fair_decimal_odds,
)

RECOMMENDATION_SCHEMA_VERSION = "w2.recommendation_decision.v4"
CANDIDATE_QUOTE_FRESHNESS_POLICY_VERSION = "w2.quote_freshness.v1"
CANDIDATE_QUOTE_MAX_AGE_SECONDS = 1800
FIXTURE_IDENTITY_VERSION_PREFIX = "w2.fixture_identity.v1:"
FIVE_STATE_OUTCOMES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
FORMAL_ADMISSION_STATUSES = {"DISABLED", "NOT_APPLICABLE", "NOT_READY", "PASSED"}

IDENTITY_REQUIRED_FIELDS = (
    "fixture_id",
    "competition_id",
    "season",
    "kickoff_utc",
    "kickoff_revision_or_fixture_identity_hash",
    "provider",
    "bookmaker_id",
    "market",
    "selection",
    "exact_line",
    "capture_id",
    "captured_at",
    "decision_evaluated_at",
    "quote_observation_ids",
    "raw_payload_sha256",
    "source_revision",
    "model_version",
    "calibration_version",
    "serializer_version",
    "recommendation_schema_version",
    "quote_schema_version",
    "model_input_manifest_hash",
)

_REQUIRED_INPUT_FIELDS = (
    *IDENTITY_REQUIRED_FIELDS,
    "decimal_odds",
    "canonical_mainline_identity",
    "settlement_distribution",
    "fair_odds",
    "expected_value",
    "uncertainty",
    "readiness",
    "capability_status",
    "formal_admission",
)
_OPTIONAL_DIAGNOSTIC_FIELDS = (
    "model_probability",
    "market_probability",
    "probability_delta_diagnostic",
)


class RecommendationOutcomeV4(StrEnum):
    NOT_READY = "NOT_READY"
    NO_EDGE = "NO_EDGE"
    ANALYSIS_PICK = "ANALYSIS_PICK"
    FORMAL_RECOMMEND = "FORMAL_RECOMMEND"


def candidate_quote_freshness_readiness(age_seconds: object) -> dict[str, Any]:
    age = _decimal(age_seconds)
    return {
        "quote_freshness_status": (
            "COMPLETE"
            if age is not None
            and Decimal("0") <= age <= Decimal(CANDIDATE_QUOTE_MAX_AGE_SECONDS)
            else "STALE"
            if age is not None and age > Decimal(CANDIDATE_QUOTE_MAX_AGE_SECONDS)
            else "INCOMPLETE"
        ),
        "quote_freshness_policy_version": CANDIDATE_QUOTE_FRESHNESS_POLICY_VERSION,
        "quote_age_seconds": age_seconds,
        "quote_max_age_seconds": CANDIDATE_QUOTE_MAX_AGE_SECONDS,
    }


@dataclass(frozen=True, kw_only=True)
class AuthoritativeRecommendationInput:
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass(frozen=True, kw_only=True)
class RecommendationDecisionV4:
    outcome: RecommendationOutcomeV4
    reason_code: str
    reason_message: str
    authoritative_input: AuthoritativeRecommendationInput
    selected_candidate: dict[str, Any] | None
    blockers: tuple[str, ...]
    decision_hash: str

    def as_dict(self) -> dict[str, Any]:
        authoritative = self.authoritative_input.as_dict()
        return {
            "schema_version": RECOMMENDATION_SCHEMA_VERSION,
            "fixture_id": authoritative.get("fixture_id"),
            "competition_id": authoritative.get("competition_id"),
            "season": authoritative.get("season"),
            "kickoff_utc": authoritative.get("kickoff_utc"),
            "outcome": self.outcome.value,
            "reason": {"code": self.reason_code, "message": self.reason_message},
            "authoritative_input": authoritative,
            "selected_candidate": self.selected_candidate,
            "blockers": list(self.blockers),
            "decision_hash": self.decision_hash,
        }


def authoritative_input_from_market_candidate(
    candidate: Mapping[str, Any],
    *,
    fixture_identity: Mapping[str, Any],
    kickoff_utc: object,
    capability_status: str,
    formal_admission: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    quote_identity = _mapping(candidate.get("quote_identity"))
    executable = _mapping(_mapping(candidate.get("quotes")).get("executable"))
    evidence = _mapping(candidate.get("analysis_evidence"))
    model = _mapping(evidence.get("model_probability"))
    comparison = _mapping(evidence.get("comparison"))
    market_probabilities = _mapping(_mapping(evidence.get("market_probability")).get("devig"))
    mainline = {
        "market": candidate.get("market"),
        **dict(_mapping(candidate.get("market_mainline"))),
        "line": _mapping(candidate.get("market_mainline")).get("line")
        or quote_identity.get("selected_line"),
        "selected_side_line": candidate.get("line"),
        "candidate_role": candidate.get("candidate_role"),
        "quote_identity_hash": quote_identity.get("quote_identity_hash"),
    }
    return {
        "fixture_id": fixture_identity.get("fixture_id") or candidate.get("fixture_id"),
        "competition_id": fixture_identity.get("competition_id"),
        "season": fixture_identity.get("season"),
        "kickoff_utc": fixture_identity.get("kickoff_utc") or kickoff_utc,
        "kickoff_revision_or_fixture_identity_hash": fixture_identity.get("identity_hash"),
        "provider": executable.get("provider") or quote_identity.get("provider"),
        "bookmaker_id": executable.get("bookmaker_id") or quote_identity.get("bookmaker_id"),
        "market": candidate.get("market"),
        "selection": candidate.get("selection"),
        "exact_line": executable.get("line") or candidate.get("line"),
        "capture_id": executable.get("capture_id") or quote_identity.get("capture_id"),
        "captured_at": executable.get("captured_at") or quote_identity.get("captured_at"),
        "decision_evaluated_at": quote_identity.get("evaluated_at") or "",
        "quote_observation_ids": quote_identity.get("observation_ids"),
        "raw_payload_sha256": quote_identity.get("raw_payload_sha256"),
        "source_revision": quote_identity.get("source_revision"),
        "model_version": model.get("model_version"),
        "calibration_version": model.get("calibration_version"),
        "serializer_version": CURRENT_SERIALIZER_VERSION.value,
        "recommendation_schema_version": RECOMMENDATION_SCHEMA_VERSION,
        "quote_schema_version": quote_identity.get("schema_version"),
        "model_input_manifest_hash": model.get("model_input_hash"),
        "decimal_odds": executable.get("decimal_odds"),
        "canonical_mainline_identity": mainline,
        "settlement_distribution": model.get("settlement_distribution"),
        "fair_odds": model.get("fair_decimal_odds"),
        "expected_value": model.get("expected_value"),
        "uncertainty": model.get("ev_se"),
        "readiness": {
            "status": "READY"
            if candidate.get("quote_status") == "COMPLETE"
            and candidate.get("quote_usage") == "EXECUTABLE"
            and model.get("status") == "READY"
            and evidence.get("status") == "COMPLETE"
            else "NOT_READY",
            "quote_identity_status": quote_identity.get("identity_status"),
            "quote_freshness_status": quote_identity.get("freshness_status"),
            "quote_freshness_policy_version": quote_identity.get(
                "freshness_schema_version"
            ),
            "quote_age_seconds": quote_identity.get("age_seconds"),
            "quote_max_age_seconds": quote_identity.get("max_age_seconds"),
            "model_status": model.get("status"),
        },
        "capability_status": capability_status,
        "formal_admission": dict(
            formal_admission
            or {
                "status": "NOT_APPLICABLE"
                if candidate.get("market") != "ASIAN_HANDICAP"
                else "DISABLED",
                "readiness_hash": None,
                "approval_hash": None,
                "candidate_identity_hash": None,
            }
        ),
        "model_probability": model.get("effective_probability"),
        "market_probability": market_probabilities.get(str(candidate.get("selection") or "")),
        "probability_delta_diagnostic": comparison.get("probability_delta"),
    }


def build_recommendation_decision_v4(
    authoritative_input: Mapping[str, Any],
) -> RecommendationDecisionV4:
    normalized, blockers = _normalize_input(authoritative_input)
    outcome, reason_code, reason_message = _outcome(normalized, blockers)
    selected_candidate = (
        _selected_candidate(normalized)
        if outcome
        in {
            RecommendationOutcomeV4.ANALYSIS_PICK,
            RecommendationOutcomeV4.FORMAL_RECOMMEND,
        }
        else None
    )
    preimage = _preimage(
        normalized=normalized,
        outcome=outcome.value,
        reason_code=reason_code,
        reason_message=reason_message,
        selected_candidate=selected_candidate,
        blockers=blockers,
    )
    return RecommendationDecisionV4(
        outcome=outcome,
        reason_code=reason_code,
        reason_message=reason_message,
        authoritative_input=AuthoritativeRecommendationInput(payload=normalized),
        selected_candidate=selected_candidate,
        blockers=tuple(blockers),
        decision_hash=canonical_sha256(
            preimage,
            domain=HashDomain.RECOMMENDATION_DECISION_V4,
            version=SerializerVersion.V2,
        ),
    )


def validate_decision_v4_identity(
    decision: RecommendationDecisionV4 | Mapping[str, Any],
) -> str:
    payload = (
        decision.as_dict() if isinstance(decision, RecommendationDecisionV4) else dict(decision)
    )
    if payload.get("schema_version") != RECOMMENDATION_SCHEMA_VERSION:
        raise ValueError("DECISION_V4_SCHEMA_CONFLICT")
    reason = payload.get("reason")
    reason_mapping = reason if isinstance(reason, Mapping) else {}
    authoritative = payload.get("authoritative_input")
    normalized = dict(authoritative) if isinstance(authoritative, Mapping) else {}
    selected = payload.get("selected_candidate")
    selected_candidate = dict(selected) if isinstance(selected, Mapping) else None
    raw_blockers = payload.get("blockers")
    blockers = (
        [str(item) for item in raw_blockers]
        if isinstance(raw_blockers, Sequence) and not isinstance(raw_blockers, str | bytes)
        else []
    )
    expected = canonical_sha256(
        _preimage(
            normalized=normalized,
            outcome=str(payload.get("outcome") or ""),
            reason_code=str(reason_mapping.get("code") or ""),
            reason_message=str(reason_mapping.get("message") or ""),
            selected_candidate=selected_candidate,
            blockers=blockers,
        ),
        domain=HashDomain.RECOMMENDATION_DECISION_V4,
        version=SerializerVersion.V2,
    )
    if not hmac.compare_digest(str(payload.get("decision_hash") or ""), expected):
        raise ValueError("DECISION_V4_IDENTITY_CONFLICT")
    return expected


def _normalize_input(value: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    payload = {field: value.get(field) for field in _REQUIRED_INPUT_FIELDS}
    payload.update({field: value.get(field) for field in _OPTIONAL_DIAGNOSTIC_FIELDS})
    blockers: list[str] = []
    raw_source_revision = value.get("source_revision")
    raw_kickoff_identity = value.get("kickoff_revision_or_fixture_identity_hash")
    for field in _REQUIRED_INPUT_FIELDS:
        raw = payload[field]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            blockers.append(f"MISSING_{field.upper()}")
    for field in (
        "fixture_id",
        "competition_id",
        "season",
        "kickoff_revision_or_fixture_identity_hash",
        "provider",
        "bookmaker_id",
        "market",
        "selection",
        "capture_id",
        "raw_payload_sha256",
        "source_revision",
        "model_version",
        "calibration_version",
        "serializer_version",
        "recommendation_schema_version",
        "quote_schema_version",
        "model_input_manifest_hash",
        "capability_status",
    ):
        if payload[field] is not None:
            payload[field] = str(payload[field]).strip()
    for field in ("kickoff_utc", "captured_at", "decision_evaluated_at"):
        normalized_time = _utc_text(payload[field])
        if normalized_time is None:
            blockers.append(f"INVALID_{field.upper()}")
        else:
            payload[field] = normalized_time
    kickoff = _utc_datetime(payload["kickoff_utc"])
    captured = _utc_datetime(payload["captured_at"])
    evaluated = _utc_datetime(payload["decision_evaluated_at"])
    if kickoff is not None and captured is not None and captured >= kickoff:
        blockers.append("QUOTE_CAPTURE_NOT_BEFORE_KICKOFF")
    if kickoff is not None and evaluated is not None and evaluated >= kickoff:
        blockers.append("DECISION_NOT_BEFORE_KICKOFF")
    if captured is not None and evaluated is not None and captured > evaluated:
        blockers.append("QUOTE_CAPTURE_AFTER_DECISION_EVALUATION")
    for field in ("exact_line", "decimal_odds", "fair_odds", "expected_value", "uncertainty"):
        number = _decimal(payload[field])
        if number is None:
            blockers.append(f"INVALID_{field.upper()}")
        else:
            payload[field] = _decimal_text(number)
    for field in _OPTIONAL_DIAGNOSTIC_FIELDS:
        if payload[field] is None:
            continue
        number = _decimal(payload[field])
        if number is None:
            blockers.append(f"INVALID_{field.upper()}")
        else:
            payload[field] = _decimal_text(number)
    decimal_odds = _decimal(payload["decimal_odds"])
    fair_odds = _decimal(payload["fair_odds"])
    uncertainty = _decimal(payload["uncertainty"])
    if decimal_odds is not None and decimal_odds <= 1:
        blockers.append("INVALID_DECIMAL_ODDS")
    if fair_odds is not None and fair_odds < 1:
        blockers.append("INVALID_FAIR_ODDS")
    if uncertainty is not None and uncertainty < 0:
        blockers.append("INVALID_UNCERTAINTY")
    for field in ("model_probability", "market_probability"):
        probability = _decimal(payload[field])
        if probability is not None and not Decimal("0") <= probability <= Decimal("1"):
            blockers.append(f"INVALID_{field.upper()}")
    payload["cashflow_price_edge"] = (
        _decimal_text(cashflow_price_edge(decimal_odds, fair_odds))
        if decimal_odds is not None
        and decimal_odds > 1
        and fair_odds is not None
        and fair_odds >= 1
        else None
    )
    payload["quote_observation_ids"] = _observation_ids(payload["quote_observation_ids"], blockers)
    payload["settlement_distribution"] = _distribution(payload["settlement_distribution"], blockers)
    _validate_pricing(payload, blockers)
    for field in ("canonical_mainline_identity", "readiness"):
        raw = payload[field]
        if not isinstance(raw, Mapping) or not raw:
            blockers.append(f"INVALID_{field.upper()}")
            payload[field] = {}
        else:
            payload[field] = dict(raw)
    mainline = dict(_mapping(payload["canonical_mainline_identity"]))
    for field in ("line", "selected_side_line"):
        normalized_line = _decimal(mainline.get(field))
        if normalized_line is None:
            blockers.append("CANONICAL_MAINLINE_IDENTITY_INCOMPLETE")
        else:
            mainline[field] = _decimal_text(normalized_line)
    payload["canonical_mainline_identity"] = mainline
    if (
        mainline.get("market") != payload.get("market")
        or mainline.get("line") is None
        or mainline.get("selected_side_line") != payload.get("exact_line")
        or mainline.get("candidate_role") != "MARKET_MAINLINE"
        or not _sha256(mainline.get("quote_identity_hash"))
    ):
        blockers.append("CANONICAL_MAINLINE_IDENTITY_INCOMPLETE")
    if not _sha256(mainline.get("quote_identity_hash")):
        blockers.append("INVALID_QUOTE_IDENTITY_HASH")
    readiness = _mapping(payload["readiness"])
    if readiness.get("quote_identity_status") != "COMPLETE":
        blockers.append("QUOTE_IDENTITY_NOT_READY")
    if readiness.get("quote_freshness_status") != "COMPLETE":
        blockers.append("QUOTE_FRESHNESS_NOT_READY")
    if (
        readiness.get("quote_freshness_policy_version")
        != CANDIDATE_QUOTE_FRESHNESS_POLICY_VERSION
    ):
        blockers.append("QUOTE_FRESHNESS_POLICY_NOT_REGISTERED")
    quote_age = _decimal(readiness.get("quote_age_seconds"))
    quote_max_age = _decimal(readiness.get("quote_max_age_seconds"))
    if (
        quote_age is None
        or quote_max_age != Decimal(CANDIDATE_QUOTE_MAX_AGE_SECONDS)
        or quote_age < 0
        or quote_age > quote_max_age
    ):
        blockers.append("QUOTE_FRESHNESS_BOUNDARY_INVALID")
    if readiness.get("model_status") != "READY":
        blockers.append("MODEL_EVIDENCE_NOT_READY")
    if payload["serializer_version"] != CURRENT_SERIALIZER_VERSION.value:
        blockers.append("UNSUPPORTED_SERIALIZER_VERSION")
    if payload["recommendation_schema_version"] != RECOMMENDATION_SCHEMA_VERSION:
        blockers.append("UNSUPPORTED_RECOMMENDATION_SCHEMA_VERSION")
    if payload["market"] not in {"ASIAN_HANDICAP", "TOTALS"}:
        blockers.append("UNSUPPORTED_MARKET")
    allowed_selections = (
        {"HOME", "AWAY"} if payload["market"] == "ASIAN_HANDICAP" else {"OVER", "UNDER"}
    )
    if payload["selection"] not in allowed_selections:
        blockers.append("INVALID_SELECTION")
    observation_ids = payload["quote_observation_ids"]
    expected_observation_sides = (
        {"home", "away"} if payload["market"] == "ASIAN_HANDICAP" else {"over", "under"}
    )
    if (
        not isinstance(observation_ids, Mapping)
        or set(observation_ids) != expected_observation_sides
    ):
        blockers.append("INVALID_QUOTE_OBSERVATION_IDS")
    if payload["capability_status"] not in {
        "ANALYSIS_ONLY",
        "FORMAL_DISABLED",
        "FORMAL_ENABLED",
    }:
        blockers.append("INVALID_CAPABILITY_STATUS")
    for field in ("raw_payload_sha256", "model_input_manifest_hash"):
        if not _sha256(payload[field]):
            blockers.append(f"INVALID_{field.upper()}")
    if not _sha40(raw_source_revision):
        blockers.append("INVALID_SOURCE_REVISION")
    if not _kickoff_identity(raw_kickoff_identity):
        blockers.append("INVALID_KICKOFF_REVISION_OR_FIXTURE_IDENTITY_HASH")
    payload["formal_admission"] = _formal_admission(payload, blockers)
    return payload, sorted(set(blockers))


def _outcome(
    payload: Mapping[str, Any], blockers: Sequence[str]
) -> tuple[RecommendationOutcomeV4, str, str]:
    if blockers:
        fixture_identity_blockers = {
            "MISSING_FIXTURE_ID",
            "MISSING_COMPETITION_ID",
            "MISSING_SEASON",
            "MISSING_KICKOFF_UTC",
            "MISSING_KICKOFF_REVISION_OR_FIXTURE_IDENTITY_HASH",
            "INVALID_KICKOFF_UTC",
            "INVALID_KICKOFF_REVISION_OR_FIXTURE_IDENTITY_HASH",
        }
        if fixture_identity_blockers.intersection(blockers):
            return RecommendationOutcomeV4.NOT_READY, "IDENTITY_NOT_READY", "比赛身份尚未完整"
        blocker_readiness = _mapping(payload.get("readiness"))
        if (
            blocker_readiness.get("model_status") != "READY"
            or "MODEL_EVIDENCE_NOT_READY" in blockers
        ):
            return RecommendationOutcomeV4.NOT_READY, "EVIDENCE_NOT_READY", "模型证据尚未就绪"
        if "QUOTE_IDENTITY_NOT_READY" in blockers:
            return RecommendationOutcomeV4.NOT_READY, "QUOTE_IDENTITY_NOT_READY", "盘口身份尚未完整"
        if "DECISION_NOT_BEFORE_KICKOFF" in blockers:
            return RecommendationOutcomeV4.NOT_READY, "FIXTURE_NOT_PREMATCH", "比赛已开始或结束"
        return RecommendationOutcomeV4.NOT_READY, "EVIDENCE_NOT_READY", "决策证据尚未就绪"
    readiness = payload.get("readiness")
    status = str(readiness.get("status") or "") if isinstance(readiness, Mapping) else ""
    if status not in {"READY", "COMPLETE"}:
        return RecommendationOutcomeV4.NOT_READY, "EVIDENCE_NOT_READY", "决策证据尚未就绪"
    expected_value = _decimal(payload.get("expected_value"))
    uncertainty = _decimal(payload.get("uncertainty"))
    cashflow_edge = _decimal(payload.get("cashflow_price_edge"))
    if (
        expected_value is None
        or uncertainty is None
        or cashflow_edge is None
        or expected_value <= 0
        or expected_value - uncertainty <= 0
        or cashflow_edge < MIN_CASHFLOW_PRICE_EDGE
    ):
        return RecommendationOutcomeV4.NO_EDGE, "CASHFLOW_EDGE_INSUFFICIENT", "五态现金流优势不足"
    formal_admission = _mapping(payload.get("formal_admission"))
    if formal_admission.get("status") == "PASSED":
        return RecommendationOutcomeV4.FORMAL_RECOMMEND, "FORMAL_ADMITTED", "正式推荐已通过能力门"
    return RecommendationOutcomeV4.ANALYSIS_PICK, "ANALYSIS_ONLY", "当前仅提供分析参考"


def _selected_candidate(payload: Mapping[str, Any]) -> dict[str, Any]:
    selected = {
        key: payload.get(key)
        for key in (
            "market",
            "selection",
            "exact_line",
            "decimal_odds",
            "provider",
            "bookmaker_id",
            "capture_id",
            "captured_at",
            "quote_observation_ids",
            "settlement_distribution",
            "fair_odds",
            "expected_value",
            "uncertainty",
            "cashflow_price_edge",
            "model_probability",
            "market_probability",
            "probability_delta_diagnostic",
        )
    }
    selected["line"] = selected["exact_line"]
    selected["odds"] = selected["decimal_odds"]
    return selected


def _preimage(
    *,
    normalized: Mapping[str, Any],
    outcome: str,
    reason_code: str,
    reason_message: str,
    selected_candidate: Mapping[str, Any] | None,
    blockers: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_version": RECOMMENDATION_SCHEMA_VERSION,
        "outcome": outcome,
        "reason": {"code": reason_code, "message": reason_message},
        "authoritative_input": dict(normalized),
        "selected_candidate": dict(selected_candidate) if selected_candidate else None,
        "blockers": list(blockers),
    }


def _observation_ids(value: Any, blockers: list[str]) -> dict[str, str] | list[str]:
    if isinstance(value, Mapping):
        mapped_ids = {str(key).strip(): str(item).strip() for key, item in value.items()}
        if (
            not mapped_ids
            or any(not key or not item for key, item in mapped_ids.items())
            or len(set(mapped_ids.values())) != len(mapped_ids)
        ):
            blockers.append("INVALID_QUOTE_OBSERVATION_IDS")
        return dict(sorted(mapped_ids.items()))
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        listed_ids = [str(item).strip() for item in value]
        if (
            not listed_ids
            or any(not item for item in listed_ids)
            or len(set(listed_ids)) != len(listed_ids)
        ):
            blockers.append("INVALID_QUOTE_OBSERVATION_IDS")
        return sorted(set(listed_ids))
    blockers.append("INVALID_QUOTE_OBSERVATION_IDS")
    return []


def _distribution(value: Any, blockers: list[str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(FIVE_STATE_OUTCOMES):
        blockers.append("INVALID_SETTLEMENT_DISTRIBUTION")
        return {}
    output: dict[str, str] = {}
    for outcome in FIVE_STATE_OUTCOMES:
        probability = _decimal(value.get(outcome))
        if probability is None or probability < 0:
            blockers.append("INVALID_SETTLEMENT_DISTRIBUTION")
            return {}
        output[outcome] = _decimal_text(probability)
    total = sum((_decimal(item) or Decimal("0") for item in output.values()), Decimal("0"))
    if abs(total - 1) > Decimal("0.000001"):
        blockers.append("INVALID_SETTLEMENT_DISTRIBUTION")
    return output


def _validate_pricing(payload: Mapping[str, Any], blockers: list[str]) -> None:
    distribution = payload.get("settlement_distribution")
    if not isinstance(distribution, Mapping) or set(distribution) != set(FIVE_STATE_OUTCOMES):
        return
    values = {outcome: _decimal(distribution[outcome]) for outcome in FIVE_STATE_OUTCOMES}
    if any(value is None for value in values.values()):
        return
    settlement = SettlementDistribution(
        full_win_probability=values["WIN"] or Decimal("0"),
        half_win_probability=values["HALF_WIN"] or Decimal("0"),
        push_probability=values["PUSH"] or Decimal("0"),
        half_loss_probability=values["HALF_LOSS"] or Decimal("0"),
        full_loss_probability=values["LOSS"] or Decimal("0"),
    )
    decimal_odds = _decimal(payload.get("decimal_odds"))
    declared_fair_odds = _decimal(payload.get("fair_odds"))
    declared_ev = _decimal(payload.get("expected_value"))
    if decimal_odds is None or declared_fair_odds is None or declared_ev is None:
        return
    try:
        recomputed_fair_odds = fair_decimal_odds(settlement)
    except ValueError:
        blockers.append("FAIR_ODDS_NOT_READY")
        return
    recomputed_ev = expected_value(decimal_odds, settlement)
    if abs(recomputed_fair_odds - declared_fair_odds) > Decimal("0.0001"):
        blockers.append("FAIR_ODDS_CONFLICT")
    if abs(recomputed_ev - declared_ev) > Decimal("0.00001"):
        blockers.append("EXPECTED_VALUE_CONFLICT")


def _utc_text(value: Any) -> str | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _utc_datetime(value: Any) -> datetime | None:
    text = _utc_text(value)
    return datetime.fromisoformat(text.replace("Z", "+00:00")) if text is not None else None


def _decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _sha40(value: Any) -> bool:
    text = value if isinstance(value, str) else ""
    return len(text) == 40 and all(character in "0123456789abcdef" for character in text)


def _kickoff_identity(value: Any) -> bool:
    text = value if isinstance(value, str) else ""
    if _sha256(text):
        return True
    if not text.startswith(FIXTURE_IDENTITY_VERSION_PREFIX):
        return False
    return _sha256(text.removeprefix(FIXTURE_IDENTITY_VERSION_PREFIX))


def valid_kickoff_identity(value: Any) -> bool:
    return _kickoff_identity(value)


def candidate_identity_hash(authoritative_input: Mapping[str, Any]) -> str:
    mainline = _mapping(authoritative_input.get("canonical_mainline_identity"))
    return canonical_sha256(
        {
            "market": str(authoritative_input.get("market") or "").strip(),
            "selection": str(authoritative_input.get("selection") or "").strip(),
            "exact_line": _normalized_decimal(authoritative_input.get("exact_line")),
            "decimal_odds": _normalized_decimal(authoritative_input.get("decimal_odds")),
            "provider": str(authoritative_input.get("provider") or "").strip(),
            "bookmaker_id": str(authoritative_input.get("bookmaker_id") or "").strip(),
            "capture_id": str(authoritative_input.get("capture_id") or "").strip(),
            "captured_at": _utc_text(authoritative_input.get("captured_at")),
            "quote_observation_ids": _canonical_observation_ids(
                authoritative_input.get("quote_observation_ids")
            ),
            "quote_identity_hash": str(mainline.get("quote_identity_hash") or ""),
        },
        domain=HashDomain.RECOMMENDATION_DECISION_V4,
        version=SerializerVersion.V2,
    )


def _formal_admission(payload: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    raw = payload.get("formal_admission")
    if not isinstance(raw, Mapping):
        blockers.append("INVALID_FORMAL_ADMISSION")
        return {}
    admission = {
        "status": raw.get("status"),
        "readiness_hash": raw.get("readiness_hash"),
        "approval_hash": raw.get("approval_hash"),
        "candidate_identity_hash": raw.get("candidate_identity_hash"),
    }
    status = admission["status"]
    if status not in FORMAL_ADMISSION_STATUSES:
        blockers.append("INVALID_FORMAL_ADMISSION_STATUS")
        return admission
    if status == "NOT_APPLICABLE" and payload.get("market") == "ASIAN_HANDICAP":
        blockers.append("FORMAL_ADMISSION_MARKET_CONFLICT")
    if status == "PASSED":
        if payload.get("market") != "ASIAN_HANDICAP":
            blockers.append("FORMAL_ADMISSION_MARKET_CONFLICT")
        if payload.get("capability_status") != "FORMAL_ENABLED":
            blockers.append("FORMAL_ADMISSION_CAPABILITY_CONFLICT")
        for field in ("readiness_hash", "approval_hash", "candidate_identity_hash"):
            if not _sha256(admission[field]):
                blockers.append(f"INVALID_FORMAL_ADMISSION_{field.upper()}")
        if admission["candidate_identity_hash"] != candidate_identity_hash(payload):
            blockers.append("FORMAL_CANDIDATE_IDENTITY_MISMATCH")
    return admission


def _normalized_decimal(value: Any) -> str | None:
    parsed = _decimal(value)
    return _decimal_text(parsed) if parsed is not None else None


def _canonical_observation_ids(value: Any) -> dict[str, str] | list[str]:
    if isinstance(value, Mapping):
        return dict(sorted((str(key).strip(), str(item).strip()) for key, item in value.items()))
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return sorted(str(item).strip() for item in value)
    return []


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
