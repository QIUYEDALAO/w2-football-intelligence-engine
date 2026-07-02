from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import log
from typing import Any

MIN_BUCKET_SAMPLES_FOR_RATE = 30
CALIBRATION_REPORT_SCHEMA_VERSION = "w2.calibration_report.v1"


@dataclass(frozen=True)
class CalibrationSample:
    release_sha: str | None
    bucket: str
    tier: str | None
    movement_pattern: str | None
    line_bucket: str
    predicted_cover_probability: float
    actual_cover: float


def build_calibration_report(
    *,
    lock_rows: list[dict[str, Any]],
    settlement_rows: list[dict[str, Any]],
    generated_at: str,
    min_bucket_samples_for_rate: int = MIN_BUCKET_SAMPLES_FOR_RATE,
) -> list[dict[str, Any]]:
    samples = _calibration_samples(lock_rows=lock_rows, settlement_rows=settlement_rows)
    grouped: dict[tuple[str | None, str, str | None, str | None, str], list[CalibrationSample]]
    grouped = defaultdict(list)
    for sample in samples:
        grouped[
            (
                sample.release_sha,
                sample.bucket,
                sample.tier,
                sample.movement_pattern,
                sample.line_bucket,
            )
        ].append(sample)

    rows = []
    for (
        release_sha,
        bucket,
        tier,
        movement_pattern,
        line_bucket,
    ), bucket_samples in sorted(
        grouped.items(),
        key=lambda item: tuple(str(part) for part in item[0]),
    ):
        sample_count = len(bucket_samples)
        ready = sample_count >= min_bucket_samples_for_rate
        row: dict[str, Any] = {
            "schema_version": CALIBRATION_REPORT_SCHEMA_VERSION,
            "generated_at": generated_at,
            "as_of": generated_at,
            "release_sha": release_sha,
            "bucket": bucket,
            "tier": tier,
            "movement_pattern": movement_pattern,
            "line_bucket": line_bucket,
            "sample_count": sample_count,
            "min_bucket_samples_for_rate": min_bucket_samples_for_rate,
            "status": "READY" if ready else "OBSERVING",
            "label": (
                f"样本已达标 {sample_count}/{min_bucket_samples_for_rate}"
                if ready
                else f"观察中 {sample_count}/{min_bucket_samples_for_rate}"
            ),
            "not_a_formal_gate": True,
            "posthoc_only": True,
            "predicted_cover_probability": None,
            "actual_cover_probability": None,
            "brier": None,
            "log_loss": None,
        }
        if ready:
            predictions = [sample.predicted_cover_probability for sample in bucket_samples]
            actuals = [sample.actual_cover for sample in bucket_samples]
            row["predicted_cover_probability"] = _round(sum(predictions) / sample_count)
            row["actual_cover_probability"] = _round(sum(actuals) / sample_count)
            row["brier"] = _round(
                sum(
                    (sample.predicted_cover_probability - sample.actual_cover) ** 2
                    for sample in bucket_samples
                )
                / sample_count,
            )
            row["log_loss"] = _round(
                sum(
                    _log_loss(
                        sample.predicted_cover_probability,
                        sample.actual_cover,
                    )
                    for sample in bucket_samples
                )
                / sample_count,
            )
        rows.append(row)
    return rows


def _calibration_samples(
    *,
    lock_rows: list[dict[str, Any]],
    settlement_rows: list[dict[str, Any]],
) -> list[CalibrationSample]:
    settlements_by_lock_id = {
        str(row.get("lock_id")): row
        for row in settlement_rows
        if row.get("lock_id") not in {None, ""}
    }
    samples = []
    for lock in lock_rows:
        if _truthy(lock.get("legacy_marker_only")) or not _truthy(lock.get("reproducible")):
            continue
        lock_id = lock.get("lock_id")
        if lock_id in {None, ""}:
            continue
        settlement = settlements_by_lock_id.get(str(lock_id))
        if settlement is None:
            continue
        predicted = _predicted_effective_cover(lock)
        actual = _settlement_effective_cover(settlement.get("outcome"))
        if predicted is None or actual is None:
            continue
        samples.append(
            CalibrationSample(
                release_sha=_string(lock.get("release_sha")),
                bucket=_probability_bucket(predicted),
                tier=_string(lock.get("tier")),
                movement_pattern=_string(
                    settlement.get("movement_pattern")
                    or _movement_pattern(lock.get("market_timeline_json")),
                ),
                line_bucket=_line_bucket(
                    lock.get("pick_line") or lock.get("recommendation_line")
                ),
                predicted_cover_probability=predicted,
                actual_cover=actual,
            )
        )
    return samples


def _predicted_effective_cover(lock: dict[str, Any]) -> float | None:
    distribution = _dict(lock.get("ah_settlement_distribution_json"))
    if not distribution:
        distribution = _dict(
            _dict(lock.get("snapshot_payload_json")).get("ah_settlement_distribution")
        )
    win = _number(distribution.get("WIN"))
    half_win = _number(distribution.get("HALF_WIN"))
    push = _number(distribution.get("PUSH"))
    half_loss = _number(distribution.get("HALF_LOSS"))
    loss = _number(distribution.get("LOSS"))
    if (
        win is None
        or half_win is None
        or push is None
        or half_loss is None
        or loss is None
    ):
        return None
    total = win + half_win + push + half_loss + loss
    if abs(total - 1.0) > 0.02:
        return None
    return _round(win + half_win * 0.5 + push * 0.5)


def _settlement_effective_cover(outcome: Any) -> float | None:
    return {
        "WIN": 1.0,
        "HALF_WIN": 0.5,
        "PUSH": 0.5,
        "HALF_LOSS": 0.0,
        "LOSS": 0.0,
    }.get(str(outcome or "").upper())


def _probability_bucket(probability: float) -> str:
    lower = max(0, min(9, int(probability * 10)))
    upper = lower + 1
    return f"{lower / 10:.1f}_{upper / 10:.1f}"


def _line_bucket(value: Any) -> str:
    line = _number(value)
    if line is None:
        return "UNKNOWN"
    absolute = abs(line)
    if absolute < 0.25:
        return "0_0.25"
    if absolute < 0.75:
        return "0.25_0.75"
    if absolute < 1.25:
        return "0.75_1.25"
    if absolute < 1.75:
        return "1.25_1.75"
    return "1.75_plus"


def _movement_pattern(value: Any) -> str | None:
    payload = _dict(value)
    pattern = payload.get("pattern")
    return _string(pattern)


def _log_loss(predicted: float, actual: float) -> float:
    p = min(max(predicted, 0.000001), 0.999999)
    return -(actual * log(p) + (1.0 - actual) * log(1.0 - p))


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _round(value: float) -> float:
    return round(value, 6)
