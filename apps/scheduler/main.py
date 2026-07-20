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
DEFAULT_FORWARD_OUTCOME_LEDGER_INTERVAL_SECONDS = 10 * 60
DEFAULT_FORWARD_OUTCOME_BACKFILL_INTERVAL_SECONDS = 60 * 60


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


def forward_outcome_ledger_enabled() -> bool:
    return os.environ.get("W2_FORWARD_OUTCOME_LEDGER_ENABLED", "false").lower() == "true"


def forward_outcome_backfill_enabled() -> bool:
    return os.environ.get("W2_FORWARD_OUTCOME_BACKFILL_ENABLED", "false").lower() == "true"


def future_fixture_refresh_competition_ids() -> tuple[str, ...]:
    raw = os.environ.get(
        "W2_FUTURE_FIXTURE_REFRESH_COMPETITION_IDS",
        os.environ.get("W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID", "world_cup_2026"),
    )
    ids = tuple(item.strip() for item in raw.split(",") if item.strip())
    return ids or ("world_cup_2026",)


def future_fixture_refresh_contract_ready() -> bool:
    if not future_fixture_refresh_enabled():
        return False
    from w2.ingestion.future_refresh import FutureRefreshError, config_from_policy

    for competition_id in future_fixture_refresh_competition_ids():
        try:
            config = config_from_policy(competition_id=competition_id)
        except (FutureRefreshError, OSError, ValueError):
            return False
        if not (config.enabled and config.competition_id == competition_id):
            return False
    return True


def parse_fixture_kickoff(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def future_refresh_fixture_payloads(
    *,
    provider_league_id: str | None = None,
) -> list[dict[str, Any]]:
    from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

    return FutureRefreshDbRepository().fixture_payloads(provider_league_id=provider_league_id)


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
    identity = "|".join(f"{item['fixture_id']}:{item['checkpoint']}" for item in checkpoints)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"checkpoint-refresh:{competition_id}:{season}:{digest}"


def due_checkpoint_refresh_batch(
    now: datetime,
    *,
    provider_league_id: str | None = None,
) -> dict[str, Any]:
    from w2.ingestion.checkpoint_refresh import (
        projected_calls_for_checkpoint_batch,
        select_checkpoint_batch,
    )
    from w2.matchday.intake_v2 import (
        build_checkpoint_plans,
        competition_policies,
        load_matchday_policy,
        parse_utc,
        require_competition_policy,
        stable_hash,
    )
    from w2.matchday.repository import MatchdayRuntimeRepository

    policy_map = competition_policies(load_matchday_policy())
    repository = MatchdayRuntimeRepository()
    fixtures = future_refresh_fixture_payloads(provider_league_id=provider_league_id)
    fixture_payload_count = len(fixtures)
    plans = []
    for item in fixtures:
        league = item.get("league") if isinstance(item, dict) else None
        fixture = item.get("fixture") if isinstance(item, dict) else None
        if not isinstance(league, dict) or not isinstance(fixture, dict):
            continue
        competition_id = _matchday_competition_for_league(
            policy_map,
            provider_league_id=str(league.get("id") or ""),
        )
        if competition_id is None:
            continue
        policy = require_competition_policy(policy_map, competition_id)
        provider_fixture_id = str(fixture.get("id") or "")
        kickoff = parse_utc(fixture.get("date"))
        if not provider_fixture_id or kickoff is None:
            continue
        plans.extend(
            build_checkpoint_plans(
                fixture_id=f"{policy.provider}:{provider_fixture_id}",
                competition_id=competition_id,
                season=policy.season,
                kickoff_utc=kickoff,
                now=now,
                policy=policy,
            )
        )
    generated_plan_ids = {stable_hash(plan.natural_identity) for plan in plans}
    for plan in plans:
        repository.upsert_checkpoint_plan(plan)
    due_rows = []
    if generated_plan_ids:
        due_rows = [
            row
            for row in repository.due_checkpoint_plans(
                now=now,
                limit=int(os.environ.get("W2_CHECKPOINT_REFRESH_MAX_DUE", "100")),
            )
            if row.get("id") in generated_plan_ids
        ]
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
        "fixture_payload_count": fixture_payload_count,
        "generated_plan_count": len(plans),
        "due_checkpoint_count": len(due_rows),
        "selected_checkpoint_count": len(selected_rows),
        "projected_calls": projected_calls,
        "all_due_projected_calls": projected_calls_for_checkpoint_batch(due_plans),
        "tick_hard_cap": provider_refresh_tick_hard_cap(),
        "checkpoints": selected_rows,
        "scheduler_checkpoint_writer": "matchday_checkpoint_plans",
        "legacy_checkpoint_writer_count": 0,
    }


