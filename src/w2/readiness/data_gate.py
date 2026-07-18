from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from w2.domain.enums import DataStatus, DecisionReasonCode
from w2.markets.quote_identity import QUOTE_IDENTITY_SCHEMA_VERSION

READINESS_SOURCE: Literal["w2.readiness.data_gate.v1"] = "w2.readiness.data_gate.v1"


@dataclass(frozen=True)
class DataFreshnessPolicy:
    odds_max_age_minutes: int = 30
    lineups_required_after_minutes: int = 90
    lineups_hard_block_after_minutes: int = 30
    xg_max_age_hours: int = 72
    ratings_max_age_hours: int = 168
    team_value_max_age_hours: int = 168
    provider_budget_required: bool = True
    default_next_refresh_minutes: int = 30
    xg_hard_required: bool = False
    ratings_hard_required: bool = False
    team_value_hard_required: bool = False
    lineups_hard_required: bool = False


@dataclass(frozen=True)
class DataFieldReadiness:
    field: str
    present: bool
    stale: bool
    captured_at: datetime | None = None
    max_age_seconds: int | None = None
    reason_code: DecisionReasonCode | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "present": self.present,
            "stale": self.stale,
            "captured_at": _iso(self.captured_at),
            "max_age_seconds": self.max_age_seconds,
            "reason_code": self.reason_code.value if self.reason_code is not None else None,
        }


@dataclass(frozen=True)
class DataReadinessInput:
    fixture_id: str
    kickoff_utc: datetime
    as_of: datetime
    fixture_status: str | None = None
    market_available: bool = False
    odds_available: bool = False
    odds_captured_at: datetime | None = None
    lineups_available: bool = False
    lineups_captured_at: datetime | None = None
    xg_available: bool = False
    xg_captured_at: datetime | None = None
    ratings_available: bool = False
    ratings_captured_at: datetime | None = None
    team_value_available: bool = False
    team_value_captured_at: datetime | None = None
    provider_budget_status: str | None = None
    provider_budget_remaining: int | None = None
    provider_budget_exhausted: bool = False
    coverage_supported: bool = True


@dataclass(frozen=True)
class DataReadinessResult:
    data_status: DataStatus
    missing_fields: tuple[str, ...]
    stale_fields: tuple[str, ...]
    reason_code: DecisionReasonCode | None
    reason_human: str
    action: str
    next_eval_at: datetime | None
    provider_budget_status: str | None
    field_statuses: tuple[DataFieldReadiness, ...]
    source: Literal["w2.readiness.data_gate.v1"] = READINESS_SOURCE

    def as_dict(self) -> dict[str, Any]:
        return {
            "data_status": self.data_status.value,
            "missing_fields": list(self.missing_fields),
            "stale_fields": list(self.stale_fields),
            "reason_code": self.reason_code.value if self.reason_code is not None else None,
            "reason_human": self.reason_human,
            "action": self.action,
            "next_eval_at": _iso(self.next_eval_at),
            "provider_budget_status": self.provider_budget_status,
            "field_statuses": [field.as_dict() for field in self.field_statuses],
            "source": self.source,
        }


