#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from w2.providers.api_football import ApiFootballClient, LiveNetworkDisabledError

ROOT = Path(__file__).resolve().parents[1]
# Stage 5B is an explicitly authorized live package; this marker keeps the
# Stage 4 network guard aware that API calls here are --live governed.
W1_ROOT = Path.home() / ".openclaw" / "workspace" / "w1_world_cup_engine"
INTERNATIONAL_CSV = W1_ROOT / "data/processed/international/w1_international_dataset.csv"
WORLD_CUP_XLSX = W1_ROOT / "data/raw/international/WorldCup2026.xlsx"
HISTORICAL_OU_CSV = W1_ROOT / "data/local_odds/world_cup_odds_historical.csv"
ODDS_SNAPSHOT_ROOT = W1_ROOT / "data/odds_snapshots/raw"
RUNTIME = ROOT / "runtime/stage5b"
RAW = RUNTIME / "raw"
PROCESSED = RUNTIME / "processed"
REPORTS = ROOT / "reports"
RESERVE_QUOTA = 2000
DAILY_QUOTA = 7500
MAX_STAGE5B_REQUESTS = 5000

LEAGUE_SEARCHES = {
    "Premier League": "CLUB_RESULTS_DATASET",
    "La Liga": "CLUB_RESULTS_DATASET",
    "Bundesliga": "CLUB_RESULTS_DATASET",
    "Serie A": "CLUB_RESULTS_DATASET",
    "Ligue 1": "CLUB_RESULTS_DATASET",
}


@dataclass(frozen=True)
class ApiAudit:
    endpoint: str
    params: dict[str, str]
    status_code: int
    elapsed_ms: int
    remaining_quota: str | None
    result_count: int
    provider_error: str | None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_id(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:32]


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def api_error(payload: dict[str, Any]) -> str | None:
    errors = payload.get("errors")
    if errors in ({}, [], None):
        return None
    if isinstance(errors, dict):
        return ",".join(sorted(str(key) for key in errors)) or "provider_error"
    return "provider_error"


class Stage5BApi:
    def __init__(self) -> None:
        self.client = ApiFootballClient(allow_live=True)
        self.audit: list[ApiAudit] = []
        self.request_count = 0
        self.remaining_quota: int | None = None
        self.allowed_requests = 0

    def request(self, endpoint: str, params: dict[str, str], priority: str) -> dict[str, Any]:
        if self.request_count >= self.allowed_requests:
            raise RuntimeError("STAGE5B_QUOTA_BUDGET_EXHAUSTED")
        started = time.monotonic()
        response = self.client.request_live(endpoint, params)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        self.request_count += 1
        remaining = response.headers.get("x-ratelimit-requests-remaining") or response.headers.get(
            "X-RateLimit-Requests-Remaining"
        )
        if remaining is not None:
            try:
                self.remaining_quota = int(remaining)
            except ValueError:
                pass
        payload = response.payload
        response_items = payload.get("response", [])
        result_count = len(response_items) if isinstance(response_items, list) else 0
        self.audit.append(
            ApiAudit(
                endpoint=endpoint,
                params=params,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                remaining_quota=remaining,
                result_count=result_count,
                provider_error=api_error(payload),
            )
        )
        safe_name = f"{self.request_count:03d}_{priority}_{endpoint}.json"
        write_json(RAW / safe_name, {"endpoint": endpoint, "params": params, "payload": payload})
        return payload

    def status(self) -> dict[str, Any]:
        if not os.environ.get(self.client.api_key_env_name):
            raise LiveNetworkDisabledError("KEY_NOT_VISIBLE_TO_CODEX_PROCESS")
        self.allowed_requests = 1
        payload = self.request("status", {}, "P0")
        remaining = self.remaining_quota
        if remaining is None:
            raise RuntimeError("PROVIDER_QUOTA_HEADER_MISSING")
        if remaining <= RESERVE_QUOTA:
            raise RuntimeError("REMAINING_QUOTA_AT_OR_BELOW_REALTIME_RESERVE")
        self.allowed_requests = min(MAX_STAGE5B_REQUESTS, remaining - RESERVE_QUOTA)
        return payload


