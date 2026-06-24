#!/usr/bin/env python3
# ruff: noqa: S608
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path(
    "/Users/liudehua/.openclaw/workspace/"
    "w2_external_data/baselight_gate3_limited_ah/baselight_limited_ah.jsonl"
)
DEFAULT_STATE = DEFAULT_OUTPUT.parent / "extract_state.json"
DEFAULT_REPORTS = ROOT / "reports"
EXTRACTION_METHOD = "ODDS_DATE_WINDOW_V3_RANKED_BOOKMAKER_CAP_THEN_MATCHES_METADATA_NO_JOIN"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def derive_resume_start_date(
    state: dict[str, Any], requested_start_date: str | None, today: datetime | None = None
) -> str:
    if requested_start_date:
        return requested_start_date
    records = state.get("date_windows")
    windows = (
        [item for item in records if isinstance(item, dict)]
        if isinstance(records, list)
        else []
    )
    pending_ends: list[datetime] = []
    starts: list[datetime] = []
    for record in windows:
        start = record.get("window_start_utc")
        end = record.get("window_end_utc")
        try:
            if start:
                starts.append(parse_utc(str(start)))
            if end and str(record.get("status", "")).upper() in {"PENDING_OR_FAILED", "STARTED"}:
                pending_ends.append(parse_utc(str(end)))
        except ValueError:
            continue
    if pending_ends:
        return max(pending_ends).date().isoformat()
    if starts:
        return min(starts).date().isoformat()
    current = today or datetime.now(UTC)
    return current.date().isoformat()


def sql_timestamp(value: datetime) -> str:
    return value.strftime("TIMESTAMP '%Y-%m-%d %H:%M:%S'")


def build_ranked_odds_window_sql(
    start: datetime,
    end: datetime,
    limit: int,
    rows_per_bookmaker: int = 2,
) -> str:
    safe_limit = max(1, min(limit, 5000))
    safe_cap = max(1, min(rows_per_bookmaker, 10))
    return f"""
WITH bookmaker_ranked AS (
    SELECT
        match_id,
        bookmaker,
        market,
        outcome,
        odds,
        odds_type,
        collected_at,
        ROW_NUMBER() OVER (
            PARTITION BY match_id, bookmaker
            ORDER BY outcome, collected_at, odds
        ) AS bookmaker_row_rank
    FROM "@blt.ultimate_soccer_dataset.match_betting_odds"
    WHERE
        collected_at >= {sql_timestamp(start)}
        AND collected_at < {sql_timestamp(end)}
        AND market = 'Asian Handicap'
        AND odds_type = 'pre_match'
        AND odds > 1
        AND regexp_matches(CAST(outcome AS VARCHAR), '[+-]?[0-9]+(\\.[0-9]+)?')
)
SELECT
    match_id,
    bookmaker,
    market,
    outcome,
    odds,
    odds_type,
    collected_at
FROM bookmaker_ranked
WHERE bookmaker_row_rank <= {safe_cap}
ORDER BY match_id, bookmaker, outcome, collected_at, odds
LIMIT {safe_limit}
""".strip()


