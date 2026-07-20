from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

TOP_FIVE_LEAGUE_IDS = {"39", "140", "135", "78", "61"}
TRACKED_LEAGUE_IDS = {*TOP_FIVE_LEAGUE_IDS, "113"}
RUNTIME_SUBDIRS = (
    "market_timeline_snapshots",
    "future_refresh",
    "stage7c/raw",
    "provider_raw",
    "raw",
    "odds",
    "fixtures",
    "results",
)
DATA_SUFFIXES = {".json", ".jsonl", ".ndjson", ".csv"}


def build_existing_football_data_inventory(
    *,
    repo_root: Path,
    database_url: str | None = None,
) -> dict[str, Any]:
    roots = _allowed_roots(repo_root)
    files: list[dict[str, Any]] = []
    counters = _empty_counters()
    samples: list[dict[str, Any]] = []
    for root in roots:
        if not root["exists"]:
            continue
        for path in _iter_data_files(Path(root["path"])):
            record = _file_record(path, repo_root=repo_root)
            file_counters, file_samples = _inspect_file(path)
            _merge_counters(counters, file_counters)
            if len(samples) < 3:
                samples.extend(file_samples[: 3 - len(samples)])
            record["detected"] = file_counters
            files.append(record)

    competition_registry = _competition_registry_summary(repo_root)
    db = inspect_local_database(database_url=database_url, repo_root=repo_root)
    db_counts = db.get("counts", {})
    if isinstance(db_counts, dict):
        _merge_counters(counters, db_counts)

    status = _inventory_status(counters)
    checked_locations = [item for item in roots]
    payload = _jsonable({
        "schema_version": "w2.existing_football_data_inventory.v1",
        "status": status,
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
        "checked_locations": checked_locations,
        "competition_registry": competition_registry,
        "database": db,
        "files": files,
        "field_shape_samples": samples[:3],
        "summary": _summary(counters),
        "classification": _classification(counters),
        "privacy": {
            "raw_payload_values_included": False,
            "credentials_included": False,
            "private_raw_data_committed": False,
            "provider_calls": 0,
            "network_downloads": 0,
            "home_directory_full_scan": False,
        },
    })
    payload["inventory_hash"] = _stable_hash(payload)
    return cast(dict[str, Any], payload)


