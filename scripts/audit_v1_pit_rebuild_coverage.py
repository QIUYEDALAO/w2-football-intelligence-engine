#!/usr/bin/env python3
"""Check that the claimed A1 rebuild fixtures have enough prior PIT xG rows."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def audit(a1_path: Path, home_away_path: Path, xg_path: Path) -> dict[str, object]:
    a1 = json.loads(a1_path.read_text(encoding="utf-8"))
    home_away = {
        row["fixture_id"]: row
        for row in csv.DictReader(home_away_path.open(newline="", encoding="utf-8"))
    }
    xg_by_team: dict[str, list[dict[str, str]]] = {}
    for row in csv.DictReader(xg_path.open(newline="", encoding="utf-8")):
        xg_by_team.setdefault(row["team_id"], []).append(row)
    missing: list[dict[str, object]] = []
    rebuild = [row for row in a1["fixtures"] if row["input_path"] == "rebuild"]
    for fixture in rebuild:
        fixture_id = str(fixture["provider_fixture_id"])
        identity = home_away[fixture_id]
        kickoff = _time(fixture["kickoff_at"])
        counts = {
            side: sum(
                _time(row["kickoff_at"]) < kickoff
                for row in xg_by_team.get(identity[key], [])
            )
            for side, key in (("home", "home_id"), ("away", "away_id"))
        }
        if min(counts.values()) < 5:
            missing.append({"fixture_id": fixture_id, "counts": counts})
    return {
        "schema": "w2.v1.a1_pit_rebuild_coverage_audit.v1",
        "claimed_rebuild_count": len(rebuild),
        "fixtures_with_both_teams_at_least_five_prior_rows": len(rebuild) - len(missing),
        "insufficient_fixture_count": len(missing),
        "insufficient_fixtures": missing,
        "strictly_pre_kickoff": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a1", type=Path, required=True)
    parser.add_argument("--home-away", type=Path, required=True)
    parser.add_argument("--xg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = audit(args.a1, args.home_away, args.xg)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: payload[k] for k in payload if k.endswith("count") or k.endswith("counts")}
        )
    )


if __name__ == "__main__":
    main()
