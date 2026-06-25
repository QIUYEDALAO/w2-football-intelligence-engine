#!/usr/bin/env python3
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

ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = ROOT / "archive/reports/W2_BASELIGHT_MCP_PROBE.json"
REPORT_MD = ROOT / "archive/reports/W2_BASELIGHT_MCP_PROBE.md"
ENDPOINT = "https://api.baselight.app/mcp"
ENV_NAME = "BASELIGHT_API_KEY"
ODDS_SQL = 'SELECT * FROM "@blt.ultimate_soccer_dataset.match_betting_odds" LIMIT 5'
MATCHES_SQL = 'SELECT * FROM "@blt.ultimate_soccer_dataset.matches" LIMIT 5'


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def raw_dir() -> Path:
    base = Path("/tmp") / f"w2_baselight_mcp_probe_{int(time.time())}"  # noqa: S108
    base.mkdir(parents=True, exist_ok=True)
    return base


def parse_mcp_body(body: str) -> dict[str, Any]:
    text = body.strip()
    if not text:
        return {"error": {"status": 0, "message": "MCP_EMPTY_RESPONSE"}}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    event_payloads: list[dict[str, Any]] = []
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
            event_payloads.append(event)
    if event_payloads:
        for event in reversed(event_payloads):
            if "result" in event or "error" in event:
                return event
        return event_payloads[-1]
    return {"error": {"status": 0, "message": "MCP_RESPONSE_PARSE_ERROR"}}


