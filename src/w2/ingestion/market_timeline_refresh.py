from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from w2.api.repository import ReadModelRepository
from w2.ingestion.market_timeline import (
    DEFAULT_TIMELINE_DIR,
    due_checkpoints,
    parse_utc,
    select_mainline_snapshot_result,
    write_timeline_snapshot,
)
from w2.ingestion.quota_budget import independent_signal_quota_decision


class MarketTimelineRepository(Protocol):
    def fixture_payloads(self) -> list[dict[str, Any]]: ...

    def future_market_observations(self) -> list[dict[str, Any]]: ...

    def future_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]: ...


def run_market_timeline_refresh(
    *,
    window: str = "next36",
    checkpoint: str = "auto",
    dry_run: bool = True,
    write_artifacts: bool = False,
    max_fixtures: int | None = None,
    runtime_root: Path | None = None,
    remaining_quota_override: str | None = None,
    network_quota_required: bool = False,
    repository: MarketTimelineRepository | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = (now or datetime.now(UTC)).astimezone(UTC)
    root = runtime_root or default_market_timeline_runtime_root()
    quota = independent_signal_quota_decision(
        remaining_quota=remaining_quota_override,
        task_type="market_timeline_backfill",
    )
    if (
        network_quota_required
        and write_artifacts
        and not dry_run
        and quota.get("allowed") is not True
    ):
        blocker = quota.get("blocker") or quota.get("reason") or "BACKFILL_QUOTA_GUARD"
        return {
            "status": "BLOCKED",
            "blockers": [blocker],
            "network_quota_required": True,
            "dry_run": bool(dry_run),
            "write_artifacts": bool(write_artifacts),
            "window": window,
            "checkpoint": checkpoint,
            "max_fixtures": max_fixtures,
            "runtime_root": str(root),
            "provider_calls": 0,
            "quota_decision": quota,
            "selected_fixtures": [],
            "fixture_count": 0,
            "observation_count": 0,
            "snapshot_candidates": 0,
            "freshness_rejections": 0,
            "written": 0,
            "already_locked": 0,
            "immutable_conflicts": 0,
            "results": [],
        }
    repo = repository or ReadModelRepository()
    fixtures = _window_fixtures(repo.fixture_payloads(), window=window, now=resolved_now)
    if max_fixtures is not None:
        fixtures = fixtures[: max(max_fixtures, 0)]
    fixture_ids = [str(item["fixture_id"]) for item in fixtures]
    observations = (
        repo.future_market_observations_for_fixtures(fixture_ids) if fixture_ids else []
    )
    results: list[dict[str, Any]] = []
    written = 0
    already_locked = 0
    immutable_conflicts = 0
    freshness_rejections = 0
    for fixture in fixtures:
        kickoff = fixture["kickoff"]
        for due_checkpoint in due_checkpoints(kickoff, resolved_now, checkpoint):
            for market in ("ASIAN_HANDICAP", "TOTALS"):
                selection = select_mainline_snapshot_result(
                    observations=observations,
                    fixture_id=str(fixture["fixture_id"]),
                    kickoff=kickoff,
                    checkpoint=due_checkpoint,
                    market=market,
                    generated_at=resolved_now,
                )
                snapshot = selection.snapshot
                if snapshot is None:
                    if selection.reason == "NO_FRESH_LOCK_OBSERVATION":
                        freshness_rejections += 1
                    results.append(
                        {
                            "fixture_id": fixture["fixture_id"],
                            "checkpoint": due_checkpoint,
                            "market": market,
                            "status": "NO_MAINLINE_OBSERVATION",
                            "reason": selection.reason or "NO_OBSERVATION",
                        }
                    )
                    continue
                status = "DRY_RUN"
                if not dry_run and write_artifacts:
                    outcome = write_timeline_snapshot(
                        root=root,
                        fixture_id=str(fixture["fixture_id"]),
                        kickoff=kickoff,
                        snapshot=snapshot,
                    )
                    status = outcome.status
                    written += 1 if outcome.written else 0
                    already_locked += 1 if outcome.status == "ALREADY_LOCKED" else 0
                    immutable_conflicts += 1 if outcome.status == "IMMUTABLE_CONFLICT" else 0
                results.append(
                    {
                        "fixture_id": fixture["fixture_id"],
                        "checkpoint": due_checkpoint,
                        "market": market,
                        "status": status,
                        "as_of": snapshot["as_of"],
                        "line": snapshot["line"],
                        "bookmaker_count": snapshot["bookmaker_count"],
                    }
                )
    return {
        "status": "PASS",
        "dry_run": bool(dry_run),
        "write_artifacts": bool(write_artifacts),
        "window": window,
        "checkpoint": checkpoint,
        "max_fixtures": max_fixtures,
        "runtime_root": str(root),
        "network_quota_required": bool(network_quota_required),
        "provider_calls": 0,
        "quota_decision": quota,
        "selected_fixtures": fixture_ids,
        "fixture_count": len(fixtures),
        "observation_count": len(observations),
        "snapshot_candidates": len(results),
        "freshness_rejections": freshness_rejections,
        "written": written,
        "already_locked": already_locked,
        "immutable_conflicts": immutable_conflicts,
        "results": results,
    }


def default_market_timeline_runtime_root() -> Path:
    configured = os.environ.get("W2_MARKET_TIMELINE_RUNTIME_ROOT")
    if configured:
        return Path(configured)
    return Path.cwd() / DEFAULT_TIMELINE_DIR


def _window_fixtures(
    rows: list[dict[str, Any]],
    *,
    window: str,
    now: datetime,
) -> list[dict[str, Any]]:
    horizon = now + timedelta(hours=36)
    fixtures: list[dict[str, Any]] = []
    for item in rows:
        fixture = item.get("fixture") if isinstance(item.get("fixture"), dict) else item
        if not isinstance(fixture, dict):
            continue
        fixture_id = fixture.get("id") or item.get("fixture_id")
        kickoff = parse_utc(fixture.get("date") or item.get("kickoff_utc"))
        if fixture_id is None or kickoff is None:
            continue
        if window == "today" and kickoff.date() != now.date():
            continue
        if window == "next36" and not (now <= kickoff <= horizon):
            continue
        fixtures.append({"fixture_id": str(fixture_id), "kickoff": kickoff})
    return sorted(fixtures, key=lambda row: row["kickoff"])
