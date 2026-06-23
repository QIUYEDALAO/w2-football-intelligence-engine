from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from w2.domain.enums import MarketType
from w2.domain.odds import canonicalize_selection, settle_asian_handicap, settle_total_goals

PHASE_OFFSETS = {
    "T-72h": timedelta(hours=72),
    "T-48h": timedelta(hours=48),
    "T-24h": timedelta(hours=24),
    "T-12h": timedelta(hours=12),
    "T-6h": timedelta(hours=6),
    "T-3h": timedelta(hours=3),
    "T-1h": timedelta(hours=1),
    "T-30m": timedelta(minutes=30),
    "T-10m": timedelta(minutes=10),
    "Closing": timedelta(0),
}

VALID_SNAPSHOT_SEMANTICS = {
    "CAPTURED_AT",
    "CLOSING",
    "UNKNOWN_PREMATCH_AGGREGATE",
    "INVALID_OR_UNUSABLE",
}


@dataclass(frozen=True, kw_only=True)
class SourceInventoryItem:
    source_system: str
    relative_path: str
    tracked: bool
    sha256: str
    file_format: str
    row_count: int
    fixture_count: int
    competition_count: int
    season_date_range: dict[str, str | None]
    bookmaker_count: int
    market_coverage: dict[str, int]
    line_coverage: list[str]
    decimal_odds_available: bool
    result_available: bool
    event_time_field: str | None
    captured_at_field: str | None
    provider_last_update_field: str | None
    fixture_mapping_fields: list[str]
    snapshot_semantics: str
    suitability: str


