from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO

from w2.domain.odds import settle_asian_handicap

CANONICAL_HISTORICAL_AH_FACT_SCHEMA = "w2.canonical_historical_ah_fact.v1"
TEAM_IDENTITY_CROSSWALK_SCHEMA = "w2.team_identity_crosswalk.v1"
TEAM_VALUE_ASOF_ARTIFACT_SCHEMA = "w2.team_value_asof_artifact.v1"
CHECKPOINT_POLICY = "LATEST_COMPLETE_TWO_SIDED_QUOTE_AT_OR_BEFORE_T_MINUS_30"
SETTLEMENT_VERSION = "w2.settle_asian_handicap.v1"
APPROVED_SOURCE_STATUS = "APPROVED_CAPTURED_AT"


@dataclass(frozen=True, kw_only=True)
class HistoricalSourceAudit:
    source_id: str
    provider: str
    local_path_or_object_uri: str
    source_sha256: str | None
    schema_version: str | None
    row_count: int
    fixture_count: int
    competition_coverage: list[str]
    season_coverage: list[str]
    bookmaker_count: int
    ah_line_coverage: list[str]
    quarter_line_count: int
    captured_at_availability: bool
    result_linkage_availability: bool
    provider_fixture_id_availability: bool
    source_license_status: str
    retention_permitted: bool
    internal_backtest_permitted: bool
    source_status: str
    exclusion_reasons: list[str]


@dataclass(frozen=True, kw_only=True)
class CanonicalHistoricalAhFactV1:
    schema_version: str
    fact_id: str
    fact_hash: str
    source_snapshot_id: str
    source_id: str
    source_sha256: str
    source_license_status: str
    source_schema_version: str
    provider_fixture_id: str
    w2_fixture_id: str | None
    competition_id: str
    season: str
    kickoff_utc: str
    home_team_provider_id: str
    away_team_provider_id: str
    checkpoint_policy: str
    as_of_utc: str
    provider: str
    bookmaker_id: str
    bookmaker_name: str
    quote_captured_at: str
    home_observation_id: str
    away_observation_id: str
    quote_identity_hash: str
    home_line: str
    away_line: str
    home_decimal_odds: str
    away_decimal_odds: str
    result_status: str
    final_home_goals_90: int
    final_away_goals_90: int
    result_source_sha256: str
    result_identity_hash: str
    home_settlement: str
    away_settlement: str
    settlement_version: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def decimal_line(value: object) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed * Decimal("4") != (parsed * Decimal("4")).to_integral_value():
        return None
    return parsed


def decimal_odds(value: object) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed > Decimal("1") else None


def load_source_registry(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("sources") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return {}
    registry: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "")
        if not source_id:
            continue
        if source_id in registry:
            raise ValueError(f"DUPLICATE_SOURCE_ID:{source_id}")
        registry[source_id] = row
    return registry


def audit_formal_ah_sources(
    *,
    source_root: Path | None,
    registry_path: Path | None,
) -> dict[str, Any]:
    registry = load_source_registry(registry_path)
    if source_root is None:
        audits = [
            _blocked_source(row, "BLOCKED_SOURCE_NOT_AVAILABLE")
            for row in sorted(registry.values(), key=lambda item: str(item.get("source_id") or ""))
        ]
        return _source_audit_report(audits)
    audits = [
        audit_registered_source(source_root=source_root, metadata=row)
        for row in sorted(registry.values(), key=lambda item: str(item.get("source_id") or ""))
    ]
    return _source_audit_report(audits)