def evaluate_data_readiness(
    data: DataReadinessInput,
    policy: DataFreshnessPolicy,
) -> DataReadinessResult:
    as_of = data.as_of.astimezone(UTC)
    kickoff = data.kickoff_utc.astimezone(UTC)
    fields = _field_statuses(data, policy)
    missing = tuple(field.field for field in fields if not field.present)
    stale = tuple(field.field for field in fields if field.stale)
    next_tick = as_of + timedelta(minutes=policy.default_next_refresh_minutes)
    provider_budget_status = _provider_budget_status(data)

    if _fixture_started_or_finished(data.fixture_status):
        return _result(
            DataStatus.BLOCKED,
            fields,
            DecisionReasonCode.FIXTURE_LIVE_OR_FINISHED,
            None,
            provider_budget_status,
        )
    if not data.coverage_supported:
        return _result(
            DataStatus.BLOCKED,
            fields,
            DecisionReasonCode.COVERAGE_NONE,
            None,
            provider_budget_status,
        )
    if _provider_budget_exhausted(data, policy):
        return _result(
            DataStatus.STALE,
            fields,
            DecisionReasonCode.PROVIDER_BUDGET_EXHAUSTED,
            next_tick,
            provider_budget_status,
        )
    if "market" in missing or "odds" in missing:
        return _result(
            DataStatus.BLOCKED,
            fields,
            DecisionReasonCode.MARKET_UNAVAILABLE,
            next_tick,
            provider_budget_status,
        )
    if "odds" in stale:
        return _result(
            DataStatus.STALE,
            fields,
            DecisionReasonCode.DATA_STALE_ODDS,
            next_tick,
            provider_budget_status,
        )

    lineups_soft = "lineups" in missing or "lineups" in stale
    independent_soft = any(
        field in missing or field in stale for field in ("xg", "ratings", "team_value")
    )
    hard_missing = _hard_required_missing(missing, policy)
    if hard_missing:
        return _result(
            DataStatus.BLOCKED,
            fields,
            _hard_required_reason(hard_missing),
            next_tick,
            provider_budget_status,
        )
    if lineups_soft:
        return _result(
            DataStatus.PARTIAL,
            fields,
            DecisionReasonCode.LINEUPS_PENDING,
            _lineups_next_eval(kickoff, as_of, policy, next_tick),
            provider_budget_status,
        )
    if independent_soft:
        return _result(
            DataStatus.PARTIAL,
            fields,
            DecisionReasonCode.DATA_MISSING_XG,
            next_tick,
            provider_budget_status,
        )
    return _result(
        DataStatus.READY,
        fields,
        None,
        None,
        provider_budget_status,
    )


