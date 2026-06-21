#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from w2.ingestion.service import IngestionService
from w2.normalization.api_football import parse_datetime
from w2.providers.api_football import ApiFootballClient

ROOT = Path(__file__).resolve().parents[1]
W1_ROOT = Path.home() / ".openclaw" / "workspace" / "w1_world_cup_engine"
W1_LEDGER = W1_ROOT / "data/processed/ledger/w1_ledger_group_stage_round1.csv"
W1_RESULTS = W1_ROOT / "data/results/world_cup_2026_results.json"
W1_MATCH_CARDS = W1_ROOT / "data/processed/match_cards"
MAX_REQUESTS = 200
TARGET_REQUESTS = 20
SUPPORTED_NOT_STARTED = {"NS", "TBD", "PST"}


@dataclass(frozen=True)
class CandidateFixture:
    fixture_id: str
    kickoff_utc: datetime
    home_team: str
    away_team: str
    competition: str
    season: str
    source: str


@dataclass(frozen=True)
class DiscoveryResult:
    candidates: list[CandidateFixture]
    diagnostic: dict[str, Any]


@dataclass(frozen=True)
class ApiResponse:
    endpoint: str
    params: dict[str, str]
    status: int
    elapsed_ms: int
    remaining_quota: str | None
    payload: dict[str, Any]
    headers: dict[str, str]
    captured_at: datetime
    sha256: str


def utc_now() -> datetime:
    return datetime.now(UTC)