class McpProbe:
    def __init__(self, endpoint: str, api_key: str, output_dir: Path) -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("Baselight MCP endpoint must use https")
        self.endpoint = endpoint
        self.api_key = api_key
        self.output_dir = output_dir
        self.counter = 0

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.counter += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.counter,
            "method": method,
            "params": params or {},
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - fixed HTTPS MCP endpoint.
            self.endpoint,
            data=data,
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
                timeout=30,
            ) as response:
                body = response.read().decode("utf-8", errors="replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            status = exc.code
        (self.output_dir / f"{self.counter:02d}_{method.replace('/', '_')}.json").write_text(
            body,
            encoding="utf-8",
        )
        if status >= 400:
            return {"error": {"status": status, "message": "MCP_HTTP_ERROR"}}
        return parse_mcp_body(body)


def summarize_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    required = schema.get("required")
    return {
        "type": schema.get("type"),
        "properties": sorted(properties) if isinstance(properties, dict) else [],
        "required": required if isinstance(required, list) else [],
    }


def tool_summaries(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for tool in tools:
        summaries.append(
            {
                "name": tool.get("name"),
                "description_present": bool(tool.get("description")),
                "input_schema": summarize_schema(tool.get("inputSchema")),
            }
        )
    return summaries


def detect_sql_tool(tools: list[dict[str, Any]]) -> dict[str, Any] | None:
    for tool in tools:
        if tool.get("name") == "baselight_sdk_query_execute":
            return tool
    for tool in tools:
        name = str(tool.get("name", "")).lower()
        description = str(tool.get("description", "")).lower()
        schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        property_names = " ".join(str(prop).lower() for prop in properties)
        text = " ".join([name, description, property_names])
        if "sql" in text and "execute" in text:
            return tool
    return None


def build_tool_arguments(tool: dict[str, Any], sql: str) -> dict[str, Any]:
    schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    for candidate in ("query", "sql", "statement"):
        if candidate in properties:
            return {candidate: sql}
    return {"query": sql}


def call_sql(probe: McpProbe, tool: dict[str, Any], sql: str) -> dict[str, Any]:
    response = probe.request(
        "tools/call",
        {
            "name": tool.get("name"),
            "arguments": build_tool_arguments(tool, sql),
        },
    )
    if "error" in response:
        return {
            "status": "ERROR",
            "error_type": response["error"].get("message", "MCP_TOOL_ERROR"),
            "row_count": 0,
            "schema_fields": [],
        }
    return summarize_query_response(response)


def extract_rows(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("rows", "data", "result", "records"):
            rows = value.get(key)
            if isinstance(rows, list):
                return rows
        content = value.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    try:
                        parsed = json.loads(item["text"])
                    except json.JSONDecodeError:
                        continue
                    rows = extract_rows(parsed)
                    if rows:
                        return rows
        result = value.get("result")
        if isinstance(result, dict):
            return extract_rows(result)
    return []


def summarize_query_response(response: dict[str, Any]) -> dict[str, Any]:
    rows = extract_rows(response)
    fields: list[str] = []
    if rows and isinstance(rows[0], dict):
        fields = sorted(str(key) for key in rows[0].keys())
    return {
        "status": "PASS",
        "row_count": len(rows),
        "schema_fields": fields,
    }


def write_reports(report: dict[str, Any]) -> None:
    write_json(REPORT_JSON, report)
    lines = [
        "# W2 Baselight MCP Probe",
        "",
        f"Generated at: `{report['generated_at_utc']}`",
        "",
        f"- MCP endpoint: `{report['mcp_endpoint']}`",
        f"- api_key_present: `{str(report['api_key_present']).lower()}`",
        f"- tools_discovered: `{len(report['tools_discovered'])}`",
        f"- sql_tool_detected: `{str(report['sql_tool_detected']).lower()}`",
        f"- sql_tool_name: `{report['sql_tool_name']}`",
        f"- odds_limit_query_status: `{report['odds_limit_query_status']}`",
        f"- matches_limit_query_status: `{report['matches_limit_query_status']}`",
        f"- no_full_data_download: `{str(report['no_full_data_download']).lower()}`",
        f"- no_secret_logged: `{str(report['no_secret_logged']).lower()}`",
        f"- candidate: `{str(report['candidate']).lower()}`",
        f"- formal_recommendation: `{str(report['formal_recommendation']).lower()}`",
        "",
        "Raw MCP responses, if any, are written only under `/tmp` and are not committed.",
    ]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def missing_key_report() -> dict[str, Any]:
    return {
        "schema_version": "W2_BASELIGHT_MCP_PROBE_V1",
        "generated_at_utc": utc_now(),
        "mcp_endpoint": ENDPOINT,
        "api_key_present": False,
        "status": "BASELIGHT_API_KEY_REQUIRED",
        "tools_discovered": [],
        "sql_tool_detected": False,
        "sql_tool_name": None,
        "odds_limit_query_status": "BASELIGHT_API_KEY_REQUIRED",
        "matches_limit_query_status": "BASELIGHT_API_KEY_REQUIRED",
        "query_row_counts": {
            "match_betting_odds": 0,
            "matches": 0,
        },
        "raw_response_dir": None,
        "no_full_data_download": True,
        "no_secret_logged": True,
        "candidate": False,
        "formal_recommendation": False,
    }


def live_flag_required_report(api_key_present: bool) -> dict[str, Any]:
    return {
        "schema_version": "W2_BASELIGHT_MCP_PROBE_V1",
        "generated_at_utc": utc_now(),
        "mcp_endpoint": ENDPOINT,
        "api_key_present": api_key_present,
        "status": "LIVE_FLAG_REQUIRED",
        "tools_discovered": [],
        "sql_tool_detected": False,
        "sql_tool_name": None,
        "odds_limit_query_status": "LIVE_FLAG_REQUIRED",
        "matches_limit_query_status": "LIVE_FLAG_REQUIRED",
        "query_row_counts": {
            "match_betting_odds": 0,
            "matches": 0,
        },
        "raw_response_dir": None,
        "no_full_data_download": True,
        "no_secret_logged": True,
        "candidate": False,
        "formal_recommendation": False,
    }


def live_error_report(
    status: str,
    output_dir: Path | None,
    api_key_present: bool = True,
) -> dict[str, Any]:
    return {
        "schema_version": "W2_BASELIGHT_MCP_PROBE_V1",
        "generated_at_utc": utc_now(),
        "mcp_endpoint": ENDPOINT,
        "api_key_present": api_key_present,
        "status": status,
        "tools_discovered": [],
        "sql_tool_detected": False,
        "sql_tool_name": None,
        "odds_limit_query_status": status,
        "matches_limit_query_status": status,
        "query_row_counts": {
            "match_betting_odds": 0,
            "matches": 0,
        },
        "raw_response_dir": str(output_dir) if output_dir else None,
        "no_full_data_download": True,
        "no_secret_logged": True,
        "candidate": False,
        "formal_recommendation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Allow the Baselight MCP read-only LIMIT probe to make network requests.",
    )
    args = parser.parse_args()
    api_key = os.environ.get(ENV_NAME)
    if not api_key:
        report = missing_key_report()
        write_reports(report)
        print("BASELIGHT_API_KEY_REQUIRED")
        return 2
    if not args.live:
        report = live_flag_required_report(api_key_present=True)
        write_reports(report)
        print("LIVE_FLAG_REQUIRED")
        return 2

    output_dir = raw_dir()
    probe = McpProbe(ENDPOINT, api_key, output_dir)
    try:
        initialize = probe.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "w2-baselight-mcp-probe", "version": "1"},
            },
        )
        tools_response = probe.request("tools/list")
    except (OSError, json.JSONDecodeError) as exc:
        report = live_error_report(type(exc).__name__, output_dir)
        write_reports(report)
        print(report["status"])
        return 1
    tools = []
    if isinstance(tools_response.get("result"), dict):
        maybe_tools = tools_response["result"].get("tools")
        if isinstance(maybe_tools, list):
            tools = [tool for tool in maybe_tools if isinstance(tool, dict)]
    sql_tool = detect_sql_tool(tools)

    odds_summary = {"status": "SQL_TOOL_NOT_DETECTED", "row_count": 0, "schema_fields": []}
    matches_summary = {"status": "SQL_TOOL_NOT_DETECTED", "row_count": 0, "schema_fields": []}
    if sql_tool is not None:
        odds_summary = call_sql(probe, sql_tool, ODDS_SQL)
        matches_summary = call_sql(probe, sql_tool, MATCHES_SQL)

    report = {
        "schema_version": "W2_BASELIGHT_MCP_PROBE_V1",
        "generated_at_utc": utc_now(),
        "mcp_endpoint": ENDPOINT,
        "api_key_present": True,
        "status": "PASS" if sql_tool is not None else "SQL_TOOL_NOT_DETECTED",
        "initialize_status": "ERROR" if "error" in initialize else "PASS",
        "tools_discovered": tool_summaries(tools),
        "sql_tool_detected": sql_tool is not None,
        "sql_tool_name": sql_tool.get("name") if sql_tool else None,
        "odds_limit_query_status": odds_summary["status"],
        "matches_limit_query_status": matches_summary["status"],
        "query_row_counts": {
            "match_betting_odds": odds_summary["row_count"],
            "matches": matches_summary["row_count"],
        },
        "query_schema_fields": {
            "match_betting_odds": odds_summary["schema_fields"],
            "matches": matches_summary["schema_fields"],
        },
        "raw_response_dir": str(output_dir),
        "no_full_data_download": True,
        "no_secret_logged": True,
        "candidate": False,
        "formal_recommendation": False,
    }
    write_reports(report)
    print(report["status"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
