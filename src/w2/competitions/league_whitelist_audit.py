from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from w2.competitions.registry import CompetitionRegistryEntry

AUDIT_SOURCE = "w2.competitions.league_whitelist_audit.v1"
AUDIT_ENDPOINT_ALLOWLIST = (
    "leagues",
    "fixtures",
    "odds",
    "lineups",
    "injuries",
    "statistics",
)
AUDIT_ITEM_NAMES = (
    "provider_mapping",
    "fixtures",
    "results",
    "xg",
    "lineups_injuries",
    "bookmaker_depth",
    "squad_value",
)
PLANNED_PROVIDER_CALLS_BY_ENDPOINT = {
    "leagues": 1,
    "fixtures_future": 1,
    "fixtures_results": 1,
    "statistics": 1,
    "lineups": 1,
    "injuries": 1,
    "odds": 1,
    "squad_value": 0,
}


class AuditItemStatus(StrEnum):
    PASS = "PASS"  # noqa: S105 - audit status enum, not a credential.
    FAIL = "FAIL"
    NOT_AUDITED = "NOT_AUDITED"
    CANNOT_VERIFY = "CANNOT_VERIFY"
    SKIPPED_PROVIDER_NOT_APPROVED = "SKIPPED_PROVIDER_NOT_APPROVED"


class LeagueAuditProvider(Protocol):
    def get_league(self, league_id: str, season: str) -> Mapping[str, Any]: ...

    def get_fixtures(
        self,
        league_id: str,
        season: str,
        status: str,
    ) -> Sequence[Mapping[str, Any]]: ...

    def get_results(self, league_id: str, season: str) -> Sequence[Mapping[str, Any]]: ...

    def get_fixture_statistics(self, fixture_id: str) -> Mapping[str, Any]: ...

    def get_fixture_lineups(self, fixture_id: str) -> Sequence[Mapping[str, Any]]: ...

    def get_injuries(
        self,
        league_id: str,
        fixture_id: str | None = None,
    ) -> Sequence[Mapping[str, Any]]: ...

    def get_odds(self, fixture_id: str) -> Sequence[Mapping[str, Any]]: ...

    def get_squad_value_mapping(self, competition_id: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True, kw_only=True)
class AuditItem:
    name: str
    status: AuditItemStatus
    message: str
    evidence_fixture_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "evidence_fixture_ids": list(self.evidence_fixture_ids),
        }


@dataclass(frozen=True, kw_only=True)
class LeagueWhitelistAuditResult:
    competition_id: str
    league_name: str
    profile_path: str
    enabled: bool
    environment: str
    provider_calls: int
    db_reads: int
    db_writes: int
    hard_cap: int
    endpoint_allowlist: tuple[str, ...]
    items: tuple[AuditItem, ...]
    overall_status: str
    can_enable: bool
    evidence_fixture_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    planned_provider_calls: int
    planned_provider_calls_by_endpoint: Mapping[str, int]
    actual_provider_calls: int
    provider_call_approval_required: bool
    source: str = AUDIT_SOURCE

    def as_dict(self) -> dict[str, Any]:
        return {
            "competition_id": self.competition_id,
            "league_name": self.league_name,
            "profile_path": self.profile_path,
            "enabled": self.enabled,
            "environment": self.environment,
            "provider_calls": self.provider_calls,
            "db_reads": self.db_reads,
            "db_writes": self.db_writes,
            "hard_cap": self.hard_cap,
            "endpoint_allowlist": list(self.endpoint_allowlist),
            "audit_items": [item.as_dict() for item in self.items],
            "items": [item.as_dict() for item in self.items],
            "overall_status": self.overall_status,
            "status": self.overall_status,
            "can_enable": self.can_enable,
            "evidence_fixture_ids": list(self.evidence_fixture_ids),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "planned_provider_calls": self.planned_provider_calls,
            "planned_provider_calls_by_endpoint": dict(
                self.planned_provider_calls_by_endpoint
            ),
            "actual_provider_calls": self.actual_provider_calls,
            "provider_call_approval_required": self.provider_call_approval_required,
            "source": self.source,
        }


def planned_provider_calls_by_endpoint() -> dict[str, int]:
    return dict(PLANNED_PROVIDER_CALLS_BY_ENDPOINT)


def planned_provider_calls_for_audit() -> int:
    return sum(PLANNED_PROVIDER_CALLS_BY_ENDPOINT.values())