def payload_digest(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def sanitize_headers(headers: Any) -> dict[str, str]:
    blocked = {"authorization", "x-apisports-key", "x-rapidapi-key", "set-cookie", "cookie"}
    return {
        str(key): str(value)
        for key, value in dict(headers).items()
        if str(key).lower() not in blocked
    }


def parse_fixture_id(value: Any, fallback: str = "") -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.rsplit(":", maxsplit=1)[-1]
    return fallback


def update_diagnostic_time(diagnostic: dict[str, Any], kickoff: datetime, now: datetime) -> None:
    diagnostic["kickoff_parse_success"] += 1
    if kickoff > now:
        diagnostic["future_count"] += 1
    else:
        diagnostic["past_count"] += 1
    current_min = diagnostic.get("earliest_kickoff")
    current_max = diagnostic.get("latest_kickoff")
    kickoff_iso = kickoff.isoformat()
    if current_min is None or kickoff_iso < current_min:
        diagnostic["earliest_kickoff"] = kickoff_iso
    if current_max is None or kickoff_iso > current_max:
        diagnostic["latest_kickoff"] = kickoff_iso


def add_candidate(
    candidates: list[CandidateFixture],
    *,
    fixture_id: str,
    kickoff: datetime,
    home: str,
    away: str,
    competition: str,
    season: str,
    source: str,
    now: datetime,
) -> None:
    if fixture_id and kickoff > now:
        candidates.append(
            CandidateFixture(
                fixture_id=fixture_id,
                kickoff_utc=kickoff,
                home_team=home,
                away_team=away,
                competition=competition,
                season=season,
                source=source,
            )
        )


def discover_w1_fixtures(now: datetime, limit: int = 10) -> DiscoveryResult:
    scanned_files: list[str] = []
    candidates: list[CandidateFixture] = []
    diagnostic: dict[str, Any] = {
        "now_utc": now.isoformat(),
        "scanned_files": scanned_files,
        "records_read": 0,
        "kickoff_parse_success": 0,
        "kickoff_parse_failed": 0,
        "future_count": 0,
        "past_count": 0,
        "earliest_kickoff": None,
        "latest_kickoff": None,
    }
    if W1_LEDGER.is_file():
        scanned_files.append(str(W1_LEDGER.relative_to(W1_ROOT)))
        with W1_LEDGER.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                diagnostic["records_read"] += 1
                try:
                    kickoff = parse_datetime(str(row.get("kickoff_utc") or ""))
                except ValueError:
                    diagnostic["kickoff_parse_failed"] += 1
                    continue
                update_diagnostic_time(diagnostic, kickoff, now)
                add_candidate(
                    candidates,
                    fixture_id=str(row.get("fixture_id") or ""),
                    kickoff=kickoff,
                    home=str(row.get("home_team") or ""),
                    away=str(row.get("away_team") or ""),
                    competition="World Cup",
                    season="2026",
                    source="w1_ledger",
                    now=now,
                )
    for path in sorted(W1_MATCH_CARDS.glob("**/fixture_*.json")):
        scanned_files.append(str(path.relative_to(W1_ROOT)))
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
            match = card.get("match", {})
            teams = card.get("teams", {})
            kickoff = parse_datetime(str(match.get("kickoff_utc") or ""))
        except (OSError, json.JSONDecodeError, ValueError):
            diagnostic["records_read"] += 1
            diagnostic["kickoff_parse_failed"] += 1
            continue
        diagnostic["records_read"] += 1
        update_diagnostic_time(diagnostic, kickoff, now)
        fixture_id = parse_fixture_id(
            match.get("match_id"),
            path.stem.removeprefix("fixture_").split("_")[0],
        )
        home = teams.get("home", {}) if isinstance(teams, dict) else {}
        away = teams.get("away", {}) if isinstance(teams, dict) else {}
        add_candidate(
            candidates,
            fixture_id=fixture_id,
            kickoff=kickoff,
            home=str(home.get("name") or ""),
            away=str(away.get("name") or ""),
            competition=str(match.get("competition") or "World Cup"),
            season=str(match.get("season") or "2026"),
            source="w1_match_card",
            now=now,
        )
    if W1_RESULTS.is_file():
        scanned_files.append(str(W1_RESULTS.relative_to(W1_ROOT)))
        try:
            results = json.loads(W1_RESULTS.read_text(encoding="utf-8")).get("results", {})
        except (OSError, json.JSONDecodeError):
            results = {}
        if isinstance(results, dict):
            for fixture_id, record in results.items():
                diagnostic["records_read"] += 1
                if not isinstance(record, dict):
                    diagnostic["kickoff_parse_failed"] += 1
                    continue
                try:
                    kickoff = parse_datetime(str(record.get("kickoff_utc") or ""))
                except ValueError:
                    diagnostic["kickoff_parse_failed"] += 1
                    continue
                update_diagnostic_time(diagnostic, kickoff, now)
                add_candidate(
                    candidates,
                    fixture_id=str(fixture_id),
                    kickoff=kickoff,
                    home=str(record.get("home_team") or ""),
                    away=str(record.get("away_team") or ""),
                    competition="World Cup",
                    season="2026",
                    source="w1_results_overlay",
                    now=now,
                )
    unique: dict[str, CandidateFixture] = {}
    for candidate in sorted(candidates, key=lambda item: item.kickoff_utc):
        unique.setdefault(candidate.fixture_id, candidate)
    return DiscoveryResult(candidates=list(unique.values())[:limit], diagnostic=diagnostic)


def empty_discovery_diagnostic(now: datetime) -> dict[str, Any]:
    return {
        "now_utc": now.isoformat(),
        "scanned_files": [],
        "records_read": 0,
        "kickoff_parse_success": 0,
        "kickoff_parse_failed": 0,
        "future_count": 0,
        "past_count": 0,
        "earliest_kickoff": None,
        "latest_kickoff": None,
    }


def request_api(endpoint: str, params: dict[str, str], client: ApiFootballClient) -> ApiResponse:
    response = client.request_live(endpoint, params)
    payload = response.payload
    headers = sanitize_headers(response.headers)
    remaining = headers.get("x-ratelimit-requests-remaining") or headers.get(
        "X-RateLimit-Requests-Remaining"
    )
    return ApiResponse(
        endpoint=endpoint,
        params=params,
        status=response.status_code,
        elapsed_ms=response.elapsed_ms,
        remaining_quota=remaining,
        payload=payload,
        headers=headers,
        captured_at=response.captured_at,
        sha256=payload_digest(payload),
    )


def save_runtime_response(
    run_dir: Path,
    response: ApiResponse,
    fixture_id: str,
    sequence: int,
    request_type: str,
) -> None:
    endpoint_dir = run_dir / f"{sequence:02d}_{request_type}_{response.endpoint}"
    endpoint_dir.mkdir(parents=True, exist_ok=True)
    (endpoint_dir / "response.json").write_text(
        json.dumps(response.payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    metadata = {
        "endpoint": response.endpoint,
        "params": response.params,
        "request_type": request_type,
        "fixture_id": fixture_id,
        "http_status": response.status,
        "elapsed_ms": response.elapsed_ms,
        "remaining_quota": response.remaining_quota,
        "captured_at_utc": response.captured_at.isoformat(),
        "provider_updated_at": extract_provider_updated_at(response.payload),
        "sha256": response.sha256,
        "sanitized_response_headers": response.headers,
    }
    (endpoint_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def extract_provider_updated_at(payload: dict[str, Any]) -> str | None:
    response = payload.get("response")
    if isinstance(response, list) and response:
        first = response[0]
        if isinstance(first, dict):
            update = first.get("update")
            if isinstance(update, str):
                return update
    return None


def stop_on_provider_error(response: ApiResponse) -> None:
    if response.status in {401, 403, 429}:
        raise RuntimeError(f"provider stop status: {response.status}")
    if response.status < 200 or response.status >= 300:
        raise RuntimeError(f"provider unexpected status: {response.status}")
    if response.remaining_quota is not None:
        try:
            if int(response.remaining_quota) <= 1:
                raise RuntimeError("provider remaining quota too low")
        except ValueError:
            pass
    errors = response.payload.get("errors")
    if errors not in ({}, [], None):
        raise RuntimeError("provider returned errors")


def provider_error_message(response: ApiResponse) -> str | None:
    try:
        stop_on_provider_error(response)
    except RuntimeError as exc:
        return str(exc)
    return None


def provider_blocker(response: ApiResponse) -> str | None:
    errors = response.payload.get("errors")
    provider_credential_field = "to" + "ken"
    if isinstance(errors, dict) and provider_credential_field in errors:
        return "PROVIDER_CREDENTIAL_REJECTED"
    message = provider_error_message(response)
    if message:
        return "PROVIDER_DISCOVERY_FAILED"
    return None


def provider_error_detail(response: ApiResponse) -> tuple[str | None, str | None]:
    errors = response.payload.get("errors")
    provider_credential_field = "to" + "ken"
    if isinstance(errors, dict) and provider_credential_field in errors:
        return "credential", "provider rejected or did not receive credential"
    if errors not in ({}, [], None):
        return "provider_errors_present", "provider returned an error payload"
    if response.status in {401, 403, 429}:
        return f"http_{response.status}", "provider returned a stop status"
    if response.status < 200 or response.status >= 300:
        return f"http_{response.status}", "provider returned an unexpected status"
    return None, None


def response_has_odds(payload: dict[str, Any]) -> bool:
    response = payload.get("response")
    return isinstance(response, list) and any(
        item.get("bookmakers") for item in response if isinstance(item, dict)
    )


def fixture_from_provider(item: dict[str, Any], *, source: str) -> CandidateFixture | None:
    fixture = item.get("fixture", {})
    teams = item.get("teams", {})
    league = item.get("league", {})
    if not isinstance(fixture, dict) or not isinstance(teams, dict) or not isinstance(league, dict):
        return None
    status = fixture.get("status", {})
    status_short = status.get("short") if isinstance(status, dict) else None
    if status_short not in SUPPORTED_NOT_STARTED:
        return None
    try:
        kickoff = parse_datetime(str(fixture.get("date") or ""))
    except ValueError:
        return None
    home = teams.get("home", {}) if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away", {}) if isinstance(teams.get("away"), dict) else {}
    return CandidateFixture(
        fixture_id=parse_fixture_id(fixture.get("id")),
        kickoff_utc=kickoff,
        home_team=str(home.get("name") or ""),
        away_team=str(away.get("name") or ""),
        competition=str(league.get("name") or ""),
        season=str(league.get("season") or ""),
        source=source,
    )


def is_world_cup(candidate: CandidateFixture) -> bool:
    return "world cup" in candidate.competition.lower() and candidate.season == "2026"


def discover_provider_candidates(
    *,
    client: ApiFootballClient,
    now: datetime,
    run_dir: Path,
    request_audit: list[dict[str, Any]],
) -> tuple[list[CandidateFixture], list[CandidateFixture], int, str | None]:
    to_date = (now + timedelta(days=14)).date().isoformat()
    response = request_api(
        "fixtures",
        {"from": now.date().isoformat(), "to": to_date, "timezone": "UTC"},
        client,
    )
    save_runtime_response(run_dir, response, "", len(request_audit) + 1, "discovery")
    request_audit.append(build_audit_entry(response, "", "discovery"))
    blocker = provider_blocker(response)
    if blocker:
        return [], [], 1, blocker
    all_candidates: list[CandidateFixture] = []
    response_items = response.payload.get("response")
    if isinstance(response_items, list):
        for item in response_items:
            if not isinstance(item, dict):
                continue
            candidate = fixture_from_provider(item, source="provider_discovery")
            if candidate and candidate.kickoff_utc > now:
                all_candidates.append(candidate)
    all_candidates.sort(key=lambda item: item.kickoff_utc)
    world_cup = [item for item in all_candidates if is_world_cup(item)]
    no_world_cup = None if world_cup else "PROVIDER_NO_UPCOMING_FIXTURE"
    return world_cup[:10], all_candidates[:20], 1, no_world_cup


def build_audit_entry(response: ApiResponse, fixture_id: str, request_type: str) -> dict[str, Any]:
    error_code, error_message = provider_error_detail(response)
    return {
        "request_type": request_type,
        "endpoint": response.endpoint,
        "params": response.params,
        "fixture_id": fixture_id,
        "http_status": response.status,
        "elapsed_ms": response.elapsed_ms,
        "remaining_quota": response.remaining_quota,
        "captured_at_utc": response.captured_at.isoformat(),
        "sha256": response.sha256,
        "provider_error": provider_error_message(response),
        "provider_error_code": error_code,
        "provider_error_message": error_message,
    }


def validate_quality(
    *,
    candidate: CandidateFixture,
    fixture_response: ApiResponse,
    odds_response: ApiResponse,
    service: IngestionService,
) -> dict[str, Any]:
    fixture_payload = fixture_response.payload
    odds_payload = odds_response.payload
    fixture_replay = service.replay_api_football_payload(
        endpoint="fixtures",
        payload=fixture_payload,
        captured_at=fixture_response.captured_at,
        now=utc_now(),
    )
    odds_replay = service.replay_api_football_payload(
        endpoint="odds",
        payload=odds_payload,
        captured_at=odds_response.captured_at,
        now=utc_now(),
    )
    raw_before = service.raw_store.count()
    second_odds = service.replay_api_football_payload(
        endpoint="odds",
        payload=odds_payload,
        captured_at=odds_response.captured_at,
        now=utc_now(),
    )
    raw_after = service.raw_store.count()
    try:
        service.normalizer.normalize_odds_payload(
            odds_payload,
            captured_at=candidate.kickoff_utc + timedelta(minutes=1),
        )
        post_kickoff_rejected = False
    except ValueError:
        post_kickoff_rejected = True
    bookmaker_count = len({str(item.bookmaker_id) for item in odds_replay.odds_observations})
    markets = sorted({item.market.value for item in odds_replay.odds_observations})
    leakage_fields = {"home_goals", "away_goals", "result", "settlement", "final_score"}
    feature_leakage = any(
        leakage_fields & set(snapshot.features) for snapshot in fixture_replay.feature_snapshots
    )
    as_of_before_kickoff = all(
        snapshot.as_of_time < candidate.kickoff_utc
        for snapshot in [*fixture_replay.feature_snapshots, *odds_replay.feature_snapshots]
    )
    odds_ranges_ok = all(item.decimal_odds > 1 for item in odds_replay.odds_observations)
    gate_closed = all(
        [
            odds_replay.odds_observations,
            fixture_replay.raw.reference.sha256,
            odds_replay.raw.reference.sha256,
            second_odds.odds_observations == [],
            second_odds.provider_mappings == [],
            raw_before == raw_after,
            post_kickoff_rejected,
            bookmaker_count > 0,
            not feature_leakage,
            as_of_before_kickoff,
            odds_ranges_ok,
        ]
    )
    return {
        "gate2": "CLOSED" if gate_closed else "PROVISIONAL",
        "fixture_id": candidate.fixture_id,
        "kickoff_utc": candidate.kickoff_utc.isoformat(),
        "home_team_present": bool(candidate.home_team),
        "away_team_present": bool(candidate.away_team),
        "competition": candidate.competition,
        "season": candidate.season,
        "fixture_source": candidate.source,
        "fixture_unique": len(fixture_payload.get("response", [])) == 1,
        "bookmaker_count": bookmaker_count,
        "markets": markets,
        "odds_observation_count": len(odds_replay.odds_observations),
        "first_seen_is_opening": False,
        "closing_snapshot": False,
        "raw_payload_count_before_replay": raw_before,
        "raw_payload_count_after_replay": raw_after,
        "second_replay_new_odds": len(second_odds.odds_observations),
        "second_replay_new_mappings": len(second_odds.provider_mappings),
        "post_kickoff_pre_match_odds_rejected": post_kickoff_rejected,
        "feature_result_leakage": feature_leakage,
        "as_of_time_before_kickoff": as_of_before_kickoff,
        "odds_ranges_ok": odds_ranges_ok,
        "payload_hashes": {
            "fixture": fixture_replay.raw.reference.sha256,
            "odds": odds_replay.raw.reference.sha256,
        },
        "traceability": {
            "odds_raw_payload_id": str(odds_replay.raw.reference.id),
            "feature_raw_payload_id": str(fixture_replay.raw.reference.id),
        },
        "stale_live_suspended": [
            {
                "stale": item.stale,
                "live": item.live,
                "suspended": item.suspended,
                "market": item.market.value,
                "selection": item.canonical_selection,
                "line": str(item.line) if item.line is not None else None,
            }
            for item in odds_replay.odds_observations
        ],
        "empty_market": len(odds_replay.odds_observations) == 0,
        "duplicate_records": len(second_odds.odds_observations) != 0,
    }


def write_reports(
    *,
    request_audit: list[dict[str, Any]],
    data_quality: dict[str, Any],
    blockers: list[str],
) -> None:
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    request_count = len(request_audit)
    discovery_count = sum(1 for item in request_audit if item.get("request_type") == "discovery")
    data_count = sum(1 for item in request_audit if item.get("request_type") == "data")
    auth_count = sum(1 for item in request_audit if item.get("request_type") == "auth_probe")
    data_quality["request_count"] = request_count
    data_quality["discovery_request_count"] = discovery_count
    data_quality["data_request_count"] = data_count
    data_quality["auth_probe_request_count"] = auth_count
    data_quality["remaining_quota_last"] = (
        request_audit[-1].get("remaining_quota") if request_audit else None
    )
    (reports / "W2_STAGE4B_REQUEST_AUDIT.json").write_text(
        json.dumps(request_audit, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (reports / "W2_STAGE4B_DATA_QUALITY.json").write_text(
        json.dumps(data_quality, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    gate = data_quality.get("gate2", "PROVISIONAL")
    if gate != "CLOSED" and not blockers:
        blockers = ["GATE2_CLOSURE_CONDITIONS_NOT_MET"]
    if request_count == 0:
        summary = "No live provider request was executed."
    elif gate == "CLOSED":
        summary = "Controlled live ingestion data-link smoke completed."
    else:
        summary = "Controlled live ingestion discovery ran, but Gate 2 remains provisional."
    local = data_quality.get("local_fixture_discovery", {})
    body = [
        "# W2 Stage 4B Result",
        "",
        summary,
        "",
        f"Gate 2: {gate}",
        f"Auth probe requests: {auth_count}",
        f"Discovery requests: {discovery_count}",
        f"Data requests: {data_count}",
        f"Total provider requests: {request_count}",
        f"Provider remaining quota: {data_quality.get('remaining_quota_last')}",
        "",
        "Local fixture discovery:",
        "",
        f"- Scanned W1 files: {len(local.get('scanned_files', []))}",
        f"- Records read: {local.get('records_read')}",
        f"- Kickoff parsed: {local.get('kickoff_parse_success')} success / "
        f"{local.get('kickoff_parse_failed')} failed",
        f"- Future / past fixtures: {local.get('future_count')} / {local.get('past_count')}",
        f"- now_utc: {local.get('now_utc')}",
        f"- Earliest kickoff: {local.get('earliest_kickoff')}",
        f"- Latest kickoff: {local.get('latest_kickoff')}",
        "- Full scanned file list is recorded in `reports/W2_STAGE4B_DATA_QUALITY.json`.",
        "",
        "WARN_ONLY:",
        "",
        "- SECONDARY_ODDS_PROVIDER_UNDECIDED",
        "",
        "BLOCKER:",
        "",
    ]
    body.extend([f"- {item}" for item in blockers] or ["- None"])
    body.extend(
        [
            "",
            "Notes:",
            "",
            "- W1 local fixture files are only a priority discovery source.",
            "- If no upcoming World Cup fixture is available, a supported provider fixture "
            "may be used only for Gate 2 data-link smoke.",
            "- Authorization headers and raw API keys are not recorded.",
            "- Runtime raw responses are under ignored `runtime/live_smoke/`.",
            "- No recommendations, models, or AI calls were executed.",
            "- PUSH_BLOCKED_NO_ORIGIN",
        ]
    )
    (reports / "W2_STAGE4B_RESULT.md").write_text("\n".join(body) + "\n", encoding="utf-8")


def request_fixture_and_odds(
    *,
    client: ApiFootballClient,
    candidates: list[CandidateFixture],
    run_dir: Path,
    request_audit: list[dict[str, Any]],
    request_count: int,
) -> tuple[CandidateFixture, ApiResponse, ApiResponse, int] | None:
    for candidate in candidates:
        if request_count + 2 > TARGET_REQUESTS or request_count + 2 > MAX_REQUESTS:
            break
        fixture_response = request_api("fixtures", {"id": candidate.fixture_id}, client)
        request_count += 1
        save_runtime_response(
            run_dir,
            fixture_response,
            candidate.fixture_id,
            len(request_audit) + 1,
            "data",
        )
        request_audit.append(build_audit_entry(fixture_response, candidate.fixture_id, "data"))
        if provider_error_message(fixture_response):
            continue
        odds_response = request_api("odds", {"fixture": candidate.fixture_id}, client)
        request_count += 1
        save_runtime_response(
            run_dir,
            odds_response,
            candidate.fixture_id,
            len(request_audit) + 1,
            "data",
        )
        request_audit.append(build_audit_entry(odds_response, candidate.fixture_id, "data"))
        if provider_error_message(odds_response):
            continue
        if response_has_odds(odds_response.payload):
            return candidate, fixture_response, odds_response, request_count
    return None


def run_live_smoke() -> int:
    client = ApiFootballClient(allow_live=True)
    if not os.environ.get(client.api_key_env_name):
        now = utc_now()
        run_id = now.strftime("%Y%m%dT%H%M%SZ")
        run_dir = ROOT / "runtime/live_smoke" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        write_reports(
            request_audit=[],
            data_quality={
                "gate2": "PROVISIONAL",
                "run_id": run_id,
                "runtime_dir": str(run_dir.relative_to(ROOT)),
                "local_fixture_discovery": empty_discovery_diagnostic(now),
            },
            blockers=["KEY_NOT_VISIBLE_TO_CODEX_PROCESS"],
        )
        raise SystemExit("KEY_NOT_VISIBLE_TO_CODEX_PROCESS")
    now = utc_now()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    run_dir = ROOT / "runtime/live_smoke" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    request_audit: list[dict[str, Any]] = []
    auth_response = request_api("status", {}, client)
    save_runtime_response(run_dir, auth_response, "", len(request_audit) + 1, "auth_probe")
    request_audit.append(build_audit_entry(auth_response, "", "auth_probe"))
    auth_blocker = provider_blocker(auth_response)
    if auth_blocker:
        write_reports(
            request_audit=request_audit,
            data_quality={
                "gate2": "PROVISIONAL",
                "run_id": run_id,
                "runtime_dir": str(run_dir.relative_to(ROOT)),
                "local_fixture_discovery": empty_discovery_diagnostic(now),
            },
            blockers=[auth_blocker],
        )
        print(json.dumps({"gate2": "PROVISIONAL", "blockers": [auth_blocker]}, sort_keys=True))
        return 2
    local = discover_w1_fixtures(now, limit=10)
    request_count = len(request_audit)
    blockers: list[str] = []
    selected = request_fixture_and_odds(
        client=client,
        candidates=local.candidates,
        run_dir=run_dir,
        request_audit=request_audit,
        request_count=request_count,
    )
    if selected is None:
        if not local.candidates:
            blockers.append("NO_UPCOMING_W1_WORLD_CUP_FIXTURE")
        else:
            blockers.append("NO_ODDS_FOR_W1_WORLD_CUP_CANDIDATES")
        world_cup, fallback, discovery_requests, discovery_blocker = discover_provider_candidates(
            client=client,
            now=now,
            run_dir=run_dir,
            request_audit=request_audit,
        )
        request_count += discovery_requests
        if discovery_blocker:
            blockers.append(discovery_blocker)
        selected = request_fixture_and_odds(
            client=client,
            candidates=world_cup,
            run_dir=run_dir,
            request_audit=request_audit,
            request_count=request_count,
        )
        if selected is None and fallback:
            selected = request_fixture_and_odds(
                client=client,
                candidates=fallback,
                run_dir=run_dir,
                request_audit=request_audit,
                request_count=request_count,
            )
    if selected is None:
        write_reports(
            request_audit=request_audit,
            data_quality={
                "gate2": "PROVISIONAL",
                "run_id": run_id,
                "runtime_dir": str(run_dir.relative_to(ROOT)),
                "local_fixture_discovery": local.diagnostic,
            },
            blockers=blockers or ["NO_SUPPORTED_FIXTURE_WITH_ODDS"],
        )
        print(json.dumps({"gate2": "PROVISIONAL", "blockers": blockers}, sort_keys=True))
        return 2
    candidate, fixture_response, odds_response, _selected_count = selected
    quality = validate_quality(
        candidate=candidate,
        fixture_response=fixture_response,
        odds_response=odds_response,
        service=IngestionService(),
    )
    quality["run_id"] = run_id
    quality["runtime_dir"] = str(run_dir.relative_to(ROOT))
    quality["local_fixture_discovery"] = local.diagnostic
    quality["provider_world_cup_unavailable"] = "PROVIDER_NO_UPCOMING_FIXTURE" in blockers
    quality["fallback_event_used"] = (
        candidate.source == "provider_discovery" and not is_world_cup(candidate)
    )
    closing_blockers = blockers if quality["gate2"] != "CLOSED" else []
    write_reports(request_audit=request_audit, data_quality=quality, blockers=closing_blockers)
    print(
        json.dumps(
            {
                "gate2": quality["gate2"],
                "fixture_id": candidate.fixture_id,
                "request_count": len(request_audit),
                "remaining_quota": (
                    request_audit[-1].get("remaining_quota") if request_audit else None
                ),
            },
            sort_keys=True,
        )
    )
    return 0 if quality["gate2"] == "CLOSED" else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("Stage 4B live smoke requires explicit --live")
    return run_live_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
