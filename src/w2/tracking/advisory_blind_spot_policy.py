from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import Any

POLICY_CHECKPOINT_KEY = "performance:policy:advisory-blind-spot"
POLICY_SCHEMA_VERSION = "w2.advisory_blind_spot_policy.v1"
BOOTSTRAP_ITERATIONS = 10_000
MIN_ADVISORY_SETTLED = 50
RECALIBRATION_SETTLED_STEP = 50
RECALIBRATION_MAX_AGE = timedelta(days=90)
BASE_ADVISORY_EV_THRESHOLD = 0.0


def build_advisory_blind_spot_policy(
    fixture_payloads: Mapping[str, Mapping[str, Any]],
    *,
    existing: Mapping[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    rows = list(fixture_payloads.values())
    strict = _clv_values(rows, "STRICT")
    advisory = _clv_values(rows, "ADVISORY")
    advisory_settled = sum(
        1
        for row in rows
        if row.get("evaluation_tier") == "ADVISORY"
        and row.get("canonical_settlement_outcome")
        in {"HIT", "MISS", "PUSH", "VOID"}
    )
    source_fixture_hash = _hash(
        {
            "fixtures": [
                {
                    "fixture_id": row.get("fixture_id"),
                    "tier": row.get("evaluation_tier"),
                    "canonical_outcome": row.get("canonical_settlement_outcome"),
                    "clv": row.get("clv_decimal"),
                    "status": row.get("status"),
                }
                for row in sorted(rows, key=lambda item: str(item.get("fixture_id") or ""))
            ]
        }
    )
    status = (
        "INSUFFICIENT_ADVISORY_CANONICAL_SAMPLE"
        if advisory_settled < MIN_ADVISORY_SETTLED
        else "INSUFFICIENT_CLV_SAMPLE"
        if not strict or not advisory
        else "READY"
    )
    strict_mean = fmean(strict) if strict else None
    advisory_mean = fmean(advisory) if advisory else None
    seed = int(source_fixture_hash[:16], 16)
    should_calibrate = status == "READY" and _recalibration_due(
        existing,
        advisory_settled=advisory_settled,
        now=now,
    )
    lower_bound: float | None
    applied_delta: float
    last_calibrated_at: str | None
    if should_calibrate:
        lower_bound = _independent_bootstrap_q10(strict, advisory, seed=seed)
        applied_delta = max(0.0, lower_bound)
        last_calibrated_at = _iso(now)
        last_calibrated_settled_count = advisory_settled
    elif validate_advisory_blind_spot_policy(existing):
        existing_payload = existing or {}
        lower_bound = _number(existing_payload.get("lower_bound_80"))
        applied_delta = _number(existing_payload.get("applied_delta")) or 0.0
        last_calibrated_at = (
            str(existing_payload["last_calibrated_at"])
            if existing_payload.get("last_calibrated_at")
            else None
        )
        last_calibrated_settled_count = int(
            existing_payload.get("last_calibrated_settled_count") or 0
        )
    else:
        lower_bound = None
        applied_delta = 0.0
        last_calibrated_at = None
        last_calibrated_settled_count = 0
    if status != "READY":
        applied_delta = 0.0
        lower_bound = None
        last_calibrated_at = None
        last_calibrated_settled_count = 0
    watch_only = bool(
        status == "READY"
        and advisory_mean is not None
        and advisory_mean - applied_delta <= 0
    )
    parsed_last_calibrated_at = _parse_time(last_calibrated_at)
    next_recalibration_at = (
        _iso(parsed_last_calibrated_at + RECALIBRATION_MAX_AGE)
        if parsed_last_calibrated_at is not None
        else None
    )
    payload = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "status": status,
        "window": "90d",
        "strict_clv_sample_count": len(strict),
        "advisory_clv_sample_count": len(advisory),
        "advisory_canonical_settled_count": advisory_settled,
        "strict_clv_mean": strict_mean,
        "advisory_clv_mean": advisory_mean,
        "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
        "bootstrap_seed": seed,
        "lower_bound_80": lower_bound,
        "applied_delta": applied_delta,
        "effective_threshold": BASE_ADVISORY_EV_THRESHOLD + applied_delta,
        "watch_only": watch_only,
        "last_calibrated_at": last_calibrated_at,
        "last_calibrated_settled_count": last_calibrated_settled_count,
        "next_recalibration_at": next_recalibration_at,
        "source_fixture_hash": source_fixture_hash,
    }
    return {**payload, "business_projection_hash": _hash(payload)}


def validate_advisory_blind_spot_policy(
    payload: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(payload, Mapping):
        return False
    required = {
        "schema_version",
        "status",
        "window",
        "applied_delta",
        "effective_threshold",
        "watch_only",
        "source_fixture_hash",
        "business_projection_hash",
    }
    return bool(
        required.issubset(payload)
        and payload.get("schema_version") == POLICY_SCHEMA_VERSION
        and payload.get("window") == "90d"
        and payload.get("status")
        in {
            "READY",
            "INSUFFICIENT_ADVISORY_CANONICAL_SAMPLE",
            "INSUFFICIENT_CLV_SAMPLE",
        }
        and _number(payload.get("applied_delta")) is not None
        and _number(payload.get("effective_threshold")) is not None
        and type(payload.get("watch_only")) is bool
    )


def _clv_values(
    rows: Sequence[Mapping[str, Any]],
    tier: str,
) -> list[float]:
    return [
        float(row["clv_decimal"])
        for row in rows
        if row.get("evaluation_tier") == tier
        and row.get("status") == "SCORED"
        and row.get("clv_status") == "AVAILABLE"
        and _number(row.get("clv_decimal")) is not None
    ]


def _recalibration_due(
    existing: Mapping[str, Any] | None,
    *,
    advisory_settled: int,
    now: datetime,
) -> bool:
    if not validate_advisory_blind_spot_policy(existing):
        return True
    existing_payload = existing or {}
    last_count = int(existing_payload.get("last_calibrated_settled_count") or 0)
    last_at = _parse_time(existing_payload.get("last_calibrated_at"))
    return (
        advisory_settled - last_count >= RECALIBRATION_SETTLED_STEP
        or last_at is None
        or now - last_at >= RECALIBRATION_MAX_AGE
    )


def _independent_bootstrap_q10(
    strict: Sequence[float],
    advisory: Sequence[float],
    *,
    seed: int,
) -> float:
    rng = random.Random(seed)  # noqa: S311 - deterministic evaluation bootstrap.
    differences = sorted(
        fmean(rng.choice(strict) for _ in strict)
        - fmean(rng.choice(advisory) for _ in advisory)
        for _ in range(BOOTSTRAP_ITERATIONS)
    )
    return differences[int((len(differences) - 1) * 0.10)]


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and abs(parsed) != float("inf") else None


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