def build_not_audited_result(
    entry: CompetitionRegistryEntry,
    *,
    environment: str,
    hard_cap: int,
    reason: str = "PROVIDER_AUDIT_NOT_EXECUTED",
) -> LeagueWhitelistAuditResult:
    items = tuple(
        AuditItem(name=name, status=AuditItemStatus.NOT_AUDITED, message=reason)
        for name in AUDIT_ITEM_NAMES
    )
    blockers = tuple(f"NOT_AUDITED:{name}" for name in AUDIT_ITEM_NAMES)
    return _result(
        entry,
        environment=environment,
        provider_calls=0,
        hard_cap=hard_cap,
        items=items,
        blockers=blockers,
        warnings=(reason,),
        planned_provider_calls=planned_provider_calls_for_audit(),
        actual_provider_calls=0,
        provider_call_approval_required=True,
    )


def build_skipped_provider_not_approved_result(
    entry: CompetitionRegistryEntry,
    *,
    environment: str,
    hard_cap: int,
) -> LeagueWhitelistAuditResult:
    items = tuple(
        AuditItem(
            name=name,
            status=AuditItemStatus.SKIPPED_PROVIDER_NOT_APPROVED,
            message="NEED_USER_APPROVAL: LEAGUE_WHITELIST_PROVIDER_AUDIT",
        )
        for name in AUDIT_ITEM_NAMES
    )
    return _result(
        entry,
        environment=environment,
        provider_calls=0,
        hard_cap=hard_cap,
        items=items,
        blockers=("NEED_USER_APPROVAL: LEAGUE_WHITELIST_PROVIDER_AUDIT",),
        warnings=(),
        planned_provider_calls=planned_provider_calls_for_audit(),
        actual_provider_calls=0,
        provider_call_approval_required=True,
        overall_status="NEED_USER_APPROVAL",
    )


def build_provider_key_missing_result(
    entry: CompetitionRegistryEntry,
    *,
    environment: str,
    hard_cap: int,
) -> LeagueWhitelistAuditResult:
    return _result(
        entry,
        environment=environment,
        provider_calls=0,
        hard_cap=hard_cap,
        items=tuple(
            AuditItem(
                name=name,
                status=AuditItemStatus.SKIPPED_PROVIDER_NOT_APPROVED,
                message="PROVIDER_KEY_MISSING",
            )
            for name in AUDIT_ITEM_NAMES
        ),
        blockers=("PROVIDER_KEY_MISSING",),
        warnings=(),
        planned_provider_calls=planned_provider_calls_for_audit(),
        actual_provider_calls=0,
        provider_call_approval_required=True,
        overall_status="PROVIDER_KEY_MISSING",
    )


def build_provider_execution_not_implemented_result(
    entry: CompetitionRegistryEntry,
    *,
    environment: str,
    hard_cap: int,
) -> LeagueWhitelistAuditResult:
    status = "PROVIDER_EXECUTION_NOT_IMPLEMENTED_IN_OFFLINE_HARNESS"
    return _result(
        entry,
        environment=environment,
        provider_calls=0,
        hard_cap=hard_cap,
        items=tuple(
            AuditItem(
                name=name,
                status=AuditItemStatus.NOT_AUDITED,
                message=status,
            )
            for name in AUDIT_ITEM_NAMES
        ),
        blockers=(status,),
        warnings=(),
        planned_provider_calls=planned_provider_calls_for_audit(),
        actual_provider_calls=0,
        provider_call_approval_required=True,
        overall_status=status,
    )


def build_hard_cap_blocked_result(
    entry: CompetitionRegistryEntry,
    *,
    environment: str,
    hard_cap: int,
    planned_provider_calls: int,
) -> LeagueWhitelistAuditResult:
    return _result(
        entry,
        environment=environment,
        provider_calls=0,
        hard_cap=hard_cap,
        items=tuple(
            AuditItem(
                name=name,
                status=AuditItemStatus.SKIPPED_PROVIDER_NOT_APPROVED,
                message="BLOCKED_BY_HARD_CAP",
            )
            for name in AUDIT_ITEM_NAMES
        ),
        blockers=("BLOCKED_BY_HARD_CAP",),
        warnings=(),
        planned_provider_calls=planned_provider_calls,
        actual_provider_calls=0,
        provider_call_approval_required=True,
        overall_status="BLOCKED_BY_HARD_CAP",
    )


def build_league_whitelist_audit_result(
    entry: CompetitionRegistryEntry,
    *,
    environment: str,
    provider_calls: int,
    hard_cap: int,
    items: tuple[AuditItem, ...],
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    planned_provider_calls: int,
    actual_provider_calls: int,
    provider_call_approval_required: bool,
    overall_status: str | None = None,
) -> LeagueWhitelistAuditResult:
    return _result(
        entry,
        environment=environment,
        provider_calls=provider_calls,
        hard_cap=hard_cap,
        items=items,
        blockers=blockers,
        warnings=warnings,
        planned_provider_calls=planned_provider_calls,
        actual_provider_calls=actual_provider_calls,
        provider_call_approval_required=provider_call_approval_required,
        overall_status=overall_status,
    )