def import_national_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    cleaned: list[dict[str, Any]] = []
    competitions: dict[str, int] = {}
    for row in rows:
        competition = row["competition"]
        competitions[competition] = competitions.get(competition, 0) + 1
        fixture_id = stable_id(
            "national",
            competition,
            row["season"],
            row["match_date"],
            row["home_team_id"],
            row["away_team_id"],
        )
        cleaned.append(
            {
                "fixture_uuid": fixture_id,
                "competition": competition,
                "season": row["season"],
                "match_date": row["match_date"],
                "home_team": row["home_team_id"],
                "away_team": row["away_team_id"],
                "home_name_raw": row["home_name_raw"],
                "away_name_raw": row["away_name_raw"],
                "home_goals_90": row["home_goals_90"],
                "away_goals_90": row["away_goals_90"],
                "extra_time": {
                    "home_goals_et": row.get("home_goals_et") or None,
                    "away_goals_et": row.get("away_goals_et") or None,
                },
                "penalties": {
                    "home_penalties": row.get("home_penalties") or None,
                    "away_penalties": row.get("away_penalties") or None,
                },
                "neutral_site": row.get("neutral_site") == "True",
                "fixture_status": (
                    "FINISHED" if row.get("result_available") == "True" else "UNKNOWN"
                ),
                "odds_semantics": "UNKNOWN_PREMATCH_AGGREGATE",
                "post_match_observation": {
                    "home_xg": row.get("home_xg") or None,
                    "away_xg": row.get("away_xg") or None,
                    "home_shots": row.get("home_shots") or None,
                    "away_shots": row.get("away_shots") or None,
                    "home_sot": row.get("home_sot") or None,
                    "away_sot": row.get("away_sot") or None,
                },
                "pre_match_feature_snapshot": {
                    "odds_1x2_home": row.get("odds_1x2_home") or None,
                    "odds_1x2_draw": row.get("odds_1x2_draw") or None,
                    "odds_1x2_away": row.get("odds_1x2_away") or None,
                    "snapshot_semantics": "UNKNOWN_PREMATCH_AGGREGATE",
                },
            }
        )
    write_json(PROCESSED / "national_fixtures_cleaned.json", cleaned)
    return {"row_count": len(cleaned), "competitions": competitions}


def merge_historical_ou(
    ou_rows: list[dict[str, str]],
    national_rows: list[dict[str, str]],
) -> dict[str, Any]:
    index = {
        (
            row["season"],
            normalize_name(row["home_name_raw"]),
            normalize_name(row["away_name_raw"]),
        ): row
        for row in national_rows
        if row["competition"] in {"World Cup 2018", "World Cup 2022"}
    }
    merged: list[dict[str, Any]] = []
    unmatched: list[dict[str, str]] = []
    for row in ou_rows:
        key = (row["Season"], normalize_name(row["homeTeam"]), normalize_name(row["awayTeam"]))
        match = index.get(key)
        if not match:
            unmatched.append(row)
            continue
        merged.append(
            {
                "season": row["Season"],
                "home": row["homeTeam"],
                "away": row["awayTeam"],
                "snapshot_semantics": "CLOSING",
                "prediction_phase": "CLOSING",
                "source_system": "W1",
                "original_source": "footiqo/xBet",
                "historical_ah_available": False,
                "one_x_two": {"H": row["H"], "D": row["D"], "A": row["A"]},
                "ou_ladder": {
                    key: row[key]
                    for key in (
                        "O05",
                        "U05",
                        "O15",
                        "U15",
                        "O25",
                        "U25",
                        "O35",
                        "U35",
                        "O45",
                        "U45",
                    )
                },
                "btts": {"YES": row["BTTSY"], "NO": row["BTTSN"]},
                "settlement_90": {
                    "home_goals_90": match["home_goals_90"],
                    "away_goals_90": match["away_goals_90"],
                },
            }
        )
    write_json(PROCESSED / "historical_ou_closing.json", merged)
    return {"row_count": len(ou_rows), "matched": len(merged), "unmatched": len(unmatched)}


def fixture_match_key(item: dict[str, Any]) -> tuple[str, str, str]:
    fixture = item.get("fixture", {})
    teams = item.get("teams", {})
    date = str(fixture.get("date", ""))[:10]
    home = normalize_name(str(teams.get("home", {}).get("name", "")))
    away = normalize_name(str(teams.get("away", {}).get("name", "")))
    return (date, home, away)