def build_data_readiness_from_legacy_payload(
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
    analysis_readiness: Mapping[str, Any] | None,
    provider_status: Mapping[str, Any] | None,
    as_of: datetime,
    kickoff_utc: datetime,
    policy: DataFreshnessPolicy,
) -> DataReadinessResult:
    raw_data_readiness = _as_mapping(card.get("data_readiness"))
    available_inputs = _as_mapping(_get(analysis_readiness, "available_inputs"))
    pricing = _as_mapping(card.get("pricing_shadow"))
    current_odds = _as_mapping(card.get("current_odds"))
    provider = provider_status or _as_mapping(card.get("provider_status"))
    provider_budget_status = _first_text(
        _get(provider, "provider_budget_status"),
        _get(provider, "status"),
        _get(provider, "quota_status"),
        _get(raw_data_readiness, "provider_budget_status"),
    )
    provider_budget_remaining = _int_or_none(
        _get(provider, "remaining_quota"),
        _get(provider, "provider_budget_remaining"),
        _get(provider, "daily_remaining"),
        _get(raw_data_readiness, "provider_budget_remaining"),
    )
    provider_budget_exhausted = _truthy(_get(provider, "provider_budget_exhausted")) or any(
        "PROVIDER_BUDGET_EXHAUSTED" in blocker
        for blocker in _legacy_blockers(card, market, recommendation, analysis_readiness)
    )
    if provider_budget_remaining is not None and provider_budget_remaining <= 0:
        provider_budget_exhausted = True

    market_available = _truthy(_get(available_inputs, "market_observations")) or _truthy(
        _get(available_inputs, "bookmakers"),
    )
    market_available = market_available or bool(market) or bool(recommendation)
    odds_available = (
        _truthy(_get(available_inputs, "odds_snapshots"))
        or _truthy(_get(available_inputs, "current_odds"))
        or bool(current_odds)
        or _has_market_odds(market)
        or _has_market_odds(recommendation)
    )
    odds_captured_at = _authoritative_quote_captured_at(card)
    lineups_available = _truthy(_get(available_inputs, "lineups")) or _truthy(
        _get(raw_data_readiness, "lineups"),
    )
    xg_available = _truthy(_get(available_inputs, "xg")) or _truthy(_get(raw_data_readiness, "xg"))
    ratings_available = _truthy(_get(raw_data_readiness, "ratings")) or _truthy(
        _get(pricing, "ratings_ready"),
    )
    team_value_available = _truthy(_get(raw_data_readiness, "team_value")) or _truthy(
        _get(pricing, "team_value_ready"),
    )
    status = _first_text(_get(analysis_readiness, "status"))
    if status == "READY":
        lineups_available = (
            True if _get(available_inputs, "lineups") is None else lineups_available
        )
        xg_available = True if _get(available_inputs, "xg") is None else xg_available
        ratings_available = (
            True if _get(raw_data_readiness, "ratings") is None else ratings_available
        )
        team_value_available = (
            True if _get(raw_data_readiness, "team_value") is None else team_value_available
        )
    result = evaluate_data_readiness(
        DataReadinessInput(
            fixture_id=str(_get(card, "fixture_id") or ""),
            kickoff_utc=kickoff_utc,
            as_of=as_of,
            fixture_status=_first_text(_get(card, "fixture_status"), _get(card, "status")),
            market_available=market_available,
            odds_available=odds_available,
            odds_captured_at=odds_captured_at,
            lineups_available=lineups_available,
            lineups_captured_at=_parse_utc(_get(raw_data_readiness, "lineups_captured_at")),
            xg_available=xg_available,
            xg_captured_at=_parse_utc(_get(raw_data_readiness, "xg_captured_at")),
            ratings_available=ratings_available,
            ratings_captured_at=_parse_utc(_get(raw_data_readiness, "ratings_captured_at")),
            team_value_available=team_value_available,
            team_value_captured_at=_parse_utc(_get(raw_data_readiness, "team_value_captured_at")),
            provider_budget_status=provider_budget_status,
            provider_budget_remaining=provider_budget_remaining,
            provider_budget_exhausted=provider_budget_exhausted,
            coverage_supported=not _coverage_unsupported(card, analysis_readiness),
        ),
        policy,
    )
    return _merge_legacy_status(result, analysis_readiness, card, market, recommendation, policy)


def _authoritative_quote_captured_at(card: Mapping[str, Any]) -> datetime | None:
    audit = _as_mapping(card.get("quote_identity_audit"))
    captured: list[datetime] = []
    for key in ("ah", "ou"):
        quote = _as_mapping(audit.get(key))
        if quote.get("schema_version") != QUOTE_IDENTITY_SCHEMA_VERSION:
            continue
        if quote.get("identity_status") != "COMPLETE":
            continue
        if quote.get("freshness_status") == "INCOMPLETE":
            continue
        parsed = _parse_utc(quote.get("captured_at"))
        if parsed is not None:
            captured.append(parsed)
    return min(captured) if captured else None


def result_from_mapping(payload: Mapping[str, Any]) -> DataReadinessResult | None:
    source = payload.get("source") or payload.get("readiness_source")
    if source != READINESS_SOURCE:
        return None
    reason_raw = payload.get("reason_code")
    return DataReadinessResult(
        data_status=DataStatus(str(payload["data_status"])),
        missing_fields=tuple(str(item) for item in _list(payload.get("missing_fields"))),
        stale_fields=tuple(str(item) for item in _list(payload.get("stale_fields"))),
        reason_code=DecisionReasonCode(str(reason_raw)) if reason_raw else None,
        reason_human=str(payload.get("reason_human") or ""),
        action=str(payload.get("action") or ""),
        next_eval_at=_parse_utc(payload.get("next_eval_at")),
        provider_budget_status=_first_text(payload.get("provider_budget_status")),
        field_statuses=tuple(
            DataFieldReadiness(
                field=str(item.get("field") or ""),
                present=bool(item.get("present")),
                stale=bool(item.get("stale")),
                captured_at=_parse_utc(item.get("captured_at")),
                max_age_seconds=_int_or_none(item.get("max_age_seconds")),
                reason_code=DecisionReasonCode(str(item["reason_code"]))
                if item.get("reason_code")
                else None,
            )
            for item in _list(payload.get("field_statuses"))
            if isinstance(item, Mapping)
        ),
    )


