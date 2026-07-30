from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from w2.analysis.market_movement import classify_divergence_origin
from w2.lineups.intelligence import build_team_rotation_prior
from w2.markets.value_engine import SettlementDistribution, expected_value
from w2.tracking.advisory_blind_spot_policy import (
    POLICY_CHECKPOINT_KEY,
    AdvisoryBlindSpotPolicyCheckpoint,
    build_advisory_blind_spot_policy,
    validate_advisory_blind_spot_policy,
)
from w2.tracking.finished_match_scoring_projection import (
    _blind_spot_attribution,
    _window_metrics,
)

KICKOFF = datetime(2026, 7, 30, 12, tzinfo=UTC)
CURRENT = KICKOFF - timedelta(hours=1)


def _observation(
    *,
    observation_id: str,
    odds: float,
    captured_at: datetime,
    line: float = -0.5,
    market: str = "ASIAN_HANDICAP",
    selection: str = "HOME",
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "fixture_id": "api_football:42",
        "provider": "api_football",
        "bookmaker_id": "7",
        "canonical_market": market,
        "canonical_selection": selection,
        "line": line,
        "decimal_odds": odds,
        "captured_at": captured_at.isoformat(),
        "live": False,
        "suspended": False,
    }


def _classification(
    opening_odds: float,
    *,
    current_odds: float = 2.4,
    current_ev: float | None = None,
    settlement_distribution: dict[str, float] | None = None,
    observations: list[dict[str, object]] | None = None,
    market: str = "ASIAN_HANDICAP",
    selection: str = "HOME",
    line: float = -0.5,
    current_provider: str = "api_football",
    current_bookmaker_id: str = "7",
) -> dict[str, object]:
    rows = observations or [
        _observation(
            observation_id="opening",
            odds=opening_odds,
            captured_at=CURRENT - timedelta(hours=5),
            line=line,
            market=market,
            selection=selection,
        ),
        _observation(
            observation_id="current",
            odds=current_odds,
            captured_at=CURRENT,
            line=line,
            market=market,
            selection=selection,
        ),
    ]
    distribution = (
        {
            "WIN": 0.5,
            "HALF_WIN": 0.0,
            "PUSH": 0.0,
            "HALF_LOSS": 0.0,
            "LOSS": 0.5,
        }
        if settlement_distribution is None
        else settlement_distribution
    )
    persisted_ev = (
        current_ev
        if current_ev is not None
        else float(
            expected_value(
                Decimal(str(current_odds)),
                SettlementDistribution(
                    full_win_probability=Decimal(str(distribution["WIN"])),
                    half_win_probability=Decimal(str(distribution["HALF_WIN"])),
                    push_probability=Decimal(str(distribution["PUSH"])),
                    half_loss_probability=Decimal(str(distribution["HALF_LOSS"])),
                    full_loss_probability=Decimal(str(distribution["LOSS"])),
                ),
            )
        )
    )
    return classify_divergence_origin(
        fixture_id="42",
        market=market,
        selection=selection,
        line=line,
        model_probability=0.5,
        settlement_distribution=distribution,
        current_decimal_odds=current_odds,
        current_expected_value=persisted_ev,
        current_captured_at=CURRENT,
        current_provider=current_provider,
        current_bookmaker_id=current_bookmaker_id,
        kickoff_utc=KICKOFF,
        current_quote_identity_status="COMPLETE",
        current_quote_freshness_status="COMPLETE",
        observations=rows,
    )


def test_divergence_classifier_freezes_registered_boundaries() -> None:
    moved = _classification(2.0)
    half = _classification(2.2)
    stable = _classification(2.24)

    assert moved["raw_classification"] == "MOVEMENT_CREATED_DIVERGENCE"
    assert moved["effective_risk_class"] == "MOVED"
    assert half["movement_ev_share"] == 0.5
    assert half["raw_classification"] == "INDETERMINATE"
    assert half["effective_risk_class"] == "MOVED_CONSERVATIVE"
    assert stable["divergence_age_ratio"] == 0.6
    assert stable["raw_classification"] == "STABLE_DIVERGENCE"
    assert stable["effective_risk_class"] == "STABLE"


