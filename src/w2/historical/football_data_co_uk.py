from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

REQUIRED_COLUMNS = {"Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
ONE_X_TWO_PRE = (
    ("B365H", "B365D", "B365A"),
    ("PSH", "PSD", "PSA"),
    ("AvgH", "AvgD", "AvgA"),
)
ONE_X_TWO_CLOSE = (
    ("B365CH", "B365CD", "B365CA"),
    ("PSCH", "PSCD", "PSCA"),
    ("AvgCH", "AvgCD", "AvgCA"),
)
OU_PRE = (("B365>2.5", "B365<2.5"), ("P>2.5", "P<2.5"), ("Avg>2.5", "Avg<2.5"))
OU_CLOSE = (("B365C>2.5", "B365C<2.5"), ("PC>2.5", "PC<2.5"), ("AvgC>2.5", "AvgC<2.5"))
AH_PRE = ("AHh", (("B365AHH", "B365AHA"), ("PAHH", "PAHA"), ("AvgAHH", "AvgAHA")))
AH_CLOSE = ("AHCh", (("B365CAHH", "B365CAHA"), ("PCAHH", "PCAHA"), ("AvgCAHH", "AvgCAHA")))
PHASE_PRE = "PRE_CLOSING"
PHASE_CLOSE = "CLOSING"
SOURCE_SYSTEM = "FOOTBALL_DATA_CO_UK"
PRECISION = "SOURCE_PHASE_ONLY"
DIV_ORDER = ("E0", "SP1", "I1", "D1", "F1", "SWE")
TOP_FIVE_DIVS = {"E0", "SP1", "I1", "D1", "F1"}


@dataclass(frozen=True)
class FootballDataCoUkRowV1:
    source_file_sha256: str
    source_file_name: str
    source_row_number: int
    div: str
    date: str
    time: str | None
    home_team: str
    away_team: str
    fthg: int | None
    ftag: int | None
    ftr: str | None
    source_phase: str
    capture_time_precision: str
    raw_column_mapping: dict[str, str]

    @property
    def fixture_natural_identity(self) -> str:
        return stable_hash(
            {
                "source_file_sha256": self.source_file_sha256,
                "Div": self.div,
                "Date": self.date,
                "Time": self.time,
                "HomeTeam": self.home_team,
                "AwayTeam": self.away_team,
            }
        )


def build_football_data_audits(source_root: Path) -> dict[str, dict[str, Any]]:
    files = discover_football_data_files(source_root)
    unsupported = discover_unsupported_football_data_files(source_root)
    inventory = _inventory(files, unsupported)
    f5 = _f5_audit(files)
    market = _market_evidence_audit(files)
    return {
        "FOOTBALL_DATA_LOCAL_INVENTORY": inventory,
        "FOOTBALL_DATA_F5_AUDIT": f5,
        "FOOTBALL_DATA_MARKET_EVIDENCE_AUDIT": market,
    }


def write_football_data_ingest_artifacts(
    source_root: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    files = discover_football_data_files(source_root)
    rows = _all_rows(files)
    snapshots = _source_snapshots(files)
    closing_facts = _ah_facts(rows, phase=PHASE_CLOSE)
    pre_closing_facts = _ah_facts(rows, phase=PHASE_PRE)
    phase_evidence = _phase_market_evidence(rows)
    f5_dataset = [
        _f5_dataset_row(fact)
        for fact in [*closing_facts, *pre_closing_facts]
        if fact["cover_bucket"] is not None
    ]
    coverage = _f5_coverage_report(closing_facts, pre_closing_facts)
    baseline = {
        "schema_version": "w2.football_data_market_baseline_candidate.v1",
        "status": "READY_CANDIDATE" if phase_evidence else "INSUFFICIENT_EVIDENCE",
        "source_system": SOURCE_SYSTEM,
        "evidence_status": "PHASE_BASED_MARKET_EVIDENCE",
        "exact_captured_at": False,
        "sample_count": len(phase_evidence),
        "phase_market_hash": stable_hash([item["phase_market_hash"] for item in phase_evidence]),
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
    }
    artifact_paths = {
        "source_snapshots": "FOOTBALL_DATA_SOURCE_SNAPSHOTS.jsonl",
        "closing_ah_facts": "FOOTBALL_DATA_CLOSING_AH_FACTS.jsonl",
        "pre_closing_ah_facts": "FOOTBALL_DATA_PRE_CLOSING_AH_FACTS.jsonl",
        "phase_market_evidence": "FOOTBALL_DATA_PHASE_MARKET_EVIDENCE.jsonl",
        "f5_dataset": "FOOTBALL_DATA_F5_DATASET.jsonl",
        "f5_coverage": "FOOTBALL_DATA_F5_COVERAGE_REPORT.json",
        "market_baseline_candidate": "FOOTBALL_DATA_MARKET_BASELINE_CANDIDATE.json",
    }
    manifest: dict[str, Any] = {
        "schema_version": "w2.football_data_ingest_manifest.v1",
        "source_system": SOURCE_SYSTEM,
        "capture_time_precision": PRECISION,
        "captured_at": None,
        "exact_captured_at": False,
        "source_snapshot_count": len(snapshots),
        "closing_ah_fact_count": len(closing_facts),
        "pre_closing_ah_fact_count": len(pre_closing_facts),
        "phase_market_evidence_count": len(phase_evidence),
        "f5_ready_count": len(f5_dataset),
        "artifacts": artifact_paths,
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
    }
    _write_jsonl(artifact_root / artifact_paths["source_snapshots"], snapshots)
    _write_jsonl(artifact_root / artifact_paths["closing_ah_facts"], closing_facts)
    _write_jsonl(artifact_root / artifact_paths["pre_closing_ah_facts"], pre_closing_facts)
    _write_jsonl(artifact_root / artifact_paths["phase_market_evidence"], phase_evidence)
    _write_jsonl(artifact_root / artifact_paths["f5_dataset"], f5_dataset)
    _write_json(artifact_root / artifact_paths["f5_coverage"], coverage)
    _write_json(artifact_root / artifact_paths["market_baseline_candidate"], baseline)
    manifest["artifact_hashes"] = {
        name: _file_hash(artifact_root / path) for name, path in artifact_paths.items()
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    _write_json(artifact_root / "FOOTBALL_DATA_INGEST_MANIFEST.json", manifest)
    return {
        "manifest": manifest,
        "f5_coverage": coverage,
        "market_baseline_candidate": baseline,
    }


def write_football_data_audits(source_root: Path, report_root: Path) -> dict[str, dict[str, Any]]:
    report_root.mkdir(parents=True, exist_ok=True)
    payloads = build_football_data_audits(source_root)
    for name, payload in payloads.items():
        (report_root / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (report_root / f"{name}.md").write_text(_to_md(name, payload), encoding="utf-8")
    return payloads


def _source_snapshots(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots = []
    for item in files:
        season = item.get("season_inferred") or _season_from_path(str(item["path"]))
        for phase in (PHASE_PRE, PHASE_CLOSE):
            source_id = stable_hash(
                {
                    "source_file_sha256": item["sha256"],
                    "archive_member": item["archive_member"],
                    "source_phase": phase,
                }
            )
            snapshots.append(
                {
                    "schema_version": "FootballDataSourceSnapshotV1",
                    "source_id": source_id,
                    "source_file_sha256": item["sha256"],
                    "source_file_name": item["file_name"],
                    "archive_member": item["archive_member"],
                    "season": season,
                    "competition": next(iter(item["div_coverage"]), ""),
                    "league_code": next(iter(item["div_coverage"]), ""),
                    "download_source": "football-data.co.uk",
                    "source_phase": phase,
                    "row_count": item["row_count"],
                }
            )
    return snapshots


def _ah_facts(rows: list[dict[str, Any]], *, phase: str) -> list[dict[str, Any]]:
    facts = []
    seen: set[str] = set()
    spec = AH_CLOSE if phase == PHASE_CLOSE else AH_PRE
    policy = (
        "FOOTBALL_DATA_CLOSING_AH_V1"
        if phase == PHASE_CLOSE
        else "FOOTBALL_DATA_PRE_CLOSING_AH_V1"
    )
    line_col = spec[0]
    for item in rows:
        row = item["row"]
        line = _decimal(row.get(line_col))
        home = _int(row.get("FTHG"))
        away = _int(row.get("FTAG"))
        odds = _first_odds_pair(row, spec[1])
        if line is None or home is None or away is None or odds is None or not _quarter_line(line):
            continue
        adapted = football_data_row(
            row,
            source_sha=item["sha256"],
            file_name=item["file_name"],
            row_number=item["row_number"],
            phase=phase,
        )
        unique_key = stable_hash(
            {
                "fixture_key": adapted.fixture_natural_identity,
                "source_phase": phase,
                "policy": policy,
            }
        )
        if unique_key in seen:
            continue
        seen.add(unique_key)
        settlement = settle_home_ah(line, home, away)
        fact = {
            "schema_version": (
                "FootballDataClosingAHFactV1"
                if phase == PHASE_CLOSE
                else "FootballDataPreClosingAHFactV1"
            ),
            "source_system": SOURCE_SYSTEM,
            "source_phase": phase,
            "capture_time_precision": PRECISION,
            "captured_at": None,
            "fixture_key": adapted.fixture_natural_identity,
            "competition": adapted.div,
            "season": _season_from_path(item["path"]),
            "kickoff_date": adapted.date,
            "home_team": adapted.home_team,
            "away_team": adapted.away_team,
            "line": str(line),
            "home_odds": odds[0],
            "away_odds": odds[1],
            "FTHG": home,
            "FTAG": away,
            "settlement": settlement,
            "cover_bucket": cover_bucket(settlement),
            "source_sha256": item["sha256"],
            "source_file_name": item["file_name"],
            "source_row_number": item["row_number"],
        }
        fact["fact_hash"] = stable_hash(fact)
        facts.append(fact)
    return facts


def _phase_market_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    seen: set[str] = set()
    for item in rows:
        row = item["row"]
        if not _season_is_2019_or_later(_season_from_path(item["path"])) or not _phase_ready(row):
            continue
        adapted = football_data_row(
            row,
            source_sha=item["sha256"],
            file_name=item["file_name"],
            row_number=item["row_number"],
            phase=PHASE_PRE,
        )
        key = stable_hash(
            {"fixture_key": adapted.fixture_natural_identity, "source": SOURCE_SYSTEM}
        )
        if key in seen:
            continue
        seen.add(key)
        payload = {
            "schema_version": "FootballDataPhaseMarketEvidenceV1",
            "source_system": SOURCE_SYSTEM,
            "evidence_status": "PHASE_BASED_MARKET_EVIDENCE",
            "exact_captured_at": False,
            "capture_time_precision": PRECISION,
            "captured_at": None,
            "fixture_key": adapted.fixture_natural_identity,
            "competition": adapted.div,
            "season": _season_from_path(item["path"]),
            "kickoff_date": adapted.date,
            "home_team": adapted.home_team,
            "away_team": adapted.away_team,
            "pre_closing": _phase_market_payload(row, phase=PHASE_PRE),
            "closing": _phase_market_payload(row, phase=PHASE_CLOSE),
            "source_sha256": item["sha256"],
            "source_row_number": item["row_number"],
        }
        payload["phase_market_hash"] = stable_hash(payload)
        evidence.append(payload)
    return evidence


def _phase_market_payload(row: dict[str, str], *, phase: str) -> dict[str, Any]:
    if phase == PHASE_CLOSE:
        one_x_two = _first_odds_group(row, ONE_X_TWO_CLOSE)
        ou = _first_odds_group(row, OU_CLOSE)
        ah_spec = AH_CLOSE
    else:
        one_x_two = _first_odds_group(row, ONE_X_TWO_PRE)
        ou = _first_odds_group(row, OU_PRE)
        ah_spec = AH_PRE
    ah_odds = _first_odds_pair(row, ah_spec[1])
    return {
        "phase": phase,
        "one_x_two": one_x_two,
        "ah": {"line": _text(row.get(ah_spec[0])), "home_odds": ah_odds[0], "away_odds": ah_odds[1]}
        if ah_odds
        else None,
        "ou": ou,
    }


def _f5_dataset_row(fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "w2.football_data_f5_dataset.v1",
        "fixture_key": fact["fixture_key"],
        "competition": fact["competition"],
        "season": fact["season"],
        "team": fact["home_team"],
        "before_kickoff": True,
        "source_phase": fact["source_phase"],
        "line": fact["line"],
        "settlement": fact["settlement"],
        "cover_bucket": fact["cover_bucket"],
        "fact_hash": fact["fact_hash"],
    }


def _f5_coverage_report(
    closing_facts: list[dict[str, Any]],
    pre_closing_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    all_facts = [*closing_facts, *pre_closing_facts]
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    teams: set[str] = set()
    push_count = 0
    for fact in all_facts:
        key = (str(fact["competition"]), str(fact["season"]))
        entry = by_key.setdefault(
            key,
            {
                "league": fact["competition"],
                "season": fact["season"],
                "matches": 0,
                "closing_facts": 0,
                "pre_closing_facts": 0,
                "push_count": 0,
                "missing": 0,
            },
        )
        entry["matches"] += 1
        if fact["source_phase"] == PHASE_CLOSE:
            entry["closing_facts"] += 1
        else:
            entry["pre_closing_facts"] += 1
        if fact["settlement"] == "PUSH":
            entry["push_count"] += 1
            push_count += 1
        teams.add(str(fact["home_team"]))
        teams.add(str(fact["away_team"]))
    payload = {
        "schema_version": "w2.football_data_f5_coverage_report.v1",
        "status": "READY" if all_facts else "INSUFFICIENT_EVIDENCE",
        "matches": len({fact["fixture_key"] for fact in all_facts}),
        "facts": len(all_facts),
        "teams": len(teams),
        "push_count": push_count,
        "missing": 0,
        "coverage_by_league_season": list(by_key.values()),
        "query_contract": {"team": True, "before_kickoff": True, "limit": True},
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
    }
    payload["coverage_hash"] = stable_hash(payload)
    return payload


def discover_football_data_files(source_root: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in _candidate_paths(source_root):
        for member_name, rows, columns in _read_candidate(path):
            if not REQUIRED_COLUMNS <= set(columns):
                continue
            stats = _file_stats(rows, columns)
            files.append(
                {
                    "path": str(path),
                    "file_name": path.name,
                    "archive_member": member_name,
                    "sha256": _file_hash(path),
                    "size_bytes": path.stat().st_size,
                    "columns": columns,
                    "row_count": len(rows),
                    **stats,
                }
            )
    return files


def discover_unsupported_football_data_files(source_root: Path) -> list[dict[str, Any]]:
    unsupported = []
    for path in _candidate_paths(source_root):
        for member_name, rows, columns in _read_candidate(path):
            if REQUIRED_COLUMNS <= set(columns):
                continue
            if _alternate_result_columns(columns):
                unsupported.append(
                    {
                        "path": str(path),
                        "file_name": path.name,
                        "archive_member": member_name,
                        "sha256": _file_hash(path),
                        "size_bytes": path.stat().st_size,
                        "columns": columns,
                        "row_count": len(rows),
                        "reason": "UNSUPPORTED_RESULT_SCHEMA_FOR_F5",
                        "has_ahh": "AHh" in columns,
                        "has_ahch": "AHCh" in columns,
                    }
                )
    return unsupported


def football_data_row(
    row: dict[str, str],
    *,
    source_sha: str,
    file_name: str,
    row_number: int,
    phase: str,
) -> FootballDataCoUkRowV1:
    return FootballDataCoUkRowV1(
        source_file_sha256=source_sha,
        source_file_name=file_name,
        source_row_number=row_number,
        div=_text(row.get("Div")),
        date=_text(row.get("Date")),
        time=_optional(row.get("Time")),
        home_team=_text(row.get("HomeTeam")),
        away_team=_text(row.get("AwayTeam")),
        fthg=_int(row.get("FTHG")),
        ftag=_int(row.get("FTAG")),
        ftr=_optional(row.get("FTR")),
        source_phase=phase,
        capture_time_precision=PRECISION,
        raw_column_mapping={key: key for key in row},
    )


def settle_home_ah(line: Decimal, home_goals: int, away_goals: int) -> str:
    margin = Decimal(home_goals - away_goals) + line
    if margin > Decimal("0.25"):
        return "WIN"
    if margin == Decimal("0.25"):
        return "HALF_WIN"
    if margin == 0:
        return "PUSH"
    if margin == Decimal("-0.25"):
        return "HALF_LOSS"
    return "LOSS"


def cover_bucket(settlement: str) -> str | None:
    if settlement in {"WIN", "HALF_WIN"}:
        return "COVER"
    if settlement in {"LOSS", "HALF_LOSS"}:
        return "NO_COVER"
    return None


def _inventory(files: list[dict[str, Any]], unsupported: list[dict[str, Any]]) -> dict[str, Any]:
    by_div: dict[str, dict[str, Any]] = {}
    for item in files:
        for div, count in item["div_coverage"].items():
            entry = by_div.setdefault(div, _div_empty())
            entry["matches"] += count
            entry["files"] += 1
            entry["ah_close_matches"] += item["odds_capability"]["ah_close_rows"]
            entry["ah_pre_matches"] += item["odds_capability"]["ah_pre_rows"]
            entry["phase_ready_matches"] += item["odds_capability"]["phase_ready_rows"]
    payload = {
        "schema_version": "w2.football_data_local_inventory.v1",
        "source_system": SOURCE_SYSTEM,
        "capture_semantics": [PHASE_PRE, PHASE_CLOSE],
        "capture_time_precision": PRECISION,
        "captured_at": None,
        "status": "FOOTBALL_DATA_FILES_FOUND" if files else "FOOTBALL_DATA_FILES_NOT_FOUND",
        "file_count": len(files),
        "archive_count": len({item["path"] for item in files if item["archive_member"]}),
        "signature_match_count": len(files),
        "unsupported_file_count": len(unsupported),
        "unsupported_files": unsupported,
        "files": files,
        "coverage_by_div": _ordered_divs(by_div),
        "capability": _capability(by_div),
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
    }
    payload["inventory_hash"] = stable_hash(payload)
    return payload


def _f5_audit(files: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _all_rows(files)
    by_div: dict[str, dict[str, Any]] = {}
    closing_facts = 0
    pre_facts = 0
    missing_line = 0
    illegal_line = 0
    missing_score = 0
    push = 0
    denominator = 0
    fact_hashes: list[str] = []
    for item in rows:
        row = item["row"]
        div = _text(row.get("Div"))
        season = _season_from_path(item["path"])
        entry = by_div.setdefault(f"{div}:{season}", _f5_empty(div, season))
        entry["total_matches"] += 1
        policies = (
            ("FOOTBALL_DATA_CLOSING_AH_V1", PHASE_CLOSE),
            ("FOOTBALL_DATA_PRE_CLOSING_AH_V1", PHASE_PRE),
        )
        for policy, phase in policies:
            line_col = "AHCh" if phase == PHASE_CLOSE else "AHh"
            line = _decimal(row.get(line_col))
            if line is None:
                missing_line += 1
                continue
            if not _quarter_line(line):
                illegal_line += 1
                entry["illegal_quarter_line"] += 1
                continue
            home = _int(row.get("FTHG"))
            away = _int(row.get("FTAG"))
            if home is None or away is None:
                missing_score += 1
                entry["missing_final_score"] += 1
                continue
            settlement = settle_home_ah(line, home, away)
            if settlement == "PUSH":
                push += 1
            else:
                denominator += 1
            fact = _fact(row, item, policy, phase, line, settlement)
            fact_hashes.append(fact["fact_hash"])
            if phase == PHASE_CLOSE:
                closing_facts += 1
                entry["closing_canonical_facts"] += 1
            else:
                pre_facts += 1
                entry["pre_closing_canonical_facts"] += 1
    payload = {
        "schema_version": "w2.football_data_f5_audit.v1",
        "source_system": SOURCE_SYSTEM,
        "capture_time_precision": PRECISION,
        "captured_at": None,
        "total_matches": len(rows),
        "matches_with_AHCh": sum(
            1 for item in rows if _decimal(item["row"].get("AHCh")) is not None
        ),
        "matches_with_AHh": sum(
            1 for item in rows if _decimal(item["row"].get("AHh")) is not None
        ),
        "closing_canonical_facts": closing_facts,
        "pre_closing_canonical_facts": pre_facts,
        "missing_ah_line": missing_line,
        "illegal_quarter_line": illegal_line,
        "missing_final_score": missing_score,
        "push_excluded_count": push,
        "f5_denominator_count": denominator,
        "coverage_by_div_season": list(by_div.values()),
        "status": "F5_CLOSING_AH_READY" if closing_facts else "AH_NOT_AVAILABLE",
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
    }
    payload["fact_manifest_hash"] = stable_hash(fact_hashes)
    return payload


def _market_evidence_audit(files: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _all_rows(files)
    phase_rows = []
    by_div: dict[str, int] = {}
    for item in rows:
        row = item["row"]
        if not _season_is_2019_or_later(_season_from_path(item["path"])):
            continue
        if _phase_ready(row):
            phase_rows.append(item)
            by_div[_text(row.get("Div"))] = by_div.get(_text(row.get("Div")), 0) + 1
    payload = {
        "schema_version": "w2.football_data_phase_market_evidence.v1",
        "source_system": SOURCE_SYSTEM,
        "evidence_status": "PHASE_BASED_MARKET_EVIDENCE" if phase_rows else "INSUFFICIENT_EVIDENCE",
        "not_evidence_status": "EXACT_CAPTURED_AT_EVIDENCE",
        "capture_time_precision": PRECISION,
        "captured_at": None,
        "phase_baseline_candidate_matches": len(phase_rows),
        "phase_clv_candidate_matches": len(phase_rows),
        "coverage_by_div": _ordered_counts(by_div),
        "limitations": [
            "EXACT_CAPTURED_AT_UNAVAILABLE",
            "T30_CLV_UNAVAILABLE",
            "WALK_FORWARD_CHECKPOINT_UNAVAILABLE",
        ],
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
    }
    payload["evidence_hash"] = stable_hash(payload)
    return payload


def _all_rows(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen: set[str] = set()
    for item in files:
        for member, rows, _columns in _read_candidate(Path(item["path"])):
            if member != item["archive_member"]:
                continue
            for index, row in enumerate(rows, start=2):
                if REQUIRED_COLUMNS <= set(row):
                    identity = stable_hash(
                        {
                            "Div": row.get("Div"),
                            "Date": row.get("Date"),
                            "Time": row.get("Time"),
                            "HomeTeam": row.get("HomeTeam"),
                            "AwayTeam": row.get("AwayTeam"),
                        }
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    output.append(
                        {
                            "row": row,
                            "path": item["path"],
                            "sha256": item["sha256"],
                            "file_name": item["file_name"],
                            "row_number": index,
                        }
                    )
    return output


def _file_stats(rows: list[dict[str, str]], columns: list[str]) -> dict[str, Any]:
    dates = [_parse_date(row.get("Date")) for row in rows]
    valid_dates = sorted(item for item in dates if item is not None)
    divs = _counter(row.get("Div") for row in rows)
    return {
        "div_coverage": divs,
        "date_range": {
            "min": valid_dates[0].isoformat() if valid_dates else None,
            "max": valid_dates[-1].isoformat() if valid_dates else None,
        },
        "season_inferred": _season_from_dates(valid_dates),
        "odds_capability": {
            "one_x_two_pre_rows": sum(1 for row in rows if _has_any(row, ONE_X_TWO_PRE)),
            "one_x_two_close_rows": sum(1 for row in rows if _has_any(row, ONE_X_TWO_CLOSE)),
            "ou_pre_rows": sum(1 for row in rows if _has_any(row, OU_PRE)),
            "ou_close_rows": sum(1 for row in rows if _has_any(row, OU_CLOSE)),
            "ah_pre_rows": sum(1 for row in rows if _has_ah(row, AH_PRE)),
            "ah_close_rows": sum(1 for row in rows if _has_ah(row, AH_CLOSE)),
            "phase_ready_rows": sum(1 for row in rows if _phase_ready(row)),
        },
        "capabilities": _file_capabilities(rows, columns),
    }


def _read_candidate(path: Path) -> list[tuple[str | None, list[dict[str, str]], list[str]]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows, columns = _read_csv_bytes(path.read_bytes())
        return [(None, rows, columns)]
    if suffix == ".gz" and path.name.endswith(".csv.gz"):
        rows, columns = _read_csv_bytes(gzip.decompress(path.read_bytes()))
        return [(None, rows, columns)]
    if suffix == ".zip":
        output: list[tuple[str | None, list[dict[str, str]], list[str]]] = []
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                if member.lower().endswith(".csv"):
                    rows, columns = _read_csv_bytes(archive.read(member))
                    output.append((member, rows, columns))
        return output
    if suffix == ".xlsx":
        rows, columns = _read_xlsx(path)
        return [(None, rows, columns)]
    return []


def _candidate_paths(source_root: Path) -> list[Path]:
    return [
        path
        for path in sorted(source_root.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".csv", ".gz", ".zip", ".xlsx", ".xls"}
    ]


def _alternate_result_columns(columns: list[str]) -> bool:
    column_set = set(columns)
    return {"Country", "League", "Season", "Date", "Home", "Away", "HG", "AG"} <= column_set


def _read_csv_bytes(data: bytes) -> tuple[list[dict[str, str]], list[str]]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(row) for row in reader if row]
    return rows, list(reader.fieldnames or [])


def _read_xlsx(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))  # noqa: S314
            for item in root.findall(".//a:si", ns):
                shared.append("".join(node.text or "" for node in item.findall(".//a:t", ns)))
        sheet_name = next(
            name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")
        )
        root = ElementTree.fromstring(archive.read(sheet_name))  # noqa: S314
    grid: list[list[str]] = []
    for row in root.findall(".//a:row", ns):
        values: list[str] = []
        for cell in row.findall("a:c", ns):
            value = cell.find("a:v", ns)
            raw = value.text if value is not None else ""
            values.append(shared[int(raw)] if cell.get("t") == "s" and raw else raw or "")
        grid.append(values)
    if not grid:
        return [], []
    columns = grid[0]
    rows = [dict(zip(columns, values, strict=False)) for values in grid[1:]]
    return rows, columns


def _fact(
    row: dict[str, str],
    item: dict[str, Any],
    policy: str,
    phase: str,
    line: Decimal,
    settlement: str,
) -> dict[str, Any]:
    adapted = football_data_row(
        row,
        source_sha=item["sha256"],
        file_name=item["file_name"],
        row_number=item["row_number"],
        phase=phase,
    )
    payload = {
        "schema_version": "w2.football_data_ah_fact.v1",
        "source_system": SOURCE_SYSTEM,
        "policy": policy,
        "source_phase": phase,
        "capture_time_precision": PRECISION,
        "captured_at": None,
        "fixture_natural_identity": adapted.fixture_natural_identity,
        "div": adapted.div,
        "date": adapted.date,
        "line": str(line),
        "settlement": settlement,
        "cover_bucket": cover_bucket(settlement),
    }
    payload["fact_hash"] = stable_hash(payload)
    return payload


def _file_capabilities(rows: list[dict[str, str]], columns: list[str]) -> list[str]:
    caps = ["RESULTS_READY"] if REQUIRED_COLUMNS <= set(columns) else []
    if any(_has_ah(row, AH_CLOSE) for row in rows):
        caps.append("F5_CLOSING_AH_READY")
    if any(_has_ah(row, AH_PRE) for row in rows):
        caps.append("F5_PRE_CLOSING_AH_READY")
    if any(_phase_ready(row) for row in rows):
        caps.extend(["PHASE_BASELINE_READY", "PHASE_CLV_READY"])
    if not any(_has_ah(row, AH_PRE) or _has_ah(row, AH_CLOSE) for row in rows):
        caps.append("AH_NOT_AVAILABLE")
    if not any(_has_any(row, OU_PRE) or _has_any(row, OU_CLOSE) for row in rows):
        caps.append("OU_NOT_AVAILABLE")
    caps.append("EXACT_CAPTURED_AT_UNAVAILABLE")
    return caps


def _phase_ready(row: dict[str, str]) -> bool:
    return (
        _has_any(row, ONE_X_TWO_PRE)
        and _has_any(row, ONE_X_TWO_CLOSE)
        and _has_ah(row, AH_PRE)
        and _has_ah(row, AH_CLOSE)
        and _has_any(row, OU_PRE)
        and _has_any(row, OU_CLOSE)
    )


def _has_ah(row: dict[str, str], spec: tuple[str, tuple[tuple[str, str], ...]]) -> bool:
    line_col, odds_pairs = spec
    return _decimal(row.get(line_col)) is not None and any(
        _has_pair(row, pair) for pair in odds_pairs
    )


def _has_any(row: dict[str, str], groups: tuple[tuple[str, ...], ...]) -> bool:
    return any(all(_decimal(row.get(column)) is not None for column in group) for group in groups)


def _has_pair(row: dict[str, str], pair: tuple[str, str]) -> bool:
    return all(_decimal(row.get(column)) is not None for column in pair)


def _first_odds_pair(
    row: dict[str, str],
    pairs: tuple[tuple[str, str], ...],
) -> tuple[str, str] | None:
    for left, right in pairs:
        left_value = _decimal(row.get(left))
        right_value = _decimal(row.get(right))
        if left_value is not None and right_value is not None:
            return str(left_value), str(right_value)
    return None


def _first_odds_group(
    row: dict[str, str],
    groups: tuple[tuple[str, ...], ...],
) -> dict[str, str] | None:
    for group in groups:
        values = [_decimal(row.get(column)) for column in group]
        if all(value is not None for value in values):
            return {column: str(value) for column, value in zip(group, values, strict=True)}
    return None


def _quarter_line(value: Decimal) -> bool:
    return value * 4 == (value * 4).to_integral_value()


def _season_is_2019_or_later(season: str) -> bool:
    match = re.match(r"^(\d{2})(\d{2})$", season)
    if not match:
        return False
    return int(match.group(1)) >= 19


def _season_from_path(path: str) -> str:
    for part in Path(path).parts:
        if re.match(r"^\d{4}$", part):
            return part
    return "UNKNOWN"


def _season_from_dates(dates: list[datetime]) -> str | None:
    if not dates:
        return None
    start = min(dates)
    year = start.year if start.month >= 7 else start.year - 1
    return f"{str(year)[2:]}{str(year + 1)[2:]}"


def _parse_date(value: str | None) -> datetime | None:
    text = _text(value)
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _decimal(value: str | None) -> Decimal | None:
    text = _text(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _int(value: str | None) -> int | None:
    try:
        return int(_text(value))
    except ValueError:
        return None


def _counter(values: Any) -> dict[str, int]:
    output: dict[str, int] = {}
    for value in values:
        key = _text(value)
        if key:
            output[key] = output.get(key, 0) + 1
    return output


def _capability(by_div: dict[str, dict[str, Any]]) -> dict[str, bool]:
    return {
        "top_five_present": any(div in by_div for div in TOP_FIVE_DIVS),
        "allsvenskan_present": "SWE" in by_div,
        "exact_captured_at_available": False,
        "phase_based_market_evidence_available": any(
            item["phase_ready_matches"] > 0 for item in by_div.values()
        ),
    }


def _div_empty() -> dict[str, int]:
    return {
        "files": 0,
        "matches": 0,
        "ah_close_matches": 0,
        "ah_pre_matches": 0,
        "phase_ready_matches": 0,
    }


def _f5_empty(div: str, season: str) -> dict[str, Any]:
    return {
        "div": div,
        "season": season,
        "total_matches": 0,
        "closing_canonical_facts": 0,
        "pre_closing_canonical_facts": 0,
        "illegal_quarter_line": 0,
        "missing_final_score": 0,
    }


def _ordered_divs(values: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {key: values[key] for key in DIV_ORDER if key in values} | {
        key: values[key] for key in sorted(values) if key not in DIV_ORDER
    }


def _ordered_counts(values: dict[str, int]) -> dict[str, int]:
    return {key: values[key] for key in DIV_ORDER if key in values} | {
        key: values[key] for key in sorted(values) if key not in DIV_ORDER
    }


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _to_md(name: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# {name}",
        "",
        f"- status: {payload.get('status') or payload.get('evidence_status')}",
    ]
    for key in (
        "file_count",
        "signature_match_count",
        "total_matches",
        "closing_canonical_facts",
        "pre_closing_canonical_facts",
        "phase_baseline_candidate_matches",
    ):
        if key in payload:
            lines.append(f"- {key}: {payload[key]}")
    lines.append("- manual_stop: MANUAL_APPROVAL_REQUIRED")
    return "\n".join(lines) + "\n"


def _text(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def _optional(value: str | None) -> str | None:
    text = _text(value)
    return text or None