def _field_statuses(
    data: DataReadinessInput,
    policy: DataFreshnessPolicy,
) -> tuple[DataFieldReadiness, ...]:
    return (
        DataFieldReadiness(
            "market",
            data.market_available,
            False,
            reason_code=None if data.market_available else DecisionReasonCode.MARKET_UNAVAILABLE,
        ),
        _timed_field(
            "odds",
            data.odds_available,
            data.odds_captured_at,
            policy.odds_max_age_minutes * 60,
            data.as_of,
            DecisionReasonCode.MARKET_UNAVAILABLE,
            DecisionReasonCode.DATA_STALE_ODDS,
        ),
        _timed_field(
            "lineups",
            data.lineups_available,
            data.lineups_captured_at,
            None,
            data.as_of,
            DecisionReasonCode.LINEUPS_PENDING,
            DecisionReasonCode.LINEUPS_PENDING,
        ),
        _timed_field(
            "xg",
            data.xg_available,
            data.xg_captured_at,
            policy.xg_max_age_hours * 3600,
            data.as_of,
            DecisionReasonCode.DATA_MISSING_XG,
            DecisionReasonCode.DATA_MISSING_XG,
        ),
        _timed_field(
            "ratings",
            data.ratings_available,
            data.ratings_captured_at,
            policy.ratings_max_age_hours * 3600,
            data.as_of,
            DecisionReasonCode.DATA_MISSING_XG,
            DecisionReasonCode.DATA_MISSING_XG,
        ),
        _timed_field(
            "team_value",
            data.team_value_available,
            data.team_value_captured_at,
            policy.team_value_max_age_hours * 3600,
            data.as_of,
            DecisionReasonCode.DATA_MISSING_XG,
            DecisionReasonCode.DATA_MISSING_XG,
        ),
    )


def _timed_field(
    field: str,
    present: bool,
    captured_at: datetime | None,
    max_age_seconds: int | None,
    as_of: datetime,
    missing_reason: DecisionReasonCode,
    stale_reason: DecisionReasonCode,
) -> DataFieldReadiness:
    captured = captured_at.astimezone(UTC) if captured_at is not None else None
    stale = (
        present
        and captured is not None
        and max_age_seconds is not None
        and as_of.astimezone(UTC) - captured > timedelta(seconds=max_age_seconds)
    )
    reason = missing_reason if not present else stale_reason if stale else None
    return DataFieldReadiness(field, present, stale, captured, max_age_seconds, reason)


def _result(
    status: DataStatus,
    fields: tuple[DataFieldReadiness, ...],
    reason: DecisionReasonCode | None,
    next_eval_at: datetime | None,
    provider_budget_status: str | None,
) -> DataReadinessResult:
    reason_human, action = _reason_text(reason)
    return DataReadinessResult(
        data_status=status,
        missing_fields=tuple(field.field for field in fields if not field.present),
        stale_fields=tuple(field.field for field in fields if field.stale),
        reason_code=reason,
        reason_human=reason_human,
        action=action,
        next_eval_at=next_eval_at.astimezone(UTC) if next_eval_at is not None else None,
        provider_budget_status=provider_budget_status,
        field_statuses=fields,
    )