def audit_registered_source(
    *,
    source_root: Path,
    metadata: Mapping[str, Any],
) -> HistoricalSourceAudit:
    rel = str(metadata.get("local_path") or metadata.get("object_uri") or "")
    source_id = str(metadata.get("source_id") or "")
    provider = str(metadata.get("provider") or "")
    root = source_root.resolve()
    path = (root / rel).resolve() if rel else root / "__missing__"
    if root not in (path, *path.parents):
        return _blocked_source(metadata, "BLOCKED_SOURCE_OUTSIDE_ROOT")
    if not path.is_file():
        return _blocked_source(metadata, "BLOCKED_SOURCE_NOT_AVAILABLE")
    rows = read_rows(path)
    source_sha = sha256_file(path)
    ah_rows = [row for row in rows if _market(row) == "ASIAN_HANDICAP"]
    lines = sorted({_text(row.get("line")) for row in ah_rows if _text(row.get("line"))})
    fixture_ids = {_text(row.get("provider_fixture_id") or row.get("fixture_id")) for row in rows}
    competitions = sorted(
        {_text(row.get("competition_id")) for row in rows if _text(row.get("competition_id"))}
    )
    seasons = sorted({_text(row.get("season")) for row in rows if _text(row.get("season"))})
    bookmakers = {_text(row.get("bookmaker_id") or row.get("bookmaker")) for row in rows}
    has_captured = any(
        _text(row.get("captured_at") or row.get("quote_captured_at"))
        for row in ah_rows
    )
    has_result = any(_result_ready(row) for row in rows)
    has_fixture_id = all(
        _text(row.get("provider_fixture_id") or row.get("fixture_id")) for row in rows
    )
    license_status = str(metadata.get("license_status") or "UNKNOWN")
    retention = bool(metadata.get("retention_permitted") is True)
    backtest = bool(metadata.get("internal_backtest_permitted") is True)
    reasons: list[str] = []
    if not source_id or not provider or not _optional_text(metadata.get("schema_version")):
        reasons.append("BLOCKED_REGISTRY_SCHEMA_INVALID")
    if license_status != "APPROVED" or not retention or not backtest:
        reasons.append(
            "BLOCKED_LICENSE_UNKNOWN"
            if license_status == "UNKNOWN"
            else "BLOCKED_LICENSE_PROHIBITS_RETENTION"
        )
    if not has_captured:
        reasons.append("BLOCKED_MISSING_CAPTURED_AT")
    if str(metadata.get("snapshot_semantics") or "").upper() == "CLOSING":
        reasons.append("DIAGNOSTIC_CLOSING_ONLY")
    if str(metadata.get("snapshot_semantics") or "").upper() in {"AGGREGATE", "DATE_ONLY"}:
        reasons.append("BLOCKED_AGGREGATE_ONLY")
    if any(not _text(row.get("bookmaker_id") or row.get("bookmaker")) for row in ah_rows):
        reasons.append("BLOCKED_MISSING_BOOKMAKER_ID")
    if any(not _text(row.get("line")) for row in ah_rows):
        reasons.append("BLOCKED_MISSING_AH_LINE")
    if not has_result:
        reasons.append("BLOCKED_MISSING_RESULT_LINK")
    if not has_fixture_id:
        reasons.append("BLOCKED_FIXTURE_IDENTITY")
    status = APPROVED_SOURCE_STATUS if not reasons else _primary_source_status(reasons)
    return HistoricalSourceAudit(
        source_id=source_id,
        provider=provider,
        local_path_or_object_uri=str(path),
        source_sha256=source_sha,
        schema_version=_optional_text(metadata.get("schema_version")),
        row_count=len(rows),
        fixture_count=len({item for item in fixture_ids if item}),
        competition_coverage=competitions,
        season_coverage=seasons,
        bookmaker_count=len({item for item in bookmakers if item}),
        ah_line_coverage=lines,
        quarter_line_count=sum(1 for line in lines if decimal_line(line) is not None),
        captured_at_availability=has_captured,
        result_linkage_availability=has_result,
        provider_fixture_id_availability=has_fixture_id,
        source_license_status=license_status,
        retention_permitted=retention,
        internal_backtest_permitted=backtest,
        source_status=status,
        exclusion_reasons=sorted(set(reasons)),
    )


