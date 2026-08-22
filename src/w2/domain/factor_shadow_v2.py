from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256

FACTOR_SHADOW_V2_CONTRACT_VERSION = "w2.factor_shadow_v2.v1"


class FactorShadowSourceMode(StrEnum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    FORWARD_SHADOW = "FORWARD_SHADOW"


def factor_shadow_forecast_contract(
    *,
    fixture_id: str,
    model_family: str,
    model_version: str,
    feature_registry_version: str,
    calibration_version: str,
    pit_input_identity_hash: str,
    captured_at: datetime,
    feature_as_of: datetime,
    computed_at: datetime | None = None,
    source_mode: FactorShadowSourceMode | str,
    production_capture_identity_hash: str | None = None,
    production_captured_at: datetime | None = None,
) -> dict[str, Any]:
    mode = FactorShadowSourceMode(str(source_mode))
    _require_aware(captured_at, "captured_at")
    _require_aware(feature_as_of, "feature_as_of")
    resolved_computed_at = computed_at or captured_at
    _require_aware(resolved_computed_at, "computed_at")
    if mode is FactorShadowSourceMode.FORWARD_SHADOW:
        if feature_as_of != captured_at:
            raise ValueError("FACTOR_SHADOW_FORWARD_FEATURE_ASOF_MUST_EQUAL_CAPTURE")
        if resolved_computed_at < captured_at:
            raise ValueError("FACTOR_SHADOW_COMPUTED_BEFORE_CAPTURE")
        if not production_capture_identity_hash or production_captured_at != captured_at:
            raise ValueError("FACTOR_SHADOW_FORWARD_CAPTURE_PAIR_REQUIRED")
    elif production_capture_identity_hash is not None or production_captured_at is not None:
        raise ValueError("FACTOR_SHADOW_HISTORY_PRODUCTION_CAPTURE_FORBIDDEN")
    elif feature_as_of > captured_at or resolved_computed_at < feature_as_of:
        raise ValueError("FACTOR_SHADOW_HISTORY_TIME_INVALID")

    identity = {
        "fixture_id": str(fixture_id),
        "model_family": str(model_family),
        "model_version": str(model_version),
        "feature_registry_version": str(feature_registry_version),
        "calibration_version": str(calibration_version),
        "pit_input_identity_hash": str(pit_input_identity_hash),
        "captured_at": captured_at,
        "source_mode": mode.value,
    }
    return {
        **identity,
        "schema_version": FACTOR_SHADOW_V2_CONTRACT_VERSION,
        "feature_as_of": feature_as_of,
        "computed_at": resolved_computed_at,
        "production_capture_identity_hash": production_capture_identity_hash,
        "probability_method": "EXACT_MATRIX",
        "sampling_used": False,
        "forecast_identity_hash": _identity_hash("FORECAST", identity),
    }


def factor_shadow_market_opportunity_identity(
    *,
    forecast_identity_hash: str,
    evaluation_policy_version: str,
    evaluation_slot_id: str,
    market: str,
) -> str:
    return _identity_hash(
        "MARKET_OPPORTUNITY",
        {
            "forecast_identity_hash": str(forecast_identity_hash),
            "evaluation_policy_version": str(evaluation_policy_version),
            "evaluation_slot_id": str(evaluation_slot_id),
            "market": str(market),
        },
    )


def factor_shadow_market_attempt_identity(
    *,
    opportunity_identity_hash: str,
    quote_identity_hash: str,
    source_event_identity: str,
) -> str:
    return _identity_hash(
        "MARKET_ATTEMPT",
        {
            "opportunity_identity_hash": str(opportunity_identity_hash),
            "quote_identity_hash": str(quote_identity_hash),
            "source_event_identity": str(source_event_identity),
        },
    )


def factor_shadow_forecast_outcome_identity(
    *,
    forecast_identity_hash: str,
    authoritative_result_identity: str,
) -> str:
    return _identity_hash(
        "FORECAST_OUTCOME",
        {
            "forecast_identity_hash": str(forecast_identity_hash),
            "authoritative_result_identity": str(authoritative_result_identity),
        },
    )


def _identity_hash(identity_type: str, identity: dict[str, Any]) -> str:
    return canonical_sha256(
        {"identity_type": identity_type, **identity},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"FACTOR_SHADOW_{field.upper()}_NAIVE")
