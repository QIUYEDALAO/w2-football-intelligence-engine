from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

logger = logging.getLogger("w2.scheduler")


def heartbeat() -> str:
    message = "w2 scheduler heartbeat"
    logger.info(message)
    return message


def future_fixture_refresh_enabled() -> bool:
    return os.environ.get("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "false").lower() == "true"


def future_fixture_refresh_tick() -> dict[str, object]:
    if not future_fixture_refresh_enabled():
        return {
            "status": "DISABLED",
            "candidate": False,
            "formal_recommendation": False,
        }
    from w2.ingestion.future_refresh import run_future_fixture_refresh

    result = run_future_fixture_refresh()
    return {
        "status": "COMPLETED" if not result.blockers else "BLOCKED",
        "generated_at_utc": result.generated_at_utc.isoformat().replace("+00:00", "Z"),
        "fixture_count": result.fixture_count,
        "mapping_count": result.mapping_count,
        "market_snapshot_count": result.market_snapshot_count,
        "request_count": result.request_count,
        "remaining_quota": result.remaining_quota,
        "blockers": result.blockers,
        "candidate": False,
        "formal_recommendation": False,
    }


def run_forever() -> None:
    interval_seconds = int(os.environ.get("W2_SCHEDULER_HEARTBEAT_INTERVAL_SECONDS", "30"))
    refresh_interval_seconds = int(
        os.environ.get("W2_FUTURE_FIXTURE_REFRESH_INTERVAL_SECONDS", "900")
    )
    next_refresh_at = datetime.now(UTC)
    while True:
        heartbeat()
        if future_fixture_refresh_enabled() and datetime.now(UTC) >= next_refresh_at:
            try:
                logger.info("w2 future fixture refresh %s", future_fixture_refresh_tick())
            except Exception:
                logger.exception("w2 future fixture refresh failed")
            next_refresh_at = datetime.now(UTC).replace(tzinfo=UTC)
            next_refresh_at = next_refresh_at.fromtimestamp(
                next_refresh_at.timestamp() + refresh_interval_seconds,
                tz=UTC,
            )
        time.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
