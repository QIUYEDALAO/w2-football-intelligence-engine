from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
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
ADAPTER_SCHEMA_VERSION = "football_data_co_uk_adapter.v2"
INGEST_MANIFEST_NAME = "DATASET_MANIFEST.json"
ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
ODDS_FAMILIES = {
    "B365": {
        PHASE_PRE: {
            "1x2": ("B365H", "B365D", "B365A"),
            "ah_line": "AHh",
            "ah": ("B365AHH", "B365AHA"),
            "ou_line": "2.5",
            "ou": ("B365>2.5", "B365<2.5"),
        },
        PHASE_CLOSE: {
            "1x2": ("B365CH", "B365CD", "B365CA"),
            "ah_line": "AHCh",
            "ah": ("B365CAHH", "B365CAHA"),
            "ou_line": "2.5",
            "ou": ("B365C>2.5", "B365C<2.5"),
        },
    },
    "PINNACLE": {
        PHASE_PRE: {
            "1x2": ("PSH", "PSD", "PSA"),
            "ah_line": "AHh",
            "ah": ("PAHH", "PAHA"),
            "ou_line": "2.5",
            "ou": ("P>2.5", "P<2.5"),
        },
        PHASE_CLOSE: {
            "1x2": ("PSCH", "PSCD", "PSCA"),
            "ah_line": "AHCh",
            "ah": ("PCAHH", "PCAHA"),
            "ou_line": "2.5",
            "ou": ("PC>2.5", "PC<2.5"),
        },
    },
    "AVERAGE": {
        PHASE_PRE: {
            "1x2": ("AvgH", "AvgD", "AvgA"),
            "ah_line": "AHh",
            "ah": ("AvgAHH", "AvgAHA"),
            "ou_line": "2.5",
            "ou": ("Avg>2.5", "Avg<2.5"),
        },
        PHASE_CLOSE: {
            "1x2": ("AvgCH", "AvgCD", "AvgCA"),
            "ah_line": "AHCh",
            "ah": ("AvgCAHH", "AvgCAHA"),
            "ou_line": "2.5",
            "ou": ("AvgC>2.5", "AvgC<2.5"),
        },
    },
}


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
                "Div": self.div,
                "Date": self.date,
                "Time": self.time,
                "HomeTeam": _source_team_identity(self.home_team),
                "AwayTeam": _source_team_identity(self.away_team),
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
    *,
    sanitized_summary_root: Path | None = None,
) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    source_root = source_root.resolve()
    dataset_manifest_path = source_root / "manifests" / INGEST_MANIFEST_NAME
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    canonical_inputs, representation_events = _canonical_inputs_from_manifest(
        source_root,
        dataset_manifest,
    )
    rows, input_failures = _manifest_rows(canonical_inputs)
    unique_rows, duplicate_report = _dedupe_fixture_rows(rows)
    snapshots = _source_snapshots_v2(canonical_inputs)
    closing_facts, closing_missing = _phase_ah_facts_v2(unique_rows, phase=PHASE_CLOSE)
    pre_closing_facts, pre_missing = _phase_ah_facts_v2(unique_rows, phase=PHASE_PRE)
    all_facts = [*closing_facts, *pre_closing_facts]
    f5_dataset = _f5_team_history_rows(all_facts)
    coverage = _f5_coverage_report_v2(
        closing_facts,
        pre_closing_facts,
        f5_dataset,
        closing_missing,
        pre_missing,
        duplicate_report,
        input_failures,
    )
    phase_evidence, phase_report = _phase_market_evidence_v2(unique_rows)
    baseline = {
        "schema_version": "w2.football_data_market_baseline_candidate.v1",
        "status": (
            "PHASE_EVIDENCE_READY_CANDIDATE" if phase_evidence else "INSUFFICIENT_EVIDENCE"
        ),
        "source_system": SOURCE_SYSTEM,
        "evidence_status": (
            "PHASE_EVIDENCE_READY_CANDIDATE" if phase_evidence else "INSUFFICIENT_EVIDENCE"
        ),
        "exact_captured_at": False,
        "sample_count": len(phase_evidence),
        "phase_market_hash": stable_hash([item["phase_market_hash"] for item in phase_evidence]),
        "calibration_training_executed": False,
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
    }
    artifact_paths = {
        "source_snapshots": "FOOTBALL_DATA_SOURCE_SNAPSHOTS.jsonl",
        "closing_ah_facts": "FOOTBALL_DATA_CLOSING_AH_FACTS_V2.jsonl",
        "pre_closing_ah_facts": "FOOTBALL_DATA_PRE_CLOSING_AH_FACTS_V2.jsonl",
        "phase_market_evidence": "FOOTBALL_DATA_PHASE_MARKET_EVIDENCE.jsonl",
        "f5_dataset": "FOOTBALL_DATA_F5_DATASET.jsonl",
        "f5_coverage": "FOOTBALL_DATA_F5_COVERAGE_REPORT.json",
        "market_baseline_candidate": "FOOTBALL_DATA_MARKET_BASELINE_CANDIDATE.json",
        "canonical_inputs": "FOOTBALL_DATA_CANONICAL_INPUTS.jsonl",
    }
    code_sha = _git_head(Path.cwd())
    manifest: dict[str, Any] = {
        "schema_version": "w2.football_data_ingest_manifest.v2",
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "implementation_head_sha": code_sha,
        "source_system": SOURCE_SYSTEM,
        "input_dataset_manifest_hash": _file_hash(dataset_manifest_path),
        "source_documentation_hashes": dataset_manifest.get("source_docs", {}),
        "capture_time_precision": PRECISION,
        "captured_at": None,
        "exact_captured_at": False,
        "canonical_input_count": len(canonical_inputs),
        "canonical_input_member_count": sum(
            1 for item in canonical_inputs if item["archive_member"]
        ),
        "unique_fixture_count": len(unique_rows),
        "source_snapshot_count": len(snapshots),
        "closing_ah_fact_count": len(closing_facts),
        "pre_closing_ah_fact_count": len(pre_closing_facts),
        "team_history_row_count": len(f5_dataset),
        "decisive_team_row_count": sum(row["decisive_denominator"] for row in f5_dataset),
        "push_team_row_count": sum(row["settlement"] == "PUSH" for row in f5_dataset),
        "phase_market_evidence_count": len(phase_evidence),
        "same_family_phase_evidence_count": len(phase_evidence),
        "top_five_phase_evidence_count": phase_report["top_five_phase_evidence_count"],
        "other_league_phase_evidence_count": phase_report["other_league_phase_evidence_count"],
        "exact_duplicate_count": duplicate_report["exact_duplicate_count"],
        "conflicting_fixture_count": duplicate_report["conflicting_fixture_count"],
        "representation_events": representation_events,
        "exclusions": {
            "fixture_duplicates": duplicate_report,
            "input_failures": input_failures,
            "f5_missing": coverage["totals"],
            "phase_evidence": phase_report["exclusions"],
        },
        "runtime_boundaries": {
            "SOURCE_LOCAL_F5_DATASET": "READY_CANDIDATE",
            "W2_TEAM_CROSSWALK": "NOT_READY",
            "W2_CANONICAL_IMPORT": "NOT_EXECUTED",
            "W2_RUNTIME_F5": "NOT_READY",
        },
        "capability_flags": _capability_flags(phase_evidence),
        "artifacts": artifact_paths,
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
    }
    _write_jsonl(artifact_root / artifact_paths["canonical_inputs"], canonical_inputs)
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
    if sanitized_summary_root is not None:
        _write_sanitized_summary(
            sanitized_summary_root,
            manifest,
            coverage,
            phase_report,
            dataset_manifest,
        )
    return {
        "manifest": manifest,
        "f5_coverage": coverage,
        "market_baseline_candidate": baseline,
        "phase_report": phase_report,
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


def query_team_history(
    rows: list[dict[str, Any]],
    *,
    source_team_identity: str,
    before_kickoff: str,
    limit: int,
    phase_policy: str,
) -> list[dict[str, Any]]:
    cutoff = _kickoff_sort_key(before_kickoff)
    candidates = [
        row
        for row in rows
        if row["source_team_identity"] == source_team_identity
        and row["phase"] == phase_policy
        and _kickoff_sort_key(str(row["kickoff_local"])) < cutoff
    ]
    return sorted(candidates, key=lambda row: str(row["kickoff_local"]), reverse=True)[:limit]


def _canonical_inputs_from_manifest(
    source_root: Path,
    dataset_manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inputs = []
    events = []
    manifest_entries = dataset_manifest.get("per_season_league", {})
    if not isinstance(manifest_entries, dict):
        msg = "DATASET_MANIFEST_PER_SEASON_LEAGUE_MISSING"
        raise ValueError(msg)
    for key in sorted(manifest_entries):
        season, league = key.split("_", maxsplit=1)
        extracted_path = source_root / "extracted" / season / f"{league}.csv"
        zip_path = source_root / "raw" / "season_zips" / f"{season}_data.zip"
        if not extracted_path.is_file():
            events.append(
                {
                    "season": season,
                    "league": league,
                    "status": "CANONICAL_SOURCE_MISSING",
                    "source_type": "extracted_csv",
                }
            )
            continue
        content = extracted_path.read_bytes()
        content_sha = hashlib.sha256(content).hexdigest()
        archive_member = None
        container_sha = content_sha
        if zip_path.is_file():
            with zipfile.ZipFile(zip_path) as archive:
                member_name = _zip_member_for_league(archive.namelist(), league)
                if member_name is not None:
                    member_bytes = archive.read(member_name)
                    member_sha = hashlib.sha256(member_bytes).hexdigest()
                    status = (
                        "SOURCE_REPRESENTATION_DUPLICATE"
                        if member_sha == content_sha
                        else "SOURCE_REPRESENTATION_CONFLICT"
                    )
                    events.append(
                        {
                            "season": season,
                            "league": league,
                            "status": status,
                            "selected_source_type": "extracted_csv",
                            "archive_member": member_name,
                            "raw_container_sha256": _file_hash(zip_path),
                            "member_sha256": member_sha,
                            "content_sha256": content_sha,
                        }
                    )
                    if status == "SOURCE_REPRESENTATION_CONFLICT":
                        msg = f"{status}: {season}/{league}"
                        raise ValueError(msg)
                    archive_member = member_name
        rows, columns, encoding = _read_csv_bytes_lossless(content)
        inputs.append(
            {
                "schema_version": "FootballDataSourceSnapshotV1",
                "source_id": stable_hash(
                    {
                        "league": league,
                        "season": season,
                        "content_sha256": content_sha,
                        "source_type": "extracted_csv",
                    }
                ),
                "source_file_name": extracted_path.name,
                "season": season,
                "competition": dataset_manifest.get("leagues", {}).get(league, league),
                "league_code": league,
                "download_source": dataset_manifest.get(
                    "source_home",
                    "https://www.football-data.co.uk",
                ),
                "source_phase": "SOURCE_FILE",
                "row_count": len(rows),
                "encoding": encoding,
                "source_type": "extracted_csv",
                "source_path": _private_path_placeholder(source_root, extracted_path),
                "local_path": str(extracted_path),
                "archive_member": archive_member,
                "raw_container_sha256": container_sha,
                "source_file_sha256": content_sha,
                "member_content_sha256": content_sha,
                "columns": columns,
            }
        )
    return inputs, events


def _manifest_rows(
    canonical_inputs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = []
    failures = []
    for item in canonical_inputs:
        path = Path(str(item["local_path"]))
        try:
            parsed_rows, _columns, encoding = _read_csv_bytes_lossless(path.read_bytes())
        except UnicodeDecodeError:
            failures.append(
                {
                    "source_id": item["source_id"],
                    "status": "SOURCE_ENCODING_UNSUPPORTED",
                }
            )
            continue
        for index, row in enumerate(parsed_rows, start=2):
            if REQUIRED_COLUMNS <= set(row):
                row_hash = stable_hash(row)
                rows.append(
                    {
                        "row": row,
                        "path": str(path),
                        "source_file_name": item["source_file_name"],
                        "season": item["season"],
                        "league": item["league_code"],
                        "competition": item["competition"],
                        "encoding": encoding,
                        "source_container_sha256": item["raw_container_sha256"],
                        "source_member_sha256": item["member_content_sha256"],
                        "archive_member": item["archive_member"],
                        "source_row_number": index,
                        "source_row_hash": row_hash,
                        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
                    }
                )
    return rows, failures


def _dedupe_fixture_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    exact_duplicate_count = 0
    conflict_hashes = []
    conflicted_keys: set[str] = set()
    for item in rows:
        key = _fixture_key_for_item(item)
        item["fixture_key"] = key
        current = unique.get(key)
        if current is None:
            unique[key] = item
            continue
        if _row_conflict_identity(current["row"]) == _row_conflict_identity(item["row"]):
            exact_duplicate_count += 1
            continue
        conflicted_keys.add(key)
        conflict_hashes.append(
            stable_hash(
                {
                    "fixture_key": key,
                    "first_row_hash": current["source_row_hash"],
                    "second_row_hash": item["source_row_hash"],
                }
            )
        )
    clean = [item for key, item in unique.items() if key not in conflicted_keys]
    return clean, {
        "exact_duplicate_count": exact_duplicate_count,
        "conflicting_fixture_count": len(conflicted_keys),
        "conflict_sample_hashes": conflict_hashes[:20],
    }


def _source_snapshots_v2(canonical_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: item[key]
            for key in (
                "schema_version",
                "source_id",
                "source_file_sha256",
                "source_file_name",
                "season",
                "competition",
                "league_code",
                "download_source",
                "source_phase",
                "row_count",
                "encoding",
                "source_type",
                "archive_member",
                "raw_container_sha256",
                "member_content_sha256",
            )
        }
        for item in canonical_inputs
    ]


def _phase_ah_facts_v2(
    rows: list[dict[str, Any]],
    *,
    phase: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    facts = []
    missing = {
        "missing_line": 0,
        "missing_result": 0,
        "missing_odds_pair": 0,
        "invalid_quarter_line": 0,
    }
    line_column = "AHCh" if phase == PHASE_CLOSE else "AHh"
    for item in rows:
        row = item["row"]
        line = _decimal(row.get(line_column))
        home = _int(row.get("FTHG"))
        away = _int(row.get("FTAG"))
        if line is None:
            missing["missing_line"] += 1
            continue
        if not _quarter_line(line):
            missing["invalid_quarter_line"] += 1
            continue
        if home is None or away is None:
            missing["missing_result"] += 1
            continue
        odds = _family_ah_odds(row, phase)
        market_price_status = "MARKET_PRICE_READY" if odds else "MARKET_PRICE_MISSING"
        if odds is None:
            missing["missing_odds_pair"] += 1
        home_settlement = settle_home_ah(line, home, away)
        away_settlement = settle_home_ah(-line, away, home)
        result_identity_hash = stable_hash({"FTHG": home, "FTAG": away, "FTR": row.get("FTR")})
        fact = {
            "schema_version": "FootballDataPhaseAhFactV2",
            "source_system": SOURCE_SYSTEM,
            "fixture_key": item["fixture_key"],
            "league": item["league"],
            "season": item["season"],
            "kickoff_local": _kickoff_local(row),
            "home_team_source_identity": _source_team_identity(_text(row.get("HomeTeam"))),
            "away_team_source_identity": _source_team_identity(_text(row.get("AwayTeam"))),
            "home_team": _text(row.get("HomeTeam")),
            "away_team": _text(row.get("AwayTeam")),
            "phase": phase,
            "capture_time_precision": PRECISION,
            "captured_at": None,
            "home_line": str(line),
            "away_line": str(-line),
            "home_settlement": home_settlement,
            "away_settlement": away_settlement,
            "FTHG": home,
            "FTAG": away,
            "result_identity_hash": result_identity_hash,
            "selected_odds_family": odds["family"] if odds else None,
            "selected_home_odds_column": odds["home_column"] if odds else None,
            "selected_away_odds_column": odds["away_column"] if odds else None,
            "home_odds": odds["home_odds"] if odds else None,
            "away_odds": odds["away_odds"] if odds else None,
            "market_price_status": market_price_status,
            "f5_settlement_ready": True,
            "market_price_ready": odds is not None,
            "source_container_sha256": item["source_container_sha256"],
            "source_member_sha256": item["source_member_sha256"],
            "archive_member": item["archive_member"],
            "source_row_number": item["source_row_number"],
            "source_row_hash": item["source_row_hash"],
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        }
        fact["fact_id"] = stable_hash(
            {"fixture_key": fact["fixture_key"], "phase": phase, "schema": fact["schema_version"]}
        )
        fact["fact_hash"] = stable_hash(fact)
        facts.append(fact)
    return facts, missing


def _f5_team_history_rows(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for fact in facts:
        for side in ("HOME", "AWAY"):
            is_home = side == "HOME"
            settlement = fact["home_settlement"] if is_home else fact["away_settlement"]
            rows.append(
                {
                    "schema_version": "w2.football_data_f5_team_history.v2",
                    "fixture_key": fact["fixture_key"],
                    "kickoff_local": fact["kickoff_local"],
                    "league": fact["league"],
                    "season": fact["season"],
                    "phase": fact["phase"],
                    "team": fact["home_team"] if is_home else fact["away_team"],
                    "source_team_identity": (
                        fact["home_team_source_identity"]
                        if is_home
                        else fact["away_team_source_identity"]
                    ),
                    "opponent": fact["away_team"] if is_home else fact["home_team"],
                    "side": side,
                    "team_line": fact["home_line"] if is_home else fact["away_line"],
                    "settlement": settlement,
                    "fact_id": fact["fact_id"],
                    "fact_hash": fact["fact_hash"],
                    "result_identity_hash": fact["result_identity_hash"],
                    "cover_bucket": cover_bucket(settlement),
                    "decisive_denominator": cover_bucket(settlement) is not None,
                }
            )
    return rows


def _f5_coverage_report_v2(
    closing_facts: list[dict[str, Any]],
    pre_closing_facts: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    closing_missing: dict[str, int],
    pre_missing: dict[str, int],
    duplicate_report: dict[str, Any],
    input_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    facts = [*closing_facts, *pre_closing_facts]
    by_layer: dict[str, dict[str, Any]] = {}
    for fact in facts:
        key = f"{fact['league']}:{fact['season']}:{fact['phase']}"
        item = by_layer.setdefault(
            key,
            {
                "league": fact["league"],
                "season": fact["season"],
                "phase": fact["phase"],
                "unique_match_facts": 0,
                "team_history_rows": 0,
                "decisive_team_rows": 0,
                "push_team_rows": 0,
                "missing_line": 0,
                "missing_result": 0,
                "missing_odds_pair": 0,
                "invalid_quarter_line": 0,
            },
        )
        item["unique_match_facts"] += 1
    for row in team_rows:
        key = f"{row['league']}:{row['season']}:{row['phase']}"
        item = by_layer[key]
        item["team_history_rows"] += 1
        item["decisive_team_rows"] += int(row["decisive_denominator"])
        item["push_team_rows"] += int(row["settlement"] == "PUSH")
    totals = {
        "missing_line": closing_missing["missing_line"] + pre_missing["missing_line"],
        "missing_result": closing_missing["missing_result"] + pre_missing["missing_result"],
        "missing_odds_pair": closing_missing["missing_odds_pair"]
        + pre_missing["missing_odds_pair"],
        "invalid_quarter_line": closing_missing["invalid_quarter_line"]
        + pre_missing["invalid_quarter_line"],
        "exact_duplicates": duplicate_report["exact_duplicate_count"],
        "content_conflicts": duplicate_report["conflicting_fixture_count"],
        "source_encoding_unsupported": len(input_failures),
    }
    payload = {
        "schema_version": "w2.football_data_f5_coverage_report.v2",
        "status": "SOURCE_LOCAL_F5_READY_CANDIDATE" if facts else "INSUFFICIENT_EVIDENCE",
        "w2_team_identity_status": "W2_TEAM_IDENTITY_MAPPING_REQUIRED",
        "unique_match_facts": len(facts),
        "team_history_rows": len(team_rows),
        "decisive_team_rows": sum(row["decisive_denominator"] for row in team_rows),
        "push_team_rows": sum(row["settlement"] == "PUSH" for row in team_rows),
        "closing_match_facts": len(closing_facts),
        "pre_closing_match_facts": len(pre_closing_facts),
        "totals": totals,
        "coverage_by_league_season_phase": sorted(
            by_layer.values(), key=lambda item: (item["league"], item["season"], item["phase"])
        ),
        "query_contract": {
            "implemented": True,
            "function": (
                "query_team_history("
                "source_team_identity,before_kickoff,limit,phase_policy)"
            ),
        },
        "runtime_boundaries": {
            "SOURCE_LOCAL_F5_DATASET": "READY_CANDIDATE",
            "W2_TEAM_CROSSWALK": "NOT_READY",
            "W2_CANONICAL_IMPORT": "NOT_EXECUTED",
            "W2_RUNTIME_F5": "NOT_READY",
        },
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
    }
    payload["coverage_hash"] = stable_hash(payload)
    return payload


def _phase_market_evidence_v2(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evidence = []
    exclusions = {"mixed_market_source_family": 0, "result_identity_incomplete": 0}
    by_league_season_family: dict[str, int] = {}
    for item in rows:
        row = item["row"]
        home = _int(row.get("FTHG"))
        away = _int(row.get("FTAG"))
        if home is None or away is None:
            exclusions["result_identity_incomplete"] += 1
            continue
        row_has_any_complete = False
        for family in ODDS_FAMILIES:
            pre = _phase_family_payload(row, family, PHASE_PRE)
            closing = _phase_family_payload(row, family, PHASE_CLOSE)
            if pre is None or closing is None:
                continue
            row_has_any_complete = True
            result_identity_hash = stable_hash({"FTHG": home, "FTAG": away, "FTR": row.get("FTR")})
            payload = {
                "schema_version": "FootballDataPhaseMarketEvidenceV1",
                "source_system": SOURCE_SYSTEM,
                "evidence_status": "PHASE_EVIDENCE_READY_CANDIDATE",
                "exact_captured_at": False,
                "capture_time_precision": PRECISION,
                "captured_at": None,
                "fixture_key": item["fixture_key"],
                "league": item["league"],
                "season": item["season"],
                "kickoff_local": _kickoff_local(row),
                "home_team": _text(row.get("HomeTeam")),
                "away_team": _text(row.get("AwayTeam")),
                "odds_family": family,
                "pre_closing": pre,
                "closing": closing,
                "FTHG": home,
                "FTAG": away,
                "result_identity_hash": result_identity_hash,
                "settlement_outcomes": {
                    "pre_home": settle_home_ah(
                        _decimal(row.get("AHh")) or Decimal("0"),
                        home,
                        away,
                    ),
                    "closing_home": settle_home_ah(
                        _decimal(row.get("AHCh")) or Decimal("0"), home, away
                    ),
                },
                "source_container_sha256": item["source_container_sha256"],
                "source_member_sha256": item["source_member_sha256"],
                "archive_member": item["archive_member"],
                "source_row_number": item["source_row_number"],
                "source_row_hash": item["source_row_hash"],
            }
            payload["phase_market_hash"] = stable_hash(payload)
            evidence.append(payload)
            key = f"{item['league']}:{item['season']}:{family}"
            by_league_season_family[key] = by_league_season_family.get(key, 0) + 1
        if not row_has_any_complete and _has_mixed_family_market(row):
            exclusions["mixed_market_source_family"] += 1
    top_five_count = sum(1 for item in evidence if item["league"] in TOP_FIVE_DIVS)
    report = {
        "schema_version": "w2.football_data_phase_evidence_report.v2",
        "status": "PHASE_EVIDENCE_READY_CANDIDATE" if evidence else "INSUFFICIENT_EVIDENCE",
        "same_family_phase_evidence_count": len(evidence),
        "top_five_phase_evidence_count": top_five_count,
        "other_league_phase_evidence_count": len(evidence) - top_five_count,
        "by_league_season_family": by_league_season_family,
        "exclusions": exclusions,
    }
    report["report_hash"] = stable_hash(report)
    return evidence, report


def _read_csv_bytes_lossless(data: bytes) -> tuple[list[dict[str, str]], list[str], str]:
    last_error: UnicodeDecodeError | None = None
    for encoding in ENCODINGS:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(row) for row in reader if row]
        return rows, list(reader.fieldnames or []), encoding
    if last_error is not None:
        raise last_error
    msg = "SOURCE_ENCODING_UNSUPPORTED"
    raise UnicodeDecodeError("unknown", b"", 0, 1, msg)


def _private_path_placeholder(source_root: Path, path: Path) -> str:
    try:
        return "$W2_FOOTBALL_DATA_ROOT/" + path.relative_to(source_root).as_posix()
    except ValueError:
        return "$W2_FOOTBALL_DATA_ROOT/" + path.name


def _zip_member_for_league(members: list[str], league: str) -> str | None:
    candidates = [
        member
        for member in members
        if Path(member).name.lower() == f"{league.lower()}.csv"
        or Path(member).stem.lower() == league.lower()
    ]
    return sorted(candidates)[0] if candidates else None


def _fixture_key_for_item(item: dict[str, Any]) -> str:
    row = item["row"]
    return stable_hash(
        {
            "league": item["league"],
            "season": item["season"],
            "kickoff": _kickoff_local(row),
            "home": _source_team_identity(_text(row.get("HomeTeam"))),
            "away": _source_team_identity(_text(row.get("AwayTeam"))),
        }
    )


def _row_conflict_identity(row: dict[str, str]) -> dict[str, str]:
    fields = (
        "Div",
        "Date",
        "Time",
        "HomeTeam",
        "AwayTeam",
        "FTHG",
        "FTAG",
        "FTR",
        "AHh",
        "AHCh",
        "B365AHH",
        "B365AHA",
        "B365CAHH",
        "B365CAHA",
        "PAHH",
        "PAHA",
        "PCAHH",
        "PCAHA",
        "AvgAHH",
        "AvgAHA",
        "AvgCAHH",
        "AvgCAHA",
    )
    return {field: _text(row.get(field)) for field in fields}


def _source_team_identity(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _kickoff_local(row: dict[str, str]) -> str:
    date = _text(row.get("Date"))
    time = _text(row.get("Time")) or "00:00"
    parsed = _parse_date(date)
    date_text = parsed.date().isoformat() if parsed is not None else date
    return f"{date_text}T{time}"


def _kickoff_sort_key(value: str) -> str:
    return value.replace("/", "-")


def _family_ah_odds(row: dict[str, str], phase: str) -> dict[str, str] | None:
    for family, spec in ODDS_FAMILIES.items():
        home_col, away_col = spec[phase]["ah"]
        home = _decimal(row.get(home_col))
        away = _decimal(row.get(away_col))
        if home is not None and away is not None:
            return {
                "family": family,
                "home_column": home_col,
                "away_column": away_col,
                "home_odds": str(home),
                "away_odds": str(away),
            }
    return None


def _phase_family_payload(row: dict[str, str], family: str, phase: str) -> dict[str, Any] | None:
    spec = ODDS_FAMILIES[family][phase]
    one_x_two_cols = cast(tuple[str, ...], spec["1x2"])
    ah_cols = cast(tuple[str, ...], spec["ah"])
    ou_cols = cast(tuple[str, ...], spec["ou"])
    one_x_two = _columns_as_decimals(row, one_x_two_cols)
    ah = _columns_as_decimals(row, ah_cols)
    ou = _columns_as_decimals(row, ou_cols)
    ah_line = _decimal(row.get(str(spec["ah_line"])))
    ou_line = Decimal(str(spec["ou_line"]))
    if one_x_two is None or ah is None or ou is None or ah_line is None or ou_line is None:
        return None
    return {
        "phase": phase,
        "odds_family": family,
        "source_columns": {
            "1x2": list(one_x_two_cols),
            "ah_line": spec["ah_line"],
            "ah": list(ah_cols),
            "ou_line": spec["ou_line"],
            "ou": list(ou_cols),
        },
        "one_x_two": {
            "home": one_x_two[one_x_two_cols[0]],
            "draw": one_x_two[one_x_two_cols[1]],
            "away": one_x_two[one_x_two_cols[2]],
        },
        "ah": {
            "line": str(ah_line),
            "home": ah[ah_cols[0]],
            "away": ah[ah_cols[1]],
        },
        "ou": {
            "line": str(ou_line),
            "over": ou[ou_cols[0]],
            "under": ou[ou_cols[1]],
        },
    }


def _columns_as_decimals(
    row: dict[str, str],
    columns: tuple[str, ...],
) -> dict[str, str] | None:
    values = {column: _decimal(row.get(column)) for column in columns}
    if not all(value is not None for value in values.values()):
        return None
    return {column: str(value) for column, value in values.items() if value is not None}


def _has_mixed_family_market(row: dict[str, str]) -> bool:
    for phase in (PHASE_PRE, PHASE_CLOSE):
        complete_pieces = []
        for family, spec in ODDS_FAMILIES.items():
            one_x_two_cols = cast(tuple[str, ...], spec[phase]["1x2"])
            ah_cols = cast(tuple[str, ...], spec[phase]["ah"])
            ou_cols = cast(tuple[str, ...], spec[phase]["ou"])
            complete_pieces.append(
                (
                    family,
                    _columns_as_decimals(row, one_x_two_cols) is not None,
                    _columns_as_decimals(row, ah_cols) is not None
                    and _decimal(row.get(str(spec[phase]["ah_line"]))) is not None,
                    _columns_as_decimals(row, ou_cols) is not None,
                )
            )
        if any(any(piece[1:]) for piece in complete_pieces) and not any(
            all(piece[1:]) for piece in complete_pieces
        ):
            return True
    return False


def _capability_flags(phase_evidence: list[dict[str, Any]]) -> list[str]:
    flags = [
        "NO_EXACT_CAPTURED_AT",
        "SOURCE_LOCAL_F5_READY_CANDIDATE",
        "W2_TEAM_IDENTITY_MAPPING_REQUIRED",
        "W2_CANONICAL_IMPORT_NOT_EXECUTED",
        "W2_RUNTIME_F5_NOT_READY",
        "CALIBRATION_TRAINING_NOT_EXECUTED",
        "FORMAL_AH_NOT_ENABLED",
        "LOCK_NOT_ENABLED",
        "PRODUCTION_NOT_ENABLED",
        "MANUAL_APPROVAL_REQUIRED",
    ]
    if phase_evidence:
        flags.append("PHASE_EVIDENCE_READY_CANDIDATE")
    return flags


def _git_head(cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "UNKNOWN"


def _write_sanitized_summary(
    repo_root: Path,
    manifest: dict[str, Any],
    coverage: dict[str, Any],
    phase_report: dict[str, Any],
    dataset_manifest: dict[str, Any],
) -> None:
    summary_path = repo_root / "docs" / "data" / "audits" / "FOOTBALL_DATA_INGEST_01R_SUMMARY.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "w2.football_data_ingest_01r_summary.v1",
        "code_sha": manifest["implementation_head_sha"],
        "input_manifest_sha": manifest["input_dataset_manifest_hash"],
        "league_season_aggregate_counts": dataset_manifest.get("per_season_league", {}),
        "duplicate_conflict_exclusion_counts": {
            "exact_duplicate_count": manifest["exact_duplicate_count"],
            "content_conflict_count": manifest["conflicting_fixture_count"],
            "f5_missing": coverage["totals"],
            "phase_exclusions": phase_report["exclusions"],
        },
        "artifact_manifest_hash": manifest["manifest_hash"],
        "capture_semantics": {
            "capture_time_precision": PRECISION,
            "captured_at": None,
            "exact_captured_at": False,
            "source_phases": [PHASE_PRE, PHASE_CLOSE],
        },
        "privacy": {
            "no_raw_rows": True,
            "no_team_level_records": True,
            "no_private_absolute_paths": True,
            "path_token": "$W2_FOOTBALL_DATA_ROOT",
        },
        "runtime_boundaries": manifest["runtime_boundaries"],
        "capability_flags": manifest["capability_flags"],
        "manual_stop": "MANUAL_APPROVAL_REQUIRED",
    }
    summary["summary_hash"] = stable_hash(summary)
    _write_json(summary_path, summary)


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
    rows, columns, _encoding = _read_csv_bytes_lossless(data)
    return rows, columns


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
