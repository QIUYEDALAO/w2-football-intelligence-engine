from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Thread
from typing import Any, cast
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
DEFAULT_FORWARD_OUTCOME_LEDGER_INTERVAL_SECONDS = 10 * 60
DEFAULT_FIXTURE_DISCOVERY_INTERVAL_SECONDS = 5 * 60
DEFAULT_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS = 7
DEFAULT_CANDIDATE_NOTIFICATION_POLL_SECONDS = 5


@dataclass(frozen=True)
class ClaimedCheckpointPlan:
    fixture_id: str
    checkpoint: str
    kickoff_utc: datetime | None
    due_at_utc: datetime | None
    endpoints: tuple[str, ...]
    source: str
    policy_version: str
    id: str
    claim_token: str | None
    claim_expires_at: str | None
    window_start: str | None
    window_end: str | None

    @property
    def needs_lineups(self) -> bool:
        return "lineups" in self.endpoints

    @property
    def needs_odds(self) -> bool:
        return "odds" in self.endpoints


def heartbeat() -> str:
    message = "w2 scheduler heartbeat"
    logger.info(message)
    return message


def future_fixture_refresh_enabled() -> bool:
    return os.environ.get("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "false").lower() == "true"


def postmatch_only_enabled() -> bool:
    return os.environ.get("W2_POSTMATCH_ONLY_ENABLED", "false").lower() == "true"


def xg_history_backfill_enabled() -> bool:
    if not future_fixture_refresh_enabled():
        return False
    return os.environ.get("W2_XG_BACKFILL_ENABLED", "false").lower() == "true"


def forward_outcome_ledger_enabled() -> bool:
    return os.environ.get("W2_FORWARD_OUTCOME_LEDGER_ENABLED", "false").lower() == "true"


def candidate_notification_summary_tick() -> dict[str, object]:
    from w2.prematch.candidate_notifications import enqueue_operational_summaries

    inserted = enqueue_operational_summaries()
    return {
        "status": "ENQUEUED" if inserted else "NO_SUMMARY_DUE",
        "outbox_event_ids": inserted,
        "db_writes": len(inserted),
        "provider_calls": 0,
    }


def candidate_notification_delivery_tick() -> dict[str, object]:
    from w2.prematch.candidate_notifications import deliver_pending_notifications

    return deliver_pending_notifications()


def candidate_notification_delivery_loop() -> None:
    """Keep notification SLO independent from slower scheduler work."""

    while True:
        try:
            result = candidate_notification_delivery_tick()
            if result["status"] not in {"IDLE", "CHANNEL_NOT_CONFIGURED"}:
                logger.info("w2 candidate notification delivery %s", result)
        except Exception:
            logger.exception("w2 candidate notification delivery failed")
        time.sleep(DEFAULT_CANDIDATE_NOTIFICATION_POLL_SECONDS)


def fixture_discovery_enabled() -> bool:
    return os.environ.get("W2_FIXTURE_DISCOVERY_ENABLED", "false").lower() == "true"


def fixture_discovery_interval_seconds() -> int:
    try:
        return max(
            int(
                os.environ.get(
                    "W2_FIXTURE_DISCOVERY_INTERVAL_SECONDS",
                    str(DEFAULT_FIXTURE_DISCOVERY_INTERVAL_SECONDS),
                )
            ),
            60,
        )
    except ValueError:
        return DEFAULT_FIXTURE_DISCOVERY_INTERVAL_SECONDS


def fixture_discovery_max_offset_days() -> int:
    try:
        value = int(
            os.environ.get(
                "W2_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS",
                str(DEFAULT_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS),
            )
        )
    except ValueError:
        return DEFAULT_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS
    return min(max(value, 0), DEFAULT_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS)


def fixture_discovery_tick() -> dict[str, object]:
    if not fixture_discovery_enabled():
        return {
            "status": "DISABLED",
            "provider_calls": 0,
            "candidate": False,
            "formal_recommendation": False,
        }
    if not provider_scheduler_enabled():
        return {
            "status": PROVIDER_SCHEDULER_DISABLED,
            "blockers": [PROVIDER_SCHEDULER_DISABLED],
            "provider_calls": 0,
            "candidate": False,
            "formal_recommendation": False,
        }
    from apps.worker.celery_app import celery_app

    now = datetime.now(UTC)
    interval = fixture_discovery_interval_seconds()
    from w2.matchday.timezone import BeijingOperationalDayPolicy

    operational_date = BeijingOperationalDayPolicy().current_window(now_utc=now).local_date
    offset = (int(now.timestamp()) // interval) % (fixture_discovery_max_offset_days() + 1)
    discovery_date = (operational_date + timedelta(days=offset)).isoformat()
    task_key = f"fixture-discovery:{operational_date.isoformat()}:{discovery_date}"
    competition_ids = matchday_checkpoint_competition_ids()
    if len(competition_ids) != 13:
        return {
            "status": "FIXTURE_DISCOVERY_SCOPE_INVALID",
            "provider_calls": 0,
            "candidate": False,
            "formal_recommendation": False,
        }
    gate = provider_task_key_gate(task_key=task_key, ttl_seconds=24 * 60 * 60)
    if not gate.allowed:
        return {
            "status": gate.status,
            "task_key": task_key,
            "dedup_backend": gate.backend,
            "provider_calls": 0,
            "candidate": False,
            "formal_recommendation": False,
        }
    task_id = f"{task_key}:{uuid4()}"
    celery_app.send_task(
        "w2.future_fixture_refresh",
        kwargs={
            "competition_id": competition_ids[0],
            "task_key": task_key,
            "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
            "discovery_date": discovery_date,
        },
        task_id=task_id,
    )
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "task_key": task_key,
        "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        "discovery_date": discovery_date,
        "provider_calls": 0,
        "candidate": False,
        "formal_recommendation": False,
    }


def future_fixture_refresh_competition_ids() -> tuple[str, ...]:
    from w2.competitions.league_whitelist_scope import load_league_whitelist_scope
    from w2.competitions.registry import CompetitionRegistry

    registry = CompetitionRegistry()
    whitelist = set(load_league_whitelist_scope(registry).all_whitelist)
    registered = tuple(
        sorted(
            entry.competition_id
            for entry in registry.entries().values()
            if entry.competition_id in whitelist
            and entry.enabled
            and entry.refresh_switches.get("fixtures") is True
        )
    )
    allowed = {
        item.strip()
        for item in os.environ.get("W2_FUTURE_REFRESH_COMPETITION_ALLOWLIST", "").split(",")
        if item.strip()
    }
    return tuple(item for item in registered if not allowed or item in allowed)


def matchday_checkpoint_policies() -> dict[str, Any]:
    from w2.matchday.intake_v2 import competition_policies, load_matchday_policy

    return competition_policies(load_matchday_policy())


def matchday_checkpoint_competition_ids() -> tuple[str, ...]:
    return tuple(
        sorted(
            competition_id
            for competition_id, policy in matchday_checkpoint_policies().items()
            if policy.enabled
        )
    )


def future_fixture_refresh_contract_ready() -> bool:
    if not future_fixture_refresh_enabled():
        return False
    from w2.competitions.registry import CompetitionRegistryError
    from w2.ingestion.future_refresh import FutureRefreshError, config_from_policy

    try:
        competition_ids = future_fixture_refresh_competition_ids()
    except (CompetitionRegistryError, OSError, ValueError):
        return False
    for competition_id in competition_ids:
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
    identity = "|".join(
        f"{item['fixture_id']}:{item['checkpoint']}:{item.get('claim_token') or ''}"
        for item in checkpoints
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"checkpoint-refresh:{competition_id}:{season}:{digest}"


def prioritized_future_fixture_refresh_competition_ids(
    *, now: datetime, competition_ids: tuple[str, ...]
) -> tuple[str, ...]:
    from w2.matchday.repository import MatchdayRuntimeRepository

    due_ids = MatchdayRuntimeRepository().due_checkpoint_competition_ids(
        now=now,
        competition_ids=competition_ids,
    )
    return tuple([*due_ids, *(item for item in competition_ids if item not in due_ids)])


def due_checkpoint_refresh_batch(
    now: datetime,
    *,
    provider_league_id: str | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    from w2.ingestion.checkpoint_refresh import (
        POSTMATCH_RESULT_CHECKPOINT,
        postmatch_result_checkpoint_plan,
        projected_calls_for_checkpoint_batch,
        select_checkpoint_batch,
    )
    from w2.matchday.intake_v2 import (
        build_checkpoint_plans,
        parse_utc,
        require_competition_policy,
        stable_hash,
    )
    from w2.matchday.repository import MatchdayRuntimeRepository

    policy_map = matchday_checkpoint_policies()
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
        if kickoff >= now - timedelta(hours=36) and kickoff <= now + timedelta(
            hours=policy.discovery_horizon_hours
        ):
            plans.append(
                postmatch_result_checkpoint_plan(
                    fixture_id=f"{policy.provider}:{provider_fixture_id}",
                    competition_id=competition_id,
                    season=policy.season,
                    kickoff_utc=kickoff,
                    now=now,
                )
            )
    if postmatch_only_enabled():
        plans = [plan for plan in plans if plan.checkpoint == POSTMATCH_RESULT_CHECKPOINT]
    generated_plan_ids = {stable_hash(plan.natural_identity) for plan in plans}
    for plan in plans:
        repository.upsert_checkpoint_plan(plan)
    due_rows = []
    if generated_plan_ids:
        claim_worker_id = worker_id or f"checkpoint-scheduler:{now.isoformat()}"
        due_rows = [
            row
            for row in repository.claim_due_checkpoint_plans(
                now=now,
                worker_id=claim_worker_id,
                plan_ids=generated_plan_ids,
                limit=int(os.environ.get("W2_CHECKPOINT_REFRESH_MAX_DUE", "100")),
            )
            if row.get("id") in generated_plan_ids
        ]
    due_plans = [
        ClaimedCheckpointPlan(
            fixture_id=str(row["fixture_id"]),
            checkpoint=str(row["checkpoint"]),
            kickoff_utc=parse_fixture_kickoff(row["kickoff_utc"]),
            due_at_utc=parse_fixture_kickoff(row["due_at"]),
            endpoints=tuple(str(item) for item in row["endpoints"]),
            source=str(row["source"]),
            policy_version=str(row["policy_version"]),
            id=str(row["id"]),
            claim_token=str(row.get("claim_token") or "") or None,
            claim_expires_at=str(row.get("claim_expires_at") or "") or None,
            window_start=str(row.get("window_start") or "") or None,
            window_end=str(row.get("window_end") or "") or None,
        )
        for row in due_rows
    ]
    postmatch_mode = bool(due_plans and due_plans[0].checkpoint == POSTMATCH_RESULT_CHECKPOINT)
    same_mode_plans = [
        plan
        for plan in due_plans
        if (plan.checkpoint == POSTMATCH_RESULT_CHECKPOINT) is postmatch_mode
    ]
    if postmatch_mode:
        same_mode_plans = same_mode_plans[:1]
    selected_raw, projected_calls = select_checkpoint_batch(
        cast(Any, same_mode_plans),
        hard_cap=provider_refresh_tick_hard_cap(),
    )
    selected = cast(list[ClaimedCheckpointPlan], selected_raw)
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
            "policy_version": plan.policy_version,
            "id": plan.id,
            "claim_token": plan.claim_token,
            "claim_expires_at": plan.claim_expires_at,
            "window_start": plan.window_start,
            "window_end": plan.window_end,
        }
        for plan in selected
    ]
    selected_ids = {str(row["id"]) for row in selected_rows}
    for row in due_rows:
        if str(row.get("id")) not in selected_ids and row.get("claim_token"):
            repository.release_checkpoint_claim(
                plan_id=str(row["id"]),
                claim_token=str(row["claim_token"]),
                reason="CHECKPOINT_NOT_SELECTED_FOR_BATCH",
                restore_attempt=True,
            )
    return {
        "status": "READY" if selected_rows else "NO_CHECKPOINT_DUE",
        "fixture_payload_count": fixture_payload_count,
        "generated_plan_count": len(plans),
        "due_checkpoint_count": len(due_rows),
        "selected_checkpoint_count": len(selected_rows),
        "projected_calls": projected_calls,
        "all_due_projected_calls": projected_calls_for_checkpoint_batch(cast(Any, due_plans)),
        "tick_hard_cap": provider_refresh_tick_hard_cap(),
        "checkpoints": selected_rows,
        "refresh_mode": "POSTMATCH_RESULT" if postmatch_mode else "PREMATCH",
        "scheduler_checkpoint_writer": "matchday_checkpoint_plans",
        "legacy_checkpoint_writer_count": 0,
    }


def release_checkpoint_batch_claims(
    checkpoints: list[dict[str, Any]],
    *,
    reason: str,
    restore_attempt: bool = False,
) -> None:
    from w2.matchday.repository import MatchdayRuntimeRepository

    repository = MatchdayRuntimeRepository()
    for item in checkpoints:
        plan_id = str(item.get("id") or "")
        claim_token = str(item.get("claim_token") or "")
        if not plan_id or not claim_token:
            continue
        repository.release_checkpoint_claim(
            plan_id=plan_id,
            claim_token=claim_token,
            reason=reason,
            restore_attempt=restore_attempt,
        )


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
    competition_ids = prioritized_future_fixture_refresh_competition_ids(
        now=datetime.now(UTC),
        competition_ids=future_fixture_refresh_competition_ids(),
    )
    results = [
        _future_fixture_refresh_tick_for_competition(competition_id)
        for competition_id in competition_ids
    ]
    if len(results) == 1:
        return results[0]
    queued = [item for item in results if item.get("status") == "QUEUED"]
    return {
        "status": "QUEUED" if queued else "MULTI_COMPETITION_TICK",
        "competition_ids": list(competition_ids),
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
    checkpoint_task_id = f"checkpoint-refresh:{uuid4()}"
    batch = due_checkpoint_refresh_batch(
        now,
        provider_league_id=config.league_id,
        worker_id=checkpoint_task_id,
    )
    if batch["status"] == "NO_CHECKPOINT_DUE":
        if postmatch_only_enabled():
            return {
                **batch,
                "status": "NO_POSTMATCH_RESULT_DUE",
                "competition_id": config.competition_id,
                "season": config.season,
                "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
                "candidate": False,
                "formal_recommendation": False,
                "provider_calls": 0,
                "checkpoint_refresh_contract": "w2.checkpoint_refresh.v1",
                "provider_refresh_min_interval_policy": "POSTMATCH_ONLY",
            }
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
        release_checkpoint_batch_claims(
            list(batch["checkpoints"]),
            reason=f"CHECKPOINT_ENQUEUE_BLOCKED:{gate.status}",
            restore_attempt=True,
        )
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
    task_id = checkpoint_task_id
    try:
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
    except Exception:
        release_checkpoint_batch_claims(
            list(batch["checkpoints"]),
            reason="CHECKPOINT_ENQUEUE_FAILED",
        )
        raise
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
    competition_ids = matchday_checkpoint_competition_ids()
    if len(competition_ids) != 13:
        return {
            "status": "XG_BACKFILL_SCOPE_INVALID",
            "provider_calls": 0,
            "candidate": False,
            "formal_recommendation": False,
        }
    task_ids = []
    for competition_id in competition_ids:
        task_id = (
            f"xg-history-backfill:{competition_id}:"
            f"{now.strftime('%Y%m%dT%H%M%S')}:{uuid4()}"
        )
        celery_app.send_task(
            "w2.xg_history_backfill",
            kwargs={
                "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
                "competition_id": competition_id,
            },
            task_id=task_id,
        )
        task_ids.append(task_id)
    return {
        "status": "QUEUED",
        "task_id": task_ids[0],
        "task_ids": task_ids,
        "competition_ids": list(competition_ids),
        "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        "candidate": False,
        "formal_recommendation": False,
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
            "window": os.environ.get("W2_FORWARD_OUTCOME_LEDGER_WINDOW", "next7"),
        },
        task_id=task_id,
    )
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "queued_at_utc": now.isoformat().replace("+00:00", "Z"),
        "candidate": os.environ.get("W2_CANDIDATE_ENABLED", "false").lower() == "true",
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
    next_forward_outcome_ledger_at = datetime.now(UTC)
    next_fixture_discovery_at = datetime.now(UTC)
    Thread(
        target=candidate_notification_delivery_loop,
        name="candidate-notification-delivery",
        daemon=True,
    ).start()
    while True:
        heartbeat()
        try:
            result = candidate_notification_summary_tick()
            if result["status"] != "NO_SUMMARY_DUE":
                logger.info("w2 candidate notification summary %s", result)
        except Exception:
            logger.exception("w2 candidate notification summary failed")
        if fixture_discovery_enabled() and datetime.now(UTC) >= next_fixture_discovery_at:
            try:
                result = fixture_discovery_tick()
                logger.info("w2 fixture discovery %s", result)
            except Exception:
                logger.exception("w2 fixture discovery failed")
            next_fixture_discovery_at = datetime.fromtimestamp(
                datetime.now(UTC).timestamp() + fixture_discovery_interval_seconds(),
                tz=UTC,
            )
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
        time.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
