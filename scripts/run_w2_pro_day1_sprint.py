from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.backtest.free_tier_2024 import (  # noqa: E402,I001
    build_free_tier_2024_backtest_report,
    report_sha256,
)
from w2.competitions.league_whitelist_scope import (  # noqa: E402
    ALL_WHITELIST_COMPETITIONS,
    IN_SEASON_NATIONAL_LEAGUES,
)
from w2.competitions.odds_market_mapping import bookmaker_observed_evidence  # noqa: E402
from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryEntry  # noqa: E402
from w2.providers.quota import parse_api_football_quota  # noqa: E402


SOURCE = "scripts.run_w2_pro_day1_sprint.v1"
IN_SEASON_LEAGUE_IDS = {
    "brasileirao_serie_a": "71",
    "argentina_primera": "128",
    "mls": "253",
    "chinese_super_league": "169",
    "allsvenskan": "113",
    "eliteserien": "103",
}
COLLECT_SEASONS = ("2026", "2024", "2025")
HISTORICAL_SEASONS = ("2024", "2025")
CURRENT_SEASON = "2026"
FINISHED_STATUSES = {"FT", "AET", "PEN"}
ODDS_PROBE_WINDOW_DAYS = 14
STOP_ERROR_KEYS = {"requests", "ratelimit", "plan"}
ENDPOINT_PATHS = {
    "lineups": "fixtures/lineups",
    "statistics": "fixtures/statistics",
}
ALLOWED_ENDPOINTS = frozenset({"status", "leagues", "fixtures", "statistics", "odds", "lineups"})


@dataclass(frozen=True)
class ProviderCall:
    endpoint: str
    params: dict[str, str]
    payload: dict[str, Any]
    headers: dict[str, str]
    status_code: int
    response_count: int
    cache_path: Path
    captured_at: datetime
    actual_call: bool
    quota_remaining: int | None
    quota_limit: int | None
    error: str | None


@dataclass
class LocalLedger:
    records: list[dict[str, Any]] = field(default_factory=list)

    def append(self, call: ProviderCall, *, phase: str, competition_id: str = "") -> None:
        self.records.append(
            {
                "phase": phase,
                "competition_id": competition_id or None,
                "endpoint": call.endpoint,
                "params": call.params,
                "status_code": call.status_code,
                "response_count": call.response_count,
                "actual_call": call.actual_call,
                "quota_remaining": call.quota_remaining,
                "quota_limit": call.quota_limit,
                "error": call.error,
                "cache_path": call.cache_path.as_posix(),
                "captured_at": call.captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            }
        )

    @property
    def actual_calls(self) -> int:
        return sum(1 for item in self.records if item["actual_call"])

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


