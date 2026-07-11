from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.features.xg_materialization import (
    TeamXgMatch,
    TeamXgRollingSnapshot,
    materialize_rolling_xg,
    parse_team_xg_matches,
)


@dataclass(frozen=True, kw_only=True)
class OfflineFeatureMaterialization:
    target_fixture_ids: tuple[str, ...]
    matches: tuple[TeamXgMatch, ...]
    snapshots: tuple[TeamXgRollingSnapshot, ...]
    blockers: tuple[str, ...]
    input_context: dict[str, Any]

    def summary(self) -> dict[str, Any]:
        return {
            "target_fixture_count": len(self.target_fixture_ids),
            "target_fixture_ids": list(self.target_fixture_ids),
            "team_xg_match_count": len(self.matches),
            "rolling_snapshot_count": len(self.snapshots),
            "ready_fixture_count": len({row.as_of_fixture_id for row in self.snapshots}),
            "blockers": list(self.blockers),
            "target_team_coverage": _target_team_coverage(self.snapshots),
            "provider_calls": 0,
            "db_reads": 0,
            "db_writes": 0,
        }

    def payload(self) -> dict[str, Any]:
        content = {
            "schema_version": "w2.offline_feature_materialization.v2",
            "summary": self.summary(),
            "input_context": self.input_context,
            "team_xg_matches": [_match_payload(row) for row in self.matches],
            "team_xg_rolling_snapshots": [_snapshot_payload(row) for row in self.snapshots],
        }
        content_hash = _canonical_hash(content)
        return {
            **content,
            "integrity": {
                "content_hash": content_hash,
                "materialization_id": f"w2mat_{content_hash}",
            },
        }


def materialize_from_pro_cache(
    *,
    raw_root: Path,
    target_fixture_ids: tuple[str, ...],
    target_fixture_file: Path | None = None,
    window: int = 8,
    min_matches: int = 5,
) -> OfflineFeatureMaterialization:
    history_fixtures = _fixture_payloads(raw_root / "fixtures")
    target_fixtures = (
        _fixture_payloads_from_file(target_fixture_file)
        if target_fixture_file is not None
        else history_fixtures
    )
    targets = [
        target_fixtures[fixture_id]
        for fixture_id in target_fixture_ids
        if fixture_id in target_fixtures
    ]
    target_teams = {
        str(team.get("id") or "")
        for item in targets
        for team in _teams(item)
        if str(team.get("id") or "")
    }
    matches: dict[str, TeamXgMatch] = {}
    for path in sorted((raw_root / "statistics").glob("*.json")):
        wrapper = _json(path)
        fixture_id = str(_mapping(wrapper.get("params")).get("fixture") or "")
        fixture = history_fixtures.get(fixture_id)
        if fixture is None:
            continue
        captured_at = _parse_utc(wrapper.get("captured_at"))
        statistics = wrapper.get("payload")
        if captured_at is None or not isinstance(statistics, dict):
            continue
        for row in parse_team_xg_matches(
            fixture_payload=fixture,
            statistics_payload=statistics,
            captured_at=captured_at,
            raw_payload_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        ):
            if row.team_id in target_teams:
                matches[row.id] = row
    ordered_matches = sorted(matches.values(), key=lambda row: (row.kickoff_at, row.id))
    snapshots: list[TeamXgRollingSnapshot] = []
    blockers: list[str] = []
    missing_targets = sorted(set(target_fixture_ids) - set(target_fixtures))
    blockers.extend(f"TARGET_FIXTURE_NOT_CACHED:{fixture_id}" for fixture_id in missing_targets)
    for item in targets:
        fixture = _mapping(item.get("fixture"))
        fixture_id = str(fixture.get("id") or "")
        kickoff = _parse_utc(fixture.get("date"))
        if not fixture_id or kickoff is None:
            blockers.append(f"TARGET_FIXTURE_INVALID:{fixture_id or 'UNKNOWN'}")
            continue
        for team in _teams(item):
            team_id = str(team.get("id") or "")
            snapshot = materialize_rolling_xg(
                team_id=team_id,
                as_of_fixture_id=fixture_id,
                as_of_time=kickoff,
                matches=ordered_matches,
                window=window,
                min_matches=min_matches,
            )
            if snapshot is None:
                blockers.append(f"FEATURE_HISTORY_INSUFFICIENT:{fixture_id}:{team_id}")
            else:
                snapshots.append(snapshot)
    return OfflineFeatureMaterialization(
        target_fixture_ids=tuple(sorted(set(target_fixture_ids))),
        matches=tuple(ordered_matches),
        snapshots=tuple(sorted(snapshots, key=lambda row: row.snapshot_id)),
        blockers=tuple(sorted(blockers)),
        input_context={
            "history_cache_hash": _directory_hash(raw_root),
            "target_fixture_hash": (
                hashlib.sha256(target_fixture_file.read_bytes()).hexdigest()
                if target_fixture_file is not None
                else _directory_hash(raw_root / "fixtures")
            ),
            "window": window,
            "min_matches": min_matches,
        },
    )


