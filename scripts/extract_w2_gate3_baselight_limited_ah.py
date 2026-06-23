#!/usr/bin/env python3
# ruff: noqa: S608
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ENDPOINT = "https://api.baselight.app/mcp"
ENV_NAME = "BASELIGHT_API_KEY"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQL = ROOT / "reports/W2_GATE3_BASELIGHT_LIMITED_AH_EXTRACT_SQL_V2.sql"
DEFAULT_OUTPUT = Path(
    "/Users/liudehua/.openclaw/workspace/"
    "w2_external_data/baselight_gate3_limited_ah/baselight_limited_ah.jsonl"
)
DEFAULT_STATE = DEFAULT_OUTPUT.parent / "extract_state.json"
PREFERRED_COMPETITIONS = [
    "Premier League",
    "Serie A",
    "Bundesliga",
    "La Liga",
    "UEFA Champions League",
    "UEFA Europa League",
    "Ligue 1",
    "Eredivisie",
    "Major League Soccer",
    "UEFA Europa Conference League",
]
MAX_PENDING_SECONDS = 180
PENDING_POLL_SECONDS = 15
REQUEST_TIMEOUT_SECONDS = 20
OUTPUT_COLUMNS = [
    "match_id",
    "competition",
    "season",
    "kickoff_utc",
    "home_team_id",
    "home_team_name",
    "away_team_id",
    "away_team_name",
    "status",
    "home_score",
    "away_score",
    "bookmaker",
    "market",
    "outcome",
    "odds",
    "odds_type",
    "collected_at",
]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def raw_dir() -> Path:
    path = Path("/tmp") / f"w2_baselight_limited_ah_extract_{int(time.time())}"  # noqa: S108
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_mcp_body(body: str) -> dict[str, Any]:
    text = body.strip()
    if not text:
        return {"error": {"message": "MCP_EMPTY_RESPONSE"}}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        payload = stripped.removeprefix("data:").strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    if events:
        for event in reversed(events):
            if "result" in event or "error" in event:
                return event
        return events[-1]
    return {"error": {"message": "MCP_RESPONSE_PARSE_ERROR"}}


class BaselightMcpClient:
    def __init__(self, api_key: str, output_dir: Path, request_timeout_seconds: int) -> None:
        if not ENDPOINT.startswith("https://"):
            raise ValueError("Baselight endpoint must use https")
        self.api_key = api_key
        self.output_dir = output_dir
        self.counter = 0
        self.request_timeout_seconds = request_timeout_seconds

    def read_response_text(self, response: Any) -> str:
        chunks: list[bytes] = []
        deadline = time.monotonic() + self.request_timeout_seconds
        while time.monotonic() < deadline:
            line = response.readline()
            if not line:
                break
            chunks.append(line)
            decoded = b"".join(chunks).decode("utf-8", errors="replace")
            if line.strip().startswith(b"data:") and (
                '"result"' in decoded or '"error"' in decoded
            ):
                break
            if not decoded.lstrip().startswith("data:") and (
                '"result"' in decoded or '"error"' in decoded
            ):
                break
        if not chunks:
            raise TimeoutError("MCP_RESPONSE_TIMEOUT")
        return b"".join(chunks).decode("utf-8", errors="replace")

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.counter += 1
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": self.counter,
                "method": method,
                "params": params or {},
            }
        ).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - fixed HTTPS MCP endpoint.
            ENDPOINT,
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "accept": "application/json, text/event-stream",
                "x-api-key": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - endpoint validated as HTTPS.
                request,
                timeout=self.request_timeout_seconds,
            ) as response:
                payload = self.read_response_text(response)
                status = response.status
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            status = exc.code
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            return {
                "error": {
                    "status": None,
                    "message": "MCP_REQUEST_ERROR",
                    "error_type": type(exc).__name__,
                }
            }
        (self.output_dir / f"{self.counter:04d}_{method.replace('/', '_')}.json").write_text(
            payload,
            encoding="utf-8",
        )
        if status >= 400:
            return {"error": {"status": status, "message": "MCP_HTTP_ERROR"}}
        return parse_mcp_body(payload)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})


