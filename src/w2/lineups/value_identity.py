from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from w2.historical.formal_ah import (
    TEAM_IDENTITY_CROSSWALK_SCHEMA,
    TEAM_VALUE_ASOF_ARTIFACT_SCHEMA,
    parse_utc,
    stable_hash,
)


@dataclass(frozen=True, kw_only=True)
class TeamIdentityCrosswalkV1:
    api_football_team_id: str
    transfermarkt_club_id: str
    competition_id: str
    valid_from: str
    valid_to: str | None
    source_refs: list[str]
    source_sha256: str
    evidence: dict[str, Any]
    reviewed_by: str | None
    reviewed_at: str | None
    review_status: str
    crosswalk_hash: str
    schema_version: str = TEAM_IDENTITY_CROSSWALK_SCHEMA

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class PlayerIdentityCrosswalkV1:
    api_football_player_id: str
    transfermarkt_player_id: str | None
    api_football_team_id: str
    transfermarkt_club_id: str | None
    competition_id: str
    valid_from: str
    valid_to: str | None
    source_sha256: str
    evidence: dict[str, Any]
    reviewed_by: str | None
    reviewed_at: str | None
    review_status: str
    crosswalk_hash: str
    schema_version: str = "w2.player_identity_crosswalk.v1"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_team_crosswalk(row: Mapping[str, Any]) -> TeamIdentityCrosswalkV1:
    requested_status = str(row.get("review_status") or "REVIEW_REQUIRED")
    source_sha = str(row.get("source_sha256") or "")
    reviewed_by = _optional_text(row.get("reviewed_by"))
    reviewed_at = _optional_text(row.get("reviewed_at"))
    evidence = _dict(row.get("evidence"))
    valid_from = str(row.get("valid_from") or "")
    if requested_status == "APPROVED" and (
        len(source_sha) != 64
        or not reviewed_by
        or not reviewed_at
        or not evidence
        or parse_utc(valid_from) is None
    ):
        requested_status = "REVIEW_REQUIRED"
    payload: dict[str, Any] = {
        "api_football_team_id": str(row.get("api_football_team_id") or ""),
        "transfermarkt_club_id": str(row.get("transfermarkt_club_id") or ""),
        "competition_id": str(row.get("competition_id") or ""),
        "valid_from": valid_from,
        "valid_to": _optional_text(row.get("valid_to")),
        "source_refs": _list(row.get("source_refs")),
        "source_sha256": source_sha,
        "evidence": evidence,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "review_status": requested_status,
    }
    payload["crosswalk_hash"] = stable_hash(payload)
    return TeamIdentityCrosswalkV1(**payload)


def build_player_crosswalk(
    row: Mapping[str, Any],
    *,
    team_crosswalks: list[TeamIdentityCrosswalkV1],
) -> PlayerIdentityCrosswalkV1:
    requested_status = str(row.get("review_status") or "REVIEW_REQUIRED")
    source_sha = str(row.get("source_sha256") or "")
    reviewed_by = _optional_text(row.get("reviewed_by"))
    reviewed_at = _optional_text(row.get("reviewed_at"))
    evidence = _dict(row.get("evidence"))
    valid_from = str(row.get("valid_from") or "")
    api_team = str(row.get("api_football_team_id") or "")
    competition_id = str(row.get("competition_id") or "")
    as_of = parse_utc(valid_from) or datetime.min.replace(tzinfo=UTC)
    team_crosswalk, team_status = approved_crosswalk_for_team(
        team_crosswalks,
        api_football_team_id=api_team,
        competition_id=competition_id,
        as_of=as_of,
    )
    if requested_status == "APPROVED" and (
        len(source_sha) != 64
        or not reviewed_by
        or not reviewed_at
        or not evidence
        or parse_utc(valid_from) is None
        or not _optional_text(row.get("transfermarkt_player_id"))
        or team_crosswalk is None
    ):
        requested_status = "REVIEW_REQUIRED"
        evidence = {
            **evidence,
            "blocked_reason": "TEAM_CROSSWALK_NOT_APPROVED"
            if team_status != "APPROVED"
            else "PLAYER_EVIDENCE_INCOMPLETE",
        }
    payload: dict[str, Any] = {
        "api_football_player_id": str(row.get("api_football_player_id") or ""),
        "transfermarkt_player_id": _optional_text(row.get("transfermarkt_player_id")),
        "api_football_team_id": api_team,
        "transfermarkt_club_id": team_crosswalk.transfermarkt_club_id
        if team_crosswalk
        else _optional_text(row.get("transfermarkt_club_id")),
        "competition_id": competition_id,
        "valid_from": valid_from,
        "valid_to": _optional_text(row.get("valid_to")),
        "source_sha256": source_sha,
        "evidence": evidence,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "review_status": requested_status,
    }
    payload["crosswalk_hash"] = stable_hash(payload)
    return PlayerIdentityCrosswalkV1(**payload)