def _fixture_payloads(root: Path) -> dict[str, dict[str, Any]]:
    fixtures: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        wrapper = _json(path)
        payload = _mapping(wrapper.get("payload"))
        response = payload.get("response")
        if not isinstance(response, list):
            continue
        for item in response:
            if not isinstance(item, dict):
                continue
            fixture_id = str(_mapping(item.get("fixture")).get("id") or "")
            if fixture_id:
                fixtures[fixture_id] = item
    return fixtures


def _fixture_payloads_from_file(path: Path) -> dict[str, dict[str, Any]]:
    payload = _json(path)
    rows = payload.get("fixtures")
    if not isinstance(rows, list):
        rows = _mapping(payload.get("payload")).get("response")
    if not isinstance(rows, list):
        rows = payload.get("response")
    fixtures: dict[str, dict[str, Any]] = {}
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        fixture_id = str(_mapping(item.get("fixture")).get("id") or item.get("fixture_id") or "")
        if "fixture" not in item and fixture_id:
            item = {
                "fixture": {"id": fixture_id, "date": item.get("kickoff_utc")},
                "league": {"id": item.get("competition_id")},
                "teams": {
                    "home": {"id": item.get("home_team_id")},
                    "away": {"id": item.get("away_team_id")},
                },
            }
        if fixture_id:
            fixtures[fixture_id] = item
    return fixtures


def verify_materialization_payload(payload: dict[str, Any]) -> bool:
    integrity = _mapping(payload.get("integrity"))
    content_hash = str(integrity.get("content_hash") or "")
    if not content_hash or integrity.get("materialization_id") != f"w2mat_{content_hash}":
        return False
    content = {key: value for key, value in payload.items() if key != "integrity"}
    return _canonical_hash(content) == content_hash


def sanitized_target_fixture_payload(
    fixtures: list[dict[str, Any]],
    *,
    kickoff_from: datetime,
    kickoff_to: datetime,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in fixtures:
        fixture = _mapping(item.get("fixture"))
        kickoff = _parse_utc(fixture.get("date"))
        teams = _mapping(item.get("teams"))
        league = _mapping(item.get("league"))
        if kickoff is None or not kickoff_from <= kickoff < kickoff_to:
            continue
        rows.append(
            {
                "fixture_id": str(fixture.get("id") or ""),
                "kickoff_utc": _iso(kickoff),
                "competition_id": str(league.get("id") or ""),
                "home_team_id": str(_mapping(teams.get("home")).get("id") or ""),
                "away_team_id": str(_mapping(teams.get("away")).get("id") or ""),
            }
        )
    rows.sort(key=lambda row: (row["kickoff_utc"], row["fixture_id"]))
    content = {"schema_version": "w2.sanitized_target_fixtures.v1", "fixtures": rows}
    return {**content, "content_hash": _canonical_hash(content)}


def _target_team_coverage(
    snapshots: tuple[TeamXgRollingSnapshot, ...],
) -> dict[str, list[str]]:
    coverage: dict[str, list[str]] = {}
    for row in snapshots:
        coverage.setdefault(row.as_of_fixture_id, []).append(row.team_id)
    return {key: sorted(value) for key, value in sorted(coverage.items())}


def _directory_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*.json") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _teams(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    teams = _mapping(item.get("teams"))
    return (_mapping(teams.get("home")), _mapping(teams.get("away")))


def _match_payload(row: TeamXgMatch) -> dict[str, Any]:
    return {
        "id": row.id,
        "fixture_id": row.fixture_id,
        "team_id": row.team_id,
        "opponent_team_id": row.opponent_team_id,
        "kickoff_at": _iso(row.kickoff_at),
        "captured_at": _iso(row.captured_at),
        "xg_for": row.xg_for,
        "xg_against": row.xg_against,
        "goals_for": row.goals_for,
        "goals_against": row.goals_against,
        "raw_payload_sha256": row.raw_payload_sha256,
        "source_system": row.source_system,
        "candidate": False,
        "formal_recommendation": False,
    }


def _snapshot_payload(row: TeamXgRollingSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": row.snapshot_id,
        "team_id": row.team_id,
        "as_of_fixture_id": row.as_of_fixture_id,
        "as_of_time": _iso(row.as_of_time),
        "match_count": row.match_count,
        "rolling_xg_for": row.rolling_xg_for,
        "rolling_xg_against": row.rolling_xg_against,
        "rolling_goals_for": row.rolling_goals_for,
        "rolling_goals_against": row.rolling_goals_against,
        "regression_index": row.regression_index,
        "source_system": row.source_system,
        "candidate": False,
        "formal_recommendation": False,
    }


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
