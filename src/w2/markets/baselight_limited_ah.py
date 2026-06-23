from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap

DATE_ONLY_LIMITATIONS = [
    "BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE",
    "PRECISE_PHASE_COVERAGE_UNAVAILABLE",
    "EXPORT_AND_RETENTION_POLICY_UNVERIFIED",
]

MIN_FIXTURES = 500
MIN_FOLDS = 5
MIN_BOOKMAKERS = 5
MIN_LINE_BUCKETS = 8
MIN_STRATA = 5


@dataclass(frozen=True)
class BaselightAhObservation:
    match_id: str
    competition: str
    season: str
    kickoff_utc: datetime
    home_team_name: str
    away_team_name: str
    home_score: int
    away_score: int
    bookmaker: str
    outcome: str
    selection: str
    line: Decimal
    odds: Decimal
    collected_at_date: str
    settlement: SettlementOutcome


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_date_only(value: str) -> str:
    raw = str(value).strip()
    if not raw:
        raise ValueError("collected_at is required")
    return parse_datetime(raw).date().isoformat()


def parse_int_score(value: Any) -> int:
    if value is None or value == "":
        raise ValueError("score is required")
    return int(float(str(value)))


def parse_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal {value!r}") from exc


def parse_outcome_selection_and_line(
    outcome: str,
    home_team_name: str,
    away_team_name: str,
) -> tuple[str, Decimal]:
    text = " ".join(str(outcome).strip().split())
    match = re.search(r"([+-]?\d+(?:\.\d+)?)", text)
    if not match:
        raise ValueError(f"outcome line not found: {outcome!r}")
    line = parse_decimal(match.group(1))
    lower = text.lower()
    home_key = home_team_name.lower()
    away_key = away_team_name.lower()
    if home_key and home_key in lower:
        return ("HOME", line)
    if away_key and away_key in lower:
        return ("AWAY", line)
    if lower.startswith("home"):
        return ("HOME", line)
    if lower.startswith("away"):
        return ("AWAY", line)
    raise ValueError(f"outcome team side not found: {outcome!r}")