def test_divergence_classifier_rejects_cross_line_future_and_post_kickoff_openings() -> None:
    rows = [
        _observation(
            observation_id="cross-line",
            odds=2.0,
            line=-0.25,
            captured_at=CURRENT - timedelta(hours=4),
        ),
        _observation(
            observation_id="future",
            odds=2.0,
            captured_at=CURRENT + timedelta(minutes=1),
        ),
        _observation(
            observation_id="post-kickoff",
            odds=2.0,
            captured_at=KICKOFF + timedelta(minutes=1),
        ),
        _observation(observation_id="current", odds=2.4, captured_at=CURRENT),
    ]
    result = _classification(2.0, observations=rows)

    assert result["raw_classification"] == "INDETERMINATE"
    assert result["input_observation_ids"] == ["current"]
    assert "SAME_LINE_OPENING_NOT_AVAILABLE" in result["blockers"]


def test_divergence_classifier_fails_closed_on_current_ev_parity_conflict() -> None:
    result = _classification(2.0, current_ev=0.21)

    assert result["status"] == "BLOCKED"
    assert "EV_IDENTITY_PARITY_CONFLICT" in result["blockers"]


@pytest.mark.parametrize(
    ("market", "selection", "line", "distribution"),
    (
        (
            "ASIAN_HANDICAP",
            "HOME",
            0.0,
            {"WIN": 0.45, "HALF_WIN": 0.0, "PUSH": 0.1, "HALF_LOSS": 0.0, "LOSS": 0.45},
        ),
        (
            "ASIAN_HANDICAP",
            "HOME",
            -0.5,
            {"WIN": 0.52, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.48},
        ),
        (
            "ASIAN_HANDICAP",
            "HOME",
            -0.25,
            {"WIN": 0.46, "HALF_WIN": 0.12, "PUSH": 0.0, "HALF_LOSS": 0.1, "LOSS": 0.32},
        ),
        (
            "TOTALS",
            "OVER",
            2.0,
            {"WIN": 0.44, "HALF_WIN": 0.0, "PUSH": 0.14, "HALF_LOSS": 0.0, "LOSS": 0.42},
        ),
        (
            "TOTALS",
            "OVER",
            2.5,
            {"WIN": 0.51, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.49},
        ),
        (
            "TOTALS",
            "OVER",
            2.25,
            {"WIN": 0.43, "HALF_WIN": 0.11, "PUSH": 0.0, "HALF_LOSS": 0.13, "LOSS": 0.33},
        ),
    ),
)
def test_divergence_reprices_same_five_state_distribution_without_false_parity(
    market: str,
    selection: str,
    line: float,
    distribution: dict[str, float],
) -> None:
    result = _classification(
        1.9,
        current_odds=2.1,
        settlement_distribution=distribution,
        market=market,
        selection=selection,
        line=line,
    )

    assert "EV_IDENTITY_PARITY_CONFLICT" not in result["blockers"]
    assert "MODEL_SETTLEMENT_DISTRIBUTION_INVALID" not in result["blockers"]
    assert result["current_ev"] == pytest.approx(
        float(
            expected_value(
                Decimal("2.1"),
                SettlementDistribution(
                    full_win_probability=Decimal(str(distribution["WIN"])),
                    half_win_probability=Decimal(str(distribution["HALF_WIN"])),
                    push_probability=Decimal(str(distribution["PUSH"])),
                    half_loss_probability=Decimal(str(distribution["HALF_LOSS"])),
                    full_loss_probability=Decimal(str(distribution["LOSS"])),
                ),
            )
        )
    )
    assert result["opening_ev"] != result["current_ev"]


def test_divergence_rejects_invalid_distribution_and_cross_bookmaker_opening() -> None:
    invalid = _classification(
        2.0,
        settlement_distribution={
            "WIN": 0.5,
            "HALF_WIN": 0.0,
            "PUSH": 0.0,
            "HALF_LOSS": 0.0,
            "LOSS": 0.6,
        },
    )
    cross_bookmaker = _observation(
        observation_id="cross-bookmaker",
        odds=2.0,
        captured_at=CURRENT - timedelta(hours=5),
    )
    cross_bookmaker["bookmaker_id"] = "other"
    current = _observation(
        observation_id="current",
        odds=2.4,
        captured_at=CURRENT,
    )
    mismatched = _classification(
        2.0,
        observations=[cross_bookmaker, current],
    )

    assert invalid["raw_classification"] == "INDETERMINATE"
    assert "MODEL_SETTLEMENT_DISTRIBUTION_INVALID" in invalid["blockers"]
    assert "SAME_LINE_OPENING_NOT_AVAILABLE" in mismatched["blockers"]


