from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from w2.domain.decision_adapter import build_decision_contract_fields
from w2.domain.enums import DataStatus
from w2.domain.environment_policy import build_environment_policy_stamp
from w2.readiness.data_gate import DataFreshnessPolicy, DataReadinessInput, evaluate_data_readiness
from w2.refresh.matchday_schedule import (
    AUTHORIZED_MATCHDAY_ENDPOINTS,
    MatchdayRefreshPolicy,
    build_matchday_refresh_plan,
)

EFFECTIVE_ENDPOINT_ORDER = ("status", "fixtures", "odds", "lineups")
SETTLEMENT_DRY_RUN_PLACEHOLDER = {
    "would_run": False,
    "reason": "not implemented in dry-run skeleton",
    "db_writes": 0,
}
PROVIDER_CALLS_APPROVAL = "PROVIDER_CALLS"
DB_WRITE_APPROVAL = "DB_WRITE"
LOCK_WRITE_APPROVAL = "STAGING_FORMAL_LOCK_CAPTURE_WRITE"


def build_matchday_dry_run(
    *,
    football_day: date,
    environment: str,
    as_of: datetime,
    fixtures: Sequence[Mapping[str, Any]],
    provider_allowed_endpoints: Sequence[str] | None = None,
    refresh_hard_cap: int = 30,
    refresh_min_interval_seconds: int = 900,
    refresh_dedupe_ttl_seconds: int = 1800,
) -> dict[str, Any]:
    current = _normalize_utc(as_of)
    environment_policy = build_environment_policy_stamp(environment)
    normalized = [_normalize_fixture(item) for item in fixtures]
    configured_endpoints = list(
        provider_allowed_endpoints or ("status", "fixtures", "odds", "lineups"),
    )
    endpoint_allowlist, skipped_endpoints = _endpoint_lists(configured_endpoints)
    if not normalized:
        return {
            **_base_payload(
                football_day=football_day,
                environment=environment,
                environment_policy=environment_policy,
                as_of=current,
                fixture_count=0,
            ),
            "status": "NO_FIXTURES",
            "fixtures": [],
            "data_readiness_summary": _readiness_summary([]),
            "decision_cards_summary": _decision_summary([]),
            "refresh_plan_summary": _refresh_summary(
                [],
                configured_endpoints=configured_endpoints,
                endpoint_allowlist=endpoint_allowlist,
                skipped_endpoints=skipped_endpoints,
                hard_cap=refresh_hard_cap,
            ),
            **_would_generate_payload(0),
            "lock_candidates": [],
            "settlement_dry_run": dict(SETTLEMENT_DRY_RUN_PLACEHOLDER),
            "provider_usage_plan": _provider_usage_plan(
                configured_endpoints=configured_endpoints,
                endpoint_allowlist=endpoint_allowlist,
                skipped_endpoints=skipped_endpoints,
                projected_calls=0,
            ),
            "next_refresh_tick": None,
            "would_enqueue": False,
            "would_write_lock": False,
            "would_write_settlement": False,
        }

    competition_id = _single_competition_id(normalized)
    fixture_outputs = [
        _fixture_dry_run(item, environment=environment, as_of=current) for item in normalized
    ]
    refresh_policy = MatchdayRefreshPolicy(
        competition_id=competition_id,
        allowed_endpoints=tuple(configured_endpoints),
        tick_hard_cap=refresh_hard_cap,
        min_interval_seconds=refresh_min_interval_seconds,
        dedupe_ttl_seconds=refresh_dedupe_ttl_seconds,
    )
    ticks = build_matchday_refresh_plan(normalized, as_of=current, policy=refresh_policy)
    refresh_summary = _refresh_summary(
        ticks,
        configured_endpoints=configured_endpoints,
        endpoint_allowlist=endpoint_allowlist,
        skipped_endpoints=skipped_endpoints,
        hard_cap=refresh_hard_cap,
    )
    lock_candidates = _lock_candidates(fixture_outputs, as_of=current)
    card_count = len(fixture_outputs)
    return {
        **_base_payload(
            football_day=football_day,
            environment=environment,
            environment_policy=environment_policy,
            as_of=current,
            fixture_count=len(normalized),
        ),
        "status": "DRY_RUN_READY",
        "fixtures": fixture_outputs,
        "data_readiness_summary": _readiness_summary(fixture_outputs),
        "decision_cards_summary": _decision_summary(fixture_outputs),
        "refresh_plan_summary": refresh_summary,
        **_would_generate_payload(card_count),
        "lock_candidates": lock_candidates,
        "settlement_dry_run": dict(SETTLEMENT_DRY_RUN_PLACEHOLDER),
        "provider_usage_plan": _provider_usage_plan(
            configured_endpoints=configured_endpoints,
            endpoint_allowlist=endpoint_allowlist,
            skipped_endpoints=skipped_endpoints,
            projected_calls=int(refresh_summary["projected_calls_total"]),
        ),
        "next_refresh_tick": refresh_summary["next_refresh_tick"],
        "provider_calls": 0,
        "db_writes": 0,
        "would_enqueue": False,
        "would_write_lock": False,
        "would_write_settlement": False,
    }