def _merge_legacy_status(
    result: DataReadinessResult,
    analysis_readiness: Mapping[str, Any] | None,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
    policy: DataFreshnessPolicy,
) -> DataReadinessResult:
    blockers = _legacy_blockers(card, market, recommendation, analysis_readiness)
    if any("PROVIDER_BUDGET_EXHAUSTED" in blocker for blocker in blockers):
        return result
    if result.reason_code in {
        DecisionReasonCode.FIXTURE_LIVE_OR_FINISHED,
        DecisionReasonCode.COVERAGE_NONE,
        DecisionReasonCode.MARKET_UNAVAILABLE,
        DecisionReasonCode.DATA_STALE_ODDS,
    }:
        return result
    status = str(_get(analysis_readiness, "status") or "").upper()
    blocker_set = {blocker.upper() for blocker in blockers}
    if "FIXTURE_NOT_UPCOMING" in blocker_set:
        return _replace_result(
            result,
            DataStatus.BLOCKED,
            DecisionReasonCode.FIXTURE_LIVE_OR_FINISHED,
            None,
            keep_next_eval=False,
        )
    if blocker_set & {"MARKET_NOT_READY", "MARKET_UNAVAILABLE", "MISSING_AH_MARKET"}:
        return _replace_result(result, DataStatus.BLOCKED, DecisionReasonCode.MARKET_UNAVAILABLE)
    if "MISSING_LINEUPS" in blocker_set and result.data_status is DataStatus.BLOCKED:
        next_eval = result.next_eval_at or _parse_utc(_get(analysis_readiness, "next_eval_at"))
        return _replace_result(
            result,
            DataStatus.PARTIAL,
            DecisionReasonCode.LINEUPS_PENDING,
            next_eval,
        )
    if "AH_EV_BELOW_FORMAL_THRESHOLD" in blocker_set and status == "BLOCKED":
        return _replace_result(result, DataStatus.PARTIAL, DecisionReasonCode.EDGE_INSUFFICIENT)
    return result


def _replace_result(
    result: DataReadinessResult,
    status: DataStatus,
    reason: DecisionReasonCode,
    next_eval_at: datetime | None = None,
    *,
    keep_next_eval: bool = True,
) -> DataReadinessResult:
    reason_human, action = _reason_text(reason)
    return DataReadinessResult(
        data_status=status,
        missing_fields=result.missing_fields,
        stale_fields=result.stale_fields,
        reason_code=reason,
        reason_human=reason_human,
        action=action,
        next_eval_at=(
            next_eval_at if next_eval_at is not None or not keep_next_eval else result.next_eval_at
        ),
        provider_budget_status=result.provider_budget_status,
        field_statuses=result.field_statuses,
    )


def _reason_text(reason: DecisionReasonCode | None) -> tuple[str, str]:
    if reason is None:
        return "", ""
    if reason is DecisionReasonCode.FIXTURE_LIVE_OR_FINISHED:
        return "比赛已开始或结束", "停止赛前评估"
    if reason is DecisionReasonCode.COVERAGE_NONE:
        return "覆盖不足", "跳过或等待覆盖"
    if reason is DecisionReasonCode.PROVIDER_BUDGET_EXHAUSTED:
        return "provider 预算耗尽", "等下一 tick 或预算恢复"
    if reason is DecisionReasonCode.MARKET_UNAVAILABLE:
        return "盘口未就绪", "等盘口开出或刷新"
    if reason is DecisionReasonCode.DATA_STALE_ODDS:
        return "盘口数据陈旧", "触发盘口刷新或等下一 tick"
    if reason is DecisionReasonCode.LINEUPS_PENDING:
        return "首发未出", "等官方首发"
    if reason is DecisionReasonCode.DATA_MISSING_XG:
        return "缺关键 xG / 独立信号不足", "等回填或下一刷新"
    if reason is DecisionReasonCode.EDGE_INSUFFICIENT:
        return "盘口价值不足", "盯价格变动"
    return "信号冲突未解释", "人工复核后再评估"