def build_canonical_ah_facts(
    *,
    source_root: Path,
    registry_path: Path,
) -> dict[str, Any]:
    registry = load_source_registry(registry_path)
    audits = [
        audit_registered_source(source_root=source_root, metadata=row)
        for row in sorted(registry.values(), key=lambda item: str(item.get("source_id") or ""))
    ]
    facts: list[CanonicalHistoricalAhFactV1] = []
    exclusions: Counter[str] = Counter()
    seen_fact_hashes: set[str] = set()
    for audit in audits:
        if audit.source_status != APPROVED_SOURCE_STATUS:
            exclusions.update(audit.exclusion_reasons or [audit.source_status])
            continue
        source_meta = registry[audit.source_id]
        path = Path(audit.local_path_or_object_uri)
        rows = read_rows(path)
        result_rows, result_conflicts = _result_rows_by_fixture(rows)
        exclusions.update(result_conflicts)
        for fixture_id, fixture_rows in _group_rows(rows).items():
            result = result_rows.get(fixture_id)
            if result is None:
                exclusions["missing_result"] += 1
                continue
            built, reason = _fact_for_fixture(
                audit=audit,
                source_meta=source_meta,
                fixture_rows=fixture_rows,
                result=result,
            )
            if built is None:
                exclusions[reason or "excluded"] += 1
                continue
            if built.fact_hash in seen_fact_hashes:
                exclusions["duplicate"] += 1
                continue
            seen_fact_hashes.add(built.fact_hash)
            facts.append(built)
    report = canonical_fact_audit([asdict(item) for item in facts], audits, exclusions)
    return {"facts": [asdict(item) for item in facts], "audit": report}


def canonical_fact_audit(
    facts: list[dict[str, Any]],
    source_audits: list[HistoricalSourceAudit],
    exclusions: Counter[str] | None = None,
) -> dict[str, Any]:
    exclusions = exclusions or Counter()
    competitions = Counter(str(item.get("competition_id") or "") for item in facts)
    seasons = Counter(str(item.get("season") or "") for item in facts)
    bookmakers = Counter(str(item.get("bookmaker_id") or "") for item in facts)
    lines = Counter(str(item.get("home_line") or "") for item in facts)
    kickoffs = sorted(
        str(item.get("kickoff_utc") or "") for item in facts if item.get("kickoff_utc")
    )
    teams = sorted(
        {
            str(item.get("home_team_provider_id") or "")
            for item in facts
        }
        | {str(item.get("away_team_provider_id") or "") for item in facts}
    )
    manifest_hash = stable_hash({"facts": sorted(item["fact_hash"] for item in facts)})
    return {
        "schema_version": "w2.fah02.canonical_ah_fact_audit.v1",
        "status": "PASS" if facts else "SOURCE_NOT_AVAILABLE",
        "source_input_rows": sum(item.row_count for item in source_audits),
        "approved_source_rows": sum(
            item.row_count
            for item in source_audits
            if item.source_status == APPROVED_SOURCE_STATUS
        ),
        "canonical_fact_count": len(facts),
        "unique_fixture_count": len({item.get("provider_fixture_id") for item in facts}),
        "competitions": dict(sorted(competitions.items())),
        "seasons": dict(sorted(seasons.items())),
        "bookmakers": dict(sorted(bookmakers.items())),
        "line_buckets": dict(sorted(lines.items())),
        "quarter_line_count": sum(1 for line in lines if decimal_line(line) is not None),
        "team_coverage": teams,
        "earliest_kickoff": kickoffs[0] if kickoffs else None,
        "latest_kickoff": kickoffs[-1] if kickoffs else None,
        "duplicate_count": exclusions.get("duplicate", 0),
        "quote_conflicts": exclusions.get("quote_conflict", 0),
        "result_conflicts": exclusions.get("result_conflict", 0),
        "fixture_mapping_conflicts": exclusions.get("fixture_mapping_conflict", 0),
        "post_kickoff_quote_exclusions": exclusions.get("post_kickoff_quote", 0),
        "closing_only_exclusions": exclusions.get("DIAGNOSTIC_CLOSING_ONLY", 0),
        "aggregate_only_exclusions": exclusions.get("BLOCKED_AGGREGATE_ONLY", 0),
        "license_exclusions": exclusions.get("BLOCKED_LICENSE_UNKNOWN", 0)
        + exclusions.get("BLOCKED_LICENSE_PROHIBITS_RETENTION", 0),
        "missing_result_exclusions": exclusions.get("missing_result", 0),
        "exclusions": dict(sorted(exclusions.items())),
        "fact_manifest_hash": manifest_hash,
        "sample_fact_hashes": sorted(item["fact_hash"] for item in facts)[:10],
    }