@pytest.mark.parametrize(
    "distribution",
    (
        {"WIN": 0.5, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.0},
        {
            "WIN": 0.5,
            "HALF_WIN": -0.1,
            "PUSH": 0.1,
            "HALF_LOSS": 0.0,
            "LOSS": 0.5,
        },
        {
            "WIN": float("inf"),
            "HALF_WIN": 0.0,
            "PUSH": 0.0,
            "HALF_LOSS": 0.0,
            "LOSS": 0.0,
        },
    ),
)
def test_divergence_rejects_incomplete_negative_and_nonfinite_distribution(
    distribution: dict[str, float],
) -> None:
    result = _classification(
        2.0,
        settlement_distribution=distribution,
        current_ev=0.0,
    )

    assert result["raw_classification"] == "INDETERMINATE"
    assert "MODEL_SETTLEMENT_DISTRIBUTION_INVALID" in result["blockers"]


@pytest.mark.parametrize(
    ("provider", "bookmaker_id"),
    (("", "7"), ("api_football", "")),
)
def test_divergence_rejects_missing_current_execution_identity(
    provider: str,
    bookmaker_id: str,
) -> None:
    result = _classification(
        2.0,
        current_provider=provider,
        current_bookmaker_id=bookmaker_id,
    )

    assert result["raw_classification"] == "INDETERMINATE"
    assert "CURRENT_QUOTE_EXECUTION_IDENTITY_INCOMPLETE" in result["blockers"]


