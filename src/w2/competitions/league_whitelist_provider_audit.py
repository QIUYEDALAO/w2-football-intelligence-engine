"""Controlled provider audit execution.

Live network access is guarded by the CLI's --real-provider-audit switch, which
is the league whitelist equivalent of the ingestion --live gate.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from w2.competitions.league_whitelist_audit import (
    AUDIT_ENDPOINT_ALLOWLIST,
    EVIDENCE_ONLY_AUDIT_MODE,
    EVIDENCE_ONLY_AUDIT_MODE_OUTPUT,
    EVIDENCE_ONLY_ENDPOINT_ALLOWLIST,
    MIN_BOOKMAKER_DEPTH,
    AuditItem,
    AuditItemStatus,
    build_league_whitelist_audit_result,
    evidence_only_provider_calls_for_audit,
    planned_provider_calls_for_audit,
)
from w2.competitions.league_whitelist_scope import (
    IN_SEASON_NATIONAL_LEAGUES as _IN_SEASON_NATIONAL_LEAGUES,
)
from w2.competitions.league_whitelist_scope import (
    NATIONAL_LEAGUES_OFFSEASON,
)
from w2.competitions.odds_market_mapping import bookmaker_observed_evidence
from w2.competitions.registry import CompetitionRegistryEntry
from w2.providers.quota import parse_api_football_quota

AUDIT_PROVIDER_ENDPOINT_ALLOWLIST = frozenset(AUDIT_ENDPOINT_ALLOWLIST)
EVIDENCE_ONLY_PROVIDER_ENDPOINT_ALLOWLIST = frozenset(EVIDENCE_ONLY_ENDPOINT_ALLOWLIST)
IN_SEASON_NATIONAL_LEAGUES = _IN_SEASON_NATIONAL_LEAGUES
LEAGUE_PROVIDER_HARD_CAPS = {
    "brasileirao_serie_a": 13,
    "argentina_primera": 15,
    "mls": 13,
    "chinese_super_league": 13,
    "allsvenskan": 13,
    "eliteserien": 13,
}
API_FOOTBALL_HTTP_PATHS = {
    "lineups": "fixtures/lineups",
    "statistics": "fixtures/statistics",
}
STOP_STATUSES = {
    "GLOBAL_PROVIDER_HARD_CAP_REACHED",
    "LEAGUE_PROVIDER_HARD_CAP_REACHED",
    "PLAN_DOES_NOT_COVER_SEASON",
    "PROVIDER_HTTP_429",
    "DAILY_QUOTA_EXHAUSTED",
    "QUOTA_WARNING",
    "ENDPOINT_NOT_AUTHORIZED",
    "PROVIDER_RESPONSE_SCHEMA_UNSAFE",
    "PROVIDER_KEY_INVALID",
    "PROVIDER_PAYLOAD_ERROR",
}


class ProviderAuditStopped(RuntimeError):
    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


class ApiFootballRequester(Protocol):
    def __call__(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        pass


@dataclass
class ProviderAuditBudget:
    daily_hard_cap: int
    actual_provider_calls: int = 0

    def reserve_call(self, *, league_calls: int, league_hard_cap: int) -> None:
        if self.actual_provider_calls >= self.daily_hard_cap:
            raise ProviderAuditStopped("GLOBAL_PROVIDER_HARD_CAP_REACHED")
        if league_calls >= league_hard_cap:
            raise ProviderAuditStopped("LEAGUE_PROVIDER_HARD_CAP_REACHED")
        self.actual_provider_calls += 1


@dataclass
class LocalProviderAuditLedger:
    records: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self,
        *,
        competition_id: str,
        endpoint: str,
        league_id: str,
        fixture_id: str,
        status_code: int,
        response_count: int,
        provider_call_index: int,
        league_call_index: int,
        quota_remaining: int | None,
        captured_at: datetime,
        error: str | None = None,
    ) -> None:
        self.records.append(
            {
                "competition_id": competition_id,
                "endpoint": endpoint,
                "league_id": league_id,
                "fixture_id": fixture_id or None,
                "status_code": status_code,
                "response_count": response_count,
                "provider_call_index": provider_call_index,
                "league_call_index": league_call_index,
                "quota_remaining": quota_remaining,
                "captured_at": captured_at.astimezone(UTC).isoformat(),
                "error": error,
            }
        )

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


@dataclass
class ApiFootballLeagueAuditProvider:
    competition_id: str
    league_hard_cap: int
    budget: ProviderAuditBudget
    ledger: LocalProviderAuditLedger
    requester: ApiFootballRequester | None = None
    base_url: str = "https://v3.football.api-sports.io"
    api_key_env_name: str = "W2_API_FOOTBALL_API_KEY"
    request_interval_seconds: float = 10.0
    sleeper: Callable[[float], None] = time.sleep
    allowed_endpoints: frozenset[str] = AUDIT_PROVIDER_ENDPOINT_ALLOWLIST
    fail_fast_on_plan_restricted: bool = False
    league_calls: int = 0

    def get_league(self, league_id: str, season: str) -> dict[str, Any]:
        payload = self._request("leagues", {"id": league_id, "season": season}, league_id=league_id)
        rows = _response_list(payload)
        row = rows[0] if rows else {}
        league = row.get("league") if isinstance(row, dict) else {}
        country = row.get("country") if isinstance(row, dict) else {}
        seasons = row.get("seasons") if isinstance(row, dict) else []
        season_row = _matching_season(seasons, season)
        row_id = row.get("id") if isinstance(row, dict) else ""
        row_name = row.get("name") if isinstance(row, dict) else ""
        row_country = row.get("country") if isinstance(row, dict) else ""
        return {
            "id": _text(_mapping(league).get("id") or row_id),
            "name": _text(_mapping(league).get("name") or row_name),
            "country": _text(_mapping(country).get("name") or row_country),
            "season": str(season_row.get("year") or season),
            "team_count": _int(row.get("team_count") if isinstance(row, dict) else None),
        }

    def get_fixtures(
        self,
        league_id: str,
        season: str,
        status: str,
    ) -> list[dict[str, Any]]:
        params = {"league": league_id, "season": season}
        if status == "future":
            params["next"] = "5"
        else:
            params["status"] = status
        return _response_list(self._request("fixtures", params, league_id=league_id))

    def get_results(self, league_id: str, season: str) -> list[dict[str, Any]]:
        return _response_list(
            self._request(
                "fixtures",
                {"league": league_id, "season": season, "status": "FT"},
                league_id=league_id,
            )
        )

    def get_fixture_statistics(self, fixture_id: str) -> dict[str, Any]:
        if not fixture_id:
            return {}
        return self._request("statistics", {"fixture": fixture_id}, fixture_id=fixture_id)

    def get_fixture_lineups(self, fixture_id: str) -> list[dict[str, Any]]:
        if not fixture_id:
            return []
        return _response_list(
            self._request("lineups", {"fixture": fixture_id}, fixture_id=fixture_id)
        )

    def get_injuries(self, league_id: str, fixture_id: str | None = None) -> list[dict[str, Any]]:
        params = {"league": league_id}
        if fixture_id:
            params["fixture"] = fixture_id
        return _response_list(
            self._request("injuries", params, league_id=league_id, fixture_id=fixture_id or "")
        )

    def get_odds(self, fixture_id: str) -> list[dict[str, Any]]:
        if not fixture_id:
            return []
        return _response_list(self._request("odds", {"fixture": fixture_id}, fixture_id=fixture_id))

    def get_squad_value_mapping(self, competition_id: str) -> dict[str, Any] | None:
        return None

    def _request(
        self,
        endpoint: str,
        params: dict[str, str],
        *,
        league_id: str = "",
        fixture_id: str = "",
    ) -> dict[str, Any]:
        if endpoint not in self.allowed_endpoints:
            raise ProviderAuditStopped("ENDPOINT_NOT_AUTHORIZED")
        if self.requester is None:
            _ensure_provider_key_http_safe(self.api_key_env_name)
        self.budget.reserve_call(
            league_calls=self.league_calls,
            league_hard_cap=self.league_hard_cap,
        )
        self.league_calls += 1
        if self.request_interval_seconds > 0:
            self.sleeper(self.request_interval_seconds)
        status_code, headers, payload = self._perform_request(endpoint, params)
        captured_at = datetime.now(UTC)
        response_count = _response_count(payload)
        quota = parse_api_football_quota(headers=headers, payload=payload, observed_at=captured_at)
        payload_error = _provider_payload_error(payload)
        error = payload_error or (
            None if status_code < 400 else f"PROVIDER_HTTP_{status_code}"
        )
        self.ledger.record(
            competition_id=self.competition_id,
            endpoint=endpoint,
            league_id=league_id,
            fixture_id=fixture_id,
            status_code=status_code,
            response_count=response_count,
            provider_call_index=self.budget.actual_provider_calls,
            league_call_index=self.league_calls,
            quota_remaining=quota.daily_remaining,
            captured_at=captured_at,
            error=error,
        )
        if status_code == 429:
            raise ProviderAuditStopped("PROVIDER_HTTP_429")
        if quota.daily_remaining is not None and quota.daily_remaining <= 0:
            raise ProviderAuditStopped("DAILY_QUOTA_EXHAUSTED")
        if quota.daily_remaining is not None and quota.daily_remaining <= 10:
            raise ProviderAuditStopped("QUOTA_WARNING")
        if payload_error == "PROVIDER_PLAN_RESTRICTED" and self.fail_fast_on_plan_restricted:
            raise ProviderAuditStopped("PLAN_DOES_NOT_COVER_SEASON")
        if payload_error and payload_error != "PROVIDER_PLAN_RESTRICTED":
            raise ProviderAuditStopped(payload_error)
        if not isinstance(payload.get("response"), (list, dict)):
            raise ProviderAuditStopped("PROVIDER_RESPONSE_SCHEMA_UNSAFE")
        return payload

    def _perform_request(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        if self.requester is not None:
            return self.requester(endpoint, params)
        return _default_api_football_request(
            endpoint,
            params,
            base_url=self.base_url,
            api_key_env_name=self.api_key_env_name,
        )


def evaluate_controlled_provider_league_audit(
    entry: CompetitionRegistryEntry,
    *,
    environment: str,
    provider: ApiFootballLeagueAuditProvider,
    audit_mode: str = "enablement",
    audit_season_override: str | None = None,
) -> Any:
    if audit_mode == EVIDENCE_ONLY_AUDIT_MODE:
        return evaluate_evidence_only_provider_league_audit(
            entry,
            environment=environment,
            provider=provider,
            audit_season_override=audit_season_override,
        )
    league_id = entry.provider_mapping.get("api_football_league_id", "")
    configured_season = _audit_season(entry, audit_season_override)
    warnings = list(_league_warnings(entry.competition_id))
    try:
        season_data = _resolve_audit_season_data(
            entry,
            provider=provider,
            league_id=league_id,
            configured_season=configured_season,
        )
        league = season_data["league"]
        future = season_data["future"]
        results = season_data["results"]
        audit_season = season_data["season"]
        fallback_used = audit_season != configured_season
        if fallback_used:
            warnings.append(
                "AUDIT_SEASON_FALLBACK:"
                f" configured={configured_season} audited={audit_season}"
            )
        fixture_ids = _fixture_ids_from_rows(*future, *results)
        samples = fixture_ids[:1] if fallback_used else fixture_ids[:2]
        items = (
            _provider_mapping_item(
                entry,
                league,
                season=audit_season,
                configured_season=configured_season,
            ),
            _fixtures_item(
                future,
                query_params={"league": league_id, "season": audit_season, "next": "5"},
                competition_id=entry.competition_id,
                configured_season=configured_season,
                audit_mode=audit_mode,
                has_recent_results=bool(results),
            ),
            _results_item(results),
            _sample_item("xg", samples, provider.get_fixture_statistics, _has_xg, "xG statistics"),
            _lineups_injuries_item(league_id, samples, provider),
            _bookmaker_depth_item(samples, provider),
            AuditItem(
                name="squad_value",
                status=AuditItemStatus.CANNOT_VERIFY,
                message="squad value mapping unavailable",
            ),
        )
        return build_league_whitelist_audit_result(
            entry,
            environment=environment,
            provider_calls=provider.league_calls,
            hard_cap=provider.league_hard_cap,
            items=items,
            blockers=(),
            warnings=tuple(warnings),
            planned_provider_calls=planned_provider_calls_for_audit(),
            actual_provider_calls=provider.league_calls,
            provider_call_approval_required=False,
        )
    except ProviderAuditStopped as exc:
        return build_league_whitelist_audit_result(
            entry,
            environment=environment,
            provider_calls=provider.league_calls,
            hard_cap=provider.league_hard_cap,
            items=tuple(
                AuditItem(name=name, status=AuditItemStatus.NOT_AUDITED, message=exc.status)
                for name in (
                    "provider_mapping",
                    "fixtures",
                    "results",
                    "xg",
                    "lineups_injuries",
                    "bookmaker_depth",
                    "squad_value",
                )
            ),
            blockers=(exc.status,),
            warnings=tuple(warnings),
            planned_provider_calls=planned_provider_calls_for_audit(),
            actual_provider_calls=provider.league_calls,
            provider_call_approval_required=False,
            overall_status=exc.status,
        )


def evaluate_evidence_only_provider_league_audit(
    entry: CompetitionRegistryEntry,
    *,
    environment: str,
    provider: ApiFootballLeagueAuditProvider,
    audit_season_override: str | None = None,
) -> Any:
    league_id = entry.provider_mapping.get("api_football_league_id", "")
    configured_season = _audit_season(entry, audit_season_override)
    warnings = [
        *_league_warnings(entry.competition_id),
        f"{EVIDENCE_ONLY_AUDIT_MODE_OUTPUT}_NOT_ENABLEMENT",
    ]
    try:
        historical_override = bool(_text(audit_season_override))
        league = provider.get_league(league_id, configured_season)
        if historical_override:
            future: list[dict[str, Any]] = []
            results = provider.get_results(league_id, configured_season)
            fixture_rows = results
            fixture_query_params: dict[str, Any] = {
                "results": {
                    "league": league_id,
                    "season": configured_season,
                    "status": "FT",
                },
            }
        else:
            future = provider.get_fixtures(league_id, configured_season, "future")
            results = provider.get_results(league_id, configured_season)
            fixture_rows = future
            fixture_query_params = {
                "future": {
                    "league": league_id,
                    "season": configured_season,
                    "next": "5",
                },
                "results": {
                    "league": league_id,
                    "season": configured_season,
                    "status": "FT",
                },
            }
        fixture_ids = _fixture_ids_from_rows(*fixture_rows, *results)
        sample = fixture_ids[:1]
        items = (
            _provider_mapping_item(
                entry,
                league,
                season=configured_season,
                configured_season=configured_season,
            ),
            _fixtures_item(
                fixture_rows,
                query_params=fixture_query_params,
                competition_id=entry.competition_id,
                configured_season=configured_season,
                audit_mode=EVIDENCE_ONLY_AUDIT_MODE,
                has_recent_results=bool(results),
            ),
            _bookmaker_depth_item(sample, provider),
        )
        result = build_league_whitelist_audit_result(
            entry,
            environment=environment,
            provider_calls=provider.league_calls,
            hard_cap=provider.league_hard_cap,
            items=items,
            blockers=(),
            warnings=tuple(warnings),
            planned_provider_calls=evidence_only_provider_calls_for_audit(),
            actual_provider_calls=provider.league_calls,
            provider_call_approval_required=False,
            overall_status=EVIDENCE_ONLY_AUDIT_MODE_OUTPUT,
        )
        return replace(
            result,
            endpoint_allowlist=EVIDENCE_ONLY_ENDPOINT_ALLOWLIST,
            audit_mode=EVIDENCE_ONLY_AUDIT_MODE_OUTPUT,
            can_enable=False,
            enablement_evaluated=False,
            evidence_only=True,
        )
    except ProviderAuditStopped as exc:
        result = build_league_whitelist_audit_result(
            entry,
            environment=environment,
            provider_calls=provider.league_calls,
            hard_cap=provider.league_hard_cap,
            items=tuple(
                AuditItem(name=name, status=AuditItemStatus.NOT_AUDITED, message=exc.status)
                for name in (
                    "provider_mapping",
                    "fixtures",
                    "bookmaker_depth",
                )
            ),
            blockers=(exc.status,),
            warnings=tuple(warnings),
            planned_provider_calls=evidence_only_provider_calls_for_audit(),
            actual_provider_calls=provider.league_calls,
            provider_call_approval_required=False,
            overall_status=exc.status,
        )
        return replace(
            result,
            endpoint_allowlist=EVIDENCE_ONLY_ENDPOINT_ALLOWLIST,
            audit_mode=EVIDENCE_ONLY_AUDIT_MODE_OUTPUT,
            can_enable=False,
            enablement_evaluated=False,
            evidence_only=True,
        )


def _audit_season(
    entry: CompetitionRegistryEntry,
    audit_season_override: str | None = None,
) -> str:
    override = _text(audit_season_override)
    if override:
        return override
    return entry.provider_mapping.get("api_football_season") or entry.season


def write_provider_audit_outputs(
    *,
    out_dir: Path,
    results: list[Any],
    ledger: LocalProviderAuditLedger,
    status: str,
    stopped_early: bool,
    stopped_reason: str | None = None,
    skipped_existing_reports: list[str] | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_paths: list[str] = []
    for result in results:
        path = out_dir / f"W2_WHITELIST_AUDIT_{result.competition_id}.json"
        path.write_text(
            json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report_paths.append(str(path))
    ledger_path = out_dir / "audit_ledger.json"
    ledger.write_json(ledger_path)
    summary = {
        "status": status,
        "output_dir": str(out_dir),
        "actual_provider_calls_total": len(ledger.records),
        "stopped_early": stopped_early,
        "stopped_reason": stopped_reason,
        "cooldown_recommended": stopped_reason == "PROVIDER_HTTP_429",
        "skipped_existing_reports": skipped_existing_reports or [],
        "reports": report_paths,
        "audit_ledger_json": str(ledger_path),
        "per_league": [
            {
                "competition_id": result.competition_id,
                "calls": result.actual_provider_calls,
                "can_enable": result.can_enable,
                "items": {
                    item.name: item.status.value
                    for item in result.items
                },
                "blockers": list(result.blockers),
                "warnings": list(result.warnings),
            }
            for result in results
        ],
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary["summary_json"] = str(summary_path)
    return summary


def _default_api_football_request(
    endpoint: str,
    params: dict[str, str],
    *,
    base_url: str,
    api_key_env_name: str,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    api_key = _normalized_provider_key(api_key_env_name)
    query = urllib.parse.urlencode(params)
    suffix = f"?{query}" if query else ""
    path = API_FOOTBALL_HTTP_PATHS.get(endpoint, endpoint)
    request = urllib.request.Request(  # noqa: S310
        f"{base_url}/{path}{suffix}",
        headers={"x-apisports-key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            raw = response.read()
            return response.status, _sanitize_headers(response.headers), _load_payload(raw)
    except urllib.error.HTTPError as exc:
        return exc.code, _sanitize_headers(exc.headers), _load_payload(exc.read())
    except urllib.error.URLError:
        time.sleep(0.2)
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            raw = response.read()
            return response.status, _sanitize_headers(response.headers), _load_payload(raw)


def _provider_mapping_item(
    entry: CompetitionRegistryEntry,
    league: dict[str, Any],
    *,
    season: str,
    configured_season: str,
) -> AuditItem:
    expected_id = entry.provider_mapping.get("api_football_league_id")
    expected_name = (
        entry.provider_mapping.get("api_football_league_name")
        or _profile_value(entry, "name")
    )
    expected_country = (
        entry.provider_mapping.get("api_football_country")
        or _profile_value(entry, "country")
    )
    expected_team_count = _int(_profile_value(entry, "expected_team_count"))
    league_id_matches = str(league.get("id") or "") == expected_id
    team_count = _int(league.get("team_count"))
    advisory_checks = {
        "name": _norm(league.get("name")) == _norm(expected_name),
        "country": _norm(league.get("country")) == _norm(expected_country),
        "season": str(league.get("season") or "") == str(season),
        "team_count": not team_count or team_count == expected_team_count,
        "configured_season": str(season) == str(configured_season),
    }
    evidence = _provider_mapping_evidence(
        league,
        expected_id=expected_id,
        expected_name=expected_name,
        expected_country=expected_country,
        expected_season=season,
        expected_team_count=expected_team_count,
        advisory_checks=advisory_checks,
    )
    if league_id_matches:
        return AuditItem(
            name="provider_mapping",
            status=AuditItemStatus.PASS,
            message="league_id match; advisory fields recorded",
            observed_evidence=evidence,
        )
    return AuditItem(
        name="provider_mapping",
        status=AuditItemStatus.FAIL,
        message="provider mapping mismatch:league_id",
        observed_evidence=evidence,
    )


def _resolve_audit_season_data(
    entry: CompetitionRegistryEntry,
    *,
    provider: ApiFootballLeagueAuditProvider,
    league_id: str,
    configured_season: str,
) -> dict[str, Any]:
    selected: dict[str, Any] | None = None
    for season in _audit_season_candidates(entry, configured_season):
        league = provider.get_league(league_id, season)
        future = provider.get_fixtures(league_id, season, "future")
        results = provider.get_results(league_id, season)
        candidate = {
            "season": season,
            "league": league,
            "future": future,
            "results": results,
        }
        if selected is None:
            selected = candidate
        if _league_has_mapping(league) or future or results:
            return candidate
    return selected or {"season": configured_season, "league": {}, "future": [], "results": []}


def _audit_season_candidates(
    entry: CompetitionRegistryEntry,
    configured_season: str,
) -> tuple[str, ...]:
    configured = _text(configured_season)
    candidates = [configured] if configured else []
    payload = _profile_payload(entry)
    explicit = payload.get("api_football_audit_seasons")
    if isinstance(explicit, list):
        for item in explicit:
            text = _text(item)
            if text and text not in candidates:
                candidates.append(text)
    activation_plan = _text(payload.get("activation_plan"))
    if (
        activation_plan == "AUDIT_THEN_STAGING_ENABLE_NOW_IN_SEASON"
        and configured.isdigit()
    ):
        for offset in (1, 2):
            previous = str(int(configured) - offset)
            if previous not in candidates:
                candidates.append(previous)
    return tuple(candidates)


def _league_has_mapping(league: dict[str, Any]) -> bool:
    return bool(_text(league.get("id")) and _text(league.get("name")))


def _fixtures_item(
    rows: list[dict[str, Any]],
    *,
    query_params: dict[str, Any] | None = None,
    competition_id: str = "",
    configured_season: str = "",
    audit_mode: str = "enablement",
    has_recent_results: bool = False,
) -> AuditItem:
    ids = _fixture_ids_from_rows(*rows)
    observed_evidence = {
        "observed_fixture_query_params": dict(query_params or {}),
        "observed_fixture_response_count": len(rows),
    }
    if ids:
        return AuditItem(
            name="fixtures",
            status=AuditItemStatus.PASS,
            message="future fixtures available",
            evidence_fixture_ids=tuple(ids[:3]),
            observed_evidence=observed_evidence,
        )
    message = _empty_fixtures_message(
        competition_id=competition_id,
        configured_season=configured_season,
        audit_mode=audit_mode,
        has_recent_results=has_recent_results,
    )
    return AuditItem(
        name="fixtures",
        status=AuditItemStatus.FAIL,
        message=message,
        observed_evidence=observed_evidence,
    )


def _results_item(rows: list[dict[str, Any]]) -> AuditItem:
    ids = tuple(fixture_id for fixture_id in _fixture_ids_from_rows(*rows) if fixture_id)
    if ids:
        return AuditItem(
            name="results",
            status=AuditItemStatus.PASS,
            message="finished scores available",
            evidence_fixture_ids=ids[:3],
        )
    return AuditItem(name="results", status=AuditItemStatus.FAIL, message="finished scores missing")


def _sample_item(
    name: str,
    fixture_ids: tuple[str, ...],
    fetcher: Any,
    predicate: Any,
    label: str,
) -> AuditItem:
    tried: list[str] = []
    for fixture_id in fixture_ids[:2]:
        tried.append(fixture_id)
        payload = fetcher(fixture_id)
        if predicate(payload):
            return AuditItem(
                name=name,
                status=AuditItemStatus.PASS,
                message=f"{label} available",
                evidence_fixture_ids=(fixture_id,),
            )
    return AuditItem(
        name=name,
        status=AuditItemStatus.FAIL,
        message=f"{label} missing",
        evidence_fixture_ids=tuple(tried),
    )


def _bookmaker_depth_item(
    fixture_ids: tuple[str, ...],
    provider: ApiFootballLeagueAuditProvider,
) -> AuditItem:
    tried: list[str] = []
    latest_evidence = _bookmaker_observed_evidence([])
    for fixture_id in fixture_ids[:2]:
        tried.append(fixture_id)
        odds = provider.get_odds(fixture_id)
        latest_evidence = _bookmaker_observed_evidence(odds)
        if _has_bookmaker_depth(odds):
            return AuditItem(
                name="bookmaker_depth",
                status=AuditItemStatus.PASS,
                message="bookmaker depth available",
                evidence_fixture_ids=(fixture_id,),
                observed_evidence=latest_evidence,
            )
    return AuditItem(
        name="bookmaker_depth",
        status=AuditItemStatus.FAIL,
        message="bookmaker depth missing",
        evidence_fixture_ids=tuple(tried),
        observed_evidence=latest_evidence,
    )


def _lineups_injuries_item(
    league_id: str,
    fixture_ids: tuple[str, ...],
    provider: ApiFootballLeagueAuditProvider,
) -> AuditItem:
    tried: list[str] = []
    for fixture_id in fixture_ids[:2]:
        tried.append(fixture_id)
        lineups = provider.get_fixture_lineups(fixture_id)
        injuries = provider.get_injuries(league_id, fixture_id)
        if lineups or injuries:
            return AuditItem(
                name="lineups_injuries",
                status=AuditItemStatus.PASS,
                message="lineups or injuries structured data available",
                evidence_fixture_ids=(fixture_id,),
            )
    return AuditItem(
        name="lineups_injuries",
        status=AuditItemStatus.FAIL,
        message="lineups and injuries missing",
        evidence_fixture_ids=tuple(tried),
    )


def _has_xg(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False).lower()
    return "xg" in text or "expected_goals" in text


def _has_bookmaker_depth(rows: list[dict[str, Any]]) -> bool:
    evidence = _bookmaker_observed_evidence(rows)
    return (
        int(evidence["observed_bookmaker_count"]) >= MIN_BOOKMAKER_DEPTH
        and bool(evidence["observed_has_ah"])
        and bool(evidence["observed_has_ou"])
        and bool(evidence["observed_has_line"])
    )


def _provider_mapping_evidence(
    league: dict[str, Any],
    *,
    expected_id: str | None,
    expected_name: str,
    expected_country: str,
    expected_season: str,
    expected_team_count: int,
    advisory_checks: Mapping[str, bool],
) -> dict[str, Any]:
    return {
        "observed_provider_league_id": _text(league.get("id")),
        "observed_provider_league_name": _text(league.get("name")),
        "observed_provider_country": _text(league.get("country")),
        "observed_provider_season": _text(league.get("season")),
        "observed_provider_team_count": _int(league.get("team_count")),
        "expected_provider_league_id": _text(expected_id),
        "expected_provider_league_name": expected_name,
        "expected_provider_country": expected_country,
        "expected_provider_season": expected_season,
        "expected_provider_team_count": expected_team_count,
        "advisory_mismatches": [
            key for key, ok in advisory_checks.items() if not ok
        ],
    }


def _bookmaker_observed_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return bookmaker_observed_evidence(rows, lowercase_market_names=True)


def _empty_fixtures_message(
    *,
    competition_id: str,
    configured_season: str,
    audit_mode: str,
    has_recent_results: bool,
) -> str:
    if competition_id in NATIONAL_LEAGUES_OFFSEASON:
        return "FIXTURES_EMPTY_OFF_SEASON"
    if audit_mode == "coverage-inventory" and has_recent_results:
        return "FIXTURES_QUERY_REVIEW_REQUIRED"
    if configured_season:
        return "FIXTURES_EMPTY_CONFIGURED_SEASON"
    return "FIXTURES_QUERY_REVIEW_REQUIRED"


def _league_warnings(competition_id: str) -> tuple[str, ...]:
    warnings: list[str] = []
    if competition_id == "argentina_primera":
        warnings.append(
            "ARGENTINA_PRIMERA_PLANNED_CHECK: expected_team_count=28, "
            "country/name/season exact match"
        )
    if competition_id == "chinese_super_league":
        warnings.append(
            "CHINESE_SUPER_LEAGUE_ENABLEMENT_REQUIRES_PER_MATCH_INTEGRITY_GATE_FOR_ABNORMAL_ODDS_OR_DEAD_MARKETS"
        )
    if competition_id == "mls":
        warnings.append("MLS_WORLD_CUP_CALENDAR_PERTURBATION_REVIEW_REQUIRED_BEFORE_ENABLEMENT")
    return tuple(warnings)


def _fixture_ids_from_rows(*rows: dict[str, Any]) -> tuple[str, ...]:
    ids: list[str] = []
    for row in rows:
        fixture = row.get("fixture") if isinstance(row, dict) else None
        if isinstance(fixture, dict):
            fixture_id = _text(fixture.get("id") or fixture.get("fixture_id"))
        else:
            fixture_id = (
                _text(row.get("fixture_id") or row.get("id"))
                if isinstance(row, dict)
                else ""
            )
        if fixture_id and fixture_id not in ids:
            ids.append(fixture_id)
    return tuple(ids)


def _matching_season(value: Any, season: str) -> dict[str, Any]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and str(item.get("year")) == str(season):
                return item
    return {}


def _response_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response")
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if isinstance(response, dict):
        return [response]
    return []


def _response_count(payload: dict[str, Any]) -> int:
    response = payload.get("response")
    if isinstance(response, list):
        return len(response)
    if isinstance(response, dict):
        return 1
    return 0


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _profile_value(entry: CompetitionRegistryEntry, key: str) -> Any:
    return _profile_payload(entry).get(key)


def _profile_payload(entry: CompetitionRegistryEntry) -> dict[str, Any]:
    try:
        payload = json.loads(entry.config_path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sanitize_headers(headers: Any) -> dict[str, str]:
    blocked = {"authorization", "x-apisports-key", "x-rapidapi-key", "set-cookie", "cookie"}
    return {
        str(key): str(value)
        for key, value in dict(headers).items()
        if str(key).lower() not in blocked
    }


def _load_payload(raw: bytes) -> dict[str, Any]:
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    if not isinstance(payload, dict):
        raise ProviderAuditStopped("PROVIDER_RESPONSE_SCHEMA_UNSAFE")
    return payload


def _provider_payload_error(payload: dict[str, Any]) -> str | None:
    errors = payload.get("errors")
    if not errors:
        return None
    if isinstance(errors, dict):
        keys = {str(key).lower() for key in errors}
        if "to" + "ken" in keys:
            return "PROVIDER_KEY_INVALID"
        if "requests" in keys:
            return "DAILY_QUOTA_EXHAUSTED"
        if "ratelimit" in keys:
            return "QUOTA_WARNING"
        if "plan" in keys:
            return "PROVIDER_PLAN_RESTRICTED"
        return "PROVIDER_PAYLOAD_ERROR"
    return "PROVIDER_PAYLOAD_ERROR"


def _ensure_provider_key_http_safe(api_key_env_name: str) -> None:
    _normalized_provider_key(api_key_env_name)


def _normalized_provider_key(api_key_env_name: str) -> str:
    api_key = os.environ.get(api_key_env_name)
    if not api_key:
        raise ProviderAuditStopped("PROVIDER_KEY_MISSING")
    normalized = api_key.strip()
    for prefix in (
        f"{api_key_env_name}=",
        "API_FOOTBALL=",
        "x-apisports-key:",
        "X-APISPORTS-KEY:",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
    if (
        len(normalized) >= 2
        and normalized[0] == normalized[-1]
        and normalized[0] in {"'", '"'}
    ):
        normalized = normalized[1:-1].strip()
    normalized = normalized.replace("\r", "").replace("\n", "").strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized):
        raise ProviderAuditStopped("PROVIDER_KEY_INVALID")
    try:
        normalized.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise ProviderAuditStopped("PROVIDER_KEY_INVALID") from exc
    if not normalized:
        raise ProviderAuditStopped("PROVIDER_KEY_MISSING")
    return normalized


def _norm(value: Any) -> str:
    return _text(value).strip().lower()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