def _matchday_competition_for_league(
    policies: dict[str, Any],
    *,
    provider_league_id: str,
) -> str | None:
    for competition_id, policy in policies.items():
        if str(policy.provider_league_id) == provider_league_id:
            return competition_id
    return None


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
    results = [
        _future_fixture_refresh_tick_for_competition(competition_id)
        for competition_id in future_fixture_refresh_competition_ids()
    ]
    if len(results) == 1:
        return results[0]
    queued = [item for item in results if item.get("status") == "QUEUED"]
    return {
        "status": "QUEUED" if queued else "MULTI_COMPETITION_TICK",
        "competition_ids": list(future_fixture_refresh_competition_ids()),
        "results": results,
        "queued_count": len(queued),
        "candidate": False,
        "formal_recommendation": False,
    }


def _future_fixture_refresh_tick_for_competition(competition_id: str) -> dict[str, object]:
    from apps.worker.celery_app import celery_app
    from w2.ingestion.future_refresh import config_from_policy, deterministic_task_key

    now = datetime.now(UTC)
    config = config_from_policy(competition_id=competition_id)
    if not config.enabled:
        return {
            "status": "DISABLED_BY_POLICY",
            "competition_id": competition_id,
            "candidate": False,
            "formal_recommendation": False,
        }
    batch = due_checkpoint_refresh_batch(now, provider_league_id=config.league_id)
    if batch["status"] == "NO_CHECKPOINT_DUE":
        if int(batch.get("fixture_payload_count") or 0) == 0:
            task_key = deterministic_task_key(
                competition_id=config.competition_id,
                season=config.season,
                now=now,
                interval_seconds=config.scheduler_interval_seconds,
            )
            gate = provider_task_key_gate(task_key=task_key)
            if not gate.allowed:
                return {
                    **batch,
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
                    "provider_refresh_min_interval_policy": ("INITIAL_SEED_WHEN_NO_LOCAL_FIXTURES"),
                }
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
                "provider_refresh_min_interval_policy": ("INITIAL_SEED_WHEN_NO_LOCAL_FIXTURES"),
            }
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
            "checkpoint_fixture_ids": [str(item["fixture_id"]) for item in batch["checkpoints"]],
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
    from apps.worker.celery_app import celery_app

    now = datetime.now(UTC)
    max_fixtures = int(os.environ.get("W2_MARKET_TIMELINE_MAX_FIXTURES", "10"))
    capture_forward_ledger = (
        os.environ.get("W2_FORWARD_OUTCOME_LEDGER_AFTER_MARKET_TIMELINE", "false").lower() == "true"
    )
    task_id = f"market-timeline-refresh:{now.strftime('%Y%m%dT%H%M%S')}:{uuid4()}"
    celery_app.send_task(
        "w2.market_timeline_refresh",
        kwargs={
            "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
            "window": os.environ.get("W2_MARKET_TIMELINE_WINDOW", "next36"),
            "checkpoint": "auto",
            "max_fixtures": max_fixtures,
            "capture_forward_ledger": capture_forward_ledger,
        },
        task_id=task_id,
    )
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        "max_fixtures": max_fixtures,
        "capture_forward_ledger": capture_forward_ledger,
        "candidate": False,
        "formal_recommendation": False,
        "beats_market": False,
    }


def forward_outcome_ledger_tick() -> dict[str, object]:
    if not forward_outcome_ledger_enabled():
        return {
            "status": "DISABLED",
            "candidate": False,
            "formal_recommendation": False,
            "provider_calls": 0,
            "db_writes": 0,
            "lock_capture_write": False,
            "settlement_write": False,
        }
    from apps.worker.celery_app import celery_app

    now = datetime.now(UTC)
    task_id = f"forward-outcome-ledger:{now.strftime('%Y%m%dT%H%M%S')}:{uuid4()}"
    celery_app.send_task(
        "w2.forward_outcome_ledger",
        kwargs={
            "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
            "window": os.environ.get("W2_FORWARD_OUTCOME_LEDGER_WINDOW", "next36"),
        },
        task_id=task_id,
    )
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        "candidate": False,
        "formal_recommendation": False,
        "provider_calls": 0,
        "db_writes": 0,
        "lock_capture_write": False,
        "settlement_write": False,
    }