def _lineup_rows(*, changes: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    starters = [str(value) for value in range(11)]
    for index in range(6):
        kickoff = KICKOFF - timedelta(days=12 - index * 2)
        rows.append(
            {
                "fixture_id": f"fixture-{index}",
                "team_external_id": "team-1",
                "kickoff_at": kickoff,
                "captured_at": kickoff - timedelta(hours=1),
                "confirmed": True,
                "starters": [{"player_id": player_id} for player_id in starters],
                "lineup_identity_hash": f"lineup-{index}",
            }
        )
        starters = starters[changes:] + [
            str(100 + index * changes + offset) for offset in range(changes)
        ]
    return rows


def test_rotation_prior_uses_four_of_eleven_boundary_and_stable_input_hash() -> None:
    rows = _lineup_rows(changes=4)
    forward = build_team_rotation_prior(
        rows,
        team_external_id="team-1",
        as_of=KICKOFF,
    )
    reverse = build_team_rotation_prior(
        list(reversed(rows)),
        team_external_id="team-1",
        as_of=KICKOFF,
    )

    assert forward["status"] == "READY"
    assert forward["transition_count"] == 5
    assert forward["rotation_rate"] == pytest.approx(4 / 11)
    assert forward["classification"] == "HIGH_ROTATION"
    assert reverse["input_hash"] == forward["input_hash"]


def test_rotation_prior_excludes_incomplete_future_and_old_same_fixture_snapshots() -> None:
    rows = _lineup_rows(changes=3)
    rows.extend(
        [
            {
                **rows[-1],
                "captured_at": KICKOFF - timedelta(days=2, hours=1, minutes=1),
                "starters": [{"player_id": "old"}] * 11,
            },
            {
                **rows[-1],
                "fixture_id": "future",
                "kickoff_at": KICKOFF + timedelta(days=1),
                "captured_at": KICKOFF,
            },
            {
                **rows[-1],
                "fixture_id": "incomplete",
                "starters": [{"player_id": str(value)} for value in range(10)],
            },
        ]
    )
    result = build_team_rotation_prior(
        rows,
        team_external_id="team-1",
        as_of=KICKOFF,
    )

    assert result["match_count"] == 6
    assert result["classification"] == "NORMAL"


def _performance_rows(
    advisory_count: int,
    *,
    strict_clv: float = 0.2,
    advisory_clv: float = 0.05,
) -> dict[str, dict[str, object]]:
    rows = {
        f"advisory-{index}": {
            "fixture_id": f"advisory-{index}",
            "kickoff_utc": (KICKOFF - timedelta(hours=index)).isoformat(),
            "evaluation_tier": "ADVISORY",
            "status": "SCORED",
            "canonical_settlement_outcome": "HIT",
            "clv_status": "AVAILABLE",
            "clv_decimal": advisory_clv,
        }
        for index in range(advisory_count)
    }
    rows["strict"] = {
        "fixture_id": "strict",
        "kickoff_utc": KICKOFF.isoformat(),
        "evaluation_tier": "STRICT",
        "status": "SCORED",
        "canonical_settlement_outcome": "HIT",
        "clv_status": "AVAILABLE",
        "clv_decimal": strict_clv,
    }
    return rows


def _policy_checkpoint(
    payload: dict[str, object],
    *,
    created_at: datetime,
) -> AdvisoryBlindSpotPolicyCheckpoint:
    return AdvisoryBlindSpotPolicyCheckpoint(
        checkpoint_key=POLICY_CHECKPOINT_KEY,
        source_hash=str(payload["business_projection_hash"]),
        created_at=created_at,
        payload=payload,
    )


def test_advisory_delta_policy_keeps_real_like_insufficient_sample_at_zero() -> None:
    policy = build_advisory_blind_spot_policy(
        _performance_rows(16),
        existing=None,
        now=KICKOFF,
    )

    assert policy["status"] == "INSUFFICIENT_ADVISORY_CANONICAL_SAMPLE"
    assert policy["advisory_canonical_settled_count"] == 16
    assert policy["applied_delta"] == 0.0
    assert policy["watch_only"] is False


def test_advisory_delta_policy_calibrates_q10_and_respects_zero_floor() -> None:
    positive = build_advisory_blind_spot_policy(
        _performance_rows(50),
        existing=None,
        now=KICKOFF,
    )
    floored = build_advisory_blind_spot_policy(
        _performance_rows(50, strict_clv=0.01, advisory_clv=0.02),
        existing=None,
        now=KICKOFF,
    )

    assert positive["status"] == "READY"
    assert positive["bootstrap_iterations"] == 10_000
    assert positive["lower_bound_80"] == pytest.approx(0.15)
    assert positive["applied_delta"] == pytest.approx(0.15)
    assert positive["watch_only"] is True
    assert floored["lower_bound_80"] < 0
    assert floored["applied_delta"] == 0.0


def test_advisory_delta_policy_recalibrates_only_on_step_or_age() -> None:
    initial = build_advisory_blind_spot_policy(
        _performance_rows(50),
        existing=None,
        now=KICKOFF,
    )
    retained = build_advisory_blind_spot_policy(
        _performance_rows(99, strict_clv=0.3, advisory_clv=0.01),
        existing=_policy_checkpoint(initial, created_at=KICKOFF),
        now=KICKOFF + timedelta(days=1),
    )
    by_count = build_advisory_blind_spot_policy(
        _performance_rows(100, strict_clv=0.3, advisory_clv=0.01),
        existing=_policy_checkpoint(initial, created_at=KICKOFF),
        now=KICKOFF + timedelta(days=1),
    )
    by_age = build_advisory_blind_spot_policy(
        _performance_rows(99, strict_clv=0.3, advisory_clv=0.01),
        existing=_policy_checkpoint(initial, created_at=KICKOFF),
        now=KICKOFF + timedelta(days=90),
    )

    assert retained["applied_delta"] == initial["applied_delta"]
    assert retained["last_calibrated_at"] == initial["last_calibrated_at"]
    assert by_count["last_calibrated_settled_count"] == 100
    assert by_age["last_calibrated_at"] != initial["last_calibrated_at"]


def test_advisory_policy_uses_exact_90d_window_and_stable_source_hash() -> None:
    start = KICKOFF - timedelta(days=90)
    rows = {
        "boundary": {
            **_performance_rows(1)["advisory-0"],
            "fixture_id": "boundary",
            "kickoff_utc": start.isoformat(),
        },
        "before": {
            **_performance_rows(1)["advisory-0"],
            "fixture_id": "before",
            "kickoff_utc": (start - timedelta(microseconds=1)).isoformat(),
        },
        "after": {
            **_performance_rows(1)["advisory-0"],
            "fixture_id": "after",
            "kickoff_utc": (KICKOFF + timedelta(microseconds=1)).isoformat(),
        },
        "anchor": {
            **_performance_rows(1)["advisory-0"],
            "fixture_id": "anchor",
            "kickoff_utc": KICKOFF.isoformat(),
        },
    }
    policy = build_advisory_blind_spot_policy(
        rows,
        existing=None,
        now=KICKOFF,
        scoring_window_anchor=KICKOFF,
    )
    reversed_policy = build_advisory_blind_spot_policy(
        dict(reversed(list(rows.items()))),
        existing=None,
        now=KICKOFF,
        scoring_window_anchor=KICKOFF,
    )
    without_lifetime = build_advisory_blind_spot_policy(
        {key: value for key, value in rows.items() if key != "before"},
        existing=None,
        now=KICKOFF,
        scoring_window_anchor=KICKOFF,
    )

    assert policy["scoring_window_anchor"] == KICKOFF.isoformat().replace("+00:00", "Z")
    assert policy["window_start"] == start.isoformat().replace("+00:00", "Z")
    assert policy["window_fixture_count"] == 2
    assert policy["advisory_canonical_settled_count"] == 2
    assert policy["source_fixture_hash"] == reversed_policy["source_fixture_hash"]
    assert policy["source_fixture_hash"] == without_lifetime["source_fixture_hash"]


def _rehash_policy(payload: dict[str, object]) -> dict[str, object]:
    projected = {key: value for key, value in payload.items() if key != "business_projection_hash"}
    digest = hashlib.sha256(
        json.dumps(
            projected,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()
    return {**projected, "business_projection_hash": digest}


def _corrupted_policy_checkpoint(
    payload: dict[str, object],
    *,
    remove: str | None = None,
    **changes: object,
) -> AdvisoryBlindSpotPolicyCheckpoint:
    corrupted = {**payload, **changes}
    if remove is not None:
        corrupted.pop(remove)
    rehashed = _rehash_policy(corrupted)
    return _policy_checkpoint(rehashed, created_at=KICKOFF)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("applied_delta", -0.1),
        ("effective_threshold", 999.0),
        ("bootstrap_iterations", 9999),
        ("last_calibrated_at", None),
        ("last_calibrated_settled_count", 51),
    ),
)
def test_policy_checkpoint_integrity_rejects_corrupt_invariants(
    field: str,
    value: object,
) -> None:
    payload = build_advisory_blind_spot_policy(
        _performance_rows(50),
        existing=None,
        now=KICKOFF,
    )
    corrupted = _rehash_policy({**payload, field: value})
    checkpoint = AdvisoryBlindSpotPolicyCheckpoint(
        checkpoint_key=POLICY_CHECKPOINT_KEY,
        source_hash=str(corrupted["business_projection_hash"]),
        created_at=KICKOFF,
        payload=corrupted,
    )

    assert validate_advisory_blind_spot_policy(checkpoint) is False


def test_policy_checkpoint_integrity_rejects_hash_and_source_hash_mismatch() -> None:
    payload = build_advisory_blind_spot_policy(
        _performance_rows(16),
        existing=None,
        now=KICKOFF,
    )
    valid = _policy_checkpoint(payload, created_at=KICKOFF)
    bad_business = {
        **payload,
        "business_projection_hash": "0" * 64,
    }

    assert validate_advisory_blind_spot_policy(valid) is True
    assert (
        validate_advisory_blind_spot_policy(
            AdvisoryBlindSpotPolicyCheckpoint(
                checkpoint_key=POLICY_CHECKPOINT_KEY,
                source_hash="f" * 64,
                created_at=KICKOFF,
                payload=payload,
            )
        )
        is False
    )
    assert (
        validate_advisory_blind_spot_policy(
            AdvisoryBlindSpotPolicyCheckpoint(
                checkpoint_key=POLICY_CHECKPOINT_KEY,
                source_hash="0" * 64,
                created_at=KICKOFF,
                payload=bad_business,
            )
        )
        is False
    )


@pytest.mark.parametrize(
    ("advisory_count", "field", "value"),
    (
        (16, "applied_delta", 0.1),
        (50, "last_calibrated_at", (KICKOFF + timedelta(seconds=1)).isoformat()),
    ),
)
def test_policy_checkpoint_integrity_rejects_state_specific_corruption(
    advisory_count: int,
    field: str,
    value: object,
) -> None:
    payload = build_advisory_blind_spot_policy(
        _performance_rows(advisory_count),
        existing=None,
        now=KICKOFF,
    )
    overrides = {field: value}
    if field == "applied_delta":
        overrides["effective_threshold"] = value
    corrupted = _rehash_policy({**payload, **overrides})

    assert (
        validate_advisory_blind_spot_policy(
            AdvisoryBlindSpotPolicyCheckpoint(
                checkpoint_key=POLICY_CHECKPOINT_KEY,
                source_hash=str(corrupted["business_projection_hash"]),
                created_at=KICKOFF,
                payload=corrupted,
            )
        )
        is False
    )


@pytest.mark.parametrize(
    ("remove", "changes"),
    (
        ("strict_clv_mean", {}),
        ("advisory_clv_mean", {}),
        ("next_recalibration_at", {}),
        (None, {"advisory_canonical_settled_count": 49}),
        (None, {"last_calibrated_settled_count": 49}),
        (None, {"bootstrap_seed": 0}),
        (None, {"strict_clv_mean": None}),
        (None, {"advisory_clv_mean": None}),
        (None, {"strict_clv_mean": float("nan")}),
        (None, {"advisory_clv_mean": float("inf")}),
        (None, {"advisory_clv_mean": float("-inf")}),
        (None, {"watch_only": False}),
        (None, {"next_recalibration_at": (KICKOFF + timedelta(days=89)).isoformat()}),
        (None, {"next_recalibration_at": (KICKOFF - timedelta(days=1)).isoformat()}),
    ),
)
def test_ready_policy_rejects_rehashed_semantic_corruption(
    remove: str | None,
    changes: dict[str, object],
) -> None:
    payload = build_advisory_blind_spot_policy(
        _performance_rows(50),
        existing=None,
        now=KICKOFF,
    )

    assert (
        validate_advisory_blind_spot_policy(
            _corrupted_policy_checkpoint(payload, remove=remove, **changes)
        )
        is False
    )


def test_ready_policy_rejects_rehashed_false_watch_only_corruption() -> None:
    payload = build_advisory_blind_spot_policy(
        _performance_rows(50, strict_clv=0.01, advisory_clv=0.02),
        existing=None,
        now=KICKOFF,
    )

    assert payload["watch_only"] is False
    assert (
        validate_advisory_blind_spot_policy(
            _corrupted_policy_checkpoint(payload, watch_only=True)
        )
        is False
    )


@pytest.mark.parametrize(
    ("tier", "count_field", "mean_field"),
    (
        ("STRICT", "strict_clv_sample_count", "strict_clv_mean"),
        ("ADVISORY", "advisory_clv_sample_count", "advisory_clv_mean"),
    ),
)
def test_policy_rejects_rehashed_count_mean_mismatch(
    tier: str,
    count_field: str,
    mean_field: str,
) -> None:
    payload = build_advisory_blind_spot_policy(
        _performance_rows(16),
        existing=None,
        now=KICKOFF,
    )
    nonzero_missing = _corrupted_policy_checkpoint(payload, **{mean_field: None})
    zero_nonempty = _corrupted_policy_checkpoint(
        payload,
        **{count_field: 0, mean_field: 0.1},
    )

    assert tier in {"STRICT", "ADVISORY"}
    assert validate_advisory_blind_spot_policy(nonzero_missing) is False
    assert validate_advisory_blind_spot_policy(zero_nonempty) is False


def test_policy_expiry_boundary_is_inclusive_then_fails_one_microsecond_later() -> None:
    payload = build_advisory_blind_spot_policy(
        _performance_rows(50),
        existing=None,
        now=KICKOFF,
    )
    checkpoint = _policy_checkpoint(payload, created_at=KICKOFF)
    expires_at = KICKOFF + timedelta(days=90)

    assert validate_advisory_blind_spot_policy(checkpoint, as_of=expires_at) is True
    assert (
        validate_advisory_blind_spot_policy(
            checkpoint,
            as_of=expires_at + timedelta(microseconds=1),
        )
        is False
    )


def test_insufficient_policy_rejects_rehashed_recalibration_metadata() -> None:
    advisory_insufficient = build_advisory_blind_spot_policy(
        _performance_rows(16),
        existing=None,
        now=KICKOFF,
    )
    clv_insufficient = build_advisory_blind_spot_policy(
        {
            key: value
            for key, value in _performance_rows(50).items()
            if key != "strict"
        },
        existing=None,
        now=KICKOFF,
    )

    assert validate_advisory_blind_spot_policy(
        _policy_checkpoint(advisory_insufficient, created_at=KICKOFF)
    )
    assert validate_advisory_blind_spot_policy(
        _policy_checkpoint(clv_insufficient, created_at=KICKOFF)
    )
    for payload in (advisory_insufficient, clv_insufficient):
        assert (
            validate_advisory_blind_spot_policy(
                _corrupted_policy_checkpoint(
                    payload,
                    next_recalibration_at=(KICKOFF + timedelta(days=90)).isoformat(),
                )
            )
            is False
        )


def _lineup_evidence(deviation: float, *, high_rotation: bool = False) -> dict[str, object]:
    prior = {
        "status": "READY",
        "classification": "HIGH_ROTATION" if high_rotation else "NORMAL",
    }
    return {
        "status": "READY",
        "home": {
            "starter_continuity": 1 - deviation,
            "rotation_prior": prior,
        },
        "away": {
            "starter_continuity": 1.0,
            "rotation_prior": {"status": "READY", "classification": "NORMAL"},
        },
        "blockers": [],
    }


@pytest.mark.parametrize(
    ("outcome", "deviation", "high_rotation", "expected"),
    (
        ("MISS", 4 / 11, False, "ROTATION_ASSOCIATED"),
        ("MISS", 3 / 11, False, "NON_ROTATION_RESIDUAL"),
        ("HIT", 4 / 11, True, "NOT_LOSS"),
        ("PUSH", 4 / 11, True, "NOT_LOSS"),
        ("VOID", 4 / 11, True, "NOT_LOSS"),
    ),
)
def test_blind_spot_attribution_is_non_causal_and_thresholded(
    outcome: str,
    deviation: float,
    high_rotation: bool,
    expected: str,
) -> None:
    result = _blind_spot_attribution(
        lineup_requirement="ADVISORY",
        lineup_evidence=_lineup_evidence(
            deviation,
            high_rotation=high_rotation,
        ),
        canonical={
            "canonical_settlement_outcome": outcome,
            "canonical_pick_market": "ASIAN_HANDICAP",
            "canonical_pick_selection": "HOME",
        },
    )

    assert result["attribution"] == expected
    assert result["causal_claim"] is False


def test_blind_spot_attribution_handles_missing_evidence_and_strict() -> None:
    canonical = {
        "canonical_settlement_outcome": "MISS",
        "canonical_pick_market": "ASIAN_HANDICAP",
        "canonical_pick_selection": "HOME",
    }
    missing = _blind_spot_attribution(
        lineup_requirement="ADVISORY",
        lineup_evidence=None,
        canonical=canonical,
    )
    strict = _blind_spot_attribution(
        lineup_requirement="STRICT",
        lineup_evidence=_lineup_evidence(1.0),
        canonical=canonical,
    )

    assert missing["attribution"] == "INSUFFICIENT_EVIDENCE"
    assert strict["attribution"] == "NOT_APPLICABLE_STRICT"


def test_blind_spot_cohort_counts_are_deterministic() -> None:
    rows = [
        {
            "status": "NOT_SCORABLE",
            "reason_codes": [],
            "blind_spot_attribution": {
                "attribution": "ROTATION_ASSOCIATED",
                "high_rotation_prior": True,
                "lineup_requirement": "ADVISORY",
            },
        },
        {
            "status": "NOT_SCORABLE",
            "reason_codes": [],
            "blind_spot_attribution": {
                "attribution": "NON_ROTATION_RESIDUAL",
                "high_rotation_prior": False,
                "lineup_requirement": "ADVISORY",
            },
        },
        {
            "status": "NOT_SCORABLE",
            "reason_codes": [],
            "blind_spot_attribution": {
                "attribution": "INSUFFICIENT_EVIDENCE",
                "high_rotation_prior": False,
                "lineup_requirement": "ADVISORY",
            },
        },
    ]
    window = _window_metrics(rows)

    assert window["blind_spot_attribution_sample_count"] == 3
    assert window["rotation_associated_miss_count"] == 1
    assert window["non_rotation_residual_miss_count"] == 1
    assert window["insufficient_attribution_count"] == 1
    assert window["high_rotation_prior_fixture_count"] == 1
    assert window["lineup_unobservable_fixture_count"] == 3
