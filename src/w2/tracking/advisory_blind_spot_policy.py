from __future__ import annotations

import hashlib
import json
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import Any

POLICY_CHECKPOINT_KEY = "performance:policy:advisory-blind-spot"
POLICY_SCHEMA_VERSION = "w2.advisory_blind_spot_policy.v1"
BOOTSTRAP_ITERATIONS = 10_000
MIN_ADVISORY_SETTLED = 50
RECALIBRATION_SETTLED_STEP = 50
RECALIBRATION_MAX_AGE = timedelta(days=90)
POLICY_WINDOW = timedelta(days=90)
BASE_ADVISORY_EV_THRESHOLD = 0.0
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, kw_only=True)
class AdvisoryBlindSpotPolicyCheckpoint:
    checkpoint_key: str
    source_hash: str
    created_at: datetime
    payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_key": self.checkpoint_key,
            "source_hash": self.source_hash,
            "created_at": _iso(self.created_at),
            "payload": dict(self.payload),
        }


def build_advisory_blind_spot_policy(
    fixture_payloads: Mapping[str, Mapping[str, Any]],
    *,
    existing: AdvisoryBlindSpotPolicyCheckpoint | Mapping[str, Any] | None,
    now: datetime,
    scoring_window_anchor: datetime | None = None,
) -> dict[str, Any]:
    timed_rows = [
        (kickoff, row)
        for row in fixture_payloads.values()
        if (kickoff := _parse_time(row.get("kickoff_utc"))) is not None
    ]
    anchor = _utc(scoring_window_anchor) or max(
        (kickoff for kickoff, _ in timed_rows),
        default=None,
    )
    window_start = anchor - POLICY_WINDOW if anchor is not None else None
    rows = (
        [
            row
            for kickoff, row in timed_rows
            if window_start is not None and window_start <= kickoff <= anchor
        ]
        if anchor is not None
        else []
    )
    strict = _clv_values(rows, "STRICT")
    advisory = _clv_values(rows, "ADVISORY")
    advisory_settled = sum(
        1
        for row in rows
        if row.get("evaluation_tier") == "ADVISORY"
        and row.get("canonical_settlement_outcome") in {"HIT", "MISS", "PUSH", "VOID"}
    )
    source_fixture_hash = _hash(
        {
            "fixtures": [
                {
                    "fixture_id": row.get("fixture_id"),
                    "kickoff_utc": _iso(_parse_time(row.get("kickoff_utc"))),
                    "tier": row.get("evaluation_tier"),
                    "canonical_outcome": row.get("canonical_settlement_outcome"),
                    "clv": row.get("clv_decimal"),
                    "status": row.get("status"),
                }
                for row in sorted(
                    rows,
                    key=lambda item: (
                        _iso(_parse_time(item.get("kickoff_utc"))) or "",
                        str(item.get("fixture_id") or ""),
                    ),
                )
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
    existing_payload = _validated_payload(existing)
    should_calibrate = status == "READY" and _recalibration_due(
        existing_payload,
        advisory_settled=advisory_settled,
        now=now,
    )
    lower_bound: float | None
    applied_delta: float
    last_calibrated_at: str | None
    last_calibrated_settled_count: int
    if should_calibrate:
        lower_bound = _independent_bootstrap_q10(strict, advisory, seed=seed)
        applied_delta = max(0.0, lower_bound)
        last_calibrated_at = _iso(now)
        last_calibrated_settled_count = advisory_settled
    elif existing_payload is not None:
        lower_bound = _number(existing_payload.get("lower_bound_80"))
        applied_delta = _number(existing_payload.get("applied_delta")) or 0.0
        last_calibrated_at = _optional_text(existing_payload.get("last_calibrated_at"))
        last_calibrated_settled_count = int(
            existing_payload.get("last_calibrated_settled_count") or 0
        )
    else:
        lower_bound = None
        applied_delta = 0.0
        last_calibrated_at = None
        last_calibrated_settled_count = 0
    if status != "READY":
        lower_bound = None
        applied_delta = 0.0
        last_calibrated_at = None
        last_calibrated_settled_count = 0
    watch_only = bool(
        status == "READY" and advisory_mean is not None and advisory_mean - applied_delta <= 0
    )
    calibrated_at = _parse_time(last_calibrated_at)
    payload = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "status": status,
        "window": "90d",
        "scoring_window_anchor": _iso(anchor),
        "window_start": _iso(window_start),
        "window_end": _iso(anchor),
        "window_fixture_count": len(rows),
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
        "next_recalibration_at": (
            _iso(calibrated_at + RECALIBRATION_MAX_AGE) if calibrated_at is not None else None
        ),
        "source_fixture_hash": source_fixture_hash,
    }
    return {**payload, "business_projection_hash": _hash(payload)}


def validate_advisory_blind_spot_policy(
    value: AdvisoryBlindSpotPolicyCheckpoint | Mapping[str, Any] | None,
) -> bool:
    checkpoint = _checkpoint(value)
    if checkpoint is None or checkpoint.checkpoint_key != POLICY_CHECKPOINT_KEY:
        return False
    payload = checkpoint.payload
    required = {
        "schema_version",
        "status",
        "window",
        "scoring_window_anchor",
        "window_start",
        "window_end",
        "window_fixture_count",
        "strict_clv_sample_count",
        "advisory_clv_sample_count",
        "advisory_canonical_settled_count",
        "bootstrap_iterations",
        "bootstrap_seed",
        "lower_bound_80",
        "applied_delta",
        "effective_threshold",
        "watch_only",
        "last_calibrated_at",
        "last_calibrated_settled_count",
        "source_fixture_hash",
        "business_projection_hash",
    }
    if not required.issubset(payload):
        return False
    business_hash = str(payload.get("business_projection_hash") or "")
    fixture_hash = str(payload.get("source_fixture_hash") or "")
    if (
        payload.get("schema_version") != POLICY_SCHEMA_VERSION
        or payload.get("window") != "90d"
        or checkpoint.source_hash != business_hash
        or _hash({key: item for key, item in payload.items() if key != "business_projection_hash"})
        != business_hash
        or _SHA256.fullmatch(business_hash) is None
        or _SHA256.fullmatch(fixture_hash) is None
        or payload.get("bootstrap_iterations") != BOOTSTRAP_ITERATIONS
        or not isinstance(payload.get("bootstrap_seed"), int)
        or isinstance(payload.get("bootstrap_seed"), bool)
        or int(payload["bootstrap_seed"]) < 0
        or type(payload.get("watch_only")) is not bool
    ):
        return False
    anchor = _parse_time(payload.get("scoring_window_anchor"))
    start = _parse_time(payload.get("window_start"))
    end = _parse_time(payload.get("window_end"))
    created_at = _utc(checkpoint.created_at)
    if (
        anchor is None
        or start is None
        or end != anchor
        or start != anchor - POLICY_WINDOW
        or created_at is None
    ):
        return False
    counts = [
        _nonnegative_int(payload.get(key))
        for key in (
            "window_fixture_count",
            "strict_clv_sample_count",
            "advisory_clv_sample_count",
            "advisory_canonical_settled_count",
            "last_calibrated_settled_count",
        )
    ]
    if any(item is None for item in counts):
        return False
    window_count, strict_count, advisory_count, settled_count, calibrated_count = (
        int(item) for item in counts if item is not None
    )
    delta = _number(payload.get("applied_delta"))
    threshold = _number(payload.get("effective_threshold"))
    lower_bound = _number(payload.get("lower_bound_80"))
    if (
        delta is None
        or delta < 0
        or threshold is None
        or abs(threshold - (BASE_ADVISORY_EV_THRESHOLD + delta)) > 1e-12
        or strict_count > window_count
        or advisory_count > window_count
        or settled_count > window_count
    ):
        return False
    status = payload.get("status")
    last_at = _parse_time(payload.get("last_calibrated_at"))
    if status == "INSUFFICIENT_ADVISORY_CANONICAL_SAMPLE":
        return (
            settled_count < MIN_ADVISORY_SETTLED
            and delta == 0
            and lower_bound is None
            and payload.get("watch_only") is False
            and last_at is None
            and calibrated_count == 0
        )
    if status == "INSUFFICIENT_CLV_SAMPLE":
        return (
            settled_count >= MIN_ADVISORY_SETTLED
            and (strict_count == 0 or advisory_count == 0)
            and delta == 0
            and lower_bound is None
            and payload.get("watch_only") is False
            and last_at is None
            and calibrated_count == 0
        )
    if status != "READY":
        return False
    return bool(
        strict_count > 0
        and advisory_count > 0
        and last_at is not None
        and last_at <= created_at
        and calibrated_count <= settled_count
        and lower_bound is not None
        and abs(delta - max(0.0, lower_bound)) <= 1e-12
    )


def _checkpoint(
    value: AdvisoryBlindSpotPolicyCheckpoint | Mapping[str, Any] | None,
) -> AdvisoryBlindSpotPolicyCheckpoint | None:
    if isinstance(value, AdvisoryBlindSpotPolicyCheckpoint):
        return value
    if not isinstance(value, Mapping) or not isinstance(value.get("payload"), Mapping):
        return None
    created_at = _parse_time(value.get("created_at"))
    if created_at is None:
        return None
    return AdvisoryBlindSpotPolicyCheckpoint(
        checkpoint_key=str(value.get("checkpoint_key") or ""),
        source_hash=str(value.get("source_hash") or ""),
        created_at=created_at,
        payload=value["payload"],
    )


def _validated_payload(
    value: AdvisoryBlindSpotPolicyCheckpoint | Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    checkpoint = _checkpoint(value)
    return (
        checkpoint.payload
        if checkpoint is not None and validate_advisory_blind_spot_policy(checkpoint)
        else None
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
    if existing is None:
        return True
    last_count = int(existing.get("last_calibrated_settled_count") or 0)
    last_at = _parse_time(existing.get("last_calibrated_at"))
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
        fmean(rng.choice(strict) for _ in strict) - fmean(rng.choice(advisory) for _ in advisory)
        for _ in range(BOOTSTRAP_ITERATIONS)
    )
    return differences[int((len(differences) - 1) * 0.10)]


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 and str(value) == str(parsed) else None


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and abs(parsed) != float("inf") else None


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _iso(value: datetime | None) -> str | None:
    parsed = _utc(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else None


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
