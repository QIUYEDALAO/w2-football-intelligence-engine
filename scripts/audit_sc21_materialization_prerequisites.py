#!/usr/bin/env python3
"""Audit rating and TeamValue materialization prerequisites without writes."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from w2.factor_model.remediation import MODEL_VERSION
from w2.features.team_factors import TeamMatchHistory
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
    TeamRatingSnapshotModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import (
    PlayerClubMembershipObservationModel,
    PlayerIdentityMappingModel,
    PlayerValuationObservationModel,
    RegisteredRosterSnapshotModel,
    TeamValueAsOfArtifactModel,
)
from w2.matchday.intake_v2 import REQUIRED_MATCHDAY_COMPETITIONS, stable_hash
from w2.ratings.elo import rating_from_history


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def build_audit(*, start: datetime, end: datetime) -> dict[str, Any]:
    engine = create_engine()
    exact13 = sorted(REQUIRED_MATCHDAY_COMPETITIONS)
    with Session(engine) as session:
        fixtures = list(
            session.scalars(
                select(MatchdayFixtureIdentityModel)
                .where(
                    MatchdayFixtureIdentityModel.provider == "api_football",
                    MatchdayFixtureIdentityModel.competition_id.in_(exact13),
                    MatchdayFixtureIdentityModel.kickoff_utc >= start,
                    MatchdayFixtureIdentityModel.kickoff_utc < end,
                )
                .order_by(MatchdayFixtureIdentityModel.kickoff_utc)
            )
        )
        teams = {
            row.w2_team_id: row.display_name for row in session.scalars(select(CanonicalTeamModel))
        }
        histories = list(
            session.scalars(
                select(CanonicalTeamMatchHistoryModel)
                .where(CanonicalTeamMatchHistoryModel.competition_id.in_(exact13))
                .order_by(
                    CanonicalTeamMatchHistoryModel.team_w2_id,
                    CanonicalTeamMatchHistoryModel.kickoff_utc,
                )
            )
        )
        history_by_team: dict[str, list[CanonicalTeamMatchHistoryModel]] = defaultdict(list)
        for row in histories:
            history_by_team[row.team_w2_id].append(row)

        rating_plan: list[dict[str, Any]] = []
        for team_id, rows in sorted(history_by_team.items()):
            history = [
                TeamMatchHistory(
                    team_id=row.team_w2_id,
                    opponent_id=row.opponent_w2_id,
                    kickoff_at=_utc(row.kickoff_utc),
                    goals_for=row.goals_for,
                    goals_against=row.goals_against,
                    source="canonical_team_match_history",
                    source_group="team_fixture_history",
                    is_independent_signal=True,
                    collection_status="READY",
                    result_identity_hash=row.result_identity_hash,
                )
                for row in rows
            ]
            rating = rating_from_history(
                team_id=team_id,
                history=history,
                as_of=end,
                min_matches=2,
            )
            if rating is None:
                continue
            payload = {
                "w2_team_id": team_id,
                "observed_at": _utc(rating.observed_at).isoformat().replace("+00:00", "Z"),
                "model_version": MODEL_VERSION,
                "elo": round(rating.elo, 6),
                "attack_strength": round(rating.attack_strength, 6),
                "defence_strength": round(rating.defence_strength, 6),
                "form_index": round(rating.form_index, 6),
                "source_history_hashes": [row.history_hash for row in rows],
            }
            rating_plan.append(
                {
                    "team_id": team_id,
                    "team_name": teams.get(team_id),
                    "rating_hash": stable_hash(payload),
                    "history_count": len(rows),
                    "source": MODEL_VERSION,
                }
            )

        existing_ratings = list(
            session.scalars(
                select(TeamRatingSnapshotModel).order_by(
                    TeamRatingSnapshotModel.w2_team_id,
                    TeamRatingSnapshotModel.observed_at,
                )
            )
        )
        existing_hashes = {row.rating_hash for row in existing_ratings}
        fixture_team_pairs = [
            (row.home_w2_team_id, row.away_w2_team_id)
            for row in fixtures
            if row.home_w2_team_id and row.away_w2_team_id
        ]
        rated_teams = {row.w2_team_id for row in existing_ratings if _utc(row.observed_at) < end}
        transfermarkt_crosswalks = list(
            session.scalars(
                select(ProviderTeamIdentityCrosswalkModel).where(
                    ProviderTeamIdentityCrosswalkModel.provider == "transfermarkt",
                    ProviderTeamIdentityCrosswalkModel.competition_id.in_(exact13),
                )
            )
        )
        counts = {
            "player_valuation_rows": int(
                session.scalar(select(func.count()).select_from(PlayerValuationObservationModel))
                or 0
            ),
            "player_identity_mapping_rows": int(
                session.scalar(select(func.count()).select_from(PlayerIdentityMappingModel)) or 0
            ),
            "registered_roster_rows": int(
                session.scalar(select(func.count()).select_from(RegisteredRosterSnapshotModel)) or 0
            ),
            "club_membership_rows": int(
                session.scalar(
                    select(func.count()).select_from(PlayerClubMembershipObservationModel)
                )
                or 0
            ),
            "team_value_artifact_rows": int(
                session.scalar(select(func.count()).select_from(TeamValueAsOfArtifactModel)) or 0
            ),
        }

    new_rating_plan = [row for row in rating_plan if row["rating_hash"] not in existing_hashes]
    team_value_ready = bool(
        counts["registered_roster_rows"]
        and counts["club_membership_rows"]
        and transfermarkt_crosswalks
    )
    team_value_plan: list[dict[str, Any]] = []
    return {
        "schema_version": "w2.sc21-materialization-prerequisites.v1",
        "provider_calls": 0,
        "database_writes": 0,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "exact13": exact13,
        "fixture_count": len(fixtures),
        "rating": {
            "source_authority": "canonical_team_match_history -> internal_elo_v1",
            "rolling_xg_proxy_excluded": True,
            "proxy_only_excluded": True,
            "natural_result_to_elo_refresh": False,
            "refresh_authority": "controlled FactorModelRemediationService.materialize_ratings",
            "existing_snapshot_count": len(existing_ratings),
            "materializable_team_count": len(rating_plan),
            "materializable_set_sha256": stable_hash(rating_plan),
            "new_snapshot_candidate_count": len(new_rating_plan),
            "new_snapshot_candidate_set_sha256": stable_hash(new_rating_plan),
            "future_fixture_bilateral_coverage": sum(
                1
                for home, away in fixture_team_pairs
                if home in rated_teams and away in rated_teams
            ),
            "future_fixture_count": len(fixtures),
            "plan": rating_plan,
        },
        "team_value": {
            **counts,
            "reviewed_transfermarkt_team_crosswalk_rows": sum(
                1
                for row in transfermarkt_crosswalks
                if row.review_status in {"REVIEWED", "APPROVED"}
                and row.reviewed_by
                and row.reviewed_at
            ),
            "materializer": "w2.lineups.value_identity.materialize_team_value_asof",
            "materialization_status": (
                "PREREQUISITES_READY"
                if team_value_ready
                else "IDENTITY_OR_ROSTER_PREREQUISITES_MISSING"
            ),
            "expected_artifact_count": len(team_value_plan),
            "expected_artifact_set_sha256": stable_hash(team_value_plan),
            "write_authorized": False,
            "reason": (
                "READY"
                if team_value_ready
                else (
                    "31,507 valuation rows cannot be aggregated without reviewed team "
                    "identity and as-of roster membership."
                )
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--end", type=datetime.fromisoformat, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build_audit(start=_utc(args.start), end=_utc(args.end))
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(
            json.dumps(
                {
                    key: payload[key]
                    for key in ("provider_calls", "database_writes", "fixture_count")
                },
                sort_keys=True,
            )
        )
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