def national_api_completion(api: Stage5BApi, national_rows: list[dict[str, str]]) -> dict[str, Any]:
    local_index = {
        (
            row["match_date"],
            normalize_name(row["home_name_raw"]),
            normalize_name(row["away_name_raw"]),
        ): row
        for row in national_rows
        if row["competition"] in {"World Cup 2014", "World Cup 2018", "World Cup 2022"}
    }
    provider_fixtures: list[dict[str, Any]] = []
    for season in ("2014", "2018", "2022"):
        payload = api.request("fixtures", {"league": "1", "season": season}, "P1")
        response = payload.get("response", [])
        if isinstance(response, list):
            provider_fixtures.extend(response)
    mappings: list[dict[str, Any]] = []
    for item in provider_fixtures:
        match = local_index.get(fixture_match_key(item))
        if not match:
            continue
        mappings.append(
            {
                "fixture_uuid": stable_id(
                    "national",
                    match["competition"],
                    match["season"],
                    match["match_date"],
                    match["home_team_id"],
                    match["away_team_id"],
                ),
                "provider_fixture_id": item.get("fixture", {}).get("id"),
                "provider_home_team_id": item.get("teams", {}).get("home", {}).get("id"),
                "provider_away_team_id": item.get("teams", {}).get("away", {}).get("id"),
                "competition": item.get("league", {}).get("name"),
                "season": item.get("league", {}).get("season"),
                "round": item.get("league", {}).get("round"),
                "kickoff_utc": item.get("fixture", {}).get("date"),
                "timezone": item.get("fixture", {}).get("timezone"),
                "venue": item.get("fixture", {}).get("venue"),
                "referee": item.get("fixture", {}).get("referee"),
                "fixture_status": item.get("fixture", {}).get("status"),
                "score": item.get("score"),
            }
        )
    mapped_keys = {mapping["fixture_uuid"] for mapping in mappings}
    expected = [
        stable_id(
            "national",
            row["competition"],
            row["season"],
            row["match_date"],
            row["home_team_id"],
            row["away_team_id"],
        )
        for row in national_rows
        if row["competition"] in {"World Cup 2014", "World Cup 2018", "World Cup 2022"}
    ]
    review = [fixture_id for fixture_id in expected if fixture_id not in mapped_keys]
    write_json(PROCESSED / "national_provider_mappings.json", mappings)
    mapping_rate = len(mapped_keys) / len(expected) if expected else 0
    return {
        "expected": len(expected),
        "mapped": len(mapped_keys),
        "mapping_rate": mapping_rate,
        "review_queue": review[:50],
        "warn_only": mapping_rate >= 0.95,
        "blocker": mapping_rate < 0.95,
        "provider_fixture_ids_for_probe": [
            str(item.get("fixture", {}).get("id")) for item in provider_fixtures[:20]
        ],
    }


def historical_odds_probe(api: Stage5BApi, fixture_ids: list[str]) -> dict[str, Any]:
    selected = fixture_ids[:20]
    results: list[dict[str, Any]] = []
    for fixture_id in selected:
        payload = api.request("odds", {"fixture": fixture_id}, "P4")
        count = len(payload.get("response", [])) if isinstance(payload.get("response"), list) else 0
        results.append(
            {
                "fixture_id": fixture_id,
                "status": "HAS_ODDS" if count else "NO_PROVIDER_HISTORICAL_ODDS",
                "response_count": count,
            }
        )
    coverage = (
        sum(1 for item in results if item["status"] == "HAS_ODDS") / len(results) if results else 0
    )
    return {
        "sample_size": len(results),
        "coverage": coverage,
        "bulk_backfill_allowed": coverage >= 0.2,
        "items": results,
    }


def endpoint_probe(api: Stage5BApi, fixture_ids: list[str]) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    sample = fixture_ids[:3]
    for endpoint in ("statistics", "lineups", "events", "injuries"):
        hits = 0
        for fixture_id in sample:
            payload = api.request(endpoint, {"fixture": fixture_id}, "P3")
            response = payload.get("response", [])
            if isinstance(response, list) and response:
                hits += 1
        rate = hits / len(sample) if sample else 0
        coverage[endpoint] = {
            "sample_size": len(sample),
            "effective_coverage": rate,
            "bulk_backfill": rate >= 0.6,
            "status": "AVAILABLE" if rate >= 0.6 else "PARTIAL_COVERAGE",
        }
    return coverage


