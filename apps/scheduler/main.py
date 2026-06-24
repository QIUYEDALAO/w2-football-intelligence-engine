from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from uuid import uuid4

logger = logging.getLogger("w2.scheduler")


def heartbeat() -> str:
    message = "w2 scheduler heartbeat"
    logger.info(message)
    return message


def future_fixture_refresh_enabled() -> bool:
    return os.environ.get("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "false").lower() == "true"


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


def future_fixture_refresh_tick() -> dict[str, object]:
    if not future_fixture_refresh_enabled():
        return {
            "status": "DISABLED",
            "candidate": False,
            "formal_recommendation": False,
        }
    from apps.worker.celery_app import celery_app
    from w2.ingestion.future_refresh import config_from_policy, deterministic_task_key

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
    task_key = deterministic_task_key(
        competition_id=config.competition_id,
        season=config.season,
        now=now,
        interval_seconds=config.scheduler_interval_seconds,
    )
    task_id = f"{task_key}:{uuid4()}"
    celery_app.send_task(
        "w2.future_fixture_refresh",
        kwargs={
            "competition_id": config.competition_id,
            "task_key": task_key,
            "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        },
        task_id=task_id,
    )
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "task_key": task_key,
        "competition_id": config.competition_id,
        "season": config.season,
        "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        "candidate": False,
        "formal_recommendation": False,
    }


def run_forever() -> None:
    interval_seconds = int(os.environ.get("W2_SCHEDULER_HEARTBEAT_INTERVAL_SECONDS", "30"))
    next_refresh_at = datetime.now(UTC)
    while True:
        heartbeat()
        if future_fixture_refresh_enabled() and datetime.now(UTC) >= next_refresh_at:
            try:
                result = future_fixture_refresh_tick()
                logger.info("w2 future fixture refresh %s", result)
                from w2.ingestion.future_refresh import config_from_policy

                refresh_interval_seconds = config_from_policy().scheduler_interval_seconds
            except Exception:
                logger.exception("w2 future fixture refresh failed")
                refresh_interval_seconds = int(
                    os.environ.get("W2_FUTURE_FIXTURE_REFRESH_INTERVAL_SECONDS", "900")
                )
            next_refresh_at = datetime.now(UTC).replace(tzinfo=UTC)
            next_refresh_at = next_refresh_at.fromtimestamp(
                next_refresh_at.timestamp() + refresh_interval_seconds,
                tz=UTC,
            )
        time.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
