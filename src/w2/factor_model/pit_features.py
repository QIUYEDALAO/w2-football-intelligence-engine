from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import groupby
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.domain.factor_registry import load_factor_registry
from w2.factor_model.history import PIT_HISTORY_MANIFEST_SCHEMA_VERSION

PIT_FEATURE_SNAPSHOT_SCHEMA_VERSION = "w2.factor_model.pit_feature_snapshot.v1"


@dataclass(frozen=True, kw_only=True)
class RecursiveRatingPolicy:
    version: str
    initial_rating: float
    k_factor: float
    home_advantage_rating: float
    rating_scale: float = 400.0

    def __post_init__(self) -> None:
        if not self.version or min(
            self.initial_rating,
            self.k_factor,
            self.rating_scale,
        ) <= 0:
            raise ValueError("PIT_RATING_POLICY_INVALID")


def build_pit_feature_snapshot(
    manifest: dict[str, Any],
    *,
    home_team_id: str,
    away_team_id: str,
    rating_policy: RecursiveRatingPolicy,
) -> dict[str, Any]:
    """Build unadmitted F3/F6/F7 raw features from one verified PIT manifest."""
    fixtures = _verified_fixtures(manifest)
    target_kickoff = _utc(manifest["target_kickoff"])
    registry = load_factor_registry("factor-model-v2")
    factors = {
        "F3_REST_FITNESS": _rest_fitness(
            fixtures,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            target_kickoff=target_kickoff,
            minimum_sample=int(registry["F3_REST_FITNESS"]["minimum_sample"]),
        ),
        "F6_H2H": _h2h(
            fixtures,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            minimum_sample=int(registry["F6_H2H"]["minimum_sample"]),
        ),
        "F7_STRENGTH_FORM": _strength_rating(
            fixtures,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            minimum_sample=int(registry["F7_STRENGTH_FORM"]["minimum_sample"]),
            policy=rating_policy,
        ),
    }
    body = {
        "schema_version": PIT_FEATURE_SNAPSHOT_SCHEMA_VERSION,
        "target_fixture_id": str(manifest["target_fixture_id"]),
        "target_kickoff": target_kickoff,
        "feature_as_of": _utc(manifest["feature_as_of"]),
        "home_team_id": str(home_team_id),
        "away_team_id": str(away_team_id),
        "pit_history_manifest_sha256": str(manifest["manifest_sha256"]),
        "rating_policy": asdict(rating_policy),
        "factors": factors,
        "numeric_effect_enabled": False,
        "candidate_eligible": False,
        "notification_eligible": False,
    }
    return {
        **body,
        "feature_snapshot_sha256": canonical_sha256(
            {"identity_type": "FACTOR_MODEL_PIT_FEATURE_SNAPSHOT", **body},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
    }


def verify_pit_feature_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    if snapshot.get("schema_version") != PIT_FEATURE_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("PIT_FEATURE_SNAPSHOT_SCHEMA_INVALID")
    expected = snapshot.get("feature_snapshot_sha256")
    body = {key: value for key, value in snapshot.items() if key != "feature_snapshot_sha256"}
    actual = canonical_sha256(
        {"identity_type": "FACTOR_MODEL_PIT_FEATURE_SNAPSHOT", **body},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )
    if expected != actual:
        raise ValueError("PIT_FEATURE_SNAPSHOT_HASH_MISMATCH")
    return snapshot


def _verified_fixtures(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != PIT_HISTORY_MANIFEST_SCHEMA_VERSION:
        raise ValueError("PIT_HISTORY_MANIFEST_SCHEMA_INVALID")
    expected = manifest.get("manifest_sha256")
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    actual = canonical_sha256(
        {"identity_type": "FACTOR_MODEL_PIT_HISTORY_MANIFEST", **body},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )
    if expected != actual:
        raise ValueError("PIT_HISTORY_MANIFEST_HASH_MISMATCH")
    fixtures = manifest.get("source_fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("PIT_HISTORY_MANIFEST_FIXTURES_INVALID")
    return fixtures


def _rest_fitness(
    fixtures: list[dict[str, Any]],
    *,
    home_team_id: str,
    away_team_id: str,
    target_kickoff: datetime,
    minimum_sample: int,
) -> dict[str, Any]:
    home = _team_fixtures(fixtures, home_team_id)
    away = _team_fixtures(fixtures, away_team_id)
    common = {
        "factor_id": "F3_REST_FITNESS",
        "minimum_sample": minimum_sample,
        "home_match_count": len(home),
        "away_match_count": len(away),
        "coverage_semantics": "LEAGUE_SCOPE_REST_FITNESS",
        "coverage_status": "PARTIAL_COVERAGE",
        "numeric_effect_enabled": False,
        **_unfitted_metadata(),
    }
    if len(home) < minimum_sample or len(away) < minimum_sample:
        return {
            **common,
            "status": "INSUFFICIENT_DATA",
            "missing": True,
            "missing_reason": "INSUFFICIENT_LEAGUE_SCOPE_HISTORY",
            "value": None,
            "raw_value": None,
        }
    home_rest = (target_kickoff - _utc(home[-1]["kickoff_utc"])).total_seconds() / 86400
    away_rest = (target_kickoff - _utc(away[-1]["kickoff_utc"])).total_seconds() / 86400
    return {
        **common,
        "status": "READY",
        "missing": False,
        "missing_reason": None,
        "value": home_rest - away_rest,
        "raw_value": home_rest - away_rest,
        "home_rest_days": home_rest,
        "away_rest_days": away_rest,
        "home_last_fixture_id": home[-1]["fixture_id"],
        "away_last_fixture_id": away[-1]["fixture_id"],
    }


def _h2h(
    fixtures: list[dict[str, Any]],
    *,
    home_team_id: str,
    away_team_id: str,
    minimum_sample: int,
) -> dict[str, Any]:
    meetings = [
        fixture
        for fixture in fixtures
        if {fixture["home_w2_team_id"], fixture["away_w2_team_id"]}
        == {home_team_id, away_team_id}
    ]
    common = {
        "factor_id": "F6_H2H",
        "minimum_sample": minimum_sample,
        "meeting_count": len(meetings),
        "numeric_effect_enabled": False,
        **_unfitted_metadata(),
    }
    if len(meetings) < minimum_sample:
        return {
            **common,
            "status": "INSUFFICIENT_DATA",
            "missing": True,
            "missing_reason": "INSUFFICIENT_H2H_HISTORY",
            "value": None,
            "raw_value": None,
        }
    diffs = [_target_home_goal_diff(row, home_team_id) for row in meetings]
    average = sum(diffs) / len(diffs)
    return {
        **common,
        "status": "READY",
        "missing": False,
        "missing_reason": None,
        "value": average,
        "raw_value": average,
        "meeting_fixture_ids": [row["fixture_id"] for row in meetings],
        "target_home_goal_diffs": diffs,
    }


def _strength_rating(
    fixtures: list[dict[str, Any]],
    *,
    home_team_id: str,
    away_team_id: str,
    minimum_sample: int,
    policy: RecursiveRatingPolicy,
) -> dict[str, Any]:
    ratings: dict[str, float] = {}
    counts: dict[str, int] = {}
    observed_at: dict[str, datetime] = {}
    for kickoff, batch_iter in groupby(fixtures, key=lambda row: _utc(row["kickoff_utc"])):
        updates: dict[str, float] = {}
        for fixture in batch_iter:
            home = str(fixture["home_w2_team_id"])
            away = str(fixture["away_w2_team_id"])
            home_rating = ratings.get(home, policy.initial_rating)
            away_rating = ratings.get(away, policy.initial_rating)
            expected_home = 1.0 / (
                1.0
                + 10
                ** (
                    (away_rating - home_rating - policy.home_advantage_rating)
                    / policy.rating_scale
                )
            )
            score_home = _home_score(fixture)
            change = policy.k_factor * (score_home - expected_home)
            updates[home] = updates.get(home, 0.0) + change
            updates[away] = updates.get(away, 0.0) - change
            counts[home] = counts.get(home, 0) + 1
            counts[away] = counts.get(away, 0) + 1
            observed_at[home] = kickoff
            observed_at[away] = kickoff
        for team_id, change in updates.items():
            ratings[team_id] = ratings.get(team_id, policy.initial_rating) + change

    home_count = counts.get(home_team_id, 0)
    away_count = counts.get(away_team_id, 0)
    common = {
        "factor_id": "F7_STRENGTH_FORM",
        "minimum_sample": minimum_sample,
        "home_match_count": home_count,
        "away_match_count": away_count,
        "rating_policy_version": policy.version,
        "numeric_effect_enabled": False,
        **_unfitted_metadata(),
    }
    if home_count < minimum_sample or away_count < minimum_sample:
        return {
            **common,
            "status": "INSUFFICIENT_DATA",
            "missing": True,
            "missing_reason": "INSUFFICIENT_RATING_HISTORY",
            "value": None,
            "raw_value": None,
        }
    home_rating = ratings[home_team_id]
    away_rating = ratings[away_team_id]
    difference = home_rating - away_rating
    return {
        **common,
        "status": "READY",
        "missing": False,
        "missing_reason": None,
        "value": difference,
        "raw_value": difference,
        "home_rating": home_rating,
        "away_rating": away_rating,
        "home_observed_at": observed_at[home_team_id],
        "away_observed_at": observed_at[away_team_id],
    }


def _team_fixtures(fixtures: list[dict[str, Any]], team_id: str) -> list[dict[str, Any]]:
    return [
        row
        for row in fixtures
        if team_id in {row["home_w2_team_id"], row["away_w2_team_id"]}
    ]


def _target_home_goal_diff(fixture: dict[str, Any], target_home_team_id: str) -> int:
    if fixture["home_w2_team_id"] == target_home_team_id:
        return int(fixture["home_goals"]) - int(fixture["away_goals"])
    return int(fixture["away_goals"]) - int(fixture["home_goals"])


def _home_score(fixture: dict[str, Any]) -> float:
    goal_diff = int(fixture["home_goals"]) - int(fixture["away_goals"])
    return 1.0 if goal_diff > 0 else 0.0 if goal_diff < 0 else 0.5


def _unfitted_metadata() -> dict[str, Any]:
    return {
        "normalized_value": None,
        "normalization_version": "UNFITTED",
        "imputation_applied": False,
        "imputation_version": None,
    }


def _utc(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("PIT_FEATURE_TIME_INVALID")
    return value.astimezone(UTC)
