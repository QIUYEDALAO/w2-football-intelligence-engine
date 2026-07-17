from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import UTC, datetime, timedelta
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
DEFAULT_CHECKPOINT_POLL_SECONDS = 15 * 60
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
        os.environ.get("W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID", "brasileirao_serie_a"),
    )
    ids = tuple(item.strip() for item in raw.split(",") if item.strip())
    return ids or ("brasileirao_serie_a",)


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
        return max(
            int(
                os.environ.get(
                    "W2_CHECKPOINT_REFRESH_POLL_SECONDS",
                    str(DEFAULT_CHECKPOINT_POLL_SECONDS),
                )
            ),
            10,
        )
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


def projected_calls_for_checkpoint_rows(checkpoints: list[dict[str, Any]]) -> int:
    # Future checkpoints are dispatched independently at their exact due time.
    # Each task therefore pays its own status + fixture preflight overhead.
    return sum(
        2
        + int("odds" in set(item.get("endpoints") or []))
        + int("lineups" in set(item.get("endpoints") or []))
        for item in checkpoints
    )


def allocate_global_checkpoint_batches(
    batches: list[tuple[str, dict[str, Any]]],
    *,
    now: datetime,
    hard_cap: int,
) -> dict[str, dict[str, Any]]:
    """Allocate one provider-call budget across all competitions in kickoff order."""
    current = now.astimezone(UTC)
    flattened: list[tuple[str, dict[str, Any]]] = []
    for competition_id, batch in batches:
        flattened.extend(
            (competition_id, dict(item)) for item in list(batch.get("checkpoints") or [])
        )
    flattened.sort(
        key=lambda item: (
            (parse_fixture_kickoff(item[1].get("kickoff_utc")) or current).date()
            != current.date(),
            parse_fixture_kickoff(item[1].get("kickoff_utc")) or current,
            parse_fixture_kickoff(item[1].get("due_at")) or current,
            str(item[1].get("fixture_id") or ""),
            str(item[1].get("checkpoint") or ""),
        )
    )
    selected: dict[str, list[dict[str, Any]]] = {
        competition_id: [] for competition_id, _ in batches
    }
    cap = max(int(hard_cap), 0)
    for competition_id, checkpoint in flattened:
        candidate = [*selected[competition_id], checkpoint]
        projected = sum(
            projected_calls_for_checkpoint_rows(rows) for rows in selected.values() if rows
        )
        projected -= projected_calls_for_checkpoint_rows(selected[competition_id])
        projected += projected_calls_for_checkpoint_rows(candidate)
        if projected <= cap:
            selected[competition_id] = candidate

    selected_total = sum(
        projected_calls_for_checkpoint_rows(items) for items in selected.values() if items
    )
    seed_allowed: dict[str, bool] = {}
    for competition_id, batch in batches:
        seed_calls = int(batch.get("initial_seed_projected_calls") or 0)
        is_seed = int(batch.get("fixture_payload_count") or 0) == 0 and not int(
            batch.get("due_checkpoint_count") or 0
        )
        allowed = not is_seed or selected_total + seed_calls <= cap
        seed_allowed[competition_id] = allowed
        if is_seed and allowed:
            selected_total += seed_calls

    allocated: dict[str, dict[str, Any]] = {}
    for competition_id, batch in batches:
        rows = selected[competition_id]
        projected = projected_calls_for_checkpoint_rows(rows)
        original_due = int(batch.get("due_checkpoint_count") or 0)
        status = str(batch.get("status") or "NO_CHECKPOINT_DUE")
        if original_due and not rows:
            status = "PROVIDER_REFRESH_BUDGET_DEFERRED"
        elif not seed_allowed[competition_id]:
            status = "PROVIDER_REFRESH_BUDGET_DEFERRED"
        elif rows:
            status = "READY"
        allocated[competition_id] = {
            **batch,
            "status": status,
            "checkpoints": rows,
            "selected_checkpoint_count": len(rows),
            "projected_calls": projected,
            "tick_hard_cap": cap,
            "initial_seed_allowed": seed_allowed[competition_id],
            "global_tick_projected_calls": selected_total,
        }
    return allocated