def write_audit_outputs(payload: Mapping[str, Any], *, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    md_path.write_text(_markdown_summary(payload), encoding="utf-8")


def read_rows(path: Path) -> list[dict[str, Any]]:
    suffix = "".join(path.suffixes[-2:]) if path.suffix == ".gz" else path.suffix
    if suffix in {".jsonl", ".jsonl.gz"}:
        return [json.loads(line) for line in _read_text(path).splitlines() if line.strip()]
    if suffix in {".json", ".json.gz"}:
        payload = json.loads(_read_text(path))
        return payload if isinstance(payload, list) else list(payload.get("rows", []))
    if suffix in {".csv", ".csv.gz"}:
        with _open_text(path) as handle:
            return list(csv.DictReader(handle))
    return []


def _fact_for_fixture(
    *,
    audit: HistoricalSourceAudit,
    source_meta: Mapping[str, Any],
    fixture_rows: list[dict[str, Any]],
    result: Mapping[str, Any],
) -> tuple[CanonicalHistoricalAhFactV1 | None, str | None]:
    ah = [row for row in fixture_rows if _market(row) == "ASIAN_HANDICAP"]
    kickoff = parse_utc(_first(row.get("kickoff_utc") for row in fixture_rows))
    if kickoff is None:
        return None, "fixture_mapping_conflict"
    fixture_reason = _fixture_identity_conflict(fixture_rows)
    if fixture_reason is not None:
        return None, fixture_reason
    eligible = [
        row
        for row in ah
        if _quote_row_valid(row, kickoff=kickoff)
        and _text(row.get("bookmaker_id") or row.get("bookmaker"))
    ]
    if not eligible:
        return None, "post_kickoff_quote"
    by_pair: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        pair_key = (
            _text(row.get("provider") or audit.provider),
            _fixture_id(row),
            _text(row.get("bookmaker_id") or row.get("bookmaker")),
            _text(row.get("captured_at") or row.get("quote_captured_at")),
        )
        by_pair[pair_key].append(row)
    pairs: list[tuple[datetime, dict[str, Any], dict[str, Any]]] = []
    for pair_rows in by_pair.values():
        home_rows = [row for row in pair_rows if _side(row) == "HOME"]
        away_rows = [row for row in pair_rows if _side(row) == "AWAY"]
        for home in home_rows:
            for away in away_rows:
                home_line = decimal_line(home.get("line"))
                away_line = decimal_line(away.get("line"))
                captured = parse_utc(home.get("captured_at") or home.get("quote_captured_at"))
                if (
                    home_line is not None
                    and away_line is not None
                    and home_line == -away_line
                    and captured is not None
                ):
                    pairs.append((captured, home, away))
    if not pairs:
        return None, "quote_conflict"
    pairs.sort(key=lambda item: (item[0], _text(item[1].get("observation_id"))), reverse=True)
    if len(pairs) > 1 and pairs[0][0] == pairs[1][0]:
        return None, "quote_conflict"
    captured, home, away = pairs[0]
    if _text(home.get("observation_id")) == _text(away.get("observation_id")):
        return None, "quote_conflict"
    pair_reason = _quote_pair_identity_conflict(home, away, audit)
    if pair_reason is not None:
        return None, pair_reason
    result_status = _text(result.get("result_status") or result.get("status"))
    if result_status not in {"FINAL", "FT"}:
        return None, "result_conflict"
    try:
        home_goals = int(result["final_home_goals_90"])
        away_goals = int(result["final_away_goals_90"])
    except (KeyError, TypeError, ValueError):
        return None, "result_conflict"
    home_line_value = decimal_line(home.get("line"))
    away_line_value = decimal_line(away.get("line"))
    if home_line_value is None or away_line_value is None:
        return None, "quote_conflict"
    home_line_text = str(home_line_value)
    away_line_text = str(away_line_value)
    home_settlement = settle_asian_handicap(
        home_goals,
        away_goals,
        "HOME",
        home_line_value,
    )
    away_settlement = settle_asian_handicap(
        home_goals,
        away_goals,
        "AWAY",
        away_line_value,
    )
    source_sha = audit.source_sha256 or ""
    result_sha = _text(result.get("result_source_sha256") or source_sha)
    quote_identity = {
        "provider_fixture_id": _fixture_id(home),
        "provider": audit.provider,
        "bookmaker_id": _text(home.get("bookmaker_id") or home.get("bookmaker")),
        "captured_at": iso(captured),
        "home_observation_id": _text(home.get("observation_id")),
        "away_observation_id": _text(away.get("observation_id")),
        "home_line": home_line_text,
        "away_line": away_line_text,
        "home_decimal_odds": str(decimal_odds(home.get("decimal_odds"))),
        "away_decimal_odds": str(decimal_odds(away.get("decimal_odds"))),
        "source_id": audit.source_id,
        "source_snapshot_id": str(source_meta.get("source_snapshot_id") or audit.source_id),
        "source_sha256": source_sha,
    }
    quote_hash = stable_hash(quote_identity)
    result_hash = stable_hash(
        {
            "provider_fixture_id": _fixture_id(home),
            "result_source_sha256": result_sha,
            "home": home_goals,
            "away": away_goals,
            "status": result_status,
        }
    )
    core = {
        "fixture_identity": {
            "provider_fixture_id": _fixture_id(home),
            "competition_id": _text(home.get("competition_id")),
            "season": _text(home.get("season")),
            "kickoff_utc": iso(kickoff),
            "home_team_provider_id": _text(home.get("home_team_provider_id")),
            "away_team_provider_id": _text(home.get("away_team_provider_id")),
        },
        "quote_identity_hash": quote_hash,
        "checkpoint_policy": CHECKPOINT_POLICY,
        "as_of_utc": iso(captured),
        "result_identity_hash": result_hash,
        "home_settlement": home_settlement.value,
        "away_settlement": away_settlement.value,
        "settlement_version": SETTLEMENT_VERSION,
        "source_id": audit.source_id,
        "source_sha256": source_sha,
        "source_license_status": audit.source_license_status,
    }
    fact_hash = stable_hash(core)
    return (
        CanonicalHistoricalAhFactV1(
            schema_version=CANONICAL_HISTORICAL_AH_FACT_SCHEMA,
            fact_id=f"canonical-ah:{fact_hash}",
            fact_hash=fact_hash,
            source_snapshot_id=str(source_meta.get("source_snapshot_id") or audit.source_id),
            source_id=audit.source_id,
            source_sha256=source_sha,
            source_license_status=audit.source_license_status,
            source_schema_version=audit.schema_version or "",
            provider_fixture_id=_fixture_id(home),
            w2_fixture_id=_optional_text(home.get("w2_fixture_id")),
            competition_id=_text(home.get("competition_id")),
            season=_text(home.get("season")),
            kickoff_utc=iso(kickoff),
            home_team_provider_id=_text(home.get("home_team_provider_id")),
            away_team_provider_id=_text(home.get("away_team_provider_id")),
            checkpoint_policy=CHECKPOINT_POLICY,
            as_of_utc=iso(captured),
            provider=audit.provider,
            bookmaker_id=_text(home.get("bookmaker_id") or home.get("bookmaker")),
            bookmaker_name=_text(home.get("bookmaker_name") or home.get("bookmaker")),
            quote_captured_at=iso(captured),
            home_observation_id=_text(home.get("observation_id")),
            away_observation_id=_text(away.get("observation_id")),
            quote_identity_hash=quote_hash,
            home_line=home_line_text,
            away_line=away_line_text,
            home_decimal_odds=str(decimal_odds(home.get("decimal_odds"))),
            away_decimal_odds=str(decimal_odds(away.get("decimal_odds"))),
            result_status=result_status,
            final_home_goals_90=home_goals,
            final_away_goals_90=away_goals,
            result_source_sha256=result_sha,
            result_identity_hash=result_hash,
            home_settlement=home_settlement.value,
            away_settlement=away_settlement.value,
            settlement_version=SETTLEMENT_VERSION,
        ),
        None,
    )


def _source_audit_report(audits: list[HistoricalSourceAudit]) -> dict[str, Any]:
    approved = [item for item in audits if item.source_status == APPROVED_SOURCE_STATUS]
    return {
        "schema_version": "w2.fah02.source_audit.v1",
        "status": "PASS" if approved else "SOURCE_NOT_AVAILABLE",
        "approved_source_count": len(approved),
        "sources": [asdict(item) for item in audits],
        "blocked_reasons": dict(
            Counter(reason for item in audits for reason in item.exclusion_reasons)
        ),
    }


def _blocked_source(metadata: Mapping[str, Any], reason: str) -> HistoricalSourceAudit:
    return HistoricalSourceAudit(
        source_id=str(metadata.get("source_id") or ""),
        provider=str(metadata.get("provider") or ""),
        local_path_or_object_uri=str(
            metadata.get("local_path") or metadata.get("object_uri") or ""
        ),
        source_sha256=None,
        schema_version=_optional_text(metadata.get("schema_version")),
        row_count=0,
        fixture_count=0,
        competition_coverage=[],
        season_coverage=[],
        bookmaker_count=0,
        ah_line_coverage=[],
        quarter_line_count=0,
        captured_at_availability=False,
        result_linkage_availability=False,
        provider_fixture_id_availability=False,
        source_license_status=str(metadata.get("license_status") or "UNKNOWN"),
        retention_permitted=bool(metadata.get("retention_permitted") is True),
        internal_backtest_permitted=bool(metadata.get("internal_backtest_permitted") is True),
        source_status=reason,
        exclusion_reasons=[reason],
    )


def _primary_source_status(reasons: list[str]) -> str:
    for candidate in (
        "BLOCKED_SOURCE_OUTSIDE_ROOT",
        "BLOCKED_REGISTRY_SCHEMA_INVALID",
        "DIAGNOSTIC_CLOSING_ONLY",
        "BLOCKED_LICENSE_UNKNOWN",
        "BLOCKED_LICENSE_PROHIBITS_RETENTION",
        "BLOCKED_MISSING_CAPTURED_AT",
        "BLOCKED_AGGREGATE_ONLY",
        "BLOCKED_MISSING_BOOKMAKER_ID",
        "BLOCKED_MISSING_AH_LINE",
        "BLOCKED_MISSING_RESULT_LINK",
        "BLOCKED_FIXTURE_IDENTITY",
    ):
        if candidate in reasons:
            return candidate
    return reasons[0]


def _quote_row_valid(row: Mapping[str, Any], *, kickoff: datetime) -> bool:
    captured = parse_utc(row.get("captured_at") or row.get("quote_captured_at"))
    return bool(
        captured is not None
        and captured <= kickoff - timedelta(minutes=30)
        and decimal_line(row.get("line")) is not None
        and decimal_odds(row.get("decimal_odds")) is not None
        and not _truthy(row.get("live"))
        and not _truthy(row.get("suspended"))
        and _text(row.get("observation_id"))
    )


def _group_rows(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_fixture_id(row)].append(row)
    return dict(grouped)


def _fixture_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("provider_fixture_id") or row.get("fixture_id"))