@dataclass(frozen=True, kw_only=True)
class MarketObservation:
    source_system: str
    source_path: str
    source_sha256: str
    fixture_source_id: str
    w2_fixture_id: str | None
    mapping_status: str
    competition: str | None
    season: str | None
    kickoff_utc: str | None
    bookmaker: str
    market: str
    raw_market_label: str
    canonical_selection: str
    line: str | None
    decimal_odds: str
    suspended: bool
    live: bool
    event_time: str | None
    captured_at: str | None
    ingested_at: str
    snapshot_semantics: str
    result: dict[str, int] | None
    settlement_rule: str
    candidate: bool = False
    formal_recommendation: bool = False

    @property
    def identity(self) -> tuple[str, ...]:
        return (
            self.source_sha256,
            self.fixture_source_id,
            self.bookmaker,
            self.market,
            self.canonical_selection,
            self.line or "",
            self.decimal_odds,
            self.captured_at or "",
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_w1_match_date(value: str) -> datetime | None:
    for fmt in ("%d-%m-%y %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def decimal_string(value: Any) -> str | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed <= Decimal("1"):
        return None
    return str(parsed)


def normalize_team_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def detect_snapshot_semantics(path: Path, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "INVALID_OR_UNUSABLE"
    if any(row.get("captured_at_utc") or row.get("captured_at") for row in rows):
        return "CAPTURED_AT"
    if "local_odds" in path.as_posix() or "world_cup_odds" in path.name:
        return "CLOSING"
    if any("UNKNOWN_PREMATCH_AGGREGATE" in json.dumps(row) for row in rows[:5]):
        return "UNKNOWN_PREMATCH_AGGREGATE"
    return "UNKNOWN_PREMATCH_AGGREGATE"


def canonical_market(raw_market: str) -> str | None:
    key = raw_market.strip().upper().replace(" ", "_")
    aliases = {
        "1X2": MarketType.ONE_X_TWO.value,
        "MATCH_WINNER": MarketType.ONE_X_TWO.value,
        "MATCH WINNER": MarketType.ONE_X_TWO.value,
        "AH": MarketType.ASIAN_HANDICAP.value,
        "ASIAN_HANDICAP": MarketType.ASIAN_HANDICAP.value,
        "ASIAN HANDICAP": MarketType.ASIAN_HANDICAP.value,
        "OU": MarketType.TOTALS.value,
        "TOTALS": MarketType.TOTALS.value,
        "GOALS_OVER/UNDER": MarketType.TOTALS.value,
        "GOALS OVER/UNDER": MarketType.TOTALS.value,
        "BTTS": MarketType.BTTS.value,
        "BOTH_TEAMS_SCORE": MarketType.BTTS.value,
        "BOTH TEAMS SCORE": MarketType.BTTS.value,
    }
    return aliases.get(key)


def parse_selection_and_line(
    market: str, raw_value: str, explicit_line: Any = None
) -> tuple[str, str | None]:
    text = raw_value.strip()
    line = decimal_line(explicit_line)
    if market == MarketType.ONE_X_TWO.value:
        selection = canonicalize_selection(MarketType.ONE_X_TWO, text)
        return selection, None
    if market == MarketType.BTTS.value:
        selection = canonicalize_selection(MarketType.BTTS, text)
        return selection, None
    if market == MarketType.TOTALS.value:
        parts = text.split()
        selection = canonicalize_selection(MarketType.TOTALS, parts[0])
        parsed_line = line or (decimal_line(parts[-1]) if len(parts) > 1 else None)
        return selection, parsed_line
    if market == MarketType.ASIAN_HANDICAP.value:
        parts = text.split()
        selection = canonicalize_selection(MarketType.ASIAN_HANDICAP, parts[0])
        parsed_line = line or (decimal_line(parts[-1]) if len(parts) > 1 else None)
        return selection, parsed_line
    raise ValueError(f"unsupported market {market}")


def decimal_line(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    scaled = parsed * Decimal("4")
    if scaled != scaled.to_integral_value():
        return None
    return str(parsed.normalize())


def normalize_w1_local_odds(path: Path, *, source_system: str = "W1") -> list[MarketObservation]:
    source_sha = sha256_file(path)
    observations: list[MarketObservation] = []
    ingested_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    with path.open(newline="", encoding="utf-8") as handle:
        for row_index, row in enumerate(csv.DictReader(handle), start=1):
            kickoff = parse_w1_match_date(row.get("matchDate", ""))
            fixture_id = row.get("id") or (
                f"{row.get('Season')}:{normalize_team_key(row.get('homeTeam', ''))}:"
                f"{normalize_team_key(row.get('awayTeam', ''))}:{row_index}"
            )
            result = None
            for market, fields in (
                (MarketType.ONE_X_TWO.value, [("HOME", "H"), ("DRAW", "D"), ("AWAY", "A")]),
                (MarketType.BTTS.value, [("YES", "BTTSY"), ("NO", "BTTSN")]),
            ):
                for selection, field in fields:
                    price = decimal_string(row.get(field))
                    if price is None:
                        continue
                    observations.append(
                        MarketObservation(
                            source_system=source_system,
                            source_path=str(path),
                            source_sha256=source_sha,
                            fixture_source_id=fixture_id,
                            w2_fixture_id=None,
                            mapping_status="UNMAPPED_SOURCE_FIXTURE",
                            competition=row.get("League") or row.get("Country"),
                            season=row.get("Season"),
                            kickoff_utc=kickoff.isoformat().replace("+00:00", "Z")
                            if kickoff
                            else None,
                            bookmaker="W1_CLOSING_AGGREGATE",
                            market=market,
                            raw_market_label=field,
                            canonical_selection=selection,
                            line=None,
                            decimal_odds=price,
                            suspended=False,
                            live=False,
                            event_time=None,
                            captured_at=None,
                            ingested_at=ingested_at,
                            snapshot_semantics="CLOSING",
                            result=result,
                            settlement_rule="1X2_OR_BTTS_CLOSING_BASELINE",
                        )
                    )
            for suffix, line in (
                ("05", "0.5"),
                ("15", "1.5"),
                ("25", "2.5"),
                ("35", "3.5"),
                ("45", "4.5"),
            ):
                for selection, field in (("OVER", f"O{suffix}"), ("UNDER", f"U{suffix}")):
                    price = decimal_string(row.get(field))
                    if price is None:
                        continue
                    observations.append(
                        MarketObservation(
                            source_system=source_system,
                            source_path=str(path),
                            source_sha256=source_sha,
                            fixture_source_id=fixture_id,
                            w2_fixture_id=None,
                            mapping_status="UNMAPPED_SOURCE_FIXTURE",
                            competition=row.get("League") or row.get("Country"),
                            season=row.get("Season"),
                            kickoff_utc=kickoff.isoformat().replace("+00:00", "Z")
                            if kickoff
                            else None,
                            bookmaker="W1_CLOSING_AGGREGATE",
                            market=MarketType.TOTALS.value,
                            raw_market_label=field,
                            canonical_selection=selection,
                            line=line,
                            decimal_odds=price,
                            suspended=False,
                            live=False,
                            event_time=None,
                            captured_at=None,
                            ingested_at=ingested_at,
                            snapshot_semantics="CLOSING",
                            result=result,
                            settlement_rule="OU_CLOSING_BASELINE",
                        )
                    )
    return deterministic_dedup(observations)


def normalize_w1_snapshot_jsonl(
    path: Path, *, source_system: str = "W1"
) -> list[MarketObservation]:
    source_sha = sha256_file(path)
    observations: list[MarketObservation] = []
    ingested_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            market = canonical_market(str(row.get("market", "")))
            raw = row.get("raw_odds") or {}
            price = decimal_string(raw.get("odds"))
            if market is None or price is None:
                continue
            try:
                selection, parsed_line = parse_selection_and_line(
                    market,
                    str(raw.get("label", "")),
                    row.get("line"),
                )
            except ValueError:
                continue
            captured = parse_utc(row.get("captured_at_utc"))
            kickoff = parse_utc(row.get("kickoff_utc"))
            semantics = "CAPTURED_AT" if captured else "INVALID_OR_UNUSABLE"
            if captured and kickoff and captured > kickoff:
                semantics = "INVALID_OR_UNUSABLE"
            observations.append(
                MarketObservation(
                    source_system=source_system,
                    source_path=str(path),
                    source_sha256=source_sha,
                    fixture_source_id=str(row.get("fixture_id") or row.get("local_card_id") or ""),
                    w2_fixture_id=None,
                    mapping_status="PROVIDER_FIXTURE_ID_AVAILABLE",
                    competition="UNKNOWN_COMPETITION",
                    season="2026",
                    kickoff_utc=kickoff.isoformat().replace("+00:00", "Z") if kickoff else None,
                    bookmaker=str(row.get("bookmaker") or "UNKNOWN"),
                    market=market,
                    raw_market_label=str(row.get("market")),
                    canonical_selection=selection,
                    line=parsed_line,
                    decimal_odds=price,
                    suspended=bool(row.get("suspended")),
                    live=bool(row.get("live")),
                    event_time=None,
                    captured_at=captured.isoformat().replace("+00:00", "Z") if captured else None,
                    ingested_at=ingested_at,
                    snapshot_semantics=semantics,
                    result=None,
                    settlement_rule=settlement_rule(market),
                )
            )
    return deterministic_dedup(observations)


def normalize_api_football_odds_payload(
    path: Path,
    *,
    captured_at: str | None,
    kickoff_utc: str | None = None,
    source_system: str = "W2",
) -> list[MarketObservation]:
    source_sha = sha256_file(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    response = (payload.get("payload") or payload).get("response") or []
    ingested_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    observations: list[MarketObservation] = []
    captured = parse_utc(captured_at)
    kickoff = parse_utc(kickoff_utc)
    for fixture in response:
        fixture_id = str(
            fixture.get("fixture", {}).get("id")
            or (payload.get("payload") or payload).get("parameters", {}).get("fixture")
            or payload.get("params", {}).get("fixture")
            or ""
        )
        for bookmaker in fixture.get("bookmakers", []):
            bookmaker_name = str(bookmaker.get("name") or bookmaker.get("id") or "UNKNOWN")
            for bet in bookmaker.get("bets", []):
                market = canonical_market(str(bet.get("name", "")))
                if market is None:
                    continue
                for value in bet.get("values", []):
                    price = decimal_string(value.get("odd"))
                    if price is None:
                        continue
                    try:
                        selection, parsed_line = parse_selection_and_line(
                            market, str(value.get("value", ""))
                        )
                    except ValueError:
                        continue
                    observations.append(
                        MarketObservation(
                            source_system=source_system,
                            source_path=str(path),
                            source_sha256=source_sha,
                            fixture_source_id=fixture_id,
                            w2_fixture_id=None,
                            mapping_status="PROVIDER_FIXTURE_ID_AVAILABLE",
                            competition="UNKNOWN",
                            season=None,
                            kickoff_utc=kickoff.isoformat().replace("+00:00", "Z")
                            if kickoff
                            else None,
                            bookmaker=bookmaker_name,
                            market=market,
                            raw_market_label=str(bet.get("name")),
                            canonical_selection=selection,
                            line=parsed_line,
                            decimal_odds=price,
                            suspended=False,
                            live=False,
                            event_time=None,
                            captured_at=captured.isoformat().replace("+00:00", "Z")
                            if captured
                            else None,
                            ingested_at=ingested_at,
                            snapshot_semantics="CAPTURED_AT" if captured else "INVALID_OR_UNUSABLE",
                            result=None,
                            settlement_rule=settlement_rule(market),
                        )
                    )
    return deterministic_dedup(observations)


def settlement_rule(market: str) -> str:
    return {
        MarketType.ONE_X_TWO.value: "90_MINUTE_1X2",
        MarketType.ASIAN_HANDICAP.value: "90_MINUTE_ASIAN_HANDICAP",
        MarketType.TOTALS.value: "90_MINUTE_TOTAL_GOALS",
        MarketType.BTTS.value: "90_MINUTE_BOTH_TEAMS_TO_SCORE",
    }.get(market, "UNKNOWN")


def deterministic_dedup(observations: Iterable[MarketObservation]) -> list[MarketObservation]:
    seen: set[tuple[str, ...]] = set()
    output: list[MarketObservation] = []
    for observation in sorted(observations, key=lambda item: item.identity):
        if observation.identity in seen:
            continue
        seen.add(observation.identity)
        output.append(observation)
    return output


def inventory_source(
    path: Path, source_system: str, tracked_paths: set[str] | None = None
) -> SourceInventoryItem:
    source_sha = sha256_file(path)
    rows = sample_rows(path)
    observations = normalize_source(path, source_system=source_system)
    fixture_ids = {obs.fixture_source_id for obs in observations if obs.fixture_source_id}
    competitions = {obs.competition for obs in observations if obs.competition}
    seasons = {obs.season for obs in observations if obs.season}
    markets = Counter(obs.market for obs in observations)
    lines = sorted(
        {obs.line for obs in observations if obs.line is not None}, key=lambda value: Decimal(value)
    )
    bookmakers = {obs.bookmaker for obs in observations if obs.bookmaker}
    kickoffs = sorted(obs.kickoff_utc for obs in observations if obs.kickoff_utc)
    semantics = detect_snapshot_semantics(path, rows)
    rel = str(path)
    tracked = tracked_paths is not None and rel in tracked_paths
    return SourceInventoryItem(
        source_system=source_system,
        relative_path=rel,
        tracked=tracked,
        sha256=source_sha,
        file_format=path.suffix.lower().lstrip(".") or "unknown",
        row_count=len(rows),
        fixture_count=len(fixture_ids),
        competition_count=len(competitions),
        season_date_range={
            "seasons": ",".join(sorted(seasons)) or None,
            "earliest_kickoff_utc": kickoffs[0] if kickoffs else None,
            "latest_kickoff_utc": kickoffs[-1] if kickoffs else None,
        },
        bookmaker_count=len(bookmakers),
        market_coverage=dict(sorted(markets.items())),
        line_coverage=lines,
        decimal_odds_available=bool(observations),
        result_available=any(obs.result for obs in observations),
        event_time_field=None,
        captured_at_field="captured_at_utc" if semantics == "CAPTURED_AT" else None,
        provider_last_update_field=None,
        fixture_mapping_fields=["fixture_id", "local_card_id"]
        if semantics == "CAPTURED_AT"
        else ["homeTeam", "awayTeam", "matchDate"],
        snapshot_semantics=semantics,
        suitability=suitability_for_semantics(semantics, observations),
    )


def normalize_source(path: Path, source_system: str) -> list[MarketObservation]:
    if path.name.startswith("world_cup_odds") and path.suffix.lower() == ".csv":
        return normalize_w1_local_odds(path, source_system=source_system)
    if path.suffix.lower() == ".jsonl":
        return normalize_w1_snapshot_jsonl(path, source_system=source_system)
    if path.suffix.lower() == ".json" and "odds" in path.name.lower():
        return normalize_api_football_odds_payload(
            path, captured_at=None, source_system=source_system
        )
    return []


def sample_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    if path.suffix.lower() == ".jsonl":
        rows = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return [payload]
    return []


def suitability_for_semantics(semantics: str, observations: list[MarketObservation]) -> str:
    markets = {obs.market for obs in observations}
    if semantics == "CAPTURED_AT":
        return "phase_coverage_candidate"
    if semantics == "CLOSING":
        return "closing_baseline_only"
    if semantics == "UNKNOWN_PREMATCH_AGGREGATE":
        return "aggregate_baseline_only"
    if not markets:
        return "invalid_or_no_market_rows"
    return "manual_review_required"


def phase_coverage(observations: list[MarketObservation]) -> dict[str, Any]:
    captured = [
        obs for obs in observations if obs.snapshot_semantics == "CAPTURED_AT" and obs.captured_at
    ]
    duplicate_count = len(captured) - len({obs.identity for obs in captured})
    mapping_conflict_count = sum(
        1 for obs in captured if obs.mapping_status not in {"PROVIDER_FIXTURE_ID_AVAILABLE"}
    )
    closing_leakage_count = 0
    by_phase: dict[str, dict[str, Any]] = {}
    for phase, offset in PHASE_OFFSETS.items():
        fixture_ids: set[str] = set()
        bookmakers: set[str] = set()
        markets: Counter[str] = Counter()
        observation_count = 0
        for obs in captured:
            kickoff = parse_utc(obs.kickoff_utc)
            captured_at = parse_utc(obs.captured_at)
            if kickoff is None or captured_at is None:
                continue
            as_of = kickoff - offset
            if phase == "Closing":
                allowed = captured_at < kickoff
            else:
                allowed = captured_at <= as_of
                if obs.snapshot_semantics == "CLOSING":
                    closing_leakage_count += 1
            if not allowed:
                continue
            fixture_ids.add(obs.fixture_source_id)
            bookmakers.add(obs.bookmaker)
            markets[obs.market] += 1
            observation_count += 1
        by_phase[phase] = {
            "fixture_count": len(fixture_ids),
            "observation_count": observation_count,
            "bookmaker_count": len(bookmakers),
            "market_coverage": dict(sorted(markets.items())),
        }
    return {
        "status": "CAPTURED_AT_AVAILABLE" if captured else "NO_CAPTURED_AT_OBSERVATIONS",
        "phases": by_phase,
        "missing_captured_at_count": sum(
            1 for obs in observations if obs.snapshot_semantics != "CAPTURED_AT"
        ),
        "excluded_closing_leakage_count": closing_leakage_count,
        "mapping_conflict_count": mapping_conflict_count,
        "duplicate_count": duplicate_count,
    }


def ah_walk_forward(observations: list[MarketObservation]) -> dict[str, Any]:
    ah = [
        obs
        for obs in observations
        if obs.market == MarketType.ASIAN_HANDICAP.value
        and obs.result is not None
        and obs.line is not None
        and obs.snapshot_semantics == "CAPTURED_AT"
    ]
    if not ah:
        return {
            "status": "NO_USABLE_INTERNAL_HISTORICAL_AH_DATA",
            "sample_count": 0,
            "fixture_count": 0,
            "walk_forward_folds": 0,
            "exclusion_reasons": {
                "NO_RESULT_FOR_CAPTURED_AT_AH": sum(
                    1 for obs in observations if obs.market == MarketType.ASIAN_HANDICAP.value
                )
            },
            "candidate": False,
            "formal_recommendation": False,
        }
    settled: Counter[str] = Counter()
    for obs in ah:
        result = obs.result or {}
        outcome = settle_asian_handicap(
            result["home_goals"],
            result["away_goals"],
            obs.canonical_selection,
            Decimal(obs.line or "0"),
        )
        settled[outcome.value] += 1
    fixtures = {obs.fixture_source_id for obs in ah}
    return {
        "status": "INSUFFICIENT_COVERAGE" if len(fixtures) < 100 else "READY",
        "sample_count": len(ah),
        "fixture_count": len(fixtures),
        "walk_forward_folds": max(len(fixtures) - 32, 0),
        "settlement_distribution": dict(sorted(settled.items())),
        "candidate": False,
        "formal_recommendation": False,
    }


def observations_to_json(observations: Iterable[MarketObservation]) -> list[dict[str, Any]]:
    return [asdict(obs) for obs in deterministic_dedup(observations)]


def validate_observations(observations: list[MarketObservation]) -> dict[str, Any]:
    errors: list[str] = []
    identities = [obs.identity for obs in observations]
    if len(identities) != len(set(identities)):
        errors.append("DUPLICATE_OBSERVATION_IDENTITY")
    for obs in observations:
        if obs.candidate or obs.formal_recommendation:
            errors.append("RECOMMENDATION_FLAG_NOT_FALSE")
        if Decimal(obs.decimal_odds) <= Decimal("1"):
            errors.append("INVALID_DECIMAL_ODDS")
        if obs.snapshot_semantics not in VALID_SNAPSHOT_SEMANTICS:
            errors.append("INVALID_SNAPSHOT_SEMANTICS")
        captured = parse_utc(obs.captured_at)
        kickoff = parse_utc(obs.kickoff_utc)
        if obs.snapshot_semantics == "CAPTURED_AT" and captured and kickoff and captured > kickoff:
            errors.append("CAPTURED_AFTER_KICKOFF")
        if obs.market == MarketType.ASIAN_HANDICAP.value and obs.line is not None:
            for result in ((3, 0), (2, 0), (1, 0)):
                settle_asian_handicap(
                    result[0], result[1], obs.canonical_selection, Decimal(obs.line)
                )
        if obs.market == MarketType.TOTALS.value and obs.line is not None:
            settle_total_goals(3, obs.canonical_selection, Decimal(obs.line))
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": sorted(set(errors)),
        "observation_count": len(observations),
    }
