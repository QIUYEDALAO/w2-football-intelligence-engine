from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from w2.providers.control import (
    PROVIDER_SCHEDULER_DISABLED,
    provider_refresh_tick_hard_cap,
    provider_scheduler_enabled,
    provider_task_key_gate,
)

logger = logging.getLogger("w2.scheduler")

DEFAULT_REFRESH_INTERVAL_SECONDS = 900
DEFAULT_CHECKPOINT_POLL_SECONDS = 60
DEFAULT_XG_BACKFILL_INTERVAL_SECONDS = 6 * 60 * 60
DEFAULT_MARKET_TIMELINE_REFRESH_INTERVAL_SECONDS = 10 * 60


def heartbeat() -> str:
    message = "w2 scheduler heartbeat"
    logger.info(message)
    return message


def future_fixture_refresh_enabled() -> bool:
    return os.environ.get("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "false").lower() == "true"


def xg_history_backfill_enabled() -> bool:
    if not future_fixture_refresh_enabled():
        return False
    return os.environ.get("W2_XG_BACKFILL_ENABLED", "false").lower() == "true"


def market_timeline_refresh_enabled() -> bool:
    if not future_fixture_refresh_enabled():
        return False
    return os.environ.get("W2_MARKET_TIMELINE_REFRESH_ENABLED", "false").lower() == "true"


def future_fixture_refresh_contract_ready() -> bool:
    if not future_fixture_refresh_enabled():
        return False
    from w2.ingestion.future_refresh import FutureRefreshError, config_from_policy

    competition_id = os.environ.get("W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID", "world_cup_2026")
    try:
        config = config_from_policy(competition_id=competition_id)
    except (FutureRefreshError, OSError, ValueError):
        return False
    return config.enabled and config.competition_id == competition_id


def parse_fixture_kickoff(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def future_refresh_fixture_payloads() -> list[dict[str, Any]]:
    from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

    return FutureRefreshDbRepository().fixture_payloads()


def checkpoint_poll_seconds() -> int:
    try:
        return max(int(os.environ.get("W2_CHECKPOINT_REFRESH_POLL_SECONDS", "60")), 10)
    except ValueError:
        return DEFAULT_CHECKPOINT_POLL_SECONDS


def checkpoint_task_key(
    *,
    competition_id: str,
    season: str,
    checkpoints: list[dict[str, Any]],
) -> str:
    identity = "|".join(
        f"{item['fixture_id']}:{item['checkpoint']}" for item in checkpoints
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"checkpoint-refresh:{competition_id}:{season}:{digest}"


def due_checkpoint_refresh_batch(now: datetime) -> dict[str, Any]:
    from w2.ingestion.checkpoint_refresh import (
        checkpoint_plans_from_fixture_payloads,
        projected_calls_for_checkpoint_batch,
        select_checkpoint_batch,
    )
    from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

    repository = FutureRefreshDbRepository()
    fixtures = future_refresh_fixture_payloads()
    plans = checkpoint_plans_from_fixture_payloads(fixtures, now=now)
    repository.upsert_checkpoint_plans(
        [
            {
                "id": plan.plan_id,
                "fixture_id": plan.fixture_id,
                "checkpoint": plan.checkpoint,
                "kickoff_utc": plan.kickoff_utc,
                "due_at": plan.due_at_utc,
                "endpoints": list(plan.endpoints),
                "source": plan.source,
                "status": plan.status,
            }
            for plan in plans
        ]
    )
    due_rows = repository.due_checkpoint_plans(
        now=now,
        limit=int(os.environ.get("W2_CHECKPOINT_REFRESH_MAX_DUE", "100")),
    )
    due_plans = [
        type(
            "DuePlan",
            (),
            {
                "fixture_id": row["fixture_id"],
                "checkpoint": row["checkpoint"],
                "kickoff_utc": parse_fixture_kickoff(row["kickoff_utc"]),
                "due_at_utc": parse_fixture_kickoff(row["due_at"]),
                "endpoints": tuple(row["endpoints"]),
                "source": row["source"],
                "needs_odds": "odds" in row["endpoints"],
                "needs_lineups": "lineups" in row["endpoints"],
            },
        )()
        for row in due_rows
    ]
    selected, projected_calls = select_checkpoint_batch(
        due_plans,
        hard_cap=provider_refresh_tick_hard_cap(),
    )
    selected_rows = [
        {
            "fixture_id": plan.fixture_id,
            "checkpoint": plan.checkpoint,
            "kickoff_utc": plan.kickoff_utc.isoformat().replace("+00:00", "Z")
            if plan.kickoff_utc is not None
            else None,
            "due_at": plan.due_at_utc.isoformat().replace("+00:00", "Z")
            if plan.due_at_utc is not None
            else None,
            "endpoints": list(plan.endpoints),
            "source": plan.source,
        }
        for plan in selected
    ]
    return {
        "status": "READY" if selected_rows else "NO_CHECKPOINT_DUE",
        "generated_plan_count": len(plans),
        "due_checkpoint_count": len(due_rows),
        "selected_checkpoint_count": len(selected_rows),
        "projected_calls": projected_calls,
        "all_due_projected_calls": projected_calls_for_checkpoint_batch(due_plans),
        "tick_hard_cap": provider_refresh_tick_hard_cap(),
        "checkpoints": selected_rows,
    }


def future_fixture_refresh_tick() -> dict[str, object]:
    if not future_fixture_refresh_enabled():
        return {
            "status": "DISABLED",
            "candidate": False,
            "formal_recommendation": False,
        }
    if not provider_scheduler_enabled():
        return {
            "status": PROVIDER_SCHEDULER_DISABLED,
            "blockers": [PROVIDER_SCHEDULER_DISABLED],
            "candidate": False,
            "formal_recommendation": False,
            "provider_calls": 0,
        }
    from apps.worker.celery_app import celery_app
    from w2.ingestion.future_refresh import config_from_policy

    competition_id = os.environ.get("W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID", "world_cup_2026")
    now = datetime.now(UTC)
    config = config_from_policy(competition_id=competition_id)
    if not config.enabled:
        return {
            "status": "DISABLED_BY_POLICY",
            "competition_id": competition_id,
            "candidate": False,
            "formal_recommendation": False,
        }
    batch = due_checkpoint_refresh_batch(now)
    if batch["status"] == "NO_CHECKPOINT_DUE":
        return {
            **batch,
            "competition_id": config.competition_id,
            "season": config.season,
            "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
            "candidate": False,
            "formal_recommendation": False,
            "provider_calls": 0,
            "checkpoint_refresh_contract": "w2.checkpoint_refresh.v1",
            "provider_refresh_min_interval_policy": "REPLACED_BY_PER_FIXTURE_CHECKPOINTS",
        }
    task_key = checkpoint_task_key(
        competition_id=config.competition_id,
        season=config.season,
        checkpoints=list(batch["checkpoints"]),
    )
    gate = provider_task_key_gate(task_key=task_key)
    if not gate.allowed:
        return {
            "status": gate.status,
            "task_key": task_key,
            "competition_id": config.competition_id,
            "season": config.season,
            "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
            "candidate": False,
            "formal_recommendation": False,
            "provider_calls": 0,
            "blockers": [gate.status],
            "dedup_backend": gate.backend,
            "checkpoint_refresh_contract": "w2.checkpoint_refresh.v1",
            "provider_refresh_min_interval_policy": "REPLACED_BY_PER_FIXTURE_CHECKPOINTS",
        }
    task_id = f"{task_key}:{uuid4()}"
    celery_app.send_task(
        "w2.future_fixture_refresh",
        kwargs={
            "competition_id": config.competition_id,
            "task_key": task_key,
            "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
            "checkpoint_fixture_ids": [
                str(item["fixture_id"]) for item in batch["checkpoints"]
            ],
            "refresh_checkpoints": batch["checkpoints"],
        },
        task_id=task_id,
    )
    return {
        **batch,
        "status": "QUEUED",
        "task_id": task_id,
        "task_key": task_key,
        "competition_id": config.competition_id,
        "season": config.season,
        "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        "candidate": False,
        "formal_recommendation": False,
        "checkpoint_refresh_contract": "w2.checkpoint_refresh.v1",
        "provider_refresh_min_interval_policy": "REPLACED_BY_PER_FIXTURE_CHECKPOINTS",
    }


def xg_history_backfill_tick() -> dict[str, object]:
    if not xg_history_backfill_enabled():
        return {
            "status": "DISABLED",
            "candidate": False,
            "formal_recommendation": False,
        }
    if not provider_scheduler_enabled():
        return {
            "status": PROVIDER_SCHEDULER_DISABLED,
            "blockers": [PROVIDER_SCHEDULER_DISABLED],
            "candidate": False,
            "formal_recommendation": False,
            "provider_calls": 0,
        }
    from apps.worker.celery_app import celery_app

    now = datetime.now(UTC)
    task_id = f"xg-history-backfill:{now.strftime('%Y%m%dT%H%M%S')}:{uuid4()}"
    celery_app.send_task(
        "w2.xg_history_backfill",
        kwargs={"queued_at_utc": now.isoformat().replace("+00:00", "Z")},
        task_id=task_id,
    )
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        "candidate": False,
        "formal_recommendation": False,
    }


def market_timeline_refresh_tick() -> dict[str, object]:
    if not market_timeline_refresh_enabled():
        return {
            "status": "DISABLED",
            "candidate": False,
            "formal_recommendation": False,
            "beats_market": False,
        }
    if not provider_scheduler_enabled():
        return {
            "status": PROVIDER_SCHEDULER_DISABLED,
            "blockers": [PROVIDER_SCHEDULER_DISABLED],
            "candidate": False,
            "formal_recommendation": False,
            "beats_market": False,
            "provider_calls": 0,
        }
    from apps.worker.celery_app import celery_app

    now = datetime.now(UTC)
    max_fixtures = int(os.environ.get("W2_MARKET_TIMELINE_MAX_FIXTURES", "10"))
    task_id = f"market-timeline-refresh:{now.strftime('%Y%m%dT%H%M%S')}:{uuid4()}"
    celery_app.send_task(
        "w2.market_timeline_refresh",
        kwargs={
            "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
            "window": os.environ.get("W2_MARKET_TIMELINE_WINDOW", "next36"),
            "checkpoint": "auto",
            "max_fixtures": max_fixtures,
        },
        task_id=task_id,
    )
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        "max_fixtures": max_fixtures,
        "candidate": False,
        "formal_recommendation": False,
        "beats_market": False,
    }


def run_forever() -> None:
    interval_seconds = int(os.environ.get("W2_SCHEDULER_HEARTBEAT_INTERVAL_SECONDS", "30"))
    next_refresh_at = datetime.now(UTC)
    next_xg_backfill_at = datetime.now(UTC)
    next_market_timeline_refresh_at = datetime.now(UTC)
    while True:
        heartbeat()
        if future_fixture_refresh_enabled() and datetime.now(UTC) >= next_refresh_at:
            try:
                result = future_fixture_refresh_tick()
                logger.info("w2 future fixture refresh %s", result)
                refresh_interval_seconds = checkpoint_poll_seconds()
            except Exception:
                logger.exception("w2 future fixture refresh failed")
                refresh_interval_seconds = checkpoint_poll_seconds()
            next_refresh_at = datetime.now(UTC).replace(tzinfo=UTC)
            next_refresh_at = next_refresh_at.fromtimestamp(
                next_refresh_at.timestamp() + refresh_interval_seconds,
                tz=UTC,
            )
        if xg_history_backfill_enabled() and datetime.now(UTC) >= next_xg_backfill_at:
            try:
                result = xg_history_backfill_tick()
                logger.info("w2 xg history backfill %s", result)
                xg_interval_seconds = int(
                    os.environ.get(
                        "W2_XG_BACKFILL_INTERVAL_SECONDS",
                        str(DEFAULT_XG_BACKFILL_INTERVAL_SECONDS),
                    )
                )
            except Exception:
                logger.exception("w2 xg history backfill failed")
                xg_interval_seconds = int(
                    os.environ.get(
                        "W2_XG_BACKFILL_INTERVAL_SECONDS",
                        str(DEFAULT_XG_BACKFILL_INTERVAL_SECONDS),
                    )
                )
            next_xg_backfill_at = datetime.now(UTC).replace(tzinfo=UTC)
            next_xg_backfill_at = next_xg_backfill_at.fromtimestamp(
                next_xg_backfill_at.timestamp() + xg_interval_seconds,
                tz=UTC,
            )
        if (
            market_timeline_refresh_enabled()
            and datetime.now(UTC) >= next_market_timeline_refresh_at
        ):
            try:
                result = market_timeline_refresh_tick()
                logger.info("w2 market timeline refresh %s", result)
                market_timeline_interval_seconds = int(
                    os.environ.get(
                        "W2_MARKET_TIMELINE_REFRESH_INTERVAL_SECONDS",
                        str(DEFAULT_MARKET_TIMELINE_REFRESH_INTERVAL_SECONDS),
                    )
                )
            except Exception:
                logger.exception("w2 market timeline refresh failed")
                market_timeline_interval_seconds = int(
                    os.environ.get(
                        "W2_MARKET_TIMELINE_REFRESH_INTERVAL_SECONDS",
                        str(DEFAULT_MARKET_TIMELINE_REFRESH_INTERVAL_SECONDS),
                    )
                )
            next_market_timeline_refresh_at = datetime.now(UTC).replace(tzinfo=UTC)
            next_market_timeline_refresh_at = next_market_timeline_refresh_at.fromtimestamp(
                next_market_timeline_refresh_at.timestamp() + market_timeline_interval_seconds,
                tz=UTC,
            )
        time.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