def load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"SCRIPT_IMPORT_FAILED:{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def patch_reports(
    reports_dir: Path,
    output: Path,
    state_file: Path,
    target_fixtures: int,
    rows_per_bookmaker: int,
    date_window_days: int,
) -> str:
    manifest_path = reports_dir / "W2_GATE3_BASELIGHT_LIMITED_AH_EXTRACT_MANIFEST.json"
    walk_path = reports_dir / "W2_GATE3_BASELIGHT_AH_WALK_FORWARD.json"
    result_path = reports_dir / "W2_GATE3_BASELIGHT_AH_WALK_FORWARD_RESULT.md"
    summary_path = reports_dir / "W2_GATE3_BASELIGHT_ODDS_DATE_WINDOW_V3_RUN.json"
    manifest = read_json(manifest_path)
    walk = read_json(walk_path)
    state = read_json(state_file)
    status = str(walk.get("status", "INSUFFICIENT_SAMPLE"))
    reached = status == "PASS_LIMITED_WALK_FORWARD" and int(
        manifest.get("fixture_count", 0)
    ) >= target_fixtures
    extract_status = (
        "ODDS_DATE_WINDOW_V3_RESUME_TARGET_REACHED"
        if reached
        else "ODDS_DATE_WINDOW_PARTIAL_SAMPLE_INSUFFICIENT"
    )
    generated_at = utc_now()
    manifest.update(
        {
            "generated_at_utc": generated_at,
            "sample_path_external": str(output),
            "state_file_external": str(state_file),
            "extraction_method": EXTRACTION_METHOD,
            "extraction_attempt_status": extract_status,
            "micro_batch_v3_status": extract_status,
            "target_fixture_count": target_fixtures,
            "rows_per_bookmaker_cap": rows_per_bookmaker,
            "date_window_days": date_window_days,
            "large_sample_committed": False,
            "candidate": False,
            "formal_recommendation": False,
        }
    )
    walk.update(
        {
            "generated_at_utc": generated_at,
            "sample_path_external": str(output),
            "sample_sha256": manifest.get("sample_sha256"),
            "extraction_method": EXTRACTION_METHOD,
            "limited_extract_status": extract_status,
            "micro_batch_v3_status": extract_status,
            "gate3_status": "PARTIAL",
            "gate5_status": "OPEN",
            "candidate": False,
            "formal_recommendation": False,
        }
    )
    blocker = "BASELIGHT_ODDS_DATE_WINDOW_PARTIAL_SAMPLE_INSUFFICIENT"
    blockers = walk.setdefault("blockers", [])
    if not reached and isinstance(blockers, list) and blocker not in blockers:
        blockers.append(blocker)
    if reached and isinstance(blockers, list) and blocker in blockers:
        blockers.remove(blocker)
    final_stats = state.get("final_stats") if isinstance(state.get("final_stats"), dict) else {}
    summary = {
        "schema_version": "W2_GATE3_BASELIGHT_ODDS_DATE_WINDOW_V3_RUN_V1",
        "generated_at_utc": generated_at,
        "extraction_method": EXTRACTION_METHOD,
        "extraction_status": extract_status,
        "walk_forward_status": status,
        "sample_sha256": manifest.get("sample_sha256"),
        "row_count": manifest.get("row_count", final_stats.get("row_count", 0)),
        "fixture_count": manifest.get("fixture_count", final_stats.get("fixture_count", 0)),
        "bookmaker_count": manifest.get("bookmaker_count", final_stats.get("bookmaker_count", 0)),
        "line_bucket_count": manifest.get(
            "line_bucket_count", final_stats.get("line_bucket_count", 0)
        ),
        "competition_count": manifest.get("competition_count", 0),
        "fold_count": walk.get("fold_count", 0),
        "new_rows_written": state.get("new_rows_written", 0),
        "new_fixtures_written": state.get("new_fixtures_written", 0),
        "gate3": "PARTIAL",
        "gate5": "OPEN",
        "candidate": False,
        "formal_recommendation": False,
        "large_sample_committed": False,
    }
    write_json(manifest_path, manifest)
    write_json(walk_path, walk)
    write_json(summary_path, summary)
    result = [
        "# W2 Gate3 Baselight AH Walk-Forward Result",
        "",
        f"Generated at: `{generated_at}`",
        "",
        f"STATUS={status}",
        f"EXTRACTION_METHOD={EXTRACTION_METHOD}",
        f"EXTRACTION_STATUS={extract_status}",
        f"SAMPLE_PATH={output}",
        f"SAMPLE_SHA256={manifest.get('sample_sha256')}",
        f"ROW_COUNT={summary['row_count']}",
        f"FIXTURE_COUNT={summary['fixture_count']}",
        f"BOOKMAKER_COUNT={summary['bookmaker_count']}",
        f"LINE_BUCKET_COUNT={summary['line_bucket_count']}",
        f"COMPETITION_COUNT={summary['competition_count']}",
        f"FOLD_COUNT={summary['fold_count']}",
        "Gate3=PARTIAL",
        "Gate5=OPEN",
        "candidate=false",
        "formal_recommendation=false",
        "",
        "Large sample data is not committed. DATE-only and export/retention limits remain.",
        "No Stage7I recovery, deployment, restart, W1 mutation, or `.env` read was performed.",
    ]
    result_path.write_text("\n".join(result) + "\n", encoding="utf-8")
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--target-fixtures", type=int, default=500)
    parser.add_argument("--max-rows", type=int, default=250000)
    parser.add_argument("--query-limit", type=int, default=5000)
    parser.add_argument("--rows-per-bookmaker", type=int, default=2)
    parser.add_argument("--metadata-batch-size", type=int, default=100)
    parser.add_argument("--date-window-days", type=int, default=7)
    parser.add_argument("--max-date-windows", type=int, default=120)
    parser.add_argument("--start-date")
    parser.add_argument("--per-query-timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    if not args.live:
        print("LIVE_FLAG_REQUIRED")
        return 2
    if not os.environ.get("BASELIGHT_API_KEY"):
        print("BASELIGHT_API_KEY_REQUIRED")
        return 2

    base = load_script(
        "w2_baselight_extract_base", ROOT / "scripts/extract_w2_gate3_baselight_limited_ah.py"
    )
    runner = load_script(
        "w2_baselight_walk_forward", ROOT / "scripts/run_w2_gate3_baselight_ah_walk_forward.py"
    )
    state = read_json(args.state_file) if args.resume else {}
    start_date = derive_resume_start_date(state, args.start_date)

    def ranked_builder(start: datetime, end: datetime, limit: int) -> str:
        return build_ranked_odds_window_sql(
            start,
            end,
            limit,
            rows_per_bookmaker=args.rows_per_bookmaker,
        )

    base.build_odds_date_window_sql = ranked_builder
    previous_argv = sys.argv
    try:
        sys.argv = [
            str(ROOT / "scripts/extract_w2_gate3_baselight_limited_ah.py"),
            "--live",
            "--strategy",
            "odds_date_window",
            "--output",
            str(args.output),
            "--state-file",
            str(args.state_file),
            "--target-fixtures",
            str(args.target_fixtures),
            "--max-rows",
            str(args.max_rows),
            "--page-size",
            str(args.query_limit),
            "--fixture-batch-size",
            str(args.metadata_batch_size),
            "--date-window-days",
            str(args.date_window_days),
            "--max-date-windows",
            str(args.max_date_windows),
            "--start-date",
            start_date,
            "--per-query-timeout-seconds",
            str(args.per_query_timeout_seconds),
        ]
        if args.resume:
            sys.argv.append("--resume")
        extract_exit = int(base.main())
    finally:
        sys.argv = previous_argv
    if extract_exit not in {0, 3}:
        return extract_exit

    args.reports_dir.mkdir(parents=True, exist_ok=True)
    runner.MANIFEST_PATH = args.reports_dir / "W2_GATE3_BASELIGHT_LIMITED_AH_EXTRACT_MANIFEST.json"
    runner.WALK_FORWARD_PATH = args.reports_dir / "W2_GATE3_BASELIGHT_AH_WALK_FORWARD.json"
    runner.RESULT_PATH = args.reports_dir / "W2_GATE3_BASELIGHT_AH_WALK_FORWARD_RESULT.md"
    runner.write_reports(args.output if args.output.is_file() else None)
    status = patch_reports(
        args.reports_dir,
        args.output,
        args.state_file,
        args.target_fixtures,
        args.rows_per_bookmaker,
        args.date_window_days,
    )
    print(f"BASELIGHT_ODDS_DATE_WINDOW_V3_RESUME_COMPLETE status={status}")
    return 0 if status == "PASS_LIMITED_WALK_FORWARD" else 3


if __name__ == "__main__":
    raise SystemExit(main())