def build_matchday_controlled_run_plan(
    *,
    football_day: date,
    environment: str,
    as_of: datetime,
    fixtures: Sequence[Mapping[str, Any]],
    approve_provider_calls: bool = False,
    approve_db_writes: bool = False,
    approve_lock_write: bool = False,
    approve_settlement_write: bool = False,
    provider_allowed_endpoints: Sequence[str] | None = None,
    refresh_hard_cap: int = 30,
    refresh_min_interval_seconds: int = 900,
    refresh_dedupe_ttl_seconds: int = 1800,
) -> dict[str, Any]:
    dry_run = build_matchday_dry_run(
        football_day=football_day,
        environment=environment,
        as_of=as_of,
        fixtures=fixtures,
        provider_allowed_endpoints=provider_allowed_endpoints,
        refresh_hard_cap=refresh_hard_cap,
        refresh_min_interval_seconds=refresh_min_interval_seconds,
        refresh_dedupe_ttl_seconds=refresh_dedupe_ttl_seconds,
    )
    refresh_plan = _as_mapping(dry_run.get("refresh_plan_summary"))
    projected_provider_calls = int(refresh_plan.get("projected_calls_total") or 0)
    lock_candidates = _mapping_list(dry_run.get("lock_candidates"))
    required_approvals = _required_approvals(
        projected_provider_calls=projected_provider_calls,
        lock_candidate_count=len(lock_candidates),
        approve_provider_calls=approve_provider_calls,
        approve_db_writes=approve_db_writes,
        approve_lock_write=approve_lock_write,
    )
    approvals = {
        "provider_calls": approve_provider_calls,
        "db_writes": approve_db_writes,
        "lock_write": approve_lock_write,
        "settlement_write": approve_settlement_write,
    }
    execution_deferred = not required_approvals
    return {
        "football_day": dry_run["football_day"],
        "environment": environment,
        "environment_policy": dry_run["environment_policy"],
        "mode": "controlled_run",
        "status": "APPROVAL_REQUIRED" if required_approvals else "EXECUTION_DEFERRED",
        "as_of": dry_run["as_of"],
        "fixture_count": dry_run["fixture_count"],
        "approvals": approvals,
        "fixtures": dry_run["fixtures"],
        "refresh_plan": refresh_plan,
        "refresh_plan_summary": refresh_plan,
        "projected_provider_calls": projected_provider_calls,
        "provider_call_approval_required": projected_provider_calls > 0,
        "db_write_approval_required": projected_provider_calls > 0,
        "lock_write_approval_required": bool(lock_candidates),
        "settlement_write_approval_required": False,
        "lock_candidates": lock_candidates,
        "settlement_dry_run": dry_run["settlement_dry_run"],
        "provider_usage_plan": dry_run["provider_usage_plan"],
        "required_approvals": required_approvals,
        "blockers": [f"APPROVAL_REQUIRED:{approval}" for approval in required_approvals],
        "execution_plan": {
            "would_execute": False,
            "execution_deferred": execution_deferred,
            "reason": "controlled-run execution is not implemented in this PR",
        },
        "would_call_provider": False,
        "would_write_db": False,
        "would_enqueue": False,
        "would_write_lock": False,
        "would_write_settlement": False,
        "provider_calls": 0,
        "db_writes": 0,
    }