@dataclass
class LedgeredApiFootballClient:
    persistent_root: Path
    ledger: LocalLedger
    daily_hard_cap: int
    reserve_quota: int
    request_interval_seconds: float
    base_url: str = "https://v3.football.api-sports.io"
    actual_provider_calls: int = 0
    stopped_reason: str | None = None

    def request(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        *,
        phase: str,
        competition_id: str = "",
        refresh: bool = False,
    ) -> ProviderCall:
        params = {key: str(value) for key, value in (params or {}).items()}
        if endpoint not in ALLOWED_ENDPOINTS:
            raise RuntimeError(f"ENDPOINT_NOT_AUTHORIZED:{endpoint}")
        cache_path = self._cache_path(endpoint, params)
        if cache_path.exists() and not refresh:
            payload = _load_json(cache_path)
            inner = _payload(payload)
            call = ProviderCall(
                endpoint=endpoint,
                params=params,
                payload=inner,
                headers={},
                status_code=int(payload.get("status_code") or 200),
                response_count=_response_count(inner),
                cache_path=cache_path,
                captured_at=_parse_time(payload.get("captured_at")) or datetime.now(UTC),
                actual_call=False,
                quota_remaining=_int(payload.get("quota_remaining")),
                quota_limit=_int(payload.get("quota_limit")),
                error=_text(payload.get("error")) or None,
            )
            self.ledger.append(call, phase=phase, competition_id=competition_id)
            return call
        self._reserve_live_call()
        if self.request_interval_seconds > 0 and self.actual_provider_calls > 0:
            time.sleep(self.request_interval_seconds)
        status_code, headers, payload = self._perform(endpoint, params)
        captured_at = datetime.now(UTC)
        quota = parse_api_football_quota(headers=headers, payload=payload, observed_at=captured_at)
        error = _provider_error(payload) or (
            f"PROVIDER_HTTP_{status_code}" if status_code >= 400 else None
        )
        self.actual_provider_calls += 1
        wrapped = {
            "source": SOURCE,
            "endpoint": endpoint,
            "params": params,
            "status_code": status_code,
            "quota_remaining": quota.daily_remaining,
            "quota_limit": quota.daily_limit,
            "error": error,
            "captured_at": captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "payload": payload,
        }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(wrapped, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        call = ProviderCall(
            endpoint=endpoint,
            params=params,
            payload=payload,
            headers=headers,
            status_code=status_code,
            response_count=_response_count(payload),
            cache_path=cache_path,
            captured_at=captured_at,
            actual_call=True,
            quota_remaining=quota.daily_remaining,
            quota_limit=quota.daily_limit,
            error=error,
        )
        self.ledger.append(call, phase=phase, competition_id=competition_id)
        self.stopped_reason = _stop_reason(call, reserve_quota=self.reserve_quota)
        return call

    def _reserve_live_call(self) -> None:
        if self.actual_provider_calls >= self.daily_hard_cap:
            raise RuntimeError("GLOBAL_PROVIDER_HARD_CAP_REACHED")

    def _perform(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        api_key = _provider_key()
        path = ENDPOINT_PATHS.get(endpoint, endpoint)
        query = urllib.parse.urlencode(params)
        suffix = f"?{query}" if query else ""
        request = urllib.request.Request(  # noqa: S310 - fixed API-Football host.
            f"{self.base_url}/{path}{suffix}",
            headers={"x-apisports-key": api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                raw = response.read()
                return response.status, _sanitize_headers(response.headers), _decode_payload(raw)
        except urllib.error.HTTPError as exc:
            return exc.code, _sanitize_headers(exc.headers), _decode_payload(exc.read())

    def _cache_path(self, endpoint: str, params: dict[str, str]) -> Path:
        key = json.dumps(
            {"endpoint": endpoint, "params": params},
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        return self.persistent_root / "raw" / endpoint / f"{endpoint}_{digest}.json"


def main() -> int:
    args = _parse_args()
    out_dir = args.out_dir or _default_out_dir()
    if not _is_tmp_path(out_dir):
        raise SystemExit("BLOCKER: OUT_DIR_MUST_BE_UNDER_TMP")
    persistent_root = args.persistent_root
    ledger = LocalLedger()
    client = LedgeredApiFootballClient(
        persistent_root=persistent_root,
        ledger=ledger,
        daily_hard_cap=args.daily_hard_cap,
        reserve_quota=args.reserve_quota,
        request_interval_seconds=args.request_interval_seconds,
    )
    provider_phases = {"phase0", "collect", "audit", "all"}
    if args.phase in provider_phases and not args.approved_provider_calls:
        raise SystemExit("NEED_USER_APPROVAL: PROVIDER_CALLS")
    if args.phase in provider_phases:
        _provider_key()
    payload: dict[str, Any]
    try:
        if args.phase == "phase0":
            payload = run_phase0(client)
        elif args.phase == "collect":
            payload = run_collect(client)
        elif args.phase == "audit":
            payload = run_audit_inventory(client)
        elif args.phase == "model":
            payload = run_model_recheck(persistent_root)
        elif args.phase == "all":
            payload = run_all(client, persistent_root)
        elif args.phase == "summary":
            payload = summarize_existing(persistent_root)
        else:
            raise SystemExit(f"UNKNOWN_PHASE:{args.phase}")
    finally:
        ledger_path = out_dir / "provider_ledger.json"
        ledger.write(ledger_path)
    payload = {
        **payload,
        "source": SOURCE,
        "out_dir": out_dir.as_posix(),
        "persistent_root": persistent_root.as_posix(),
        "ledger_path": ledger_path.as_posix(),
        "actual_provider_calls_this_run": ledger.actual_calls,
        "daily_hard_cap": args.daily_hard_cap,
        "reserve_quota": args.reserve_quota,
        "stopped_reason": client.stopped_reason,
        "safety": _safety(),
    }
    payload["report_sha256"] = report_sha256(payload)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    payload["summary_path"] = summary_path.as_posix()
    if args.json_output:
        print(json.dumps(_sanitized_output(payload), ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(_sanitized_output(payload), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def run_phase0(client: LedgeredApiFootballClient) -> dict[str, Any]:
    status = client.request("status", phase="phase0", refresh=True)
    league = client.request(
        "leagues",
        {"id": IN_SEASON_LEAGUE_IDS["brasileirao_serie_a"], "season": CURRENT_SEASON},
        phase="phase0",
        competition_id="brasileirao_serie_a",
        refresh=True,
    )
    fixtures = client.request(
        "fixtures",
        {"league": IN_SEASON_LEAGUE_IDS["brasileirao_serie_a"], "season": CURRENT_SEASON},
        phase="phase0",
        competition_id="brasileirao_serie_a",
        refresh=True,
    )
    status_text = json.dumps(status.payload, ensure_ascii=False).lower()
    pro_detected = "pro" in status_text
    daily_limit = _max_int(status.payload)
    fixtures_ok = fixtures.error is None and fixtures.response_count > 0
    errors = {
        "status": _errors(status.payload),
        "leagues": _errors(league.payload),
        "fixtures": _errors(fixtures.payload),
    }
    return {
        "status": "PASS" if fixtures_ok and not any(errors.values()) else "BLOCKED",
        "phase": "phase0",
        "pro_detected": pro_detected,
        "daily_limit_or_largest_status_number": daily_limit,
        "status_response_count": status.response_count,
        "league_probe_response_count": league.response_count,
        "fixture_probe_response_count": fixtures.response_count,
        "errors": errors,
        "greenlight_for_bulk_collection": fixtures_ok and not any(errors.values()),
        "provider_calls": 3,
    }


def run_collect(client: LedgeredApiFootballClient) -> dict[str, Any]:
    registry = CompetitionRegistry().entries()
    per_league: dict[str, Any] = {}
    for competition_id in IN_SEASON_NATIONAL_LEAGUES:
        entry = registry[competition_id]
        league_id = IN_SEASON_LEAGUE_IDS.get(competition_id) or entry.provider_mapping.get(
            "api_football_league_id",
            "",
        )
        per_league[competition_id] = _collect_league(client, competition_id, league_id)
        if client.stopped_reason:
            break
    return {
        "status": "STOPPED" if client.stopped_reason else "COMPLETED",
        "phase": "collect",
        "in_scope_leagues": list(IN_SEASON_NATIONAL_LEAGUES),
        "per_league": per_league,
        "coverage": _coverage_summary(client.persistent_root),
    }


def _collect_league(
    client: LedgeredApiFootballClient,
    competition_id: str,
    league_id: str,
) -> dict[str, Any]:
    seasons: dict[str, Any] = {}
    for season in COLLECT_SEASONS:
        league_call = client.request(
            "leagues",
            {"id": league_id, "season": season},
            phase="collect",
            competition_id=competition_id,
        )
        fixtures_call = client.request(
            "fixtures",
            {"league": league_id, "season": season},
            phase="collect",
            competition_id=competition_id,
        )
        fixtures = _response_list(fixtures_call.payload)
        finished = [row for row in fixtures if _fixture_status(row) in FINISHED_STATUSES]
        future = [row for row in fixtures if _fixture_status(row) not in FINISHED_STATUSES]
        stats_calls = _collect_fixture_endpoint(
            client,
            "statistics",
            competition_id=competition_id,
            fixture_ids=[_fixture_id(row) for row in finished],
            phase="collect",
        )
        odds_calls = 0
        lineups_calls = 0
        if season == CURRENT_SEASON:
            odds_calls = _collect_fixture_endpoint(
                client,
                "odds",
                competition_id=competition_id,
                fixture_ids=[_fixture_id(row) for row in future],
                phase="collect",
            )
            lineups_calls = _collect_fixture_endpoint(
                client,
                "lineups",
                competition_id=competition_id,
                fixture_ids=[_fixture_id(row) for row in [*finished, *future]],
                phase="collect",
            )
        seasons[season] = {
            "league_response_count": league_call.response_count,
            "fixtures_total": len(fixtures),
            "finished_fixtures": len(finished),
            "future_or_non_finished_fixtures": len(future),
            "statistics_requests_or_cache_hits": stats_calls,
            "odds_requests_or_cache_hits": odds_calls,
            "lineups_requests_or_cache_hits": lineups_calls,
            "stopped_reason": client.stopped_reason,
        }
        if client.stopped_reason:
            break
    return seasons


def _collect_fixture_endpoint(
    client: LedgeredApiFootballClient,
    endpoint: str,
    *,
    competition_id: str,
    fixture_ids: list[str],
    phase: str,
) -> int:
    count = 0
    for fixture_id in fixture_ids:
        if not fixture_id:
            continue
        client.request(
            endpoint,
            {"fixture": fixture_id},
            phase=phase,
            competition_id=competition_id,
        )
        count += 1
        if client.stopped_reason:
            break
    return count


def run_audit_inventory(client: LedgeredApiFootballClient) -> dict[str, Any]:
    registry = CompetitionRegistry().entries()
    results = []
    for competition_id in ALL_WHITELIST_COMPETITIONS:
        entry = registry[competition_id]
        results.append(_audit_competition(client, entry))
        if client.stopped_reason:
            break
    return {
        "status": "STOPPED" if client.stopped_reason else "COMPLETED",
        "phase": "audit",
        "competition_count": len(ALL_WHITELIST_COMPETITIONS),
        "results": results,
        "can_enter_staging_candidates": [
            item["competition_id"]
            for item in results
            if item["provider_mapping"] == "PASS"
            and item["fixtures"] == "PASS"
            and item["odds"] == "PASS"
            and item["bookmaker_depth"] == "PASS"
        ],
        "enabled_true": False,
    }


def _audit_competition(
    client: LedgeredApiFootballClient,
    entry: CompetitionRegistryEntry,
) -> dict[str, Any]:
    league_id = entry.provider_mapping.get("api_football_league_id", "")
    season = entry.provider_mapping.get("api_football_season") or CURRENT_SEASON
    league = client.request(
        "leagues",
        {"id": league_id, "season": season},
        phase="audit",
        competition_id=entry.competition_id,
    )
    fixtures = client.request(
        "fixtures",
        {"league": league_id, "season": season},
        phase="audit",
        competition_id=entry.competition_id,
    )
    fixture_rows = _response_list(fixtures.payload)
    fixture_id = _select_odds_probe_fixture_id(fixture_rows)
    odds_status = "FAIL"
    bookmaker_depth_status = "FAIL"
    bookmaker_evidence: dict[str, Any] = bookmaker_observed_evidence([])
    if fixture_id:
        odds = client.request(
            "odds",
            {"fixture": fixture_id},
            phase="audit",
            competition_id=entry.competition_id,
        )
        odds_rows = _response_list(odds.payload)
        odds_status = "PASS" if odds_rows else "FAIL"
        bookmaker_evidence = bookmaker_observed_evidence(odds_rows)
        bookmaker_depth_status = "PASS" if _has_bookmaker_depth(bookmaker_evidence) else "FAIL"
    observed_id = _observed_league_id(league.payload)
    return {
        "competition_id": entry.competition_id,
        "league_id": league_id,
        "season": season,
        "provider_mapping": "PASS" if observed_id == str(league_id) else "FAIL",
        "fixtures": "PASS" if fixture_rows else "FAIL",
        "odds": odds_status,
        "bookmaker_depth": bookmaker_depth_status,
        "fixture_response_count": len(fixture_rows),
        "odds_fixture_id": fixture_id or None,
        "bookmaker_evidence": bookmaker_evidence,
        "can_enable": False,
    }


def run_model_recheck(persistent_root: Path) -> dict[str, Any]:
    raw_root = persistent_root / "raw"
    raw_dirs = (
        raw_root,
        raw_root / "fixtures",
        raw_root / "statistics",
        raw_root / "odds",
        raw_root / "lineups",
    )
    reports = {}
    for season in HISTORICAL_SEASONS:
        reports[season] = build_free_tier_2024_backtest_report(
            raw_dirs=raw_dirs,
            season=season,
            competitions=IN_SEASON_NATIONAL_LEAGUES,
            true_xg_source="api_football_statistics",
        )
    return {
        "status": "COMPLETED",
        "phase": "model",
        "reports": {
            season: {
                "covered_competitions": report["scope"]["covered_competitions"],
                "missing_competitions": report["scope"]["missing_competitions"],
                "overall": report["overall"],
                "calibration_status": report["calibration_status"],
            }
            for season, report in reports.items()
        },
        "provider_calls": 0,
    }


def run_all(client: LedgeredApiFootballClient, persistent_root: Path) -> dict[str, Any]:
    phase0 = run_phase0(client)
    if not phase0["greenlight_for_bulk_collection"]:
        return {"status": "BLOCKED", "phase0": phase0}
    collect = run_collect(client)
    audit = run_audit_inventory(client) if not client.stopped_reason else {"status": "SKIPPED"}
    model = run_model_recheck(persistent_root)
    return {
        "status": "STOPPED" if client.stopped_reason else "COMPLETED",
        "phase0": phase0,
        "collect": collect,
        "audit": audit,
        "model": model,
    }


def summarize_existing(persistent_root: Path) -> dict[str, Any]:
    return {
        "status": "SUMMARY",
        "coverage": _coverage_summary(persistent_root),
        "provider_calls": 0,
    }


def _coverage_summary(persistent_root: Path) -> dict[str, Any]:
    root = persistent_root / "raw"
    endpoints = {}
    for endpoint in sorted(ALLOWED_ENDPOINTS):
        endpoint_dir = root / endpoint
        endpoints[endpoint] = len(list(endpoint_dir.glob("*.json"))) if endpoint_dir.exists() else 0
    return endpoints


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run W2 Pro day-1 data sprint safely.")
    parser.add_argument(
        "--phase",
        choices=("phase0", "collect", "audit", "model", "all", "summary"),
        required=True,
    )
    parser.add_argument(
        "--approved-provider-calls",
        action="store_true",
        default=False,
        help="Required live-provider gate; Pro sprint equivalent of --live.",
    )
    parser.add_argument("--daily-hard-cap", type=int, default=7000)
    parser.add_argument("--reserve-quota", type=int, default=500)
    parser.add_argument("--request-interval-seconds", type=float, default=0.15)
    parser.add_argument(
        "--persistent-root",
        type=Path,
        default=ROOT / "runtime" / "w2_pro_day1_provider_data",
    )
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args()


def _default_out_dir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path(f"/tmp/w2_pro_day1_sprint_{stamp}")  # noqa: S108 - user-required temp reports.


def _provider_key() -> str:
    value = os.environ.get("W2_API_FOOTBALL_API_KEY")
    if value is None:
        raise RuntimeError("PROVIDER_KEY_MISSING")
    normalized = value.strip().replace("\r", "").replace("\n", "")
    if normalized.startswith(("W2_API_FOOTBALL_API_KEY=", "API_FOOTBALL=")):
        raise RuntimeError("PROVIDER_KEY_INVALID:LOOKS_LIKE_ASSIGNMENT")
    if normalized.startswith(("x-apisports-key:", "X-APISPORTS-KEY:")):
        raise RuntimeError("PROVIDER_KEY_INVALID:LOOKS_LIKE_HEADER")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized):
        raise RuntimeError("PROVIDER_KEY_INVALID:CONTROL_CHARACTER")
    try:
        normalized.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise RuntimeError("PROVIDER_KEY_INVALID:NOT_HTTP_HEADER_SAFE_ENCODING") from exc
    if not normalized:
        raise RuntimeError("PROVIDER_KEY_MISSING")
    return normalized


def _sanitize_headers(headers: Any) -> dict[str, str]:
    blocked = {"authorization", "x-apisports-key", "x-rapidapi-key", "set-cookie", "cookie"}
    return {
        str(key): str(value)
        for key, value in dict(headers).items()
        if str(key).lower() not in blocked
    }


def _decode_payload(raw: bytes) -> dict[str, Any]:
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    if not isinstance(payload, dict):
        raise RuntimeError("PROVIDER_RESPONSE_SCHEMA_UNSAFE")
    return payload


def _provider_error(payload: dict[str, Any]) -> str | None:
    errors = payload.get("errors")
    if not errors:
        return None
    if isinstance(errors, dict):
        keys = {str(key).lower() for key in errors}
        if "requests" in keys:
            return "DAILY_QUOTA_EXHAUSTED"
        if "ratelimit" in keys:
            return "QUOTA_WARNING"
        if "plan" in keys:
            return "PLAN_DOES_NOT_COVER_ENDPOINT_OR_SEASON"
        return "PROVIDER_PAYLOAD_ERROR"
    return "PROVIDER_PAYLOAD_ERROR"


def _stop_reason(call: ProviderCall, *, reserve_quota: int) -> str | None:
    if call.status_code == 429:
        return "PROVIDER_HTTP_429"
    if call.status_code >= 400:
        return f"PROVIDER_HTTP_{call.status_code}"
    if call.error in {"DAILY_QUOTA_EXHAUSTED", "QUOTA_WARNING"}:
        return call.error
    if call.quota_remaining is not None and call.quota_remaining <= reserve_quota:
        return "PROVIDER_RESERVE_REACHED"
    return None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _payload(wrapper: dict[str, Any]) -> dict[str, Any]:
    payload = wrapper.get("payload")
    return payload if isinstance(payload, dict) else wrapper


def _response_count(payload: dict[str, Any]) -> int:
    response = payload.get("response")
    if isinstance(response, list):
        return len(response)
    if isinstance(response, dict):
        return 1
    return 0


def _response_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response")
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if isinstance(response, dict):
        return [response]
    return []


def _errors(payload: dict[str, Any]) -> dict[str, Any]:
    errors = payload.get("errors")
    return errors if isinstance(errors, dict) else {}


def _fixture_status(row: dict[str, Any]) -> str:
    fixture = row.get("fixture") if isinstance(row, dict) else {}
    status = fixture.get("status") if isinstance(fixture, dict) else {}
    return str(status.get("short") or "").upper() if isinstance(status, dict) else ""


def _fixture_id(row: dict[str, Any]) -> str:
    fixture = row.get("fixture") if isinstance(row, dict) else {}
    if isinstance(fixture, dict):
        return str(fixture.get("id") or "")
    return str(row.get("fixture_id") or row.get("id") or "")


def _select_odds_probe_fixture_id(rows: list[dict[str, Any]]) -> str:
    now = datetime.now(UTC)
    window_end = now + timedelta(days=ODDS_PROBE_WINDOW_DAYS)
    dated: list[tuple[datetime, str]] = []
    for row in rows:
        fixture_id = _fixture_id(row)
        kickoff_at = _fixture_kickoff_at(row)
        if fixture_id and kickoff_at:
            dated.append((kickoff_at, fixture_id))
    window_candidates = [
        (kickoff_at, fixture_id)
        for kickoff_at, fixture_id in dated
        if now <= kickoff_at <= window_end
    ]
    if window_candidates:
        return min(window_candidates, key=lambda item: item[0])[1]
    future_candidates = [
        (kickoff_at, fixture_id)
        for kickoff_at, fixture_id in dated
        if kickoff_at >= now
    ]
    if future_candidates:
        return min(future_candidates, key=lambda item: item[0])[1]
    return next((_fixture_id(row) for row in rows if _fixture_id(row)), "")


def _fixture_kickoff_at(row: dict[str, Any]) -> datetime | None:
    fixture = row.get("fixture") if isinstance(row, dict) else {}
    value = ""
    if isinstance(fixture, dict):
        value = str(fixture.get("date") or fixture.get("kickoff_utc") or "")
    if not value:
        value = str(row.get("date") or row.get("kickoff_utc") or "")
    if not value:
        return None
    return _parse_time(value)


def _observed_league_id(payload: dict[str, Any]) -> str:
    rows = _response_list(payload)
    if not rows:
        return ""
    league = rows[0].get("league") if isinstance(rows[0], dict) else {}
    return str(league.get("id") or rows[0].get("id") or "") if isinstance(league, dict) else ""


def _has_bookmaker_depth(evidence: dict[str, Any]) -> bool:
    return (
        int(evidence.get("observed_bookmaker_count") or 0) >= 3
        and bool(evidence.get("observed_has_ah"))
        and bool(evidence.get("observed_has_ou"))
        and bool(evidence.get("observed_has_line"))
    )


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _max_int(value: Any) -> int | None:
    found: list[int] = []

    def walk(item: Any) -> None:
        parsed = _int(item)
        if parsed is not None:
            found.append(parsed)
        if isinstance(item, dict):
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return max(found) if found else None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_tmp_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(Path("/tmp").resolve())  # noqa: S108 - blocks non-temp reports.
    except ValueError:
        return False
    return True


def _safety() -> dict[str, Any]:
    return {
        "db_reads": 0,
        "db_writes": 0,
        "enabled_true": False,
        "staging_deploy": False,
        "production_deploy": False,
        "scheduler_restart": False,
        "checkpoint_write": False,
        "lock_capture_write": False,
        "settlement_write": False,
        "canonical_season_changed": False,
    }


def _sanitized_output(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
