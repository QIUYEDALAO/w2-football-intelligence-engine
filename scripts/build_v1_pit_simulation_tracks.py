#!/usr/bin/env python3
"""Build X/Y/Z V1 simulation tracks from strictly pre-kickoff xG inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from w2.strategy.simulate import _exact_score_matrix_with_uncertainty


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mean(rows: list[dict[str, str]], field: str) -> float:
    return sum(float(row[field]) for row in rows) / len(rows)


def _lambdas(
    values: dict[str, float], *, home_advantage: float, scale: float
) -> tuple[float, float]:
    base_home = (values["home_xg_for"] + values["away_xg_against"]) / 2.0
    base_away = (values["away_xg_for"] + values["home_xg_against"]) / 2.0
    total = min(max(base_home + base_away, 1.35), 4.4)
    delta = scale * (base_home - base_away) + home_advantage
    return (
        round(min(max((total + delta) / 2.0, 0.15), 4.25), 6),
        round(min(max((total - delta) / 2.0, 0.15), 4.25), 6),
    )


def _track(
    fixture_id: str,
    input_path: str,
    values: dict[str, float],
    *,
    name: str,
    home_advantage: float,
    scale: float,
) -> dict[str, Any]:
    home, away = _lambdas(values, home_advantage=home_advantage, scale=scale)
    matrix = _exact_score_matrix_with_uncertainty(
        home, away, sigma_home=0.0, sigma_away=0.0, rho=0.0, max_goals=12
    )
    return {
        "track": name,
        "home_advantage_goals": home_advantage,
        "raw_delta_scale": scale,
        "fixture_id": fixture_id,
        "input_path": input_path,
        "status": "READY",
        "lambda_home": home,
        "lambda_away": away,
        "score_matrix_summary": {
            "distribution": [
                {"home_goals": h, "away_goals": a, "probability": round(p, 12)}
                for (h, a), p in sorted(matrix.items())
            ]
        },
        "xg_inputs": values,
    }


def build(
    a1_path: Path,
    home_away_path: Path,
    xg_path: Path,
    snapshot_path: Path,
    scale: float,
) -> dict[str, Any]:
    a1 = json.loads(a1_path.read_text(encoding="utf-8"))
    identities = {
        row["fixture_id"]: row
        for row in csv.DictReader(home_away_path.open(newline="", encoding="utf-8"))
    }
    histories: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in csv.DictReader(xg_path.open(newline="", encoding="utf-8")):
        histories[row["team_id"]].append(row)
    for rows in histories.values():
        rows.sort(key=lambda row: (row["kickoff_at"], row["fixture_id"]))
    snapshots: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in csv.DictReader(snapshot_path.open(newline="", encoding="utf-8")):
        snapshots[(row["as_of_fixture_id"], row["team_id"])].append(row)

    tracks = []
    counts: dict[str, int] = defaultdict(int)
    excluded: list[dict[str, Any]] = []
    for fixture in a1["fixtures"]:
        fixture_id = str(fixture["provider_fixture_id"])
        kickoff = _time(fixture["kickoff_at"])
        identity = identities[fixture_id]
        side_values: dict[str, tuple[float, float]] = {}
        exclusion: str | None = None
        for side, team_key in (("home", "home_id"), ("away", "away_id")):
            team_id = identity[team_key]
            if fixture["input_path"] == "snapshot":
                eligible = [
                    row
                    for row in snapshots[(fixture_id, team_id)]
                    if _time(row["as_of_time"]) <= kickoff and int(row["match_count"]) >= 3
                ]
                if not eligible:
                    exclusion = f"{side.upper()}_PIT_SNAPSHOT_MISSING"
                    break
                row = max(eligible, key=lambda item: item["as_of_time"])
                side_values[side] = (
                    float(row["rolling_xg_for"]),
                    float(row["rolling_xg_against"]),
                )
            else:
                eligible = [row for row in histories[team_id] if _time(row["kickoff_at"]) < kickoff]
                if len(eligible) < 5:
                    exclusion = f"{side.upper()}_PRIOR_XG_LT_5"
                    break
                latest = eligible[-5:]
                side_values[side] = (_mean(latest, "xg_for"), _mean(latest, "xg_against"))
        if exclusion:
            excluded.append({"fixture_id": fixture_id, "reason": exclusion})
            continue
        values = {
            "home_xg_for": side_values["home"][0],
            "home_xg_against": side_values["home"][1],
            "away_xg_for": side_values["away"][0],
            "away_xg_against": side_values["away"][1],
        }
        counts[fixture["input_path"]] += 1
        tracks.extend(
            _track(
                fixture_id,
                fixture["input_path"],
                values,
                name=name,
                home_advantage=advantage,
                scale=track_scale,
            )
            for name, advantage, track_scale in (
                ("X", 0.12, 1.0),
                ("Y", 0.30, 1.0),
                ("Z", 0.30, scale),
            )
        )
    if counts != {"snapshot": 178, "rebuild": 81} or len(excluded) != 24:
        raise ValueError(f"unexpected input split: {dict(counts)}")
    return {
        "schema": "w2.v1_recalibration.pit_simulation_tracks.v2",
        "source": {
            "a1_sha256": _sha256(a1_path),
            "home_away_sha256": _sha256(home_away_path),
            "xg_sha256": _sha256(xg_path),
            "snapshot_sha256": _sha256(snapshot_path),
        },
        "strictly_pre_kickoff": True,
        "input_counts": dict(counts),
        "excluded": excluded,
        "tracks": tracks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a1", type=Path, required=True)
    parser.add_argument("--home-away", type=Path, required=True)
    parser.add_argument("--xg", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--raw-delta-scale", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.a1, args.home_away, args.xg, args.snapshot, args.raw_delta_scale)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"input_counts": payload["input_counts"], "tracks": len(payload["tracks"])}))


if __name__ == "__main__":
    main()