def parse_text_content(response: dict[str, Any]) -> dict[str, Any]:
    if "error" in response:
        return response
    result = response.get("result")
    if not isinstance(result, dict):
        return {"error": {"message": "MCP_RESULT_MISSING"}}
    content = result.get("content")
    if not isinstance(content, list):
        return result
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            try:
                parsed = json.loads(item["text"])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return {"error": {"message": "MCP_TEXT_CONTENT_PARSE_ERROR"}}


def table_payload(parsed: dict[str, Any]) -> tuple[str | None, int, list[str], list[list[Any]]]:
    if "error" in parsed:
        raise RuntimeError(str(parsed["error"].get("message", "MCP_TOOL_ERROR")))
    result_id = parsed.get("resultId") or parsed.get("jobId")
    state = str(parsed.get("state", "")).upper()
    if state and state not in {"DONE", "COMPLETED", "SUCCESS"}:
        if state == "PENDING" and result_id:
            return str(result_id), 0, [], []
        raise RuntimeError(f"BASELIGHT_QUERY_NOT_DONE:{state}")
    result = parsed.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("BASELIGHT_RESULT_MISSING")
    columns = result.get("columns")
    rows = result.get("rows")
    total = result.get("totalResults", 0)
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise RuntimeError("BASELIGHT_RESULT_SHAPE_UNSUPPORTED")
    return (
        str(result_id) if result_id else None,
        int(total or 0),
        [str(column) for column in columns],
        [row for row in rows if isinstance(row, list)],
    )