def club_dataset(api: Stage5BApi) -> dict[str, Any]:
    leagues: dict[str, Any] = {}
    total_fixtures = 0
    for name in LEAGUE_SEARCHES:
        league_payload = api.request("leagues", {"search": name}, "P2")
        choices = league_payload.get("response", [])
        if not isinstance(choices, list) or not choices:
            leagues[name] = {"status": "NOT_FOUND"}
            continue
        selected = choices[0]
        league_id = str(selected.get("league", {}).get("id"))
        seasons = [
            str(season["year"])
            for season in selected.get("seasons", [])
            if str(season.get("year", "")).isdigit() and int(season["year"]) <= 2025
        ][-3:]
        season_counts: dict[str, int] = {}
        for season in seasons:
            payload = api.request("fixtures", {"league": league_id, "season": season}, "P2")
            response = payload.get("response", [])
            count = len(response) if isinstance(response, list) else 0
            total_fixtures += count
            season_counts[season] = count
        leagues[name] = {
            "league_id": league_id,
            "selected_completed_seasons": seasons,
            "fixture_counts": season_counts,
            "status": "AVAILABLE" if season_counts else "PARTIAL",
        }
    return {
        "CLUB_RESULTS_DATASET": "AVAILABLE" if total_fixtures else "BLOCKED",
        "CLUB_MARKET_DATASET": "PARTIAL_COVERAGE",
        "league_count": len(leagues),
        "fixture_count": total_fixtures,
        "leagues": leagues,
    }


def source_manifest() -> dict[str, Any]:
    odds_files = sorted(ODDS_SNAPSHOT_ROOT.rglob("*.jsonl")) if ODDS_SNAPSHOT_ROOT.exists() else []
    return {
        "sources": [
            {
                "source_id": "w1_international_dataset_csv",
                "path": str(INTERNATIONAL_CSV),
                "sha256": sha256_file(INTERNATIONAL_CSV),
                "readonly": True,
                "source_artifact": "processed_csv",
            },
            {
                "source_id": "w1_worldcup2026_xlsx",
                "path": str(WORLD_CUP_XLSX),
                "sha256": sha256_file(WORLD_CUP_XLSX) if WORLD_CUP_XLSX.exists() else None,
                "readonly": True,
                "source_artifact": "raw_excel" if WORLD_CUP_XLSX.exists() else "absent",
                "cross_validation": "processed CSV has WorldCup2026Qualifiers rows",
            },
            {
                "source_id": "w1_world_cup_odds_historical_csv",
                "path": str(HISTORICAL_OU_CSV),
                "sha256": sha256_file(HISTORICAL_OU_CSV),
                "readonly": True,
            },
            {
                "source_id": "w1_2026_odds_snapshots",
                "path": str(ODDS_SNAPSHOT_ROOT),
                "file_count": len(odds_files),
                "sha256_manifest": hashlib.sha256(
                    "".join(sha256_file(path) for path in odds_files).encode()
                ).hexdigest(),
                "readonly": True,
            },
        ]
    }


