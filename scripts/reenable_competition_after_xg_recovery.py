from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from w2.competitions.seed import _hash as stable_hash
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import TeamXgMatchModel
from w2.infrastructure.persistence.league_models import (
    LeagueReadinessAuditModel,
    LeagueSeasonModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayFixtureIdentityModel,
)
from w2.matchday.intake_v2 import CheckpointPlan

DISABLED_BLOCKER = "COMPETITION_DISABLED_NO_XG_COVERAGE"
MIN_COVERAGE_PERCENT = 70.0
MAX_NEWEST_XG_AGE = timedelta(days=7)


def recover_competition(
    *,
    competition_id: str,
    apply: bool,
    updated_by: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(days=30)
    engine = create_engine()
    with Session(engine) as session:
        season = session.scalar(
            select(LeagueSeasonModel)
            .where(LeagueSeasonModel.competition_id == competition_id)
            .order_by(LeagueSeasonModel.season.desc())
            .with_for_update()
        )
        if season is None:
            raise ValueError(f"COMPETITION_NOT_REGISTERED:{competition_id}")
        if dict(season.payload or {}).get("enabled") is True:
            raise ValueError(f"COMPETITION_ALREADY_ENABLED:{competition_id}")

        fixtures = list(
            session.scalars(
                select(MatchdayFixtureIdentityModel).where(
                    MatchdayFixtureIdentityModel.competition_id == competition_id,
                    MatchdayFixtureIdentityModel.kickoff_utc >= cutoff,
                    MatchdayFixtureIdentityModel.kickoff_utc < current,
                    MatchdayFixtureIdentityModel.fixture_status.in_(("FT", "AET", "PEN")),
                )
            )
        )
        provider_ids = {row.provider_fixture_id for row in fixtures}
        covered_ids = set(
            session.scalars(
                select(TeamXgMatchModel.fixture_id)
                .where(TeamXgMatchModel.fixture_id.in_(provider_ids))
                .group_by(TeamXgMatchModel.fixture_id)
                .having(func.count(TeamXgMatchModel.id) == 2)
            )
        ) if provider_ids else set()
        coverage = 100.0 * len(covered_ids) / len(provider_ids) if provider_ids else 0.0
        newest_xg = session.scalar(
            select(func.max(TeamXgMatchModel.kickoff_at)).where(
                TeamXgMatchModel.fixture_id.in_(provider_ids)
            )
        ) if provider_ids else None
        if coverage < MIN_COVERAGE_PERCENT:
            raise ValueError(f"XG_COVERAGE_BELOW_GATE:{coverage:.1f}")
        if newest_xg is None or current - newest_xg > MAX_NEWEST_XG_AGE:
            raise ValueError("XG_NEWEST_EVIDENCE_STALE")

        plans = list(
            session.scalars(
                select(MatchdayCheckpointPlanModel)
                .where(
                    MatchdayCheckpointPlanModel.competition_id == competition_id,
                    MatchdayCheckpointPlanModel.status == "SKIPPED_POLICY",
                    MatchdayCheckpointPlanModel.window_end > current,
                )
                .with_for_update()
            )
        )
        plans = [row for row in plans if DISABLED_BLOCKER in list(row.blockers or [])]
        plan_ids = sorted(row.plan_id for row in plans)
        result = {
            "competition_id": competition_id,
            "coverage_30d": {
                "covered": len(covered_ids),
                "finished": len(provider_ids),
                "percent": coverage,
            },
            "newest_xg_kickoff": newest_xg.isoformat(),
            "reopen_plan_count": len(plans),
            "reopen_plan_set_sha256": stable_hash(plan_ids),
            "apply": apply,
        }
        if not apply:
            session.rollback()
            return result

        payload = dict(season.payload or {})
        payload.update(
            {"enabled": True, "updated_by": updated_by, "updated_at": current.isoformat()}
        )
        payload["config_hash"] = stable_hash(
            {
                key: value
                for key, value in payload.items()
                if key not in {"config_hash", "updated_at", "updated_by"}
            }
        )
        season.payload = payload
        season.lifecycle = "ACTIVE"
        for row in plans:
            row.status = "PLANNED"
            row.blockers = [item for item in list(row.blockers or []) if item != DISABLED_BLOCKER]
            row.claimed_at = row.claimed_by = row.claim_token = row.claim_expires_at = None
            row.missed_at = None
            row.plan_hash = CheckpointPlan(
                fixture_id=row.fixture_id,
                competition_id=row.competition_id,
                season=row.season,
                policy_version=row.policy_version,
                checkpoint=row.checkpoint,
                kickoff_utc=row.kickoff_utc,
                scheduled_at=row.scheduled_at,
                window_start=row.window_start,
                window_end=row.window_end,
                endpoints=tuple(row.endpoints or []),
                status=row.status,
                blockers=tuple(row.blockers or []),
            ).plan_hash
        audit_payload = {
            "schema_version": "w2.competition_xg_recovery.v1",
            "action": "REENABLE_AFTER_XG_RECOVERY",
            "updated_by": updated_by,
            "updated_at": current.isoformat(),
            **result,
        }
        audit_hash = stable_hash(audit_payload)
        session.add(
            LeagueReadinessAuditModel(
                competition_id=competition_id,
                audit_sha256=audit_hash,
                created_at=current,
                payload=audit_payload,
            )
        )
        session.commit()
        return {**result, "audit_sha256": audit_hash}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--competition-id", required=True)
    parser.add_argument("--updated-by", default="w2-xg-capability-recovery")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(recover_competition(
        competition_id=args.competition_id,
        apply=args.apply,
        updated_by=args.updated_by,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