def _fixture_dry_run(
    fixture: Mapping[str, Any],
    *,
    environment: str,
    as_of: datetime,
) -> dict[str, Any]:
    fixture_id = str(fixture["fixture_id"])
    kickoff_utc = _normalize_utc(_datetime_value(fixture["kickoff_utc"]))
    market_payload = _market_payload(fixture)
    readiness = evaluate_data_readiness(
        DataReadinessInput(
            fixture_id=fixture_id,
            kickoff_utc=kickoff_utc,
            as_of=as_of,
            fixture_status=_optional_text(fixture.get("fixture_status")) or "UPCOMING",
            market_available=bool(_optional_text(fixture.get("market"))),
            odds_available=bool(_optional_text(fixture.get("odds"))),
            odds_captured_at=as_of if _optional_text(fixture.get("odds")) else None,
            lineups_available=bool(fixture.get("lineups_available", False)),
            lineups_captured_at=as_of if fixture.get("lineups_available") else None,
            xg_available=bool(fixture.get("xg_available", False)),
            xg_captured_at=as_of if fixture.get("xg_available") else None,
            ratings_available=bool(fixture.get("ratings_available", False)),
            ratings_captured_at=as_of if fixture.get("ratings_available") else None,
            team_value_available=bool(fixture.get("team_value_available", False)),
            team_value_captured_at=as_of if fixture.get("team_value_available") else None,
            provider_budget_status="AVAILABLE",
            provider_budget_remaining=0,
            provider_budget_exhausted=False,
            coverage_supported=True,
        ),
        DataFreshnessPolicy(),
    )
    decision = build_decision_contract_fields(
        card={
            "source": "w2.matchday.dry_run",
            "fixture_id": fixture_id,
            "competition_id": _optional_text(fixture.get("competition_id")) or "",
            "quote_identity_audit": fixture.get("quote_identity_audit"),
        },
        market=market_payload,
        recommendation=_recommendation_payload(fixture, market_payload),
        readiness={"data_readiness": readiness.as_dict()},
        environment=environment,
        as_of=as_of,
        kickoff_utc=kickoff_utc,
        competition_id=_optional_text(fixture.get("competition_id")) or "",
        fixture_id=fixture_id,
    )
    return {
        "fixture_id": fixture_id,
        "kickoff_utc": _iso(kickoff_utc),
        "home_team": _optional_text(fixture.get("home_team")),
        "away_team": _optional_text(fixture.get("away_team")),
        "market": _optional_text(fixture.get("market")),
        "line": _optional_text(fixture.get("line")),
        "odds": _optional_text(fixture.get("odds")),
        "data_readiness": readiness.as_dict(),
        "data_status": readiness.data_status.value,
        "reason_code": readiness.reason_code.value if readiness.reason_code else None,
        "decision_contract": decision["decision_contract"],
        "decision_tier": decision["decision_tier"],
        "lock_eligible": decision["lock_eligible"],
        "recommendation_id": decision["recommendation_id"],
        "provider_calls": 0,
        "db_writes": 0,
    }


def _market_payload(fixture: Mapping[str, Any]) -> dict[str, Any] | None:
    market = _optional_text(fixture.get("market"))
    if market is None:
        return None
    line = _optional_text(fixture.get("line"))
    odds = _optional_text(fixture.get("odds"))
    payload = {
        "market": market,
        "line": line,
        "odds": odds,
        "tendency": _optional_text(fixture.get("selection")) or "HOME",
    }
    if line is not None and odds is not None:
        payload["decision"] = "PICK"
    return payload


def _recommendation_payload(
    fixture: Mapping[str, Any],
    market: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    recommendation_id = _optional_text(fixture.get("recommendation_id"))
    if recommendation_id is None:
        return None
    payload: dict[str, Any] = {"recommendation_id": recommendation_id}
    if market is not None:
        payload.update(
            {
                "market": market.get("market"),
                "line": market.get("line"),
                "odds": market.get("odds"),
                "selection": market.get("tendency"),
            },
        )
    return payload


def _refresh_summary(
    ticks: Sequence[Any],
    *,
    configured_endpoints: Sequence[str],
    endpoint_allowlist: Sequence[str],
    skipped_endpoints: Sequence[str],
    hard_cap: int,
) -> dict[str, Any]:
    tick_payloads = [tick.as_dict() for tick in ticks]
    next_tick = (
        min(tick_payloads, key=lambda item: str(item["scheduled_at"])) if tick_payloads else None
    )
    return {
        "ticks": tick_payloads,
        "projected_calls_by_tick": {tick.task_key: tick.projected_calls for tick in ticks},
        "projected_calls_total": sum(int(tick.projected_calls) for tick in ticks),
        "blocked_ticks": [tick.task_key for tick in ticks if tick.status == "BLOCKED"],
        "configured_endpoint_allowlist": list(configured_endpoints),
        "endpoint_allowlist": list(endpoint_allowlist),
        "skipped_endpoints": list(skipped_endpoints),
        "hard_cap": hard_cap,
        "next_refresh_tick": next_tick,
    }


def _lock_candidates(
    fixtures: Sequence[Mapping[str, Any]],
    *,
    as_of: datetime,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for fixture in fixtures:
        recommendation_id = _optional_text(fixture.get("recommendation_id"))
        if (
            fixture.get("lock_eligible") is True
            and recommendation_id is not None
            and _datetime_value(str(fixture["kickoff_utc"])) > as_of
        ):
            candidates.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "recommendation_id": recommendation_id,
                    "needs_approval": True,
                    "approval_required": "STAGING_FORMAL_LOCK_CAPTURE_WRITE",
                    "would_write_lock": False,
                },
            )
    return candidates