def rows_from_sample(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    if suffix in {".jsonl", ".ndjson"}:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [dict(row) for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            return [dict(row) for row in payload["rows"] if isinstance(row, dict)]
    raise ValueError(f"unsupported sample format: {path}")


def normalize_observations(
    rows: list[dict[str, Any]],
) -> tuple[list[BaselightAhObservation], Counter[str]]:
    observations: list[BaselightAhObservation] = []
    errors: Counter[str] = Counter()
    for row in rows:
        try:
            if str(row.get("market", "")).strip() != "Asian Handicap":
                errors["MARKET_NOT_AH"] += 1
                continue
            if str(row.get("odds_type", "")).strip() != "pre_match":
                errors["ODDS_TYPE_NOT_PRE_MATCH"] += 1
                continue
            odds = parse_decimal(row.get("odds"))
            if odds <= Decimal("1"):
                errors["ODDS_NOT_GREATER_THAN_ONE"] += 1
                continue
            home = str(row.get("home_team_name", "")).strip()
            away = str(row.get("away_team_name", "")).strip()
            selection, line = parse_outcome_selection_and_line(
                str(row.get("outcome", "")),
                home,
                away,
            )
            home_score = parse_int_score(row.get("home_score"))
            away_score = parse_int_score(row.get("away_score"))
            settlement = settle_asian_handicap(home_score, away_score, selection, line)
            observations.append(
                BaselightAhObservation(
                    match_id=str(row["match_id"]),
                    competition=str(row.get("competition", "")),
                    season=str(row.get("season", "")),
                    kickoff_utc=parse_datetime(str(row["kickoff_utc"])),
                    home_team_name=home,
                    away_team_name=away,
                    home_score=home_score,
                    away_score=away_score,
                    bookmaker=str(row.get("bookmaker", "")),
                    outcome=str(row.get("outcome", "")),
                    selection=selection,
                    line=line,
                    odds=odds,
                    collected_at_date=parse_date_only(str(row["collected_at"])),
                    settlement=settlement,
                )
            )
        except (KeyError, ValueError) as exc:
            errors[type(exc).__name__] += 1
    return observations, errors


def line_bucket(line: Decimal) -> str:
    absolute = abs(line)
    if absolute >= Decimal("4"):
        return "4+"
    return str(absolute.normalize())


def build_manifest(
    sample_path: Path | None,
    observations: list[BaselightAhObservation],
) -> dict[str, Any]:
    competitions = {obs.competition for obs in observations}
    seasons = {obs.season for obs in observations}
    fixtures = {obs.match_id for obs in observations}
    bookmakers = {obs.bookmaker for obs in observations}
    buckets = {line_bucket(obs.line) for obs in observations}
    return {
        "schema_version": "W2_GATE3_BASELIGHT_LIMITED_AH_EXTRACT_MANIFEST_V1",
        "status": "READY_FOR_WALK_FORWARD" if observations else "INSUFFICIENT_SAMPLE",
        "sample_path": str(sample_path) if sample_path else None,
        "sample_sha256": sha256_file(sample_path) if sample_path else None,
        "row_count": len(observations),
        "fixture_count": len(fixtures),
        "bookmaker_count": len(bookmakers),
        "line_bucket_count": len(buckets),
        "competition_count": len(competitions),
        "season_count": len(seasons),
        "collected_at_precision": "DATE_ONLY",
        "candidate": False,
        "formal_recommendation": False,
        "remaining_limitations": DATE_ONLY_LIMITATIONS,
        "large_sample_committed": False,
    }


def chronological_folds(
    observations: list[BaselightAhObservation],
    fold_count: int = MIN_FOLDS,
) -> list[dict[str, Any]]:
    fixtures: dict[str, datetime] = {}
    for obs in observations:
        fixtures.setdefault(obs.match_id, obs.kickoff_utc)
    ordered = sorted(fixtures.items(), key=lambda item: (item[1], item[0]))
    if len(ordered) < fold_count:
        return []
    chunk = math.ceil(len(ordered) / fold_count)
    folds: list[dict[str, Any]] = []
    for index in range(fold_count):
        fold_fixtures = ordered[index * chunk : (index + 1) * chunk]
        if not fold_fixtures:
            continue
        fixture_ids = {fixture_id for fixture_id, _ in fold_fixtures}
        fold_observations = [obs for obs in observations if obs.match_id in fixture_ids]
        settlements = Counter(obs.settlement.value for obs in fold_observations)
        folds.append(
            {
                "fold": index + 1,
                "fixture_count": len(fixture_ids),
                "observation_count": len(fold_observations),
                "start_kickoff_utc": fold_fixtures[0][1].isoformat().replace("+00:00", "Z"),
                "end_kickoff_utc": fold_fixtures[-1][1].isoformat().replace("+00:00", "Z"),
                "settlement_distribution": dict(sorted(settlements.items())),
            }
        )
    return folds


def build_walk_forward(observations: list[BaselightAhObservation]) -> dict[str, Any]:
    manifest = build_manifest(None, observations)
    folds = chronological_folds(observations)
    fixture_count = manifest["fixture_count"]
    status = "PASS_LIMITED_WALK_FORWARD"
    blockers: list[str] = []
    if fixture_count < MIN_FIXTURES:
        status = "INSUFFICIENT_SAMPLE"
        blockers.append("BASELIGHT_LIMITED_AH_SAMPLE_TOO_SMALL")
    if len(folds) < MIN_FOLDS:
        status = "INSUFFICIENT_SAMPLE"
        blockers.append("BASELIGHT_WALK_FORWARD_FOLDS_INSUFFICIENT")
    if manifest["bookmaker_count"] < MIN_BOOKMAKERS:
        status = "INSUFFICIENT_SAMPLE"
        blockers.append("BASELIGHT_BOOKMAKER_COVERAGE_INSUFFICIENT")
    if manifest["line_bucket_count"] < MIN_LINE_BUCKETS:
        status = "INSUFFICIENT_SAMPLE"
        blockers.append("BASELIGHT_AH_LINE_BUCKET_COVERAGE_INSUFFICIENT")
    if manifest["competition_count"] < MIN_STRATA:
        status = "INSUFFICIENT_SAMPLE"
        blockers.append("BASELIGHT_COMPETITION_STRATA_INSUFFICIENT")
    all_fixture_sets: list[set[str]] = [set() for _ in folds]
    for fold_index, fold in enumerate(folds):
        start = parse_datetime(fold["start_kickoff_utc"])
        end = parse_datetime(fold["end_kickoff_utc"])
        all_fixture_sets[fold_index] = {
            obs.match_id for obs in observations if start <= obs.kickoff_utc <= end
        }
    cross_fold_overlap = any(
        left & right
        for index, left in enumerate(all_fixture_sets)
        for right in all_fixture_sets[index + 1 :]
    )
    if cross_fold_overlap:
        status = "DATA_SEMANTICS_BLOCKED"
        blockers.append("FIXTURE_SPLIT_LEAKAGE")
    return {
        "schema_version": "W2_GATE3_BASELIGHT_AH_WALK_FORWARD_V1",
        "status": status,
        "fold_count": len(folds),
        "folds": folds,
        "fixture_count": fixture_count,
        "observation_count": len(observations),
        "bookmaker_count": manifest["bookmaker_count"],
        "line_bucket_count": manifest["line_bucket_count"],
        "competition_count": manifest["competition_count"],
        "settlement_distribution": dict(
            sorted(Counter(obs.settlement.value for obs in observations).items())
        ),
        "blockers": blockers,
        "resolved_if_pass": [
            "HISTORICAL_AH_BASELINE_BACKTEST_MISSING",
            "AH_WALK_FORWARD_EVIDENCE_MISSING",
        ]
        if status == "PASS_LIMITED_WALK_FORWARD"
        else [],
        "remaining_limitations": DATE_ONLY_LIMITATIONS,
        "candidate": False,
        "formal_recommendation": False,
    }
