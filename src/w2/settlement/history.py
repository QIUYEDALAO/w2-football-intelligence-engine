from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.models import (
    RecommendationLockModel,
    ResultModel,
    SettlementModel,
)
from w2.settlement.settle import settle_market

WRITE_CONFIRMATION_PHRASE = "SETTLEMENT_HISTORY_WRITE_APPROVED"  # noqa: S105


class SettlementHistoryError(ValueError):
    """Raised when settlement history automation would violate its write contract."""


@dataclass(frozen=True, kw_only=True)
class SettlementCandidate:
    lock_id: str
    recommendation_id: str
    result_id: str
    fixture_id: str
    outcome: str
    selection: str
    line: str
    tier: str | None
    movement_pattern: str | None

    def as_result(self, *, status: str) -> dict[str, Any]:
        return {
            "status": status,
            "lock_id": self.lock_id,
            "recommendation_id": self.recommendation_id,
            "result_id": self.result_id,
            "fixture_id": self.fixture_id,
            "outcome": self.outcome,
            "selection": self.selection,
            "line": self.line,
            "tier": self.tier,
            "movement_pattern": self.movement_pattern,
        }


def run_settlement_history(
    *,
    session: Session,
    dry_run: bool = True,
    write_db: bool = False,
    confirm_write: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if write_db and dry_run:
        raise SettlementHistoryError("write_db requires dry_run=false")
    if write_db and confirm_write != WRITE_CONFIRMATION_PHRASE:
        raise SettlementHistoryError("SETTLEMENT_HISTORY_WRITE_REQUIRES_CONFIRMATION")

    settled_at = now or datetime.now(UTC)
    counts: Counter[str] = Counter()
    results: list[dict[str, Any]] = []
    writes = 0

    locks = list(
        session.scalars(
            select(RecommendationLockModel).order_by(
                RecommendationLockModel.fixture_id,
                RecommendationLockModel.locked_at,
                RecommendationLockModel.id,
            )
        )
    )
    counts["inspected_locks"] = len(locks)

    for lock in locks:
        candidate = _candidate_from_lock(session, lock, counts)
        if candidate is None:
            continue
        status = "WOULD_WRITE" if dry_run or not write_db else "WRITTEN"
        results.append(candidate.as_result(status=status))
        counts["candidate_settlements"] += 1
        if write_db and not dry_run:
            session.add(
                SettlementModel(
                    recommendation_id=candidate.recommendation_id,
                    lock_id=candidate.lock_id,
                    result_id=candidate.result_id,
                    outcome=candidate.outcome,
                    settled_at=settled_at,
                    matched_recommendation=True,
                    tier=candidate.tier,
                    movement_pattern=candidate.movement_pattern,
                )
            )
            writes += 1

    if write_db and not dry_run:
        session.commit()

    return {
        "status": "PASS",
        "dry_run": dry_run,
        "write_db": write_db,
        "db_writes": writes,
        "provider_calls": 0,
        "read_only": not write_db,
        "not_a_formal_gate": True,
        "posthoc_only": True,
        "counts": dict(counts),
        "results": results,
    }


def _candidate_from_lock(
    session: Session,
    lock: RecommendationLockModel,
    counts: Counter[str],
) -> SettlementCandidate | None:
    if lock.legacy_marker_only or not lock.reproducible:
        counts["legacy_or_unreproducible_skipped"] += 1
        return None
    if not lock.fixture_id:
        counts["missing_fixture_id"] += 1
        return None
    if not lock.recommendation_id:
        counts["missing_recommendation_id"] += 1
        return None
    if not lock.pick_side or lock.pick_line is None:
        counts["missing_lock_fields"] += 1
        return None

    result = session.scalar(select(ResultModel).where(ResultModel.fixture_id == lock.fixture_id))
    if result is None:
        counts["missing_result"] += 1
        return None

    existing = session.scalar(
        select(SettlementModel.id).where(
            or_(
                SettlementModel.lock_id == lock.id,
                (
                    (SettlementModel.recommendation_id == lock.recommendation_id)
                    & (SettlementModel.result_id == result.id)
                ),
            )
        )
    )
    if existing is not None:
        counts["already_settled"] += 1
        return None

    selection = _settlement_selection(lock.pick_side)
    line = str(Decimal(lock.pick_line))
    outcome = settle_market(
        market="ASIAN_HANDICAP",
        selection=selection,
        line=line,
        home_goals_90=result.home_goals,
        away_goals_90=result.away_goals,
    )
    return SettlementCandidate(
        lock_id=lock.id,
        recommendation_id=lock.recommendation_id,
        result_id=result.id,
        fixture_id=lock.fixture_id,
        outcome=outcome,
        selection=selection,
        line=line,
        tier=lock.tier,
        movement_pattern=_movement_pattern(lock.market_timeline_json),
    )


def _settlement_selection(pick_side: str) -> str:
    normalized = pick_side.strip().upper()
    if normalized == "HOME_AH":
        return "HOME"
    if normalized == "AWAY_AH":
        return "AWAY"
    raise SettlementHistoryError(f"unsupported AH pick_side {pick_side!r}")


def _movement_pattern(value: Any) -> str | None:
    if isinstance(value, dict):
        pattern = value.get("pattern")
        return str(pattern) if pattern else None
    return None