def approved_crosswalk_for_team(
    rows: list[TeamIdentityCrosswalkV1],
    *,
    api_football_team_id: str,
    competition_id: str,
    as_of: datetime,
) -> tuple[TeamIdentityCrosswalkV1 | None, str]:
    valid = [
        row
        for row in rows
        if row.review_status == "APPROVED"
        and row.api_football_team_id == api_football_team_id
        and row.competition_id == competition_id
        and _valid_at(row.valid_from, row.valid_to, as_of)
    ]
    if len(valid) == 1:
        return valid[0], "APPROVED"
    if len(valid) > 1:
        return None, "CONFLICT"
    return None, "MISSING"


def import_team_crosswalk_file(path: Path) -> list[TeamIdentityCrosswalkV1]:
    rows = read_table(path)
    return [build_team_crosswalk(row) for row in rows]


def load_transfermarkt_source_root(source_root: Path) -> dict[str, Any]:
    files = {
        name: _first_existing(source_root, name)
        for name in (
            "clubs.csv",
            "players.csv",
            "player_valuations.csv",
            "registered_roster_snapshots.csv",
            "game_lineups.csv",
            "appearances.csv",
            "games.csv",
        )
    }
    return {
        key: {
            "path": str(path) if path else None,
            "sha256": sha256_file(path) if path else None,
            "rows": read_table(path) if path else [],
        }
        for key, path in files.items()
    }


def materialize_team_value_asof(
    *,
    fixture: Mapping[str, Any],
    crosswalks: list[TeamIdentityCrosswalkV1],
    player_crosswalks: list[PlayerIdentityCrosswalkV1] | None = None,
    source_root: Path,
) -> dict[str, Any]:
    as_of = parse_utc(fixture.get("as_of"))
    if as_of is None:
        raise ValueError("fixture as_of is required")
    team_external_id = str(fixture.get("team_external_id") or "")
    competition_id = str(fixture.get("competition_id") or "")
    crosswalk, crosswalk_status = approved_crosswalk_for_team(
        crosswalks,
        api_football_team_id=team_external_id,
        competition_id=competition_id,
        as_of=as_of,
    )
    sources = load_transfermarkt_source_root(source_root)
    blockers: list[str] = []
    if crosswalk is None:
        blockers.append(f"TEAM_CROSSWALK_{crosswalk_status}")
    club_id = crosswalk.transfermarkt_club_id if crosswalk else ""
    memberships, roster_status = _memberships_for_club(sources, club_id=club_id, as_of=as_of)
    if not memberships:
        blockers.append(roster_status)
    approved_players = _approved_players_for_team(
        player_crosswalks or [],
        api_football_team_id=team_external_id,
        transfermarkt_club_id=club_id,
        competition_id=competition_id,
        as_of=as_of,
    )
    valuations = sources["player_valuations.csv"]["rows"]
    total = Decimal("0")
    valued = 0
    missing_valuation = 0
    missing_mapping = 0
    future_exclusions = 0
    valuation_hashes: set[str] = set()
    seen_players: set[str] = set()
    conflict_count = 0
    for membership in memberships:
        player_id = str(
            membership.get("transfermarkt_player_id") or membership.get("player_id") or ""
        )
        if not player_id or player_id in seen_players:
            continue
        player_mapping = approved_players.get(player_id)
        if player_mapping is None:
            missing_mapping += 1
            blockers.append("PLAYER_CROSSWALK_MISSING")
            continue
        seen_players.add(player_id)
        chosen, future_count = _latest_valuation(valuations, player_id=player_id, as_of=as_of)
        future_exclusions += future_count
        if chosen is None:
            missing_valuation += 1
            continue
        if chosen.get("_conflict") is True:
            conflict_count += 1
            continue
        try:
            value = Decimal(
                str(chosen.get("market_value_eur") or chosen.get("market_value_in_eur"))
            )
        except (InvalidOperation, TypeError, ValueError):
            missing_valuation += 1
            continue
        total += value
        valued += 1
        valuation_hashes.add(
            str(
                chosen.get("_source_sha256")
                or sources["player_valuations.csv"]["sha256"]
                or ""
            )
        )
    if missing_valuation:
        blockers.append("VALUATION_MISSING")
    if conflict_count:
        blockers.append("VALUATION_CONFLICT")
    roster_hash = sources["registered_roster_snapshots.csv"]["sha256"]
    artifact = {
        "schema_version": TEAM_VALUE_ASOF_ARTIFACT_SCHEMA,
        "team_external_id": team_external_id,
        "transfermarkt_club_id": club_id,
        "competition_id": competition_id,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "roster_policy": "TIME_VALID_MEMBERSHIP_AS_OF",
        "roster_source_hash": roster_hash,
        "team_crosswalk_hash": crosswalk.crosswalk_hash if crosswalk else None,
        "player_count": len(seen_players),
        "uniquely_mapped_count": len(seen_players),
        "valued_count": valued,
        "conflict_count": conflict_count,
        "missing_mapping_count": missing_mapping if crosswalk else len(memberships),
        "missing_valuation_count": missing_valuation,
        "player_mapping_hashes": sorted(
            approved_players[_membership_player_id(row)].crosswalk_hash
            for row in memberships
            if _membership_player_id(row) in approved_players
        ),
        "valuation_source_hashes": sorted(valuation_hashes),
        "membership_source_hashes": sorted(filter(None, [roster_hash])),
        "squad_value_eur": str(total) if not missing_valuation and not conflict_count else None,
        "status": (
            "READY"
            if not blockers and conflict_count == 0 and valued == len(seen_players)
            else "INCOMPLETE"
        ),
        "blockers": sorted(set(blockers)),
        "future_valuation_exclusions": future_exclusions,
    }
    artifact["artifact_hash"] = stable_hash(artifact)
    return artifact