def _hard_required_missing(
    missing: tuple[str, ...],
    policy: DataFreshnessPolicy,
) -> tuple[str, ...]:
    hard_fields = []
    if policy.xg_hard_required:
        hard_fields.append("xg")
    if policy.ratings_hard_required:
        hard_fields.append("ratings")
    if policy.team_value_hard_required:
        hard_fields.append("team_value")
    if policy.lineups_hard_required:
        hard_fields.append("lineups")
    return tuple(field for field in missing if field in hard_fields)


def _hard_required_reason(fields: tuple[str, ...]) -> DecisionReasonCode:
    if "lineups" in fields:
        return DecisionReasonCode.LINEUPS_PENDING
    if "xg" in fields or "ratings" in fields or "team_value" in fields:
        return DecisionReasonCode.DATA_MISSING_XG
    return DecisionReasonCode.COVERAGE_NONE


def _lineups_next_eval(
    kickoff_utc: datetime,
    as_of: datetime,
    policy: DataFreshnessPolicy,
    fallback: datetime,
) -> datetime:
    target = kickoff_utc.astimezone(UTC) - timedelta(
        minutes=policy.lineups_required_after_minutes,
    )
    if target <= as_of.astimezone(UTC):
        target = kickoff_utc.astimezone(UTC) - timedelta(
            minutes=policy.lineups_hard_block_after_minutes,
        )
    if target <= as_of.astimezone(UTC):
        return fallback
    return target


def _provider_budget_exhausted(
    data: DataReadinessInput,
    policy: DataFreshnessPolicy,
) -> bool:
    if not policy.provider_budget_required:
        return False
    if data.provider_budget_exhausted:
        return True
    status = str(data.provider_budget_status or "").upper()
    return status in {"EXHAUSTED", "BLOCKED", "PROVIDER_BUDGET_EXHAUSTED", "QUOTA_EXHAUSTED"}


def _provider_budget_status(data: DataReadinessInput) -> str | None:
    if data.provider_budget_exhausted:
        return "EXHAUSTED"
    if data.provider_budget_status:
        return str(data.provider_budget_status)
    if data.provider_budget_remaining is not None:
        return "EXHAUSTED" if data.provider_budget_remaining <= 0 else "AVAILABLE"
    return None


def _fixture_started_or_finished(status: str | None) -> bool:
    return str(status or "").upper() in {
        "LIVE",
        "IN_PLAY",
        "1H",
        "2H",
        "HT",
        "ET",
        "P",
        "FINISHED",
        "FT",
        "AET",
        "PEN",
    }


def _coverage_unsupported(
    card: Mapping[str, Any],
    analysis_readiness: Mapping[str, Any] | None,
) -> bool:
    blockers = _legacy_blockers(card, None, None, analysis_readiness)
    text = " ".join(blockers).upper()
    return "COVERAGE_NONE" in text or "UNSUPPORTED_COVERAGE" in text


def _legacy_blockers(
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
    analysis_readiness: Mapping[str, Any] | None,
) -> list[str]:
    pricing = _as_mapping(card.get("pricing_shadow"))
    values: list[str] = []
    for source in (
        _get(analysis_readiness, "blockers"),
        _get(pricing, "formal_blockers"),
        _get(pricing, "canonical_ah_market_blocker"),
        _get(pricing, "ah_mainline_blocker"),
        _get(market, "blockers"),
        _get(market, "reason_code"),
        _get(recommendation, "reason_code"),
    ):
        values.extend(str(item) for item in _list(source) if item)
    return values


def _has_market_odds(payload: Mapping[str, Any] | None) -> bool:
    return payload is not None and _get(payload, "odds") is not None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _get(mapping: Mapping[str, Any] | None, key: str) -> Any:
    if mapping is None:
        return None
    return mapping.get(key)


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _int_or_none(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value > 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ready", "available"}
    return False


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return list(value)
    return [value]


def _parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