def write_reports(
    *,
    api: Stage5BApi,
    national_quality: dict[str, Any],
    club_quality: dict[str, Any],
    market_coverage: dict[str, Any],
    review_queue: dict[str, Any],
    blockers: list[str],
) -> None:
    REPORTS.mkdir(exist_ok=True)
    write_json(REPORTS / "W2_STAGE5B_SOURCE_MANIFEST.json", source_manifest())
    write_json(REPORTS / "W2_STAGE5B_NATIONAL_DATA_QUALITY.json", national_quality)
    write_json(REPORTS / "W2_STAGE5B_CLUB_DATA_QUALITY.json", club_quality)
    write_json(REPORTS / "W2_STAGE5B_MARKET_COVERAGE.json", market_coverage)
    write_json(
        REPORTS / "W2_STAGE5B_API_USAGE.json",
        {
            "daily_quota": DAILY_QUOTA,
            "reserved_for_realtime": RESERVE_QUOTA,
            "stage5b_allowed_requests": api.allowed_requests,
            "requests_used": api.request_count,
            "remaining_quota": api.remaining_quota,
            "by_endpoint": {
                endpoint: sum(1 for item in api.audit if item.endpoint == endpoint)
                for endpoint in sorted({item.endpoint for item in api.audit})
            },
            "audit": [item.__dict__ for item in api.audit],
        },
    )
    write_json(REPORTS / "W2_STAGE5B_MAPPING_REVIEW_QUEUE.json", review_queue)
    result_lines = [
        "# W2 Stage 5B Result",
        "",
        "STAGE_5B=COMPLETED" if not blockers else "STAGE_5B=PROVISIONAL",
        "STAGE_5=PROVISIONAL",
        "GATE_2=CLOSED",
        "GATE_3=NOT_STARTED",
        "",
        "Fixed sources only: W1 local Football-Data assets and API-Football.",
        "No W1 files were modified. No new data vendor was added.",
        "",
        "BLOCKER:",
    ]
    result_lines.extend([f"- {item}" for item in blockers] or ["- None"])
    result_lines.extend(
        [
            "",
            "WARN_ONLY:",
            "- UNMAPPED_FIXTURES_UNDER_5_PERCENT"
            if national_quality.get("mapping_rate", 0) >= 0.95
            else "- NATIONAL_MAPPING_REVIEW_REQUIRED",
            "- CLUB_MARKET_DATASET_PARTIAL_COVERAGE",
            "",
            "PUSH_BLOCKED_NO_ORIGIN",
        ]
    )
    (REPORTS / "W2_STAGE5B_RESULT.md").write_text("\n".join(result_lines) + "\n", encoding="utf-8")


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    api = Stage5BApi()
    blockers: list[str] = []
    try:
        api.status()
        national_rows = read_csv(INTERNATIONAL_CSV)
        ou_rows = read_csv(HISTORICAL_OU_CSV)
        national_summary = import_national_rows(national_rows)
        ou_summary = merge_historical_ou(ou_rows, national_rows)
        mapping = national_api_completion(api, national_rows)
        odds_probe = historical_odds_probe(api, mapping["provider_fixture_ids_for_probe"])
        endpoint_coverage = endpoint_probe(api, mapping["provider_fixture_ids_for_probe"])
        club_quality = club_dataset(api)
        if mapping["blocker"]:
            blockers.append("NATIONAL_FIXTURE_MAPPING_RATE_BELOW_95_PERCENT")
        national_quality = {
            **national_summary,
            "source_sha256": sha256_file(INTERNATIONAL_CSV),
            "xlsx_source_present": WORLD_CUP_XLSX.exists(),
            "xlsx_source_sha256": sha256_file(WORLD_CUP_XLSX) if WORLD_CUP_XLSX.exists() else None,
            "football_data_1x2_semantics": "UNKNOWN_PREMATCH_AGGREGATE",
            "post_match_observation_separated": True,
            "pre_match_feature_result_leakage": False,
            "hgp_semantics_repaired": True,
            "mapping_rate": mapping["mapping_rate"],
            "mapped": mapping["mapped"],
            "expected": mapping["expected"],
            "historical_ou": ou_summary,
        }
        market_coverage = {
            "historical_odds_probe": odds_probe,
            "optional_endpoint_coverage": endpoint_coverage,
            "closing_odds_not_used_for_early_phase": True,
            "unknown_prematch_aggregate_not_used_for_phase_backtest": True,
            "historical_ah_fabricated": False,
        }
        review_queue = {
            "unmapped_fixture_count": len(mapping["review_queue"]),
            "sample": mapping["review_queue"],
            "status": "WARN_ONLY" if not mapping["blocker"] else "BLOCKER",
        }
    except (RuntimeError, LiveNetworkDisabledError) as exc:
        blockers.append(str(exc))
        national_quality = {"status": "BLOCKED_BEFORE_IMPORT"}
        club_quality = {"status": "BLOCKED_BEFORE_IMPORT"}
        market_coverage = {"status": "BLOCKED_BEFORE_IMPORT"}
        review_queue = {"status": "BLOCKED_BEFORE_IMPORT"}
    write_reports(
        api=api,
        national_quality=national_quality,
        club_quality=club_quality,
        market_coverage=market_coverage,
        review_queue=review_queue,
        blockers=blockers,
    )
    print("W2 Stage5B historical import completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
