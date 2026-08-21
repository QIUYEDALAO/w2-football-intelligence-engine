from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from w2.factor_model.history import API_FOOTBALL_TEAM_ID_NAMESPACE, build_pit_history_manifest
from w2.factor_model.pit_features import RecursiveRatingPolicy, build_pit_feature_snapshot

TARGET = datetime(2026, 8, 21, 12, tzinfo=UTC)
POLICY = RecursiveRatingPolicy(
    version="recursive-rating-v1.test",
    initial_rating=1500.0,
    k_factor=20.0,
    home_advantage_rating=60.0,
)
TEAM_NS = API_FOOTBALL_TEAM_ID_NAMESPACE


def _pair(
    index: int,
    *,
    kickoff: datetime,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
) -> list[dict[str, Any]]:
    fixture_id = f"api_football:{index}"
    common = {
        "fixture_id": fixture_id,
        "provider": "api_football",
        "provider_fixture_id": str(index),
        "provider_league_id": "140",
        "season": "2025",
        "kickoff_utc": kickoff,
        "fixture_status": "FT",
        "team_identity_namespace": TEAM_NS,
        "result_identity_hash": f"result:{index}",
        "raw_payload_sha256": f"{index:064x}",
        "raw_captured_at": kickoff + timedelta(hours=3),
    }
    return [
        {
            **common,
            "history_hash": f"history:{index}:home",
            "team_side": "HOME",
            "team_id": home,
            "opponent_team_id": away,
            "goals_for": home_goals,
            "goals_against": away_goals,
        },
        {
            **common,
            "history_hash": f"history:{index}:away",
            "team_side": "AWAY",
            "team_id": away,
            "opponent_team_id": home,
            "goals_for": away_goals,
            "goals_against": home_goals,
        },
    ]


def _manifest() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index in range(1, 6):
        rows.extend(
            _pair(
                index,
                kickoff=TARGET - timedelta(days=20 - index * 2),
                home="team:home" if index % 2 else "team:away",
                away="team:away" if index % 2 else "team:home",
                home_goals=2 if index % 2 else 0,
                away_goals=0 if index % 2 else 1,
            )
        )
    return build_pit_history_manifest(
        rows,
        target_fixture_id="api_football:target",
        target_kickoff=TARGET,
        feature_as_of=TARGET,
        team_identity_namespace=TEAM_NS,
    )


def test_f3_f6_f7_share_verified_pit_manifest_and_remain_unadmitted() -> None:
    snapshot = build_pit_feature_snapshot(
        _manifest(),
        home_team_id="team:home",
        away_team_id="team:away",
        team_identity_namespace=TEAM_NS,
        rating_policy=POLICY,
    )

    factors = snapshot["factors"]
    assert set(factors) == {"F3_REST_FITNESS", "F6_H2H", "F7_STRENGTH_FORM"}
    assert all(factor["status"] == "READY" for factor in factors.values())
    assert all(factor["numeric_effect_enabled"] is False for factor in factors.values())
    assert all(factor["normalization_version"] == "UNFITTED" for factor in factors.values())
    assert all(factor["imputation_applied"] is False for factor in factors.values())
    assert factors["F3_REST_FITNESS"]["coverage_status"] == "PARTIAL_COVERAGE"
    assert factors["F6_H2H"]["meeting_count"] == 5
    assert factors["F6_H2H"]["value"] == 1.6
    assert factors["F7_STRENGTH_FORM"]["home_match_count"] == 5
    assert snapshot["numeric_effect_enabled"] is False
    assert snapshot["candidate_eligible"] is False
    assert snapshot["notification_eligible"] is False


def test_feature_snapshot_rejects_tampered_history_manifest() -> None:
    manifest = _manifest()
    manifest["source_fixtures"][0]["home_goals"] = 99

    with pytest.raises(ValueError, match="MANIFEST_HASH_MISMATCH"):
        build_pit_feature_snapshot(
            manifest,
            home_team_id="team:home",
            away_team_id="team:away",
            team_identity_namespace=TEAM_NS,
            rating_policy=POLICY,
        )


def test_feature_snapshot_keeps_missing_distinct_from_neutral_zero() -> None:
    manifest = build_pit_history_manifest(
        [],
        target_fixture_id="api_football:target",
        target_kickoff=TARGET,
        feature_as_of=TARGET,
        team_identity_namespace=TEAM_NS,
    )

    snapshot = build_pit_feature_snapshot(
        manifest,
        home_team_id="team:home",
        away_team_id="team:away",
        team_identity_namespace=TEAM_NS,
        rating_policy=POLICY,
    )

    assert all(factor["missing"] is True for factor in snapshot["factors"].values())
    assert all(factor["value"] is None for factor in snapshot["factors"].values())
    assert all(factor["missing_reason"] for factor in snapshot["factors"].values())


def test_recursive_rating_is_order_independent_within_same_kickoff_batch() -> None:
    same_time = TARGET - timedelta(days=5)
    rows = (
        _pair(1, kickoff=same_time, home="team:home", away="team:x", home_goals=2, away_goals=0)
        + _pair(2, kickoff=same_time, home="team:y", away="team:away", home_goals=0, away_goals=1)
    )
    first = build_pit_history_manifest(
        rows,
        target_fixture_id="api_football:target",
        target_kickoff=TARGET,
        feature_as_of=TARGET,
        team_identity_namespace=TEAM_NS,
    )
    second = build_pit_history_manifest(
        list(reversed(rows)),
        target_fixture_id="api_football:target",
        target_kickoff=TARGET,
        feature_as_of=TARGET,
        team_identity_namespace=TEAM_NS,
    )

    assert build_pit_feature_snapshot(
        first,
        home_team_id="team:home",
        away_team_id="team:away",
        team_identity_namespace=TEAM_NS,
        rating_policy=POLICY,
    ) == build_pit_feature_snapshot(
        second,
        home_team_id="team:home",
        away_team_id="team:away",
        team_identity_namespace=TEAM_NS,
        rating_policy=POLICY,
    )
