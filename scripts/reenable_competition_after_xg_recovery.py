from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.competitions.seed import _hash as stable_hash
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import TeamXgMatchModel
from w2.infrastructure.persistence.league_models import (
    LeagueProfileModel,
    LeagueReadinessAuditModel,
    LeagueSeasonModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayFixtureIdentityModel,
)
from w2.matchday.intake_v2 import CheckpointPlan

DISABLED_BLOCKER = "COMPETITION_DISABLED_NO_XG_COVERAGE"
APPROVED_COMPETITION_ID = "allsvenskan"
PROTECTED_DISABLED_COMPETITION_ID = "chinese_super_league"
MIN_COVERAGE_PERCENT = 70.0
MAX_NEWEST_XG_AGE = timedelta(days=7)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _require_sha256(name: str, value: str | None) -> str:
    if value is None or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name}_REQUIRED_AS_SHA256")
    return value


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _current_season(
    session: Session, competition_id: str, *, for_update: bool = False
) -> LeagueSeasonModel | None:
    profile = session.scalar(
        select(LeagueProfileModel).where(LeagueProfileModel.competition_id == competition_id)
    )
    current_season = str(dict(profile.payload or {}).get("current_season") or "") if profile else ""
    statement = select(LeagueSeasonModel).where(LeagueSeasonModel.competition_id == competition_id)
    if current_season:
        statement = statement.where(LeagueSeasonModel.season == current_season)
    statement = statement.order_by(LeagueSeasonModel.season.desc())
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def recover_competition(
    *,
    competition_id: str,
    apply: bool,
    updated_by: str,
    now: datetime | None = None,
    engine: Engine | None = None,
    production_decision_id: str | None = None,
    deployment_evidence_sha256: str | None = None,
    backfill_evidence_sha256: str | None = None,
    capacity_evidence_sha256: str | None = None,
    expected_reopen_plan_count: int | None = None,
    expected_reopen_plan_set_sha256: str | None = None,
) -> dict[str, Any]:
    if competition_id != APPROVED_COMPETITION_ID:
        raise ValueError(f"COMPETITION_NOT_OWNER_APPROVED:{competition_id}")
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(days=30)
    resolved_engine = engine or create_engine()
    with Session(resolved_engine) as session:
        season = _current_season(session, competition_id, for_update=True)
        if season is None:
            raise ValueError(f"COMPETITION_NOT_REGISTERED:{competition_id}")
        if dict(season.payload or {}).get("enabled") is True:
            raise ValueError(f"COMPETITION_ALREADY_ENABLED:{competition_id}")
        protected_season = _current_season(session, PROTECTED_DISABLED_COMPETITION_ID)
        if protected_season is None:
            raise ValueError("PROTECTED_COMPETITION_NOT_REGISTERED")
        if dict(protected_season.payload or {}).get("enabled") is not False:
            raise ValueError("PROTECTED_COMPETITION_MUST_REMAIN_DISABLED")

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
        covered_ids = (
            set(
                session.scalars(
                    select(TeamXgMatchModel.fixture_id)
                    .where(TeamXgMatchModel.fixture_id.in_(provider_ids))
                    .group_by(TeamXgMatchModel.fixture_id)
                    .having(func.count(TeamXgMatchModel.id) == 2)
                )
            )
            if provider_ids
            else set()
        )
        coverage = 100.0 * len(covered_ids) / len(provider_ids) if provider_ids else 0.0
        newest_xg = (
            session.scalar(
                select(func.max(TeamXgMatchModel.kickoff_at)).where(
                    TeamXgMatchModel.fixture_id.in_(provider_ids)
                )
            )
            if provider_ids
            else None
        )
        if coverage < MIN_COVERAGE_PERCENT:
            raise ValueError(f"XG_COVERAGE_BELOW_GATE:{coverage:.1f}")
        if newest_xg is None or current - _as_utc(newest_xg) > MAX_NEWEST_XG_AGE:
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
        plans = [row for row in plans if list(row.blockers or []) == [DISABLED_BLOCKER]]
        plan_ids = sorted(row.plan_id for row in plans)
        result = {
            "competition_id": competition_id,
            "coverage_30d": {
                "covered": len(covered_ids),
                "finished": len(provider_ids),
                "percent": coverage,
            },
            "newest_xg_kickoff": _as_utc(newest_xg).isoformat(),
            "reopen_plan_count": len(plans),
            "reopen_plan_set_sha256": stable_hash(plan_ids),
            "apply": apply,
        }
        if not apply:
            session.rollback()
            return result

        if not production_decision_id:
            raise ValueError("PRODUCTION_DECISION_ID_REQUIRED")
        deployment_hash = _require_sha256("DEPLOYMENT_EVIDENCE_SHA256", deployment_evidence_sha256)
        backfill_hash = _require_sha256("BACKFILL_EVIDENCE_SHA256", backfill_evidence_sha256)
        capacity_hash = _require_sha256("CAPACITY_EVIDENCE_SHA256", capacity_evidence_sha256)
        if expected_reopen_plan_count is None:
            raise ValueError("EXPECTED_REOPEN_PLAN_COUNT_REQUIRED")
        if len(plans) != expected_reopen_plan_count:
            raise ValueError(f"REOPEN_PLAN_COUNT_DRIFT:{len(plans)}:{expected_reopen_plan_count}")
        expected_plan_hash = _require_sha256(
            "EXPECTED_REOPEN_PLAN_SET_SHA256", expected_reopen_plan_set_sha256
        )
        if result["reopen_plan_set_sha256"] != expected_plan_hash:
            raise ValueError("REOPEN_PLAN_SET_DRIFT")

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
            "schema_version": "w2.competition_xg_recovery.v2",
            "action": "REENABLE_AFTER_XG_RECOVERY",
            "updated_by": updated_by,
            "updated_at": current.isoformat(),
            "production_decision_id": production_decision_id,
            "deployment_evidence_sha256": deployment_hash,
            "backfill_evidence_sha256": backfill_hash,
            "capacity_evidence_sha256": capacity_hash,
            "reopened_plan_ids": plan_ids,
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
    parser.add_argument("--production-decision-id")
    parser.add_argument("--deployment-evidence-sha256")
    parser.add_argument("--backfill-evidence-sha256")
    parser.add_argument("--capacity-evidence-sha256")
    parser.add_argument("--expected-reopen-plan-count", type=int)
    parser.add_argument("--expected-reopen-plan-set-sha256")
    args = parser.parse_args()
    print(
        json.dumps(
            recover_competition(
                competition_id=args.competition_id,
                apply=args.apply,
                updated_by=args.updated_by,
                production_decision_id=args.production_decision_id,
                deployment_evidence_sha256=args.deployment_evidence_sha256,
                backfill_evidence_sha256=args.backfill_evidence_sha256,
                capacity_evidence_sha256=args.capacity_evidence_sha256,
                expected_reopen_plan_count=args.expected_reopen_plan_count,
                expected_reopen_plan_set_sha256=args.expected_reopen_plan_set_sha256,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
