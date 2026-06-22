from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from w2.matchday.timezone import (
    BeijingOperationalDayPolicy,
    FixtureOperationalDateResolver,
    OperationalDayWindow,
)

MISSING_REASONS = {
    "INCLUDED",
    "OUTSIDE_BEIJING_OPERATIONAL_DAY",
    "COMPETITION_FILTERED",
    "STATUS_FILTERED",
    "PROVIDER_MAPPING_MISSING",
    "DUPLICATE_FIXTURE",
    "NORMALIZATION_FAILED",
    "DATABASE_WRITE_MISSING",
    "READ_MODEL_PROJECTION_MISSING",
    "DASHBOARD_FILTERED",
    "MISSED_PREMATCH_WINDOW",
    "DATA_BLOCKED",
}


@dataclass(frozen=True)
class FixtureSetCounts:
    authoritative_count: int
    normalized_count: int
    database_count: int
    discovered_count: int
    eligible_count: int
    card_count: int
    read_model_count: int
    displayed_count: int


class MatchdayCoverageReconciler:
    def __init__(self) -> None:
        self.resolver = FixtureOperationalDateResolver()

    def reconcile(
        self,
        *,
        window: OperationalDayWindow,
        authoritative_fixtures: list[dict[str, Any]],
        cards: list[dict[str, Any]],
        read_model_fixtures: list[dict[str, Any]],
        displayed_fixtures: list[dict[str, Any]] | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        now = (now_utc or datetime.now(UTC)).astimezone(UTC)
        card_ids = {str(item.get("fixture", {}).get("fixture_id")) for item in cards}
        read_ids = {str(item.get("fixture_id")) for item in read_model_fixtures}
        displayed = displayed_fixtures if displayed_fixtures is not None else read_model_fixtures
        displayed_ids = {str(item.get("fixture_id")) for item in displayed}
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        eligible_count = 0
        for fixture in authoritative_fixtures:
            fixture_id = str(fixture.get("fixture_id") or fixture.get("id"))
            kickoff = self._parse_utc(str(fixture["kickoff_utc"]))
            annotation = self.resolver.annotate(kickoff)
            reason = "INCLUDED"
            evidence: list[str] = []
            if fixture_id in seen:
                reason = "DUPLICATE_FIXTURE"
            elif not window.contains(kickoff):
                reason = "OUTSIDE_BEIJING_OPERATIONAL_DAY"
            elif fixture.get("competition_filtered") is True:
                reason = "COMPETITION_FILTERED"
            elif fixture.get("status_filtered") is True:
                reason = "STATUS_FILTERED"
            elif fixture.get("provider_mapping_missing") is True:
                reason = "PROVIDER_MAPPING_MISSING"
            elif fixture.get("normalization_failed") is True:
                reason = "NORMALIZATION_FAILED"
            elif fixture_id not in read_ids:
                reason = "READ_MODEL_PROJECTION_MISSING"
            elif fixture_id not in displayed_ids:
                reason = "DASHBOARD_FILTERED"
            elif fixture_id not in card_ids and kickoff <= now:
                reason = "MISSED_PREMATCH_WINDOW"
            elif fixture_id not in card_ids:
                reason = "DATA_BLOCKED"
            else:
                eligible_count += 1
                evidence.append("card_and_read_model_present")
            seen.add(fixture_id)
            if reason not in MISSING_REASONS:
                raise ValueError(f"invalid missing reason: {reason}")
            rows.append(
                {
                    "fixture_id": fixture_id,
                    "competition": fixture.get("competition"),
                    "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
                    **annotation,
                    "reason": reason,
                    "evidence": evidence or [reason.lower()],
                }
            )
        counts = FixtureSetCounts(
            authoritative_count=len(authoritative_fixtures),
            normalized_count=len(read_model_fixtures),
            database_count=len(read_model_fixtures),
            discovered_count=len(cards),
            eligible_count=eligible_count,
            card_count=len(cards),
            read_model_count=len(read_model_fixtures),
            displayed_count=len(displayed),
        )
        reason_distribution = dict(Counter(row["reason"] for row in rows))
        missing_count = sum(1 for row in rows if row["reason"] != "INCLUDED")
        no_silent_loss = (
            len(rows) == len(authoritative_fixtures)
            and "UNKNOWN" not in reason_distribution
        )
        ready = (
            no_silent_loss
            and counts.read_model_count == counts.displayed_count
            and all(row["reason"] in MISSING_REASONS for row in rows)
        )
        if not ready:
            status = "BLOCKED"
        elif missing_count:
            status = "PARTIAL"
        else:
            status = "READY"
        return {
            **window.as_dict(),
            **counts.__dict__,
            "missing_count": missing_count,
            "reason_distribution": reason_distribution,
            "coverage_status": status,
            "fixtures": rows,
            "timezone": "Asia/Shanghai",
        }

    def _parse_utc(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("kickoff_utc must be timezone-aware")
        return parsed.astimezone(UTC)


class MatchdayCoverageAudit:
    def __init__(self, *, policy: BeijingOperationalDayPolicy | None = None) -> None:
        self.policy = policy or BeijingOperationalDayPolicy()
        self.reconciler = MatchdayCoverageReconciler()

    def audit(
        self,
        *,
        local_date: str,
        authoritative_fixtures: list[dict[str, Any]],
        cards: list[dict[str, Any]],
        read_model_fixtures: list[dict[str, Any]],
        displayed_fixtures: list[dict[str, Any]] | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        window = self.policy.window_for_date(datetime.fromisoformat(local_date).date())
        return self.reconciler.reconcile(
            window=window,
            authoritative_fixtures=authoritative_fixtures,
            cards=cards,
            read_model_fixtures=read_model_fixtures,
            displayed_fixtures=displayed_fixtures,
            now_utc=now_utc,
        )