def _required_approvals(
    *,
    projected_provider_calls: int,
    lock_candidate_count: int,
    approve_provider_calls: bool,
    approve_db_writes: bool,
    approve_lock_write: bool,
) -> list[str]:
    required: list[str] = []
    if projected_provider_calls > 0 and not approve_provider_calls:
        required.append(PROVIDER_CALLS_APPROVAL)
    if projected_provider_calls > 0 and not approve_db_writes:
        required.append(DB_WRITE_APPROVAL)
    if lock_candidate_count > 0 and not approve_lock_write:
        required.append(LOCK_WRITE_APPROVAL)
    return required


def _readiness_summary(fixtures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {status.value: 0 for status in DataStatus}
    reason_codes: dict[str, int] = {}
    blocked_fixture_ids: list[str] = []
    for fixture in fixtures:
        status = str(fixture["data_status"])
        counts[status] = counts.get(status, 0) + 1
        reason_code = _optional_text(fixture.get("reason_code"))
        if reason_code is not None:
            reason_codes[reason_code] = reason_codes.get(reason_code, 0) + 1
        if status == DataStatus.BLOCKED.value:
            blocked_fixture_ids.append(str(fixture["fixture_id"]))
    return {
        "counts_by_status": counts,
        "reason_codes": reason_codes,
        "blocked_fixture_ids": blocked_fixture_ids,
    }


def _decision_summary(fixtures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for fixture in fixtures:
        tier = str(fixture["decision_tier"])
        counts[tier] = counts.get(tier, 0) + 1
    return {
        "would_generate": len(fixtures),
        "counts_by_decision_tier": counts,
        "lock_eligible_count": len(
            [item for item in fixtures if item.get("lock_eligible") is True],
        ),
    }


def _would_generate_payload(card_count: int) -> dict[str, Any]:
    return {
        "dashboard_would_generate": {"would_generate": card_count > 0, "card_count": card_count},
        "markdown_would_generate": {"would_generate": card_count > 0, "card_count": card_count},
        "html_would_generate": {"would_generate": card_count > 0, "card_count": card_count},
        "audit_would_generate": {"would_generate": card_count > 0, "row_count": card_count},
    }


def _provider_usage_plan(
    *,
    configured_endpoints: Sequence[str],
    endpoint_allowlist: Sequence[str],
    skipped_endpoints: Sequence[str],
    projected_calls: int,
) -> dict[str, Any]:
    return {
        "provider_calls": 0,
        "projected_calls": projected_calls,
        "configured_endpoint_allowlist": list(configured_endpoints),
        "endpoint_allowlist": list(endpoint_allowlist),
        "skipped_endpoints": list(skipped_endpoints),
        "would_enqueue": False,
    }


def _base_payload(
    *,
    football_day: date,
    environment: str,
    environment_policy: Mapping[str, Any],
    as_of: datetime,
    fixture_count: int,
) -> dict[str, Any]:
    return {
        "football_day": football_day.isoformat(),
        "environment": environment,
        "environment_policy": dict(environment_policy),
        "mode": "dry_run",
        "as_of": _iso(as_of),
        "fixture_count": fixture_count,
        "provider_calls": 0,
        "db_writes": 0,
    }


def _normalize_fixture(item: Mapping[str, Any]) -> dict[str, Any]:
    fixture_id = _optional_text(item.get("fixture_id") or item.get("id"))
    if fixture_id is None:
        raise ValueError("fixture_id is required")
    kickoff = item.get("kickoff_utc") or item.get("date")
    if kickoff is None:
        raise ValueError("kickoff_utc is required")
    return {
        **dict(item),
        "fixture_id": fixture_id,
        "competition_id": str(item.get("competition_id") or ""),
        "kickoff_utc": _datetime_value(kickoff),
    }


def _single_competition_id(fixtures: Sequence[Mapping[str, Any]]) -> str:
    values = {str(item.get("competition_id") or "") for item in fixtures}
    values.discard("")
    if len(values) != 1:
        raise ValueError("MATCHDAY_POLICY_NOT_AVAILABLE")
    return values.pop()


def _endpoint_lists(endpoints: Sequence[str]) -> tuple[list[str], list[str]]:
    normalized = [str(endpoint).strip().lower() for endpoint in endpoints if str(endpoint).strip()]
    effective = [
        endpoint
        for endpoint in EFFECTIVE_ENDPOINT_ORDER
        if endpoint in normalized and endpoint in AUTHORIZED_MATCHDAY_ENDPOINTS
    ]
    skipped = sorted(
        {
            endpoint
            for endpoint in normalized
            if endpoint not in AUTHORIZED_MATCHDAY_ENDPOINTS
        },
    )
    return effective, skipped


def _datetime_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _normalize_utc(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _normalize_utc(parsed)


def _normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    return _normalize_utc(value).isoformat().replace("+00:00", "Z")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]