def identity_value_audit(
    *,
    crosswalks: list[TeamIdentityCrosswalkV1],
    artifacts: list[Mapping[str, Any]],
    source_root: Path | None,
) -> dict[str, Any]:
    source = (
        load_transfermarkt_source_root(source_root)
        if source_root and source_root.is_dir()
        else {}
    )
    valuation_rows = source.get("player_valuations.csv", {}).get("rows", []) if source else []
    valuation_dates = sorted(
        str(row.get("observed_at") or row.get("valuation_date") or "")
        for row in valuation_rows
        if row.get("observed_at") or row.get("valuation_date")
    )
    statuses = Counter(row.review_status for row in crosswalks)
    return {
        "schema_version": "w2.fah04.identity_value_audit.v1",
        "status": (
            "SOURCE_NOT_AVAILABLE"
            if not crosswalks and not artifacts
            else "CODE_COMPLETE_DATA_PENDING"
        ),
        "team_crosswalk_total": len(crosswalks),
        "approved_team_crosswalk_count": statuses.get("APPROVED", 0),
        "review_required_team_crosswalk_count": statuses.get("REVIEW_REQUIRED", 0),
        "conflict_team_crosswalk_count": statuses.get("CONFLICT", 0),
        "missing_team_crosswalk_count": 0 if crosswalks else 0,
        "player_mapping_total": 0,
        "matched_player_mapping_count": 0,
        "review_required_player_mapping_count": 0,
        "conflict_player_mapping_count": 0,
        "historical_membership_coverage": (
            len(source.get("registered_roster_snapshots.csv", {}).get("rows", []))
            if source
            else 0
        ),
        "valuation_row_count": len(valuation_rows),
        "valuation_date_range": (
            [valuation_dates[0], valuation_dates[-1]] if valuation_dates else None
        ),
        "future_valuation_exclusions": sum(
            int(item.get("future_valuation_exclusions") or 0) for item in artifacts
        ),
        "roster_coverage": sum(int(item.get("player_count") or 0) for item in artifacts),
        "team_value_artifacts": len(artifacts),
        "ready_team_value_artifact_count": sum(
            1 for item in artifacts if item.get("status") == "READY"
        ),
        "incomplete_team_value_artifact_count": sum(
            1 for item in artifacts if item.get("status") == "INCOMPLETE"
        ),
        "artifact_hashes": sorted(str(item.get("artifact_hash") or "") for item in artifacts),
        "source_hashes": sorted(
            str(value.get("sha256"))
            for value in source.values()
            if value.get("sha256")
        )
        if source
        else [],
    }