def evaluate_league_whitelist_audit(
    entry: CompetitionRegistryEntry,
    *,
    environment: str,
    provider: LeagueAuditProvider,
    hard_cap: int = 20,
) -> LeagueWhitelistAuditResult:
    league_id = entry.provider_mapping.get("api_football_league_id", "")
    season = entry.provider_mapping.get("api_football_season") or entry.season
    items = (
        _provider_mapping_item(entry, provider.get_league(league_id, season), season=season),
        _fixtures_item(provider.get_fixtures(league_id, season, "future")),
        _results_item(provider.get_results(league_id, season)),
    )
    evidence_fixture_ids = _fixture_ids(items[1], items[2])
    first_fixture_id = evidence_fixture_ids[0] if evidence_fixture_ids else ""
    remaining = (
        _xg_item(provider.get_fixture_statistics(first_fixture_id), fixture_id=first_fixture_id),
        _lineups_injuries_item(
            provider.get_fixture_lineups(first_fixture_id),
            provider.get_injuries(league_id, first_fixture_id or None),
            fixture_id=first_fixture_id,
        ),
        _bookmaker_depth_item(provider.get_odds(first_fixture_id), fixture_id=first_fixture_id),
        _squad_value_item(provider.get_squad_value_mapping(entry.competition_id)),
    )
    return _result(
        entry,
        environment=environment,
        provider_calls=planned_provider_calls_for_audit(),
        hard_cap=hard_cap,
        items=(*items, *remaining),
        blockers=(),
        warnings=_planned_warnings(entry),
        planned_provider_calls=planned_provider_calls_for_audit(),
        actual_provider_calls=planned_provider_calls_for_audit(),
        provider_call_approval_required=False,
    )


