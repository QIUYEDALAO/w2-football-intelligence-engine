#!/usr/bin/env python3
# ruff: noqa: S608
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
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
PREFERRED_COMPETITIONS = [
    "Premier League",
    "Serie A",
    "Bundesliga",
    "La Liga",
    "UEFA Champions League",
    "UEFA Europa League",
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
    def __init__(self, api_key: str, output_dir: Path) -> None:
        if not ENDPOINT.startswith("https://"):
            raise ValueError("Baselight endpoint must use https")
        self.api_key = api_key
        self.output_dir = output_dir
        self.counter = 0

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
                timeout=90,
            ) as response:
                payload = response.read().decode("utf-8", errors="replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            status = exc.code
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
    for _ in range(10):
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


def build_fixture_sql(max_fixtures: int) -> str:
    competitions = ", ".join(sql_string(item) for item in PREFERRED_COMPETITIONS)
    return f"""  # noqa: S608 - controlled constants and numeric LIMIT only.
WITH preferred_matches AS (
    SELECT
        m.match_id,
        m.competition_name AS competition,
        CAST(m.season_year AS VARCHAR) AS season,
        m.kickoff_timestamp AS kickoff_utc,
        m.home_team_id,
        m.home_team_name,
        m.away_team_id,
        m.away_team_name,
        m.status,
        m.home_score,
        m.away_score,
        ROW_NUMBER() OVER (
            PARTITION BY m.competition_name, CAST(m.season_year AS VARCHAR)
            ORDER BY m.kickoff_timestamp, m.match_id
        ) AS fixture_rank
    FROM "@blt.ultimate_soccer_dataset.matches" m
    WHERE
        lower(CAST(m.status AS VARCHAR)) IN (
            'match finished',
            'finished',
            'ft',
            'aet',
            'pen'
        )
        AND m.home_score IS NOT NULL
        AND m.away_score IS NOT NULL
        AND m.competition_name IN ({competitions})
)
SELECT
    match_id,
    competition,
    season,
    kickoff_utc,
    home_team_id,
    home_team_name,
    away_team_id,
    away_team_name,
    status,
    home_score,
    away_score
FROM preferred_matches
WHERE fixture_rank <= 250
ORDER BY competition, season, kickoff_utc, match_id
LIMIT {max_fixtures}
""".strip()


def build_odds_sql(match_ids: list[str]) -> str:
    ids = ", ".join(sql_string(match_id) for match_id in match_ids)
    return f"""  # noqa: S608 - match IDs are SQL-escaped literals from Baselight rows.
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
    match_id IN ({ids})
    AND market = 'Asian Handicap'
    AND odds_type = 'pre_match'
    AND odds > 1
    AND regexp_matches(CAST(outcome AS VARCHAR), '[+-]?[0-9]+(\\\\.[0-9]+)?')
ORDER BY match_id, bookmaker, outcome, collected_at
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--sql-file", type=Path, default=DEFAULT_SQL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-fixtures", type=int, default=1000)
    parser.add_argument("--max-rows", type=int, default=250000)
    parser.add_argument("--page-size", type=int, default=5000)
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
    client = BaselightMcpClient(api_key, output_dir)
    client.request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "w2-baselight-limited-ah-extract", "version": "1"},
        },
    )
    fixture_columns, fixture_rows, fixture_total = execute_sql_rows(
        client,
        build_fixture_sql(args.max_fixtures),
        effective_page_size,
        args.max_fixtures,
    )
    fixtures = row_dicts(fixture_columns, fixture_rows)
    if args.output.exists():
        args.output.unlink()
    fixture_by_id = {str(row["match_id"]): row for row in fixtures}
    written = 0
    batch_size = 5
    match_ids = list(fixture_by_id)
    for start in range(0, len(match_ids), batch_size):
        if written >= args.max_rows:
            break
        batch = match_ids[start : start + batch_size]
        odds_columns, odds_rows, _ = execute_sql_rows(
            client,
            build_odds_sql(batch),
            effective_page_size,
            args.max_rows - written,
        )
        combined_rows: list[dict[str, Any]] = []
        for odds in row_dicts(odds_columns, odds_rows):
            fixture = fixture_by_id.get(str(odds.get("match_id")))
            if fixture is None:
                continue
            combined_rows.append({**fixture, **odds})
        columns = [
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
        rows = [[row.get(column) for column in columns] for row in combined_rows]
        written += write_rows(args.output, columns, rows, append=written > 0)
    print(
        "BASELIGHT_LIMITED_AH_EXTRACT_COMPLETE "
        f"rows={written} fixture_candidates={len(fixtures)} fixture_total={fixture_total} "
        f"effective_page_size={effective_page_size} raw_response_dir={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
