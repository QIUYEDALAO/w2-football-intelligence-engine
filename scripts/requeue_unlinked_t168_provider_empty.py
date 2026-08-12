from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, exists, func, select, update
from sqlalchemy.engine import Engine

from w2.competitions.league_whitelist_scope import load_league_whitelist_scope
from w2.competitions.registry import CompetitionRegistry
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCapturePlanModel,
)


@dataclass(frozen=True)
class RequeueReport:
    schema_version: str
    mode: str
    as_of: str
    matched: int
    eligible: int
    outside_window: int
    updated: int
    plan_ids: tuple[str, ...]
    plan_ids_sha256: str
    targets: tuple[dict[str, str], ...]


def requeue_unlinked_t168_provider_empty(
    engine: Engine,
    *,
    now: datetime,
    apply: bool = False,
    expected_count: int | None = None,
    expected_plan_ids_sha256: str | None = None,
) -> RequeueReport:
    if apply and (expected_count is None or expected_plan_ids_sha256 is None):
        raise ValueError("--apply requires --expected-count and --expected-plan-ids-sha256")
    if expected_count is not None and expected_count < 0:
        raise ValueError("--expected-count must be non-negative")
    current = now.astimezone(UTC)
    plans = MatchdayCheckpointPlanModel
    links = MatchdayEndpointCapturePlanModel
    competition_ids = tuple(
        load_league_whitelist_scope(CompetitionRegistry(engine)).all_whitelist
    )
    if len(competition_ids) != 13:
        raise RuntimeError(f"REQUEUE_SCOPE_NOT_EXACT_13:{len(competition_ids)}")
    unlinked_first_attempt = and_(
        plans.checkpoint == "T168_OPEN_ODDS",
        plans.status == "PROVIDER_EMPTY",
        plans.attempt_count == 1,
        plans.capture_id.is_(None),
        plans.test_only.is_(False),
        plans.namespace.is_(None),
        plans.competition_id.in_(competition_ids),
        ~exists(select(1).where(links.plan_id == plans.plan_id)),
    )

    with engine.begin() as connection:
        candidates = select(
            plans.plan_id,
            plans.fixture_id,
            plans.competition_id,
            plans.window_start,
            plans.window_end,
        ).where(unlinked_first_attempt)
        if apply:
            candidates = candidates.with_for_update()
        rows = list(connection.execute(candidates.order_by(plans.plan_id)))
        plan_ids = tuple(
            row.plan_id
            for row in rows
            if _utc(row.window_start) <= current <= _utc(row.window_end)
        )
        plan_ids_sha256 = _plan_ids_sha256(plan_ids)
        targets = tuple(
            {
                "plan_id": row.plan_id,
                "fixture_id": row.fixture_id,
                "competition_id": row.competition_id,
            }
            for row in rows
            if row.plan_id in plan_ids
        )
        if apply and len(plan_ids) != expected_count:
            raise RuntimeError(
                "REQUEUE_EXPECTED_COUNT_MISMATCH:"
                f"expected={expected_count}:actual={len(plan_ids)}"
            )
        if apply and plan_ids_sha256 != expected_plan_ids_sha256:
            raise RuntimeError(
                "REQUEUE_EXPECTED_PLAN_IDS_MISMATCH:"
                f"expected={expected_plan_ids_sha256}:actual={plan_ids_sha256}"
            )

        updated = 0
        if apply and plan_ids:
            result = connection.execute(
                update(plans)
                .where(
                    plans.plan_id.in_(plan_ids),
                    unlinked_first_attempt,
                    plans.window_start <= current,
                    plans.window_end >= current,
                )
                .values(
                    status="DUE",
                    claimed_at=None,
                    claimed_by=None,
                    claim_token=None,
                    claim_expires_at=None,
                )
            )
            updated = int(result.rowcount or 0)
            if updated != len(plan_ids):
                raise RuntimeError(
                    f"REQUEUE_UPDATE_COUNT_MISMATCH:expected={len(plan_ids)}:actual={updated}"
                )
            verified = int(
                connection.scalar(
                    select(func.count())
                    .select_from(plans)
                    .where(
                        plans.plan_id.in_(plan_ids),
                        plans.status == "DUE",
                        plans.claimed_at.is_(None),
                        plans.claimed_by.is_(None),
                        plans.claim_token.is_(None),
                        plans.claim_expires_at.is_(None),
                        plans.attempt_count == 1,
                        plans.capture_id.is_(None),
                        ~exists(select(1).where(links.plan_id == plans.plan_id)),
                    )
                )
                or 0
            )
            if verified != updated:
                raise RuntimeError(
                    f"REQUEUE_POSTCONDITION_FAILED:expected={updated}:actual={verified}"
                )

    return RequeueReport(
        schema_version="w2.t168_zero_call_requeue.v1",
        mode="APPLY" if apply else "DRY_RUN",
        as_of=current.isoformat().replace("+00:00", "Z"),
        matched=len(rows),
        eligible=len(plan_ids),
        outside_window=len(rows) - len(plan_ids),
        updated=updated,
        plan_ids=plan_ids,
        plan_ids_sha256=plan_ids_sha256,
        targets=targets,
    )


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _plan_ids_sha256(plan_ids: Sequence[str]) -> str:
    return hashlib.sha256(("\n".join(plan_ids) + "\n").encode()).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or explicitly requeue the bounded unlinked T168 failure set."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--expected-plan-ids-sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.apply and (
        args.expected_count is None or args.expected_plan_ids_sha256 is None
    ):
        raise SystemExit("--apply requires --expected-count and --expected-plan-ids-sha256")
    engine = create_engine()
    report = requeue_unlinked_t168_provider_empty(
        engine,
        now=datetime.now(UTC),
        apply=args.apply,
        expected_count=args.expected_count,
        expected_plan_ids_sha256=args.expected_plan_ids_sha256,
    )
    print(json.dumps(asdict(report), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