def write_inventory_outputs(payload: dict[str, Any], *, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary = payload["summary"]
    classification = payload["classification"]
    lines = [
        "# Existing Football Data Inventory",
        "",
        f"- status: {payload['status']}",
        f"- manual_stop: {payload['manual_stop']}",
        f"- checked_locations: {len(payload['checked_locations'])}",
        f"- discovered_files: {len(payload['files'])}",
        f"- database_status: {payload['database']['status']}",
        f"- top_five_existing_download_detected: "
        f"{summary['top_five_existing_download_detected']}",
        f"- historical_odds_found: {summary['historical_odds_found']}",
        f"- bookmaker_found: {summary['bookmaker_found']}",
        f"- ah_line_found: {summary['ah_line_found']}",
        f"- ou_line_found: {summary['ou_line_found']}",
        f"- captured_at_found: {summary['captured_at_found']}",
        f"- final_result_found: {summary['final_result_found']}",
        f"- f5_ready_candidate_fixtures: {classification['f5_ready_candidate_fixtures']}",
        f"- calibration_baseline_candidate_batches: "
        f"{classification['calibration_baseline_candidate_batches']}",
        "",
        "## Missing Fields",
    ]
    lines.extend(f"- {item}" for item in payload["classification"]["missing_fields"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def inspect_local_database(*, database_url: str | None, repo_root: Path) -> dict[str, Any]:
    url = database_url or os.getenv("W2_DATABASE_URL") or "sqlite+pysqlite:///.local/w2.db"
    target = _database_target(url, repo_root=repo_root)
    if not target["read_allowed"]:
        return {
            "status": "READ_ONLY_DATABASE_AUTHORIZATION_REQUIRED",
            "target": target,
            "tables": [],
            "counts": _empty_counters(),
        }
    if target["dialect"].startswith("sqlite") and target.get("path_exists") is False:
        return {
            "status": "LOCAL_DATABASE_NOT_FOUND",
            "target": target,
            "tables": [],
            "counts": _empty_counters(),
        }
    try:
        engine = create_engine(url)
        inspector = inspect(engine)
        tables = sorted(inspector.get_table_names())
        relevant = [name for name in tables if _table_is_relevant(name)]
        counts = _empty_counters()
        table_rows = []
        with engine.connect() as connection:
            for table in relevant:
                quoted = table.replace('"', '""')
                count = connection.execute(
                    text(f'select count(*) from "{quoted}"')  # noqa: S608
                ).scalar_one()
                table_rows.append({"table": table, "row_count": int(count)})
        return {"status": "READ_ONLY_OK", "target": target, "tables": table_rows, "counts": counts}
    except Exception as exc:
        return {
            "status": "READ_ONLY_DATABASE_UNAVAILABLE",
            "target": target,
            "error": type(exc).__name__,
            "tables": [],
            "counts": _empty_counters(),
        }


def _allowed_roots(repo_root: Path) -> list[dict[str, Any]]:
    candidates: list[Path] = []
    env_root = os.getenv("W2_RUNTIME_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())
    runtime = repo_root / "runtime"
    candidates.append(runtime)
    candidates.extend(runtime / name for name in RUNTIME_SUBDIRS)
    deduped: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in deduped:
            deduped.append(resolved)
    return [
        {"path": str(path), "exists": path.exists(), "is_dir": path.is_dir()}
        for path in deduped
    ]


def _iter_data_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in DATA_SUFFIXES else []
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix.lower() in DATA_SUFFIXES
    ]


def _file_record(path: Path, *, repo_root: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": _display_path(path, repo_root=repo_root),
        "size_bytes": stat.st_size,
        "sha256": _file_hash(path),
        "suffix": path.suffix.lower(),
    }


def _inspect_file(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    counters = _empty_counters()
    samples: list[dict[str, Any]] = []
    try:
        rows = _load_rows(path)
    except Exception:
        counters["unreadable_files"] += 1
        return counters, samples
    for row in rows:
        _inspect_row(row, counters)
        if len(samples) < 3:
            samples.append(_field_shape(row))
    return counters, samples


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    text_value = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        return [json.loads(line) for line in text_value.splitlines() if line.strip()][:10000]
    payload = json.loads(text_value)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        response = payload.get("response")
        if isinstance(response, list):
            return [row for row in response if isinstance(row, dict)]
        return [payload]
    return []


def _inspect_row(row: dict[str, Any], counters: dict[str, Any]) -> None:
    endpoint = _endpoint(row)
    if endpoint:
        counters["endpoints"][endpoint] += 1
    league_id = _league_id(row)
    if league_id:
        counters["league_ids"][league_id] += 1
        if league_id in TOP_FIVE_LEAGUE_IDS:
            counters["top_five_rows"] += 1
        if league_id == "113":
            counters["allsvenskan_rows"] += 1
    season = _text(_nested(row, "league", "season") or row.get("season"))
    if season:
        counters["seasons"][season] += 1
    fixture_id = _fixture_id(row)
    if fixture_id:
        counters["fixtures"].add(fixture_id)
    if _has_result(row):
        counters["final_results"].add(fixture_id or _stable_hash(row))
    bookmaker_id = _bookmaker_id(row)
    if bookmaker_id:
        counters["bookmakers"].add(bookmaker_id)
    captured_at = _captured_at(row)
    if captured_at:
        counters["captured_at_values"].append(captured_at)
    markets = _markets(row)
    for market in markets:
        counters["markets"][market["market"]] += 1
        if market["line"] is not None and market["market"] in {"ASIAN_HANDICAP", "TOTALS"}:
            counters["lined_markets"][market["market"]] += 1
        if market["market"] == "ASIAN_HANDICAP" and market["has_home_away"]:
            counters["ah_pair_keys"].add(
                (fixture_id, bookmaker_id, captured_at, str(market["line"]))
            )
        if market["market"] == "TOTALS" and market["has_over_under"]:
            counters["ou_pair_keys"].add(
                (fixture_id, bookmaker_id, captured_at, str(market["line"]))
            )
        if _is_quarter_line(market["line"]):
            counters["quarter_lines"] += 1
    if _is_live(row):
        counters["live_rows"] += 1
    elif markets:
        counters["prematch_rows"] += 1


def _summary(counters: dict[str, Any]) -> dict[str, Any]:
    captured = sorted(counters["captured_at_values"])
    return {
        "raw_payload_count": counters["endpoints"].get("raw", 0),
        "fixture_count": len(counters["fixtures"]),
        "final_result_count": len(counters["final_results"]),
        "odds_observation_count": sum(counters["markets"].values()),
        "earliest_captured_at": captured[0] if captured else None,
        "latest_captured_at": captured[-1] if captured else None,
        "bookmaker_count": len(counters["bookmakers"]),
        "one_x_two_count": counters["markets"].get("ONE_X_TWO", 0),
        "ah_count": counters["markets"].get("ASIAN_HANDICAP", 0),
        "ou_count": counters["markets"].get("TOTALS", 0),
        "quarter_line_count": counters["quarter_lines"],
        "live_count": counters["live_rows"],
        "prematch_count": counters["prematch_rows"],
        "ah_pair_count": len(counters["ah_pair_keys"]),
        "complete_same_batch_1x2_ah_ou_count": 0,
        "t30_or_earlier_complete_ah_pair_count": 0,
        "closing_quote_count": 0,
        "fixtures_with_final_90_result_count": len(counters["final_results"]),
        "top_five_existing_download_detected": counters["top_five_rows"] > 0,
        "historical_odds_found": sum(counters["markets"].values()) > 0,
        "bookmaker_found": bool(counters["bookmakers"]),
        "ah_line_found": counters["lined_markets"].get("ASIAN_HANDICAP", 0) > 0,
        "ou_line_found": counters["lined_markets"].get("TOTALS", 0) > 0,
        "captured_at_found": bool(captured),
        "final_result_found": bool(counters["final_results"]),
        "league_ids": dict(counters["league_ids"]),
        "endpoints": dict(counters["endpoints"]),
        "seasons": dict(counters["seasons"]),
    }


def _classification(counters: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    summary = _summary(counters)
    required = {
        "historical odds": summary["historical_odds_found"],
        "bookmaker ID": summary["bookmaker_found"],
        "AH line": summary["ah_line_found"],
        "OU line": summary["ou_line_found"],
        "captured_at": summary["captured_at_found"],
        "final 90-minute result": summary["final_result_found"],
    }
    missing.extend(name for name, present in required.items() if not present)
    return {
        "f5_ready_candidate_fixtures": 0,
        "calibration_baseline_candidate_batches": 0,
        "clv_candidate_count": 0,
        "missing_fields": missing,
        "requires_user_extra_data": False,
        "reason": "EXISTING_DATA_FIRST_NO_NEW_USER_DATA_REQUEST",
    }


def _inventory_status(counters: dict[str, Any]) -> str:
    summary = _summary(counters)
    if not summary["top_five_existing_download_detected"] and not summary["historical_odds_found"]:
        return "NO_EXISTING_DATA_FOUND"
    if (
        summary["historical_odds_found"]
        and summary["ah_line_found"]
        and summary["final_result_found"]
    ):
        return "EXISTING_DATA_PARTIALLY_USABLE"
    if summary["fixture_count"] or summary["final_result_count"]:
        return "EXISTING_DATA_INSUFFICIENT"
    return "NO_EXISTING_DATA_FOUND"


def _database_target(url: str, *, repo_root: Path) -> dict[str, Any]:
    parsed = make_url(url)
    dialect = parsed.get_backend_name()
    database = parsed.database or ""
    host = parsed.host or ""
    host_category = _host_category(host, dialect)
    database_hash = hashlib.sha256(database.encode()).hexdigest() if database else ""
    result = {
        "dialect": dialect,
        "host_category": host_category,
        "database_name_hash": database_hash,
        "read_allowed": host_category in {"local", "container"} or dialect.startswith("sqlite"),
    }
    if dialect.startswith("sqlite"):
        db_path = Path(database) if database else Path(":memory:")
        if database and database != ":memory:" and not db_path.is_absolute():
            db_path = repo_root / db_path
        result["path"] = _display_path(db_path, repo_root=repo_root)
        result["path_exists"] = db_path.exists() if database != ":memory:" else True
    return result


def _host_category(host: str, dialect: str) -> str:
    if dialect.startswith("sqlite") or host in {"", "localhost", "127.0.0.1", "::1"}:
        return "local"
    if host in {"postgres", "db"} or host.endswith(".local"):
        return "container"
    return "remote"


def _competition_registry_summary(repo_root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((repo_root / "config/competitions").rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        provider_id = _text(
            (payload.get("provider_mapping") or {}).get("api_football_league_id")
        )
        if provider_id in TRACKED_LEAGUE_IDS:
            rows.append(
                {
                    "competition_id": payload.get("competition_id"),
                    "name": payload.get("name"),
                    "api_football_league_id": provider_id,
                    "season": payload.get("season"),
                    "enabled": payload.get("enabled"),
                    "path": _display_path(path, repo_root=repo_root),
                }
            )
    return rows


def _empty_counters() -> dict[str, Any]:
    return {
        "endpoints": Counter(),
        "league_ids": Counter(),
        "seasons": Counter(),
        "fixtures": set(),
        "final_results": set(),
        "bookmakers": set(),
        "captured_at_values": [],
        "markets": Counter(),
        "lined_markets": Counter(),
        "ah_pair_keys": set(),
        "ou_pair_keys": set(),
        "quarter_lines": 0,
        "live_rows": 0,
        "prematch_rows": 0,
        "top_five_rows": 0,
        "allsvenskan_rows": 0,
        "unreadable_files": 0,
    }


def _merge_counters(left: dict[str, Any], right: dict[str, Any]) -> None:
    for key, value in right.items():
        if isinstance(value, Counter):
            left[key].update(value)
        elif isinstance(value, set):
            left[key].update(value)
        elif isinstance(value, list):
            left[key].extend(value)
        elif isinstance(value, int):
            left[key] += value


def _table_is_relevant(name: str) -> bool:
    lowered = name.lower()
    markers = (
        "raw",
        "payload",
        "fixture",
        "result",
        "settlement",
        "odds",
        "market",
        "timeline",
        "provider",
    )
    return any(marker in lowered for marker in markers)


def _field_shape(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fields": sorted(row.keys()),
        "types": {key: type(value).__name__ for key, value in row.items()},
    }


def _endpoint(row: dict[str, Any]) -> str | None:
    return _text(
        row.get("endpoint")
        or row.get("provider_endpoint")
        or row.get("schema")
        or row.get("source_endpoint")
    )


def _league_id(row: dict[str, Any]) -> str | None:
    return _text(
        _nested(row, "league", "id")
        or row.get("league_id")
        or row.get("provider_league_id")
    )


def _fixture_id(row: dict[str, Any]) -> str | None:
    return _text(
        _nested(row, "fixture", "id")
        or row.get("fixture_id")
        or row.get("provider_fixture_id")
    )


def _bookmaker_id(row: dict[str, Any]) -> str | None:
    return _text(_nested(row, "bookmaker", "id") or row.get("bookmaker_id"))


def _captured_at(row: dict[str, Any]) -> str | None:
    value = row.get("captured_at") or row.get("observed_at") or row.get("provider_last_update")
    text_value = _text(value)
    if not text_value:
        return None
    try:
        datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return text_value


def _has_result(row: dict[str, Any]) -> bool:
    status = _text(_nested(row, "fixture", "status", "short") or row.get("status"))
    raw_goals = row.get("goals")
    goals: dict[str, Any] = raw_goals if isinstance(raw_goals, dict) else {}
    has_score = goals.get("home") is not None and goals.get("away") is not None
    return status in {"FT", "AET", "PEN"} and has_score


def _markets(row: dict[str, Any]) -> list[dict[str, Any]]:
    direct_market = _canonical_market(row.get("canonical_market") or row.get("market"))
    if direct_market:
        selection = _text(row.get("selection"))
        return [
            {
                "market": direct_market,
                "line": row.get("line"),
                "has_home_away": selection in {"HOME", "AWAY", "Home", "Away"},
                "has_over_under": selection in {"OVER", "UNDER", "Over", "Under"},
            }
        ]
    bookmakers = row.get("bookmakers")
    markets: list[dict[str, Any]] = []
    if isinstance(bookmakers, list):
        for bookmaker in bookmakers:
            for bet in bookmaker.get("bets", []) if isinstance(bookmaker, dict) else []:
                market = _canonical_market(bet.get("name") or bet.get("market"))
                values = bet.get("values") if isinstance(bet, dict) else None
                if market and isinstance(values, list):
                    names = {_text(item.get("value")) for item in values if isinstance(item, dict)}
                    line = next(
                        (
                            item.get("handicap") or item.get("line")
                            for item in values
                            if isinstance(item, dict)
                        ),
                        None,
                    )
                    markets.append(
                        {
                            "market": market,
                            "line": line,
                            "has_home_away": {"Home", "Away"} <= names or {"HOME", "AWAY"} <= names,
                            "has_over_under": {"Over", "Under"} <= names
                            or {"OVER", "UNDER"} <= names,
                        }
                    )
    return markets


def _canonical_market(value: Any) -> str | None:
    text_value = _text(value).upper().replace("-", "_").replace(" ", "_")
    if text_value in {"MATCH_WINNER", "1X2", "ONE_X_TWO"}:
        return "ONE_X_TWO"
    if text_value in {"ASIAN_HANDICAP", "HANDICAP"}:
        return "ASIAN_HANDICAP"
    if text_value in {"GOALS_OVER_UNDER", "OVER_UNDER", "TOTALS", "TOTAL_GOALS"}:
        return "TOTALS"
    return None


def _is_quarter_line(value: Any) -> bool:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return False
    return abs(number * 4 - round(number * 4)) < 0.00001


def _is_live(row: dict[str, Any]) -> bool:
    value = _text(row.get("live") or row.get("is_live") or row.get("inplay"))
    return value.lower() in {"1", "true", "yes", "live"}


def _nested(row: dict[str, Any], *keys: str) -> Any:
    current: Any = row
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(_jsonable(payload), sort_keys=True).encode()).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Counter):
        return dict(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _display_path(path: Path, *, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)