def forward_outcome_backfill_tick() -> dict[str, object]:
    if not forward_outcome_backfill_enabled():
        return {
            "status": "DISABLED",
            "candidate": False,
            "formal_recommendation": False,
            "provider_calls": 0,
            "db_writes": 0,
            "lock_capture_write": False,
            "settlement_write": False,
        }
    from apps.worker.celery_app import celery_app

    now = datetime.now(UTC)
    task_id = f"forward-outcome-backfill:{now.strftime('%Y%m%dT%H%M%S')}:{uuid4()}"
    celery_app.send_task(
        "w2.forward_outcome_backfill",
        kwargs={
            "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
            "window": os.environ.get("W2_FORWARD_OUTCOME_BACKFILL_WINDOW", "next36"),
            "max_fixtures": min(
                max(int(os.environ.get("W2_FORWARD_OUTCOME_BACKFILL_MAX_FIXTURES", "20")), 0),
                20,
            ),
        },
        task_id=task_id,
    )
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        "candidate": False,
        "formal_recommendation": False,
        "provider_calls": 0,
        "db_writes": 0,
        "lock_capture_write": False,
        "settlement_write": False,
    }


def run_forever() -> None:
    interval_seconds = int(os.environ.get("W2_SCHEDULER_HEARTBEAT_INTERVAL_SECONDS", "30"))
    next_refresh_at = datetime.now(UTC)
    next_xg_backfill_at = datetime.now(UTC)
    next_market_timeline_refresh_at = datetime.now(UTC)
    next_forward_outcome_ledger_at = datetime.now(UTC)
    next_forward_outcome_backfill_at = datetime.now(UTC)
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
        if forward_outcome_ledger_enabled() and datetime.now(UTC) >= next_forward_outcome_ledger_at:
            try:
                result = forward_outcome_ledger_tick()
                logger.info("w2 forward outcome ledger %s", result)
                forward_outcome_ledger_interval_seconds = int(
                    os.environ.get(
                        "W2_FORWARD_OUTCOME_LEDGER_INTERVAL_SECONDS",
                        str(DEFAULT_FORWARD_OUTCOME_LEDGER_INTERVAL_SECONDS),
                    )
                )
            except Exception:
                logger.exception("w2 forward outcome ledger failed")
                forward_outcome_ledger_interval_seconds = int(
                    os.environ.get(
                        "W2_FORWARD_OUTCOME_LEDGER_INTERVAL_SECONDS",
                        str(DEFAULT_FORWARD_OUTCOME_LEDGER_INTERVAL_SECONDS),
                    )
                )
            next_forward_outcome_ledger_at = datetime.now(UTC).replace(tzinfo=UTC)
            next_forward_outcome_ledger_at = next_forward_outcome_ledger_at.fromtimestamp(
                next_forward_outcome_ledger_at.timestamp()
                + forward_outcome_ledger_interval_seconds,
                tz=UTC,
            )
        if (
            forward_outcome_backfill_enabled()
            and datetime.now(UTC) >= next_forward_outcome_backfill_at
        ):
            try:
                result = forward_outcome_backfill_tick()
                logger.info("w2 forward outcome backfill %s", result)
                forward_outcome_backfill_interval_seconds = int(
                    os.environ.get(
                        "W2_FORWARD_OUTCOME_BACKFILL_INTERVAL_SECONDS",
                        str(DEFAULT_FORWARD_OUTCOME_BACKFILL_INTERVAL_SECONDS),
                    )
                )
            except Exception:
                logger.exception("w2 forward outcome backfill failed")
                forward_outcome_backfill_interval_seconds = int(
                    os.environ.get(
                        "W2_FORWARD_OUTCOME_BACKFILL_INTERVAL_SECONDS",
                        str(DEFAULT_FORWARD_OUTCOME_BACKFILL_INTERVAL_SECONDS),
                    )
                )
            next_forward_outcome_backfill_at = datetime.now(UTC).replace(tzinfo=UTC)
            next_forward_outcome_backfill_at = next_forward_outcome_backfill_at.fromtimestamp(
                next_forward_outcome_backfill_at.timestamp()
                + forward_outcome_backfill_interval_seconds,
                tz=UTC,
            )
        time.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
