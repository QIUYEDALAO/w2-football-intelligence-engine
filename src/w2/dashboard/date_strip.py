from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from w2.dashboard.date_window import football_day_for_kickoff

FINISHED_STATUSES = {"FT", "AET", "PEN", "FINISHED"}
ACTIVE_WHITELIST_COUNT = 13
WINDOW_RADIUS_DAYS = 7


def build_persisted_date_strip(
    selected_date: date,
    *,
    fixtures: Iterable[Mapping[str, Any]],
    odds_plans: Iterable[Mapping[str, Any]],
    market_evidence_fixture_ids: set[str],
    as_of: datetime,
) -> list[dict[str, Any]]:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    reference = as_of.astimezone(UTC)
    fixtures_by_day: dict[date, list[Mapping[str, Any]]] = defaultdict(list)
    for fixture in fixtures:
        kickoff = fixture.get("kickoff_utc")
        if not isinstance(kickoff, datetime):
            continue
        normalized_kickoff = kickoff.replace(tzinfo=UTC) if kickoff.tzinfo is None else kickoff
        fixtures_by_day[football_day_for_kickoff(normalized_kickoff)].append(fixture)

    first_odds_plan: dict[str, datetime] = {}
    for plan in odds_plans:
        if "odds" not in {str(item) for item in plan.get("endpoints") or []}:
            continue
        fixture_id = str(plan.get("fixture_id") or "")
        scheduled_at = plan.get("scheduled_at")
        if not fixture_id or not isinstance(scheduled_at, datetime):
            continue
        scheduled = (
            scheduled_at.replace(tzinfo=UTC)
            if scheduled_at.tzinfo is None
            else scheduled_at.astimezone(UTC)
        )
        current = first_odds_plan.get(fixture_id)
        if current is None or scheduled < current:
            first_odds_plan[fixture_id] = scheduled

    entries: list[dict[str, Any]] = []
    for offset in range(-WINDOW_RADIUS_DAYS, WINDOW_RADIUS_DAYS + 1):
        football_day = selected_date + timedelta(days=offset)
        day_fixtures = fixtures_by_day.get(football_day, [])
        fixture_ids = {str(row.get("fixture_id") or "") for row in day_fixtures}
        evidence_count = len(fixture_ids & market_evidence_fixture_ids)
        finished_count = sum(
            str(row.get("fixture_status") or "").upper() in FINISHED_STATUSES
            for row in day_fixtures
        )
        competition_count = len(
            {str(row.get("competition_id") or "") for row in day_fixtures}
            - {""}
        )
        collection_status = _collection_status(
            fixture_ids=fixture_ids,
            first_odds_plan=first_odds_plan,
            evidence_count=evidence_count,
            reference=reference,
        )
        entries.append(
            {
                "football_day": football_day.isoformat(),
                "fixture_count": len(day_fixtures),
                "competition_count": competition_count,
                "finished_fixture_count": finished_count,
                "upcoming_fixture_count": len(day_fixtures) - finished_count,
                "persisted_inventory_status": (
                    "PERSISTED_FIXTURES_AVAILABLE"
                    if day_fixtures
                    else "EMPTY_PERSISTED_DAY"
                ),
                "persisted_competition_coverage_count": competition_count,
                "active_whitelist_count": ACTIVE_WHITELIST_COUNT,
                "market_collection_window_status": collection_status,
                "market_evidence_fixture_count": evidence_count,
                "display_state": (
                    "FINISHED"
                    if day_fixtures and finished_count == len(day_fixtures)
                    else collection_status
                ),
            }
        )
    return entries


def next_available_date(
    selected_date: date,
    date_strip: Iterable[Mapping[str, Any]],
) -> str | None:
    return next(
        (
            str(entry["football_day"])
            for entry in date_strip
            if date.fromisoformat(str(entry["football_day"])) > selected_date
            and int(entry.get("fixture_count") or 0) > 0
        ),
        None,
    )


def _collection_status(
    *,
    fixture_ids: set[str],
    first_odds_plan: Mapping[str, datetime],
    evidence_count: int,
    reference: datetime,
) -> str:
    if not fixture_ids:
        return "EMPTY_PERSISTED_DAY"
    if evidence_count:
        return "MARKET_EVIDENCE_AVAILABLE"
    scheduled = [first_odds_plan[item] for item in fixture_ids if item in first_odds_plan]
    if any(item <= reference for item in scheduled):
        return "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY"
    if scheduled:
        return "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW"
    return "MARKET_COLLECTION_PLAN_NOT_PERSISTED"
