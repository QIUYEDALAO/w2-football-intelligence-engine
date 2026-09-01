#!/usr/bin/env python3
"""Fetch sanitized historical fixture xG for the frozen V1 blind test."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from w2.providers.api_football import ApiFootballClient


def _numeric_xg(payload: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in payload.get("response") or []:
        team_id = str((row.get("team") or {}).get("id") or "")
        for item in row.get("statistics") or []:
            label = str(item.get("type") or "").strip().lower().replace(" ", "_")
            if label != "expected_goals":
                continue
            try:
                result[team_id] = float(item.get("value"))
            except (TypeError, ValueError):
                pass
    return result


def _append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def _completed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        str(json.loads(line)["fixture_id"])
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def fetch(args: argparse.Namespace) -> dict[str, int]:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    fixtures = [
        row
        for competition in manifest["competitions"].values()
        for row in competition["fixtures"]
        if row["status"] in {"FT", "AET", "PEN"}
    ]
    fixtures.sort(key=lambda row: (row["kickoff_at"], row["fixture_id"]))
    done = _completed(args.output)
    calls = 0
    complete = missing = 0
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"statistics"}),
    )
    for fixture in fixtures:
        fixture_id = fixture["fixture_id"]
        if fixture_id in done:
            continue
        if args.task_calls_already_used + calls >= args.task_call_limit or calls >= args.max_calls:
            break
        response = client.request_live("statistics", {"fixture": fixture_id})
        calls += 1
        remaining = response.headers.get("x-ratelimit-requests-remaining")
        if response.status_code != 200:
            raise RuntimeError(f"statistics HTTP {response.status_code} for fixture {fixture_id}")
        values = _numeric_xg(response.payload)
        expected = {fixture["home_team_id"], fixture["away_team_id"]}
        status = "COMPLETE" if set(values) == expected else "MISSING_XG"
        complete += status == "COMPLETE"
        missing += status == "MISSING_XG"
        _append(
            args.output,
            {
                "fixture_id": fixture_id,
                "kickoff_at": fixture["kickoff_at"],
                "competition": fixture["competition"],
                "season": fixture["season"],
                "home_team_id": fixture["home_team_id"],
                "away_team_id": fixture["away_team_id"],
                "home_xg": values.get(fixture["home_team_id"]),
                "away_xg": values.get(fixture["away_team_id"]),
                "status": status,
                "http_status": response.status_code,
                "captured_at": response.captured_at.isoformat(),
                "source_payload_sha256": hashlib.sha256(
                    json.dumps(
                        response.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest(),
            },
        )
        if remaining is not None and int(remaining) <= args.provider_remaining_floor:
            break
        if calls % 25 == 0:
            print(json.dumps({"calls": calls, "complete": complete, "missing": missing, "remaining": remaining}), flush=True)
        time.sleep(args.pause_seconds)
    return {"calls": calls, "complete": complete, "missing": missing, "already_present": len(done)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-calls-already-used", type=int, required=True)
    parser.add_argument("--task-call-limit", type=int, default=6000)
    parser.add_argument("--max-calls", type=int, default=6000)
    parser.add_argument("--provider-remaining-floor", type=int, default=1500)
    parser.add_argument("--pause-seconds", type=float, default=0.25)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(fetch(args), sort_keys=True))


if __name__ == "__main__":
    main()