def wait_for_results(
    client: BaselightMcpClient,
    job_id: str,
    limit: int,
    offset: int,
) -> tuple[int, list[str], list[list[Any]]]:
    deadline = time.monotonic() + MAX_PENDING_SECONDS
    while time.monotonic() < deadline:
        parsed = parse_text_content(
            client.call_tool(
                "baselight_sdk_get_results",
                {
                    "jobId": job_id,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )
        next_job_id, total, columns, rows = table_payload(parsed)
        if columns:
            return total, columns, rows
        if not next_job_id:
            break
        time.sleep(PENDING_POLL_SECONDS)
    raise RuntimeError("BASELIGHT_QUERY_STILL_PENDING")


def write_rows(path: Path, columns: list[str], rows: list[list[Any]], append: bool) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    count = 0
    with path.open(mode, encoding="utf-8") as handle:
        for row in rows:
            record = {
                column: row[index] if index < len(row) else None
                for index, column in enumerate(columns)
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            count += 1
    return count


def row_dicts(columns: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    return [
        {column: row[index] if index < len(row) else None for index, column in enumerate(columns)}
        for row in rows
    ]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def economic_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("match_id", "")),
        str(row.get("bookmaker", "")),
        str(row.get("market", "")),
        str(row.get("outcome", "")),
        str(row.get("collected_at", "")),
    )


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"state_error": "STATE_JSON_INVALID"}
    return payload if isinstance(payload, dict) else {}


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = utc_now()
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sample_stats(path: Path) -> dict[str, Any]:
    rows = read_jsonl(path)
    fixtures = {str(row.get("match_id", "")) for row in rows if row.get("match_id")}
    bookmakers = {str(row.get("bookmaker", "")) for row in rows if row.get("bookmaker")}
    competitions = {str(row.get("competition", "")) for row in rows if row.get("competition")}
    line_buckets: set[str] = set()
    for row in rows:
        outcome = str(row.get("outcome", ""))
        marker = None
        for piece in outcome.replace("(", " ").replace(")", " ").split():
            try:
                value = abs(float(piece))
            except ValueError:
                continue
            marker = "4+" if value >= 4 else str(value).rstrip("0").rstrip(".")
            break
        if marker:
            line_buckets.add(marker)
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return {
        "row_count": len(rows),
        "fixture_count": len(fixtures),
        "bookmaker_count": len(bookmakers),
        "competition_count": len(competitions),
        "line_bucket_count": len(line_buckets),
        "sample_sha256": digest.hexdigest() if path.is_file() else None,
    }


def execute_sql_rows(
    client: BaselightMcpClient,
    sql: str,
    page_size: int,
    max_rows: int,
) -> tuple[list[str], list[list[Any]], int]:
    first = parse_text_content(client.call_tool("baselight_sdk_query_execute", {"sql": sql}))
    job_id, total_results, columns, rows = table_payload(first)
    if job_id and not columns:
        total_results, columns, rows = wait_for_results(client, job_id, page_size, 0)
    all_rows = rows[:max_rows]
    offset = len(rows)
    while job_id and offset < total_results and len(all_rows) < max_rows:
        page = parse_text_content(
            client.call_tool(
                "baselight_sdk_get_results",
                {
                    "jobId": job_id,
                    "limit": page_size,
                    "offset": offset,
                },
            )
        )
        _, _, page_columns, page_rows = table_payload(page)
        if page_columns != columns:
            raise RuntimeError("BASELIGHT_PAGE_SCHEMA_CHANGED")
        if not page_rows:
            break
        remaining = max_rows - len(all_rows)
        all_rows.extend(page_rows[:remaining])
        offset += len(page_rows)
    return columns, all_rows, total_results


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_timestamp(value: datetime) -> str:
    return value.strftime("TIMESTAMP '%Y-%m-%d %H:%M:%S'")


def outcome_has_line(value: Any) -> bool:
    text = str(value)
    for piece in text.replace("(", " ").replace(")", " ").split():
        try:
            float(piece)
        except ValueError:
            continue
        return True
    return False


def build_odds_date_window_sql(start: datetime, end: datetime, limit: int) -> str:
    return f"""
SELECT
    match_id,
    bookmaker,
    market,
    outcome,
    odds,
    odds_type,
    collected_at
FROM "@blt.ultimate_soccer_dataset.match_betting_odds"
WHERE
    collected_at >= {sql_timestamp(start)}
    AND collected_at < {sql_timestamp(end)}
    AND market = 'Asian Handicap'
    AND odds_type = 'pre_match'
    AND odds > 1
LIMIT {limit}
""".strip()


def build_competition_seed_sql(competition: str, limit: int = 150) -> str:
    return f"""
SELECT
    match_id,
    competition_name AS competition,
    CAST(season_year AS VARCHAR) AS season,
    kickoff_timestamp AS kickoff_utc,
    home_team_id,
    home_team_name,
    away_team_id,
    away_team_name,
    status,
    home_score,
    away_score
FROM "@blt.ultimate_soccer_dataset.matches"
WHERE
    competition_name = {sql_string(competition)}
    AND home_score IS NOT NULL
    AND away_score IS NOT NULL
    AND lower(CAST(status AS VARCHAR)) IN (
        'match finished',
        'finished',
        'ft',
        'aet',
        'pen'
    )
ORDER BY kickoff_timestamp, match_id
LIMIT {limit}
""".strip()


def build_ah_match_id_sql(max_fixtures: int) -> str:
    return f"""
SELECT
    match_id
FROM "@blt.ultimate_soccer_dataset.match_betting_odds"
WHERE
    market = 'Asian Handicap'
    AND odds_type = 'pre_match'
    AND odds > 1
    AND regexp_matches(CAST(outcome AS VARCHAR), '[+-]?[0-9]+(\\\\.[0-9]+)?')
GROUP BY match_id
ORDER BY match_id
LIMIT {max_fixtures}
""".strip()


def build_match_metadata_sql(match_ids: list[str]) -> str:
    ids = ", ".join(sql_string(match_id) for match_id in match_ids)
    return f"""
SELECT
    match_id,
    competition_name AS competition,
    CAST(season_year AS VARCHAR) AS season,
    kickoff_timestamp AS kickoff_utc,
    home_team_id,
    home_team_name,
    away_team_id,
    away_team_name,
    status,
    home_score,
    away_score
FROM "@blt.ultimate_soccer_dataset.matches"
WHERE
    match_id IN ({ids})
    AND home_score IS NOT NULL
    AND away_score IS NOT NULL
ORDER BY kickoff_timestamp, match_id
""".strip()


def combine_odds_with_matches(
    odds_rows: list[dict[str, Any]],
    match_rows: list[dict[str, Any]],
    existing_keys: set[tuple[str, str, str, str, str]],
) -> tuple[list[dict[str, Any]], set[str]]:
    fixture_by_id = {
        str(row["match_id"]): row
        for row in match_rows
        if row.get("match_id")
        and row.get("home_score") is not None
        and row.get("away_score") is not None
    }
    combined_rows: list[dict[str, Any]] = []
    fixture_ids: set[str] = set()
    for odds in odds_rows:
        if not outcome_has_line(odds.get("outcome")):
            continue
        fixture = fixture_by_id.get(str(odds.get("match_id")))
        if fixture is None:
            continue
        row = {**fixture, **odds}
        key = economic_key(row)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        combined_rows.append(row)
        fixture_ids.add(str(row["match_id"]))
    return combined_rows, fixture_ids


def append_combined_rows(
    output: Path,
    rows_to_append: list[dict[str, Any]],
    existing_keys: set[tuple[str, str, str, str, str]],
) -> int:
    rows = [[row.get(column) for column in OUTPUT_COLUMNS] for row in rows_to_append]
    for row in rows_to_append:
        existing_keys.add(economic_key(row))
    return write_rows(output, OUTPUT_COLUMNS, rows, append=output.exists())


def run_odds_date_window_strategy(
    client: BaselightMcpClient,
    args: argparse.Namespace,
    state: dict[str, Any],
    existing_keys: set[tuple[str, str, str, str, str]],
    effective_page_size: int,
) -> tuple[int, set[str]]:
    state["method"] = "ODDS_DATE_WINDOW_THEN_MATCHES_METADATA_NO_JOIN"
    state.setdefault("date_windows", [])
    written = 0
    appended_fixtures: set[str] = set()
    start_date = datetime.fromisoformat(args.start_date).replace(tzinfo=UTC)
    match_batch_size = max(1, min(args.fixture_batch_size, 100))
    for index in range(args.max_date_windows):
        current_stats = sample_stats(args.output)
        if (
            current_stats["fixture_count"] >= args.target_fixtures
            and current_stats["bookmaker_count"] >= 5
            and current_stats["line_bucket_count"] >= 8
            and current_stats["competition_count"] >= 5
        ):
            break
        if current_stats["row_count"] >= args.max_rows:
            break
        window_end = start_date - timedelta(days=index * args.date_window_days)
        window_start = window_end - timedelta(days=args.date_window_days)
        window_record = {
            "window_start_utc": window_start.isoformat().replace("+00:00", "Z"),
            "window_end_utc": window_end.isoformat().replace("+00:00", "Z"),
            "status": "STARTED",
            "observed_at_utc": utc_now(),
        }
        try:
            odds_columns, odds_raw_rows, _ = execute_sql_rows(
                client,
                build_odds_date_window_sql(window_start, window_end, min(args.page_size, 5000)),
                effective_page_size,
                min(args.max_rows - current_stats["row_count"], 5000),
            )
        except RuntimeError as exc:
            window_record.update({"status": "PENDING_OR_FAILED", "reason": str(exc)})
            state["date_windows"].append(window_record)
            write_state(args.state_file, state)
            continue
        odds_rows = [
            row
            for row in row_dicts(odds_columns, odds_raw_rows)
            if row.get("match_id") and outcome_has_line(row.get("outcome"))
        ]
        match_ids = sorted({str(row["match_id"]) for row in odds_rows})
        window_written = 0
        window_fixtures: set[str] = set()
        for start in range(0, len(match_ids), match_batch_size):
            batch = match_ids[start : start + match_batch_size]
            try:
                match_columns, match_raw_rows, _ = execute_sql_rows(
                    client,
                    build_match_metadata_sql(batch),
                    effective_page_size,
                    len(batch),
                )
            except RuntimeError as exc:
                state.setdefault("metadata_batches", []).append(
                    {
                        "match_ids": batch,
                        "status": "PENDING_OR_FAILED",
                        "reason": str(exc),
                        "observed_at_utc": utc_now(),
                    }
                )
                write_state(args.state_file, state)
                continue
            batch_set = set(batch)
            batch_odds = [row for row in odds_rows if str(row.get("match_id")) in batch_set]
            combined_rows, fixture_ids = combine_odds_with_matches(
                batch_odds,
                row_dicts(match_columns, match_raw_rows),
                existing_keys,
            )
            window_written += append_combined_rows(args.output, combined_rows, existing_keys)
            window_fixtures.update(fixture_ids)
            appended_fixtures.update(fixture_ids)
        written += window_written
        window_record.update(
            {
                "status": "APPENDED",
                "odds_row_count": len(odds_rows),
                "match_id_count": len(match_ids),
                "new_rows": window_written,
                "new_fixtures": len(window_fixtures),
            }
        )
        state["date_windows"].append(window_record)
        write_state(args.state_file, state)
    return written, appended_fixtures


def build_odds_sql(match_ids: list[str]) -> str:
    ids = ", ".join(sql_string(match_id) for match_id in match_ids)
    return f"""
WITH ranked_odds AS (
SELECT
    match_id,
    bookmaker,
    market,
    outcome,
    odds,
    odds_type,
    collected_at,
    ROW_NUMBER() OVER (
        PARTITION BY match_id
        ORDER BY bookmaker, outcome, collected_at
    ) AS row_rank
FROM "@blt.ultimate_soccer_dataset.match_betting_odds"
WHERE
    match_id IN ({ids})
    AND market = 'Asian Handicap'
    AND odds_type = 'pre_match'
    AND odds > 1
    AND regexp_matches(CAST(outcome AS VARCHAR), '[+-]?[0-9]+(\\\\.[0-9]+)?')
)
SELECT
    match_id,
    bookmaker,
    market,
    outcome,
    odds,
    odds_type,
    collected_at
FROM ranked_odds
WHERE row_rank <= 50
ORDER BY match_id, bookmaker, outcome, collected_at
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--strategy",
        choices=["match_seed", "odds_date_window"],
        default="odds_date_window",
    )
    parser.add_argument("--sql-file", type=Path, default=DEFAULT_SQL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-fixtures", type=int, default=1000)
    parser.add_argument("--max-rows", type=int, default=250000)
    parser.add_argument("--page-size", type=int, default=5000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--target-fixtures", type=int, default=500)
    parser.add_argument("--max-new-fixtures", type=int, default=700)
    parser.add_argument("--fixture-batch-size", type=int, default=3)
    parser.add_argument("--date-window-days", type=int, default=1)
    parser.add_argument("--max-date-windows", type=int, default=60)
    parser.add_argument(
        "--start-date",
        default=datetime.now(UTC).date().isoformat(),
        help="UTC date used as the exclusive end of the first odds window.",
    )
    parser.add_argument("--per-query-timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    api_key = os.environ.get(ENV_NAME)
    if not api_key:
        print("BASELIGHT_API_KEY_REQUIRED")
        return 2
    if not args.live:
        print("LIVE_FLAG_REQUIRED")
        return 2
    if not args.sql_file.is_file():
        print("SQL_FILE_MISSING")
        return 1

    effective_page_size = min(args.page_size, 100)
    if effective_page_size < args.page_size:
        print(f"MCP_PAGE_SIZE_CAPPED={effective_page_size}")
    args.sql_file.read_text(encoding="utf-8")
    output_dir = raw_dir()
    client = BaselightMcpClient(
        api_key,
        output_dir,
        max(1, min(args.per_query_timeout_seconds, 180)),
    )
    client.request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "w2-baselight-limited-ah-extract", "version": "1"},
        },
    )
    existing_rows = read_jsonl(args.output) if args.resume else []
    existing_keys = {economic_key(row) for row in existing_rows}
    existing_fixtures = {
        str(row.get("match_id", "")) for row in existing_rows if row.get("match_id")
    }
    if args.output.exists() and not args.resume:
        args.output.unlink()
    state = load_state(args.state_file)
    state.setdefault("schema_version", "W2_BASELIGHT_MICRO_BATCH_EXTRACT_STATE_V2")
    state.setdefault("method", "MATCH_SEED_PLUS_ODDS_MICRO_BATCH_NO_JOIN")
    state.setdefault("attempted_competitions", [])
    state.setdefault("pending_competitions", [])
    state.setdefault("completed_competitions", [])
    state.setdefault("fixture_batches", [])
    state["raw_response_dir"] = str(output_dir)
    state["strategy"] = args.strategy
    if args.strategy == "odds_date_window":
        written, appended_fixtures = run_odds_date_window_strategy(
            client,
            args,
            state,
            existing_keys,
            effective_page_size,
        )
        final_stats = sample_stats(args.output)
        state["final_stats"] = final_stats
        state["new_rows_written"] = written
        state["new_fixtures_written"] = len(appended_fixtures)
        write_state(args.state_file, state)
        print(
            "BASELIGHT_LIMITED_AH_EXTRACT_COMPLETE "
            f"strategy=odds_date_window new_rows={written} "
            f"total_rows={final_stats['row_count']} "
            f"total_fixtures={final_stats['fixture_count']} "
            f"effective_page_size={effective_page_size} raw_response_dir={output_dir}"
        )
        return 0
    candidate_fixtures: list[dict[str, Any]] = []
    for competition in PREFERRED_COMPETITIONS:
        candidate_count = len({str(row.get("match_id")) for row in candidate_fixtures})
        if len(existing_fixtures) + candidate_count >= args.max_new_fixtures:
            break
        state["attempted_competitions"].append(competition)
        try:
            seed_columns, seed_rows, _ = execute_sql_rows(
                client,
                build_competition_seed_sql(competition),
                effective_page_size,
                150,
            )
        except RuntimeError as exc:
            state["pending_competitions"].append(
                {"competition": competition, "reason": str(exc), "observed_at_utc": utc_now()}
            )
            write_state(args.state_file, state)
            continue
        seed_records = row_dicts(seed_columns, seed_rows)
        state["completed_competitions"].append(
            {"competition": competition, "seed_count": len(seed_records)}
        )
        for record in seed_records:
            match_id = str(record.get("match_id", ""))
            if not match_id or match_id in existing_fixtures:
                continue
            candidate_fixtures.append(record)
    write_state(args.state_file, state)
    written = 0
    appended_fixtures: set[str] = set()
    batch_size = max(1, min(args.fixture_batch_size, 3))
    start = 0
    while start < len(candidate_fixtures):
        current_stats = sample_stats(args.output)
        if (
            current_stats["fixture_count"] >= args.target_fixtures
            and current_stats["bookmaker_count"] >= 5
            and current_stats["line_bucket_count"] >= 8
            and current_stats["competition_count"] >= 5
        ):
            break
        if current_stats["row_count"] >= args.max_rows:
            break
        batch_records = candidate_fixtures[start : start + batch_size]
        batch = [str(row["match_id"]) for row in batch_records if row.get("match_id")]
        fixture_by_id = {str(row["match_id"]): row for row in batch_records if row.get("match_id")}
        if not batch:
            start += batch_size
            continue
        try:
            odds_columns, odds_rows, _ = execute_sql_rows(
                client,
                build_odds_sql(batch),
                effective_page_size,
                args.max_rows - current_stats["row_count"],
            )
        except RuntimeError as exc:
            retryable = (
                "BASELIGHT_QUERY_STILL_PENDING" in str(exc)
                or "MCP_REQUEST_ERROR" in str(exc)
            )
            if batch_size > 1 and retryable:
                batch_size = 1
                continue
            state["fixture_batches"].append(
                {
                    "match_ids": batch,
                    "status": "PENDING_OR_FAILED",
                    "reason": str(exc),
                    "observed_at_utc": utc_now(),
                }
            )
            write_state(args.state_file, state)
            if batch_size == 1 and retryable:
                print("BASELIGHT_SINGLE_FIXTURE_QUERY_PENDING")
                return 3
            start += batch_size
            continue
        combined_rows: list[dict[str, Any]] = []
        for odds in row_dicts(odds_columns, odds_rows):
            fixture = fixture_by_id.get(str(odds.get("match_id")))
            if fixture is None:
                continue
            row = {**fixture, **odds}
            key = economic_key(row)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            combined_rows.append(row)
            if row.get("match_id"):
                appended_fixtures.add(str(row["match_id"]))
        rows = [[row.get(column) for column in OUTPUT_COLUMNS] for row in combined_rows]
        written += write_rows(args.output, OUTPUT_COLUMNS, rows, append=args.output.exists())
        state["fixture_batches"].append(
            {
                "match_ids": batch,
                "status": "APPENDED",
                "new_rows": len(rows),
                "observed_at_utc": utc_now(),
            }
        )
        write_state(args.state_file, state)
        start += batch_size
    final_stats = sample_stats(args.output)
    state["final_stats"] = final_stats
    state["new_rows_written"] = written
    state["new_fixtures_written"] = len(appended_fixtures)
    write_state(args.state_file, state)
    print(
        "BASELIGHT_LIMITED_AH_EXTRACT_COMPLETE "
        f"new_rows={written} total_rows={final_stats['row_count']} "
        f"total_fixtures={final_stats['fixture_count']} "
        f"effective_page_size={effective_page_size} raw_response_dir={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