def write_json_and_md(payload: Mapping[str, Any], json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    md = [f"# {payload.get('schema_version')}", "", f"- status: {payload.get('status')}"]
    for key in (
        "approved_team_crosswalk_count",
        "ready_team_value_artifact_count",
        "valuation_row_count",
    ):
        if key in payload:
            md.append(f"- {key}: {payload[key]}")
    json_path.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")


def read_table(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    actual = path.with_suffix("") if path.suffix == ".gz" else path
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    sha = sha256_file(path)
    return [
        {
            **row,
            "_source_sha256": sha,
            "_source_path": str(path),
            "_schema_version": actual.name,
        }
        for row in rows
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _first_existing(root: Path, name: str) -> Path | None:
    for candidate in (root / name, root / f"{name}.gz"):
        if candidate.is_file():
            return candidate
    return None


def _memberships_for_club(
    sources: Mapping[str, Mapping[str, Any]],
    *,
    club_id: str,
    as_of: datetime,
) -> tuple[list[dict[str, Any]], str]:
    roster_rows = list(sources.get("registered_roster_snapshots.csv", {}).get("rows", []))
    if not roster_rows:
        return [], "REGISTERED_ROSTER_SNAPSHOT_MISSING"
    eligible = []
    for row in roster_rows:
        row_club = str(
            row.get("club_id") or row.get("team_id") or row.get("transfermarkt_club_id") or ""
        )
        observed = parse_utc(row.get("observed_at") or row.get("snapshot_date"))
        status = str(row.get("snapshot_status") or row.get("status") or "COMPLETE")
        if (
            row_club == club_id
            and observed is not None
            and observed <= as_of
            and status == "COMPLETE"
        ):
            eligible.append((observed, row))
    if not eligible:
        return [], "ROSTER_MEMBERSHIP_MISSING"
    latest = max(observed for observed, _row in eligible)
    return [row for observed, row in eligible if observed == latest], "ROSTER_MEMBERSHIP_MISSING"


def _approved_players_for_team(
    rows: list[PlayerIdentityCrosswalkV1],
    *,
    api_football_team_id: str,
    transfermarkt_club_id: str,
    competition_id: str,
    as_of: datetime,
) -> dict[str, PlayerIdentityCrosswalkV1]:
    output: dict[str, PlayerIdentityCrosswalkV1] = {}
    conflicted: set[str] = set()
    for row in rows:
        if (
            row.review_status != "APPROVED"
            or row.api_football_team_id != api_football_team_id
            or row.transfermarkt_club_id != transfermarkt_club_id
            or row.competition_id != competition_id
            or row.transfermarkt_player_id is None
            or not _valid_at(row.valid_from, row.valid_to, as_of)
        ):
            continue
        existing = output.get(row.transfermarkt_player_id)
        if existing is not None and existing.crosswalk_hash != row.crosswalk_hash:
            conflicted.add(row.transfermarkt_player_id)
            output.pop(row.transfermarkt_player_id, None)
            continue
        if row.transfermarkt_player_id not in conflicted:
            output[row.transfermarkt_player_id] = row
    return output


def _membership_player_id(row: Mapping[str, Any]) -> str:
    return str(row.get("transfermarkt_player_id") or row.get("player_id") or "")


def _latest_valuation(
    rows: list[Mapping[str, Any]],
    *,
    player_id: str,
    as_of: datetime,
) -> tuple[Mapping[str, Any] | None, int]:
    candidates = [
        row
        for row in rows
        if str(row.get("transfermarkt_player_id") or row.get("player_id") or "") == player_id
    ]
    future = sum(
        1
        for row in candidates
        if (observed := parse_utc(row.get("observed_at") or row.get("valuation_date"))) is not None
        and observed > as_of
    )
    eligible = [
        (observed, row)
        for row in candidates
        if (observed := parse_utc(row.get("observed_at") or row.get("valuation_date"))) is not None
        and observed <= as_of
    ]
    eligible.sort(key=lambda item: item[0], reverse=True)
    if eligible:
        latest_date = eligible[0][0]
        same_day = [row for observed, row in eligible if observed.date() == latest_date.date()]
        values = {
            str(row.get("market_value_eur") or row.get("market_value_in_eur") or "")
            for row in same_day
        }
        if len(values) > 1:
            return {"_conflict": True}, future
    return (eligible[0][1] if eligible else None), future


def _valid_at(valid_from: str, valid_to: str | None, as_of: datetime) -> bool:
    start = parse_utc(valid_from)
    end = parse_utc(valid_to)
    return start is not None and start <= as_of and (end is None or as_of < end)


def _list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return []


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_text(value: object) -> str | None:
    return str(value).strip() if value not in {None, ""} else None