def _market(row: Mapping[str, Any]) -> str:
    text = _text(row.get("market")).upper().replace("AH", "ASIAN_HANDICAP")
    return "ASIAN_HANDICAP" if text in {"ASIAN_HANDICAP", "ASIAN HANDICAP"} else text


def _side(row: Mapping[str, Any]) -> str:
    return _text(row.get("side") or row.get("selection")).upper().replace("_AH", "")


def _result_ready(row: Mapping[str, Any]) -> bool:
    return _text(row.get("result_status") or row.get("status")).upper() in {"FINAL", "FT"} and (
        row.get("final_home_goals_90") is not None and row.get("final_away_goals_90") is not None
    )


def _result_rows_by_fixture(
    rows: Iterable[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], Counter[str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if _result_ready(row):
            grouped[_fixture_id(row)].append(row)
    output: dict[str, dict[str, Any]] = {}
    exclusions: Counter[str] = Counter()
    for fixture_id, fixture_rows in grouped.items():
        identities = {
            stable_hash(
                {
                    "status": _text(row.get("result_status") or row.get("status")),
                    "home": _text(row.get("final_home_goals_90")),
                    "away": _text(row.get("final_away_goals_90")),
                    "source": _text(row.get("result_source_sha256") or row.get("_source_sha256")),
                }
            )
            for row in fixture_rows
        }
        if len(identities) > 1:
            exclusions["result_conflict"] += 1
            continue
        output[fixture_id] = fixture_rows[0]
    return output, exclusions


def _fixture_identity_conflict(rows: Sequence[Mapping[str, Any]]) -> str | None:
    fields = (
        "provider_fixture_id",
        "competition_id",
        "season",
        "kickoff_utc",
        "home_team_provider_id",
        "away_team_provider_id",
    )
    for field in fields:
        values = {_text(row.get(field)) for row in rows if _text(row.get(field))}
        if len(values) > 1:
            return "fixture_mapping_conflict"
    return None


def _quote_pair_identity_conflict(
    home: Mapping[str, Any],
    away: Mapping[str, Any],
    audit: HistoricalSourceAudit,
) -> str | None:
    fields = (
        "provider_fixture_id",
        "competition_id",
        "season",
        "kickoff_utc",
        "home_team_provider_id",
        "away_team_provider_id",
        "bookmaker_id",
    )
    for field in fields:
        if _text(home.get(field)) != _text(away.get(field)):
            return "quote_conflict"
    if _text(home.get("captured_at") or home.get("quote_captured_at")) != _text(
        away.get("captured_at") or away.get("quote_captured_at")
    ):
        return "quote_conflict"
    if _text(home.get("provider") or audit.provider) != _text(
        away.get("provider") or audit.provider
    ):
        return "quote_conflict"
    if _text(home.get("_source_sha256") or audit.source_sha256) != _text(
        away.get("_source_sha256") or audit.source_sha256
    ):
        return "quote_conflict"
    return None


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def _read_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return handle.read()
    return path.read_text(encoding="utf-8")


def _first(values: Iterable[object]) -> object | None:
    return next((value for value in values if value not in {None, ""}), None)


def _text(value: object) -> str:
    return str(value).strip() if value not in {None, ""} else ""


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _truthy(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _markdown_summary(payload: Mapping[str, Any]) -> str:
    status = payload.get("status")
    lines = [f"# {payload.get('schema_version', 'FAH audit')}", "", f"- status: {status}"]
    for key in (
        "approved_source_count",
        "canonical_fact_count",
        "unique_fixture_count",
        "fact_manifest_hash",
    ):
        if key in payload:
            lines.append(f"- {key}: {payload[key]}")
    if "blocked_reasons" in payload:
        lines.append(f"- blocked_reasons: {payload['blocked_reasons']}")
    if "exclusions" in payload:
        lines.append(f"- exclusions: {payload['exclusions']}")
    return "\n".join(lines) + "\n"
