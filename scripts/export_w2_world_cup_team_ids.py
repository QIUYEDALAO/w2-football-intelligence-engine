from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class TeamSeen:
    team_id: str
    team_name: str
    fixture_ids: set[str]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def default_fixture_paths(root: Path = ROOT) -> list[Path]:
    candidates: list[Path] = []
    for pattern in (
        "runtime/stage7*/raw/*fixtures*.json",
        "runtime/independent_signal_backfill/raw_payloads/fixtures/*.json",
        "runtime/stage5b/raw/*fixtures*.json",
    ):
        candidates.extend(sorted(root.glob(pattern)))
    return [path for path in candidates if path.is_file()]


def fixture_rows(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield from fixture_rows(item)
        return
    if not isinstance(payload, dict):
        return
    if _is_fixture_row(payload):
        yield payload
    for key in ("payload", "response", "items", "fixtures", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list | dict):
            yield from fixture_rows(value)


def collect_team_ids(
    paths: Iterable[Path],
    *,
    competition_id: str,
) -> dict[str, TeamSeen]:
    teams: dict[str, TeamSeen] = {}
    for path in paths:
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        for row in fixture_rows(payload):
            if not _competition_matches(row, competition_id=competition_id):
                continue
            fixture_id = _fixture_id(row)
            for side in ("home", "away"):
                teams_payload = row.get("teams")
                team = teams_payload.get(side) if isinstance(teams_payload, dict) else None
                if not isinstance(team, dict):
                    continue
                team_id = str(team.get("id") or "")
                team_name = str(team.get("name") or "").strip()
                if not team_id or not team_name:
                    continue
                current = teams.setdefault(
                    team_id,
                    TeamSeen(team_id=team_id, team_name=team_name, fixture_ids=set()),
                )
                current.fixture_ids.add(fixture_id)
                if len(team_name) > len(current.team_name):
                    current.team_name = team_name
    return teams


def write_csv(path: Path, teams: dict[str, TeamSeen]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["team_id", "team_name", "seen_fixture_count", "example_fixture_id"],
        )
        writer.writeheader()
        for item in sorted(teams.values(), key=lambda row: (row.team_name.lower(), row.team_id)):
            writer.writerow(
                {
                    "team_id": item.team_id,
                    "team_name": item.team_name,
                    "seen_fixture_count": len(item.fixture_ids),
                    "example_fixture_id": sorted(item.fixture_ids)[0] if item.fixture_ids else "",
                }
            )


def _is_fixture_row(row: dict[str, Any]) -> bool:
    teams = row.get("teams")
    fixture = row.get("fixture")
    return isinstance(teams, dict) and isinstance(fixture, dict)


def _fixture_id(row: dict[str, Any]) -> str:
    raw_fixture = row.get("fixture")
    fixture = raw_fixture if isinstance(raw_fixture, dict) else {}
    return str(fixture.get("id") or row.get("fixture_id") or "")


def _competition_matches(row: dict[str, Any], *, competition_id: str) -> bool:
    raw_league = row.get("league")
    league = raw_league if isinstance(raw_league, dict) else {}
    league_id = str(league.get("id") or "")
    league_name = str(league.get("name") or "")
    if competition_id == "world_cup_2026":
        return league_id == "1" or league_name.lower() == "world cup"
    return competition_id in {league_id, league_name}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export local API-Football World Cup team ids for reviewed value mapping.",
    )
    parser.add_argument("--competition-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--input",
        action="append",
        type=Path,
        default=[],
        help="Optional fixture payload JSON path. Defaults to local runtime fixture artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = args.input or default_fixture_paths()
    teams = collect_team_ids(paths, competition_id=str(args.competition_id))
    if not teams:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "NO_TEAM_IDS_FOUND",
                    "searched_files": len(paths),
                    "competition_id": args.competition_id,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    write_csv(args.output, teams)
    print(
        json.dumps(
            {
                "ok": True,
                "team_count": len(teams),
                "output": str(args.output),
                "searched_files": len(paths),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