def due_checkpoint_refresh_batch(
    now: datetime,
    *,
    provider_league_id: str | None = None,
    hard_cap: int | None = None,
) -> dict[str, Any]:
    from w2.ingestion.checkpoint_refresh import (
        checkpoint_plans_from_fixture_payloads,
        dedupe_active_odds_plans,
        prioritize_checkpoint_plans,
    )
    from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

    repository = FutureRefreshDbRepository()
    fixtures = future_refresh_fixture_payloads(provider_league_id=provider_league_id)
    fixture_payload_count = len(fixtures)
    fixture_ids = [
        str(item.get("fixture", {}).get("id") or "")
        for item in fixtures
        if isinstance(item, dict) and isinstance(item.get("fixture"), dict)
    ]
    quote_reader = getattr(repository, "latest_observation_captured_at_for_fixture_ids", None)
    attempt_reader = getattr(repository, "latest_odds_refresh_attempt_at_for_fixture_ids", None)
    latest_quotes = quote_reader(fixture_ids) if callable(quote_reader) else {}
    latest_attempts = attempt_reader(fixture_ids) if callable(attempt_reader) else {}
    plans = checkpoint_plans_from_fixture_payloads(
        fixtures,
        now=now,
        latest_quote_at_by_fixture=latest_quotes,
        latest_attempt_at_by_fixture=latest_attempts,
    )
    generated_plan_ids = {plan.plan_id for plan in plans}
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
    active_plan_ids = {
        plan.plan_id
        for plan in plans
        if str(plan.checkpoint).startswith("ACTIVE_ODDS_")
    }
    supersede_active = getattr(repository, "supersede_pending_active_checkpoint_plans", None)
    if callable(supersede_active):
        supersede_active(fixture_ids=fixture_ids, active_plan_ids=active_plan_ids)
    due_rows = []
    if generated_plan_ids:
        ready_before = now + timedelta(seconds=checkpoint_poll_seconds())
        due_rows = [
            row
            for row in repository.due_checkpoint_plans(
                now=ready_before,
                limit=int(os.environ.get("W2_CHECKPOINT_REFRESH_MAX_DUE", "100")),
                fixture_ids=fixture_ids,
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
    due_plans = dedupe_active_odds_plans(due_plans)
    due_plans = prioritize_checkpoint_plans(due_plans, now=now)
    resolved_hard_cap = (
        provider_refresh_tick_hard_cap() if hard_cap is None else max(int(hard_cap), 0)
    )
    selected = []
    projected_calls = 0
    for plan in due_plans:
        plan_calls = 2 + int(plan.needs_odds) + int(plan.needs_lineups)
        if projected_calls + plan_calls > resolved_hard_cap:
            continue
        selected.append(plan)
        projected_calls += plan_calls
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
        "all_due_projected_calls": sum(
            2 + int(plan.needs_odds) + int(plan.needs_lineups) for plan in due_plans
        ),
        "tick_hard_cap": resolved_hard_cap,
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
    from w2.ingestion.future_refresh import config_from_policy

    now = datetime.now(UTC)
    competition_ids = future_fixture_refresh_competition_ids()
    candidate_batches: list[tuple[str, dict[str, Any]]] = []
    for competition_id in competition_ids:
        config = config_from_policy(competition_id=competition_id)
        candidate_batches.append(
            (
                competition_id,
                due_checkpoint_refresh_batch(
                    now,
                    provider_league_id=config.league_id,
                    hard_cap=provider_refresh_tick_hard_cap(),
                )
                | {
                    "initial_seed_projected_calls": (
                        2
                        + max(config.max_odds_requests, 0)
                        + max(config.feature_enrichment_request_budget, 0)
                    )
                },
            )
        )
    allocated = allocate_global_checkpoint_batches(
        candidate_batches,
        now=now,
        hard_cap=provider_refresh_tick_hard_cap(),
    )
    results = [
        _future_fixture_refresh_tick_for_competition(
            competition_id,
            now=now,
            batch=allocated[competition_id],
        )
        for competition_id in competition_ids
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


def _future_fixture_refresh_tick_for_competition(
    competition_id: str,
    *,
    now: datetime | None = None,
    batch: dict[str, Any] | None = None,
) -> dict[str, object]:
    from apps.worker.celery_app import celery_app
    from w2.ingestion.future_refresh import config_from_policy, deterministic_task_key

    current = now or datetime.now(UTC)
    config = config_from_policy(competition_id=competition_id)
    if not config.enabled:
        return {
            "status": "DISABLED_BY_POLICY",
            "competition_id": competition_id,
            "candidate": False,
            "formal_recommendation": False,
        }
    resolved_batch = batch or due_checkpoint_refresh_batch(
        current,
        provider_league_id=config.league_id,
    )
    if resolved_batch["status"] == "PROVIDER_REFRESH_BUDGET_DEFERRED":
        return {
            **resolved_batch,
            "competition_id": config.competition_id,
            "season": config.season,
            "queued_at_utc": current.isoformat().replace("+00:00", "Z"),
            "candidate": False,
            "formal_recommendation": False,
            "provider_calls": 0,
            "blockers": ["PROVIDER_REFRESH_BUDGET_DEFERRED"],
        }
    if resolved_batch["status"] == "NO_CHECKPOINT_DUE":
        if int(resolved_batch.get("fixture_payload_count") or 0) == 0:
            task_key = deterministic_task_key(
                competition_id=config.competition_id,
                season=config.season,
                now=current,
                interval_seconds=config.scheduler_interval_seconds,
            )
            gate = provider_task_key_gate(task_key=task_key)
            if not gate.allowed:
                return {
                    **resolved_batch,
                    "status": gate.status,
                    "task_key": task_key,
                    "competition_id": config.competition_id,
                    "season": config.season,
                    "queued_at_utc": current.isoformat().replace("+00:00", "Z"),
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
                    "queued_at_utc": current.isoformat().replace("+00:00", "Z"),
                },
                task_id=task_id,
            )
            return {
                **resolved_batch,
                "status": "QUEUED",
                "task_id": task_id,
                "task_key": task_key,
                "competition_id": config.competition_id,
                "season": config.season,
                "queued_at_utc": current.isoformat().replace("+00:00", "Z"),
                "candidate": False,
                "formal_recommendation": False,
                "checkpoint_refresh_contract": "w2.checkpoint_refresh.v1",
                "provider_refresh_min_interval_policy": ("INITIAL_SEED_WHEN_NO_LOCAL_FIXTURES"),
            }
        return {
            **resolved_batch,
            "competition_id": config.competition_id,
            "season": config.season,
            "queued_at_utc": current.isoformat().replace("+00:00", "Z"),
            "candidate": False,
            "formal_recommendation": False,
            "provider_calls": 0,
            "checkpoint_refresh_contract": "w2.checkpoint_refresh.v1",
            "provider_refresh_min_interval_policy": "REPLACED_BY_PER_FIXTURE_CHECKPOINTS",
        }
    dispatches: list[dict[str, str]] = []
    suppressed: list[str] = []
    attempted_task_keys: list[str] = []
    for checkpoint in resolved_batch["checkpoints"]:
        task_key = checkpoint_task_key(
            competition_id=config.competition_id,
            season=config.season,
            checkpoints=[checkpoint],
        )
        attempted_task_keys.append(task_key)
        gate = provider_task_key_gate(task_key=task_key)
        if not gate.allowed:
            suppressed.append(gate.status)
            continue
        task_id = f"{task_key}:{uuid4()}"
        dispatch_at = parse_fixture_kickoff(checkpoint.get("due_at")) or current
        send_options: dict[str, Any] = {"task_id": task_id}
        if dispatch_at > current:
            send_options["eta"] = dispatch_at
        celery_app.send_task(
            "w2.future_fixture_refresh",
            kwargs={
                "competition_id": config.competition_id,
                "task_key": task_key,
                "queued_at_utc": current.isoformat().replace("+00:00", "Z"),
                "checkpoint_fixture_ids": [str(checkpoint["fixture_id"])],
                "refresh_checkpoints": [checkpoint],
            },
            **send_options,
        )
        dispatches.append(
            {
                "task_id": task_id,
                "task_key": task_key,
                "fixture_id": str(checkpoint["fixture_id"]),
                "dispatch_at_utc": dispatch_at.isoformat().replace("+00:00", "Z"),
            }
        )
    if not dispatches:
        status = suppressed[0] if suppressed else "NO_CHECKPOINT_DUE"
        return {
            **resolved_batch,
            "status": status,
            "task_key": attempted_task_keys[0] if attempted_task_keys else None,
            "competition_id": config.competition_id,
            "season": config.season,
            "queued_at_utc": current.isoformat().replace("+00:00", "Z"),
            "candidate": False,
            "formal_recommendation": False,
            "provider_calls": 0,
            "blockers": list(dict.fromkeys(suppressed)),
            "checkpoint_refresh_contract": "w2.checkpoint_refresh.v1",
            "provider_refresh_min_interval_policy": "REPLACED_BY_PER_FIXTURE_CHECKPOINTS",
        }
    first = dispatches[0]
    return {
        **resolved_batch,
        "status": "QUEUED",
        "task_id": first["task_id"],
        "task_key": first["task_key"],
        "task_ids": [item["task_id"] for item in dispatches],
        "dispatches": dispatches,
        "competition_id": config.competition_id,
        "season": config.season,
        "queued_at_utc": current.isoformat().replace("+00:00", "Z"),
        "dispatch_at_utc": first["dispatch_at_utc"],
        "suppressed": list(dict.fromkeys(suppressed)),
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
            "window": os.environ.get("W2_FORWARD_OUTCOME_BACKFILL_WINDOW", "all"),
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
