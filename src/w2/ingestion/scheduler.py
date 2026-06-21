from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from w2.domain.time import require_utc

SNAPSHOT_PHASES = (
    "T-72h",
    "T-48h",
    "T-24h",
    "T-12h",
    "T-6h",
    "T-3h",
    "T-1h",
    "T-30m",
    "T-10m",
    "Closing",
)

PHASE_OFFSETS = {
    "T-72h": timedelta(hours=72),
    "T-48h": timedelta(hours=48),
    "T-24h": timedelta(hours=24),
    "T-12h": timedelta(hours=12),
    "T-6h": timedelta(hours=6),
    "T-3h": timedelta(hours=3),
    "T-1h": timedelta(hours=1),
    "T-30m": timedelta(minutes=30),
    "T-10m": timedelta(minutes=10),
    "Closing": timedelta(minutes=0),
}


@dataclass(frozen=True)
class SnapshotJob:
    fixture_id: str
    phase: str
    scheduled_for: datetime
    priority: int
    closing: bool


def build_snapshot_schedule(fixture_id: str, kickoff_at: datetime) -> list[SnapshotJob]:
    kickoff_utc = require_utc(kickoff_at, "kickoff_at")
    jobs: list[SnapshotJob] = []
    for index, phase in enumerate(SNAPSHOT_PHASES, start=1):
        jobs.append(
            SnapshotJob(
                fixture_id=fixture_id,
                phase=phase,
                scheduled_for=(kickoff_utc - PHASE_OFFSETS[phase]).astimezone(UTC),
                priority=index,
                closing=phase == "Closing",
            )
        )
    return jobs

