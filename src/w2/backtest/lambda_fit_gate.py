from __future__ import annotations

from typing import Any

MIN_LAMBDA_FIT_SETTLED_LOCK_SAMPLES = 200
BLOCKED_WITH_SAMPLE_GATE = "BLOCKED_WITH_SAMPLE_GATE"
WALK_FORWARD_REQUIRES_SETTLED_LOCK_SAMPLE_N_GE_200 = (
    "WALK_FORWARD_REQUIRES_SETTLED_LOCK_SAMPLE_N_GE_200"
)


def build_lambda_fit_gap_report(
    *,
    settled_lock_sample_count: int,
    generated_at: str,
    min_samples: int = MIN_LAMBDA_FIT_SETTLED_LOCK_SAMPLES,
) -> dict[str, Any]:
    if settled_lock_sample_count < min_samples:
        status = BLOCKED_WITH_SAMPLE_GATE
        blockers = [WALK_FORWARD_REQUIRES_SETTLED_LOCK_SAMPLE_N_GE_200]
    else:
        status = "READY_FOR_OFFLINE_REVIEW"
        blockers = []
    return {
        "schema_version": "w2.lambda_fit_gap_audit.v1",
        "generated_at": generated_at,
        "as_of": generated_at,
        "status": status,
        "settled_lock_sample_count": settled_lock_sample_count,
        "min_samples": min_samples,
        "blockers": blockers,
        "config_generated": False,
        "enabled_for_online_path": False,
        "provider_calls": 0,
        "db_writes": 0,
        "market_odds_or_lines_used": False,
    }