def write_audit_report(path: Path, result: LeagueWhitelistAuditResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _provider_mapping_item(
    entry: CompetitionRegistryEntry,
    league: Mapping[str, Any],
    *,
    season: str,
) -> AuditItem:
    expected_id = entry.provider_mapping.get("api_football_league_id")
    expected_team_count = _expected_team_count(entry)
    checks = {
        "league_id": str(league.get("league_id") or league.get("id") or "") == expected_id,
        "name": _norm(league.get("name")) == _norm(_profile_name(entry)),
        "country": _norm(league.get("country")) == _norm(_profile_country(entry)),
        "season": str(league.get("season") or "") == str(season),
        "team_count": _int(league.get("team_count")) == expected_team_count,
    }
    if all(checks.values()):
        return AuditItem(
            name="provider_mapping",
            status=AuditItemStatus.PASS,
            message="league/country/season/team_count match",
        )
    failed = ",".join(key for key, ok in checks.items() if not ok)
    return AuditItem(
        name="provider_mapping",
        status=AuditItemStatus.FAIL,
        message=f"provider mapping mismatch:{failed}",
    )


def _fixtures_item(fixtures: Sequence[Mapping[str, Any]]) -> AuditItem:
    ids = tuple(_fixture_id(item) for item in fixtures if _fixture_id(item))
    if ids:
        return AuditItem(
            name="fixtures",
            status=AuditItemStatus.PASS,
            message="future fixtures available",
            evidence_fixture_ids=ids[:3],
        )
    return AuditItem(
        name="fixtures",
        status=AuditItemStatus.FAIL,
        message="future fixtures missing",
    )


def _results_item(results: Sequence[Mapping[str, Any]]) -> AuditItem:
    ids = tuple(_fixture_id(item) for item in results if _fixture_id(item) and _has_score(item))
    if ids:
        return AuditItem(
            name="results",
            status=AuditItemStatus.PASS,
            message="finished scores available",
            evidence_fixture_ids=ids[:3],
        )
    return AuditItem(name="results", status=AuditItemStatus.FAIL, message="finished scores missing")


def _xg_item(statistics: Mapping[str, Any], *, fixture_id: str) -> AuditItem:
    text = json.dumps(statistics, ensure_ascii=False).lower()
    if "xg" in text or "expected_goals" in text:
        return AuditItem(
            name="xg",
            status=AuditItemStatus.PASS,
            message="xG statistics available",
            evidence_fixture_ids=(fixture_id,) if fixture_id else (),
        )
    return AuditItem(name="xg", status=AuditItemStatus.FAIL, message="xG statistics missing")


def _lineups_injuries_item(
    lineups: Sequence[Mapping[str, Any]],
    injuries: Sequence[Mapping[str, Any]],
    *,
    fixture_id: str,
) -> AuditItem:
    if lineups or injuries:
        return AuditItem(
            name="lineups_injuries",
            status=AuditItemStatus.PASS,
            message="lineups or injuries structured data available",
            evidence_fixture_ids=(fixture_id,) if fixture_id else (),
        )
    return AuditItem(
        name="lineups_injuries",
        status=AuditItemStatus.FAIL,
        message="lineups and injuries missing",
    )


def _bookmaker_depth_item(odds: Sequence[Mapping[str, Any]], *, fixture_id: str) -> AuditItem:
    bookmakers = {_text(item.get("bookmaker") or item.get("bookmaker_id")) for item in odds}
    markets = {_text(item.get("market")) for item in odds}
    has_ah = bool({"AH", "ASIAN_HANDICAP", "Asian Handicap"} & markets)
    has_ou = bool({"OU", "TOTALS", "OVER_UNDER", "Over/Under"} & markets)
    has_line = any(_text(item.get("line")) for item in odds)
    if len({item for item in bookmakers if item}) >= 3 and has_ah and has_ou and has_line:
        return AuditItem(
            name="bookmaker_depth",
            status=AuditItemStatus.PASS,
            message="AH/OU lines and bookmaker depth available",
            evidence_fixture_ids=(fixture_id,) if fixture_id else (),
        )
    return AuditItem(
        name="bookmaker_depth",
        status=AuditItemStatus.FAIL,
        message="bookmaker depth or AH/OU lines missing",
    )


def _squad_value_item(mapping: Mapping[str, Any] | None) -> AuditItem:
    if mapping and mapping.get("teams"):
        return AuditItem(
            name="squad_value",
            status=AuditItemStatus.PASS,
            message="squad value mapping available",
        )
    return AuditItem(
        name="squad_value",
        status=AuditItemStatus.CANNOT_VERIFY,
        message="squad value mapping unavailable",
    )


def _result(
    entry: CompetitionRegistryEntry,
    *,
    environment: str,
    provider_calls: int,
    hard_cap: int,
    items: tuple[AuditItem, ...],
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    planned_provider_calls: int,
    actual_provider_calls: int,
    provider_call_approval_required: bool,
    overall_status: str | None = None,
) -> LeagueWhitelistAuditResult:
    item_blockers = tuple(
        f"{item.name}:{item.status.value}"
        for item in items
        if item.status is not AuditItemStatus.PASS
    )
    can_enable = all(item.status is AuditItemStatus.PASS for item in items)
    status = overall_status or ("PASS" if can_enable else "FAIL")
    evidence = tuple(
        dict.fromkeys(
            fixture_id
            for item in items
            for fixture_id in item.evidence_fixture_ids
            if fixture_id
        )
    )
    return LeagueWhitelistAuditResult(
        competition_id=entry.competition_id,
        league_name=_profile_name(entry),
        profile_path=str(entry.config_path),
        enabled=entry.enabled,
        environment=environment,
        provider_calls=provider_calls,
        db_reads=0,
        db_writes=0,
        hard_cap=hard_cap,
        endpoint_allowlist=AUDIT_ENDPOINT_ALLOWLIST,
        items=items,
        overall_status=status,
        can_enable=can_enable and status == "PASS",
        evidence_fixture_ids=evidence,
        blockers=(*blockers, *item_blockers),
        warnings=warnings,
        planned_provider_calls=planned_provider_calls,
        planned_provider_calls_by_endpoint=planned_provider_calls_by_endpoint(),
        actual_provider_calls=actual_provider_calls,
        provider_call_approval_required=provider_call_approval_required,
    )


def _planned_warnings(entry: CompetitionRegistryEntry) -> tuple[str, ...]:
    if entry.competition_id == "argentina_primera":
        return (
            "ARGENTINA_PRIMERA_PLANNED_CHECK: expected_team_count=28, "
            "country/name/season exact match",
        )
    return ()


def _fixture_ids(*items: AuditItem) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            fixture_id
            for item in items
            for fixture_id in item.evidence_fixture_ids
            if fixture_id
        )
    )


def _fixture_id(item: Mapping[str, Any]) -> str:
    fixture = item.get("fixture")
    if isinstance(fixture, Mapping):
        return _text(fixture.get("id") or fixture.get("fixture_id"))
    return _text(item.get("fixture_id") or item.get("id"))


def _has_score(item: Mapping[str, Any]) -> bool:
    goals = item.get("goals")
    if isinstance(goals, Mapping):
        return goals.get("home") is not None and goals.get("away") is not None
    return item.get("score") is not None


def _profile_name(entry: CompetitionRegistryEntry) -> str:
    return _text(_payload(entry).get("name") or entry.competition_id)


def _profile_country(entry: CompetitionRegistryEntry) -> str:
    return _text(_payload(entry).get("country"))


def _expected_team_count(entry: CompetitionRegistryEntry) -> int:
    return _int(_payload(entry).get("expected_team_count"))


def _payload(entry: CompetitionRegistryEntry) -> Mapping[str, Any]:
    try:
        payload = json.loads(entry.config_path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _norm(value: Any) -> str:
    return _text(value).strip().lower()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
