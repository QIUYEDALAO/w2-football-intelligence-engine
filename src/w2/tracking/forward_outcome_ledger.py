from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from w2.domain.canonical_decision_projection import project_canonical_decision
from w2.domain.odds import settle_asian_handicap, settle_total_goals

SCHEMA_VERSION = "w2.forward_outcome_ledger.v3"
DEFAULT_LEDGER_DIR = Path("runtime/forward_outcome_ledger")
SETTLED_STATUSES = {"FT", "AET", "PEN"}
VOID_STATUSES = {"CANC", "ABD", "AWD", "WO"}
SUPPORTED_MARKETS = {"ASIAN_HANDICAP", "TOTALS"}


def run_forward_outcome_ledger(
    day_view: Mapping[str, Any],
    *,
    dry_run: bool = True,
    write_artifacts: bool = False,
    runtime_root: Path | None = None,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    resolved_captured_at = (captured_at or datetime.now(UTC)).astimezone(UTC)
    root = runtime_root or Path.cwd() / DEFAULT_LEDGER_DIR
    records = build_forward_outcome_records(
        day_view,
        captured_at=resolved_captured_at,
    )
    written = 0
    skipped_existing = 0
    output_file = _ledger_path(root, day_view)
    if write_artifacts and not dry_run:
        existing_keys = _existing_keys(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("a", encoding="utf-8") as handle:
            for record in records:
                key = _record_key(record)
                if key in existing_keys:
                    skipped_existing += 1
                    continue
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                existing_keys.add(key)
                written += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "dry_run": bool(dry_run),
        "write_artifacts": bool(write_artifacts),
        "provider_calls": 0,
        "db_writes": 0,
        "lock_capture_write": False,
        "settlement_write": False,
        "runtime_root": str(root),
        "output_file": str(output_file),
        "record_count": len(records),
        "written": written,
        "skipped_existing": skipped_existing,
        "records": records if dry_run or not write_artifacts else [],
    }


def build_forward_outcome_records(
    day_view: Mapping[str, Any],
    *,
    captured_at: datetime,
) -> list[dict[str, Any]]:
    captured = captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    football_day = _text(day_view.get("football_day") or day_view.get("date"))
    environment = _text(day_view.get("environment") or "unknown")
    rows: list[dict[str, Any]] = []
    for card in _cards(day_view):
        fixture_id = _text(card.get("fixture_id"))
        if not fixture_id:
            continue
        v3 = _mapping(card.get("recommendation_decision_v3"))
        canonical = project_canonical_decision(v3) if v3 else {}
        shadow_pick = canonical.get("pick") if v3 else _shadow_pick(card)
        recommendation_scope = _recommendation_scope(card, shadow_pick)
        fixture_identity = _fixture_identity(card)
        quote_provenance = _quote_provenance(card)
        artifact_provenance = _artifact_provenance(card)
        probability_identity = _probability_identity(card)
        capture_identity = {
            "fixture_identity": fixture_identity,
            "recommendation_scope": recommendation_scope,
            "pick": _mapping_copy(card.get("pick")),
            "secondary_picks": _secondary_picks(card),
            "shadow_pick": shadow_pick,
            "quote_provenance": quote_provenance,
            "artifact_provenance": artifact_provenance,
            "probability_identity": probability_identity,
            "card_hash": _optional_text(card.get("card_hash")),
            "captured_at": captured,
        }
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "record_type": "capture",
                "captured_at": captured,
                "football_day": football_day,
                "environment": environment,
                "fixture_id": fixture_id,
                "kickoff_utc": _optional_text(card.get("kickoff_utc")),
                "competition_id": _optional_text(card.get("competition_id")),
                "competition_name": _optional_text(card.get("competition_name")),
                "home_team_name": _optional_text(card.get("home_team_name")),
                "away_team_name": _optional_text(card.get("away_team_name")),
                "decision_tier": _text(
                    canonical.get("decision_tier") or card.get("decision_tier") or "SKIP"
                ),
                "data_status": _text(card.get("data_status") or "PARTIAL"),
                "reason_code": _optional_text(
                    canonical.get("reason_code") or card.get("reason_code")
                ),
                "action": _optional_text(canonical.get("next_action") or card.get("action")),
                "probability_source": _optional_text(card.get("probability_source")),
                "model_market_divergence": _mapping_copy(card.get("model_market_divergence")),
                "shadow_pick": shadow_pick,
                "pick": _mapping_copy(shadow_pick),
                "secondary_picks": _secondary_picks(card),
                "non_pick": _mapping_copy(card.get("non_pick")),
                "current_odds": _market_odds_summary(card.get("current_odds")),
                "card_hash": _optional_text(card.get("card_hash")),
                "recommendation_scope": recommendation_scope,
                "fixture_identity": fixture_identity,
                "quote_provenance": quote_provenance,
                "artifact_provenance": artifact_provenance,
                "probability_identity": probability_identity,
                "capture_identity_hash": _canonical_sha256(capture_identity),
                "outcome_tracked": bool(canonical.get("outcome_tracked"))
                if v3
                else bool(card.get("outcome_tracked") is True),
                "lock_eligible": bool(canonical.get("lock_eligible"))
                if v3
                else bool(card.get("lock_eligible") is True),
                "decision_hash": _optional_text(
                    canonical.get("decision_hash") or v3.get("decision_hash")
                ),
                "recommendation_id": _optional_text(card.get("recommendation_id")),
                "source": _optional_text(card.get("source")),
                "posthoc_only": True,
                "not_a_lock": True,
            }
        )
    return rows


def backfill_outcomes(
    runtime_root: Path,
    day_view_or_results_source: Mapping[str, Any],
    *,
    dry_run: bool = True,
    write_artifacts: bool = False,
    settled_at: datetime | None = None,
) -> dict[str, Any]:
    root = runtime_root / "forward_outcome_ledger"
    resolved_settled_at = (settled_at or datetime.now(UTC)).astimezone(UTC)
    results = _finished_results(day_view_or_results_source)
    ledger_rows = _ledger_rows_by_file(root)
    pending_before = _pending_entries(ledger_rows)
    outcome_records: list[tuple[Path, dict[str, Any]]] = []
    for path, entry, side, item in pending_before.values():
        result = results.get(_text(entry.get("fixture_id")))
        if result is None:
            continue
        record = _outcome_record(
            entry,
            side=side,
            item=item,
            result=result,
            settled_at=resolved_settled_at,
        )
        if record is not None:
            outcome_records.append((path, record))

    written = 0
    skipped_existing = 0
    if write_artifacts and not dry_run:
        existing_by_path = {path: _existing_keys(path) for path in ledger_rows}
        for path, record in outcome_records:
            existing_keys = existing_by_path.setdefault(path, _existing_keys(path))
            key = _record_key(record)
            if key in existing_keys:
                skipped_existing += 1
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            _append_jsonl_record(path, record)
            existing_keys.add(key)
            written += 1

    processed_keys = {_settlement_identity(record) for _, record in outcome_records}
    processed_fixture_counts: dict[str, int] = {}
    for _, record in outcome_records:
        fixture_id = _text(record.get("fixture_id"))
        if fixture_id:
            processed_fixture_counts[fixture_id] = processed_fixture_counts.get(fixture_id, 0) + 1
    unresolved_count = sum(1 for identity in pending_before if identity not in processed_keys)
    if not pending_before:
        status = "NO_DUE_WORK"
    elif unresolved_count:
        status = "PARTIAL"
    else:
        status = "PASS"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "dry_run": bool(dry_run),
        "write_artifacts": bool(write_artifacts),
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "lock_capture_write": False,
        "settlement_write": False,
        "runtime_root": str(runtime_root),
        "result_fixture_count": len(results),
        "pending_count": len(pending_before),
        "unresolved_count": unresolved_count,
        "record_count": len(outcome_records),
        "processed_fixture_counts": processed_fixture_counts,
        "written": written,
        "skipped_existing": skipped_existing,
        "records": [record for _, record in outcome_records]
        if dry_run or not write_artifacts
        else [],
    }


def _ledger_path(root: Path, day_view: Mapping[str, Any]) -> Path:
    football_day = _text(day_view.get("football_day") or day_view.get("date") or "unknown")
    environment = _text(day_view.get("environment") or "unknown")
    return root / f"{football_day}_{environment}.jsonl"


def _existing_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, Mapping):
            keys.add(_record_key(record))
    return keys


def _record_key(record: Mapping[str, Any]) -> str:
    record_type = _text(record.get("record_type") or "capture")
    parts = [
        _text(record.get("football_day")),
        _text(record.get("environment")),
        _text(record.get("fixture_id")),
        _text(record.get("card_hash") or record.get("captured_at")),
        record_type,
    ]
    if record_type == "outcome":
        parts.extend(
            [
                _text(record.get("settled_side")),
                _text(record.get("market")),
                _text(record.get("selection")),
            ]
        )
    return "|".join(parts)


def _ledger_rows_by_file(root: Path) -> dict[Path, list[dict[str, Any]]]:
    if not root.exists():
        return {}
    rows: dict[Path, list[dict[str, Any]]] = {}
    for path in sorted(root.glob("*.jsonl")):
        items: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    items.append(record)
        rows[path] = items
    return rows


def _append_jsonl_record(path: Path, record: Mapping[str, Any]) -> None:
    needs_newline = path.exists() and path.stat().st_size > 0
    if needs_newline:
        with path.open("rb") as handle:
            handle.seek(-1, 2)
            needs_newline = handle.read(1) != b"\n"
    with path.open("a", encoding="utf-8") as handle:
        if needs_newline:
            handle.write("\n")
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _settlement_entries(
    records: Sequence[Mapping[str, Any]],
    results: Mapping[str, Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], str, Mapping[str, Any]]]:
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    conflicted_validation = _conflicted_validation_fixtures(records)
    for record in records:
        if _text(record.get("record_type") or "capture") != "capture":
            continue
        fixture_id = _text(record.get("fixture_id"))
        if fixture_id not in results:
            continue
        sides = [("shadow_pick", record.get("shadow_pick"))]
        schema_version = _text(record.get("schema_version"))
        legacy_capture = schema_version in {
            "w2.forward_outcome_ledger.v1",
            "w2.forward_outcome_ledger.v2",
        }
        scope = _text(record.get("recommendation_scope")).upper()
        legacy_tracked = legacy_capture and (
            scope in {"VALIDATION", "OFFICIAL"}
            or (
                _text(record.get("decision_tier")).upper() in {"ANALYSIS_PICK", "RECOMMEND"}
                and record.get("outcome_tracked") is True
            )
        )
        if legacy_tracked or (
            record.get("outcome_tracked") is True and scope in {"VALIDATION", "OFFICIAL"}
        ):
            if fixture_id not in conflicted_validation:
                sides.insert(0, ("pick", record.get("pick")))
        for side, item in sides:
            if not isinstance(item, Mapping):
                continue
            market = _text(item.get("market"))
            selection = _text(item.get("selection"))
            if market not in SUPPORTED_MARKETS or not selection:
                continue
            grouped.setdefault((fixture_id, side, market, selection), []).append(record)

    entries: list[tuple[Mapping[str, Any], str, Mapping[str, Any]]] = []
    for (_, side, _, _), items in grouped.items():
        ordered = sorted(
            items,
            key=lambda item: (
                _parse_time(item.get("captured_at")) or datetime.min.replace(tzinfo=UTC)
            ),
        )
        entry = _entry_record(ordered)
        pick_item = entry.get(side)
        if isinstance(pick_item, Mapping):
            entries.append((entry, side, pick_item))
    return entries


def _conflicted_validation_fixtures(
    records: Sequence[Mapping[str, Any]],
) -> set[str]:
    signatures: dict[str, set[tuple[str, ...]]] = {}
    for record in records:
        if _text(record.get("record_type") or "capture") != "capture":
            continue
        if _text(record.get("recommendation_scope")).upper() != "VALIDATION":
            continue
        fixture_id = _text(record.get("fixture_id"))
        pick = record.get("pick")
        if not fixture_id or not isinstance(pick, Mapping):
            continue
        market = _text(pick.get("market"))
        selection = _text(pick.get("selection"))
        quote = _quote(record, market, selection)
        identity = _mapping(record.get("fixture_identity"))
        signature = (
            market,
            selection,
            quote[0] if quote else "",
            _text(identity.get("kickoff_utc") or record.get("kickoff_utc")),
            _text(identity.get("competition_id") or record.get("competition_id")),
            _text(identity.get("home_team_name") or record.get("home_team_name")),
            _text(identity.get("away_team_name") or record.get("away_team_name")),
        )
        signatures.setdefault(fixture_id, set()).add(signature)
    return {
        fixture_id
        for fixture_id, values in signatures.items()
        if len(values) != 1 or any(not all(signature) for signature in values)
    }


def _outcome_record(
    entry: Mapping[str, Any],
    *,
    side: str,
    item: Mapping[str, Any],
    result: Mapping[str, Any],
    settled_at: datetime,
) -> dict[str, Any] | None:
    market = _text(item.get("market"))
    selection = _text(item.get("selection"))
    quote = _quote(entry, market, selection)
    status = _text(result.get("status") or "FT").upper()
    void_reason = _optional_text(result.get("void_reason"))
    home_goals = _int(result.get("home_goals"))
    away_goals = _int(result.get("away_goals"))
    final_score = {
        "home": home_goals,
        "away": away_goals,
        "status": status,
    }
    recommendation_scope = _outcome_scope(entry, side)
    base = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "outcome",
        "settled_at": settled_at.isoformat().replace("+00:00", "Z"),
        "football_day": _text(entry.get("football_day")),
        "environment": _text(entry.get("environment")),
        "fixture_id": _text(entry.get("fixture_id")),
        "competition_id": _optional_text(entry.get("competition_id")),
        "competition_name": _optional_text(entry.get("competition_name")),
        "card_hash": _optional_text(entry.get("card_hash")),
        "capture_identity_hash": _optional_text(entry.get("capture_identity_hash")),
        "recommendation_scope": recommendation_scope,
        "fixture_identity": _mapping_copy(entry.get("fixture_identity")),
        "quote_provenance": _mapping_copy(entry.get("quote_provenance")),
        "artifact_provenance": _mapping_copy(entry.get("artifact_provenance")),
        "probability_identity": _mapping_copy(entry.get("probability_identity")),
        "market": market,
        "selection": selection,
        "settled_side": side,
        "final_score": final_score,
        "provider_calls": 0,
        "db_writes": 0,
        "lock_capture_write": False,
        "settlement_write": False,
    }
    if void_reason or status in VOID_STATUSES:
        return {
            **base,
            "settlement_outcome": "VOID",
            "void_reason": void_reason or f"TERMINAL_STATUS_{status}",
        }
    if home_goals is None or away_goals is None:
        return None
    if quote is None:
        return None
    line, _price = quote
    settlement_selection = _settlement_selection(market, selection)
    decimal_line = _decimal(line)
    if settlement_selection is None or decimal_line is None:
        return None
    if market == "ASIAN_HANDICAP":
        outcome = settle_asian_handicap(
            home_goals,
            away_goals,
            settlement_selection,
            decimal_line,
        )
    else:
        outcome = settle_total_goals(
            home_goals + away_goals,
            settlement_selection,
            decimal_line,
        )
    return {
        **base,
        "entry_line": line,
        "entry_price": _price,
        "settlement_outcome": outcome.value,
    }


def _finished_results(source: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    candidates: list[Mapping[str, Any]] = []
    for key in ("cards", "results", "fixtures"):
        value = source.get(key)
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            candidates.extend(item for item in value if isinstance(item, Mapping))
    if not candidates and source:
        candidates.append(source)
    for item in candidates:
        fixture_id = _fixture_id(item)
        status = _status(item)
        score = _score(item)
        void_reason = _optional_text(item.get("void_reason"))
        if not fixture_id:
            continue
        if status in VOID_STATUSES or void_reason:
            results[fixture_id] = {
                "fixture_id": fixture_id,
                "status": status or "VOID",
                "home_goals": None,
                "away_goals": None,
                "void_reason": void_reason or f"TERMINAL_STATUS_{status}",
            }
            continue
        if status not in SETTLED_STATUSES or score is None:
            continue
        home_goals, away_goals = score
        results[fixture_id] = {
            "fixture_id": fixture_id,
            "status": status,
            "home_goals": home_goals,
            "away_goals": away_goals,
        }
    return results


def _fixture_id(item: Mapping[str, Any]) -> str:
    fixture = item.get("fixture")
    if isinstance(fixture, Mapping):
        value = fixture.get("id")
        if value is not None:
            return _text(value)
    return _text(item.get("fixture_id") or item.get("id"))


def _status(item: Mapping[str, Any]) -> str:
    fixture = item.get("fixture")
    if isinstance(fixture, Mapping):
        status = fixture.get("status")
        if isinstance(status, Mapping):
            return _text(status.get("short")).upper()
        value = fixture.get("status")
        if value is not None:
            return _text(value).upper()
    return _text(item.get("status") or item.get("result_status")).upper()


def _score(item: Mapping[str, Any]) -> tuple[int, int] | None:
    direct = _score_pair(item.get("home_score"), item.get("away_score"))
    if direct is not None:
        return direct
    score = item.get("score")
    if isinstance(score, Mapping):
        for key in ("fulltime", "full_time", "ft"):
            value = score.get(key)
            if isinstance(value, Mapping):
                pair = _score_pair(value.get("home"), value.get("away"))
                if pair is not None:
                    return pair
        pair = _score_pair(score.get("home"), score.get("away"))
        if pair is not None:
            return pair
    goals = item.get("goals")
    if isinstance(goals, Mapping):
        pair = _score_pair(goals.get("home"), goals.get("away"))
        if pair is not None:
            return pair
    result = item.get("result")
    if isinstance(result, Mapping):
        return _score_pair(result.get("home_goals"), result.get("away_goals"))
    return None


def _score_pair(home: Any, away: Any) -> tuple[int, int] | None:
    home_goals = _int(home)
    away_goals = _int(away)
    if home_goals is None or away_goals is None:
        return None
    return (home_goals, away_goals)


def _quote(record: Mapping[str, Any], market: str, selection: str) -> tuple[str, float] | None:
    odds = record.get("current_odds")
    if not isinstance(odds, Mapping):
        return None
    if market == "ASIAN_HANDICAP":
        ah = odds.get("ah")
        if not isinstance(ah, Mapping):
            return None
        if selection == "HOME_AH":
            return _line_price(ah.get("home_line"), ah.get("home_price"))
        if selection == "AWAY_AH":
            return _line_price(ah.get("away_line"), ah.get("away_price"))
    if market == "TOTALS":
        totals = odds.get("ou")
        if not isinstance(totals, Mapping):
            return None
        if selection == "OVER":
            return _line_price(totals.get("line"), totals.get("over_price"))
        if selection == "UNDER":
            return _line_price(totals.get("line"), totals.get("under_price"))
    return None


def _line_price(line: Any, price: Any) -> tuple[str, float] | None:
    if _optional_text(line) is None:
        return None
    value = _number(price)
    if value is None:
        return None
    return (_text(line), value)


def _entry_record(records: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    for record in records:
        kickoff = _parse_time(record.get("kickoff_utc"))
        captured = _parse_time(record.get("captured_at"))
        if kickoff and captured and (kickoff - captured).total_seconds() >= 23 * 3600:
            return record
    return records[0]


def _settlement_selection(market: str, selection: str) -> str | None:
    if market == "ASIAN_HANDICAP" and selection == "HOME_AH":
        return "HOME"
    if market == "ASIAN_HANDICAP" and selection == "AWAY_AH":
        return "AWAY"
    if market == "TOTALS" and selection in {"OVER", "UNDER"}:
        return selection
    return None


def pending_outcome_entries(
    runtime_root: Path,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return canonical fixture-market captures that still need an outcome."""
    root = runtime_root / "forward_outcome_ledger"
    rows = _ledger_rows_by_file(root)
    pending = _pending_entries(rows)
    resolved_now = (now or datetime.now(UTC)).astimezone(UTC)
    output: list[dict[str, Any]] = []
    for identity, (path, entry, side, item) in pending.items():
        kickoff = _parse_time(entry.get("kickoff_utc"))
        due_at = kickoff + timedelta(hours=3) if kickoff else None
        output.append(
            {
                "identity": list(identity),
                "ledger_file": str(path),
                "fixture_id": _text(entry.get("fixture_id")),
                "kickoff_utc": _optional_text(entry.get("kickoff_utc")),
                "due_at_utc": due_at.isoformat().replace("+00:00", "Z") if due_at else None,
                "due": bool(due_at is not None and resolved_now >= due_at),
                "capture_identity_hash": _optional_text(entry.get("capture_identity_hash")),
                "recommendation_scope": _outcome_scope(entry, side),
                "settled_side": side,
                "market": _text(item.get("market")),
                "selection": _text(item.get("selection")),
            }
        )
    return sorted(output, key=lambda row: (str(row["kickoff_utc"]), str(row["fixture_id"])))


def _pending_entries(
    rows_by_file: Mapping[Path, Sequence[Mapping[str, Any]]],
) -> dict[tuple[str, str, str, str, str], tuple[Path, Mapping[str, Any], str, Mapping[str, Any]]]:
    pending: dict[
        tuple[str, str, str, str, str],
        tuple[Path, Mapping[str, Any], str, Mapping[str, Any]],
    ] = {}
    settled: set[tuple[str, str, str, str, str]] = set()
    all_records = [record for records in rows_by_file.values() for record in records]
    globally_conflicted_validation = _conflicted_validation_fixtures(all_records)
    for path, records in rows_by_file.items():
        for record in records:
            if _text(record.get("record_type")) == "outcome":
                settled.add(_settlement_identity(record))
        grouped = _settlement_entries(
            records,
            {
                str(record.get("fixture_id")): {"fixture_id": record.get("fixture_id")}
                for record in records
                if record.get("fixture_id")
            },
        )
        # _settlement_entries only needs fixture membership here; settlement payload is unused.
        for entry, side, item in grouped:
            if side == "pick" and _text(entry.get("fixture_id")) in globally_conflicted_validation:
                continue
            identity = _settlement_identity_from_parts(entry, side, item)
            pending.setdefault(identity, (path, entry, side, item))
    return {identity: value for identity, value in pending.items() if identity not in settled}


def _settlement_identity(record: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _text(record.get("capture_identity_hash") or record.get("card_hash")),
        _text(record.get("fixture_id")),
        _text(record.get("settled_side")),
        _text(record.get("market")),
        _text(record.get("selection")),
    )


def _settlement_identity_from_parts(
    entry: Mapping[str, Any], side: str, item: Mapping[str, Any]
) -> tuple[str, str, str, str, str]:
    return (
        _text(entry.get("capture_identity_hash") or entry.get("card_hash")),
        _text(entry.get("fixture_id")),
        side,
        _text(item.get("market")),
        _text(item.get("selection")),
    )


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _shadow_pick(card: Mapping[str, Any]) -> dict[str, Any] | None:
    # v2 shadow capture starts with AH only. TOTALS shadow capture needs a separate
    # fair_ou/market_ou contract before it can be made deterministic.
    divergence = _mapping(card.get("model_market_divergence"))
    fair_line = _number(divergence.get("model_fair_line"))
    market_line = _number(divergence.get("market_line"))
    if fair_line is None or market_line is None:
        return None
    delta = fair_line - market_line
    if abs(delta) <= 0.005:
        return None
    return {
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH" if delta < 0 else "AWAY_AH",
        "model_fair_line": fair_line,
        "market_line_at_capture": market_line,
        "divergence_line_units": round(delta, 4),
        "derived_from": "model_market_divergence",
        "display_tier_at_capture": _text(card.get("decision_tier") or "SKIP"),
        "shadow": True,
        "not_a_recommendation": True,
        "not_displayed": True,
    }


def _cards(day_view: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = day_view.get("cards")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _market_odds_summary(value: Any) -> dict[str, Any]:
    odds = _mapping(value)
    summary: dict[str, Any] = {}
    for key in ("ah", "ou", "one_x_two"):
        item = _mapping(odds.get(key))
        if item:
            summary[key] = {
                field: item.get(field)
                for field in (
                    "line",
                    "home_line",
                    "away_line",
                    "home_price",
                    "away_price",
                    "over_price",
                    "under_price",
                    "draw_price",
                    "bookmaker_count",
                    "bookmaker_id",
                    "provider",
                    "captured_at",
                    "as_of",
                )
                if item.get(field) is not None
            }
    return summary


def _recommendation_scope(card: Mapping[str, Any], shadow_pick: Mapping[str, Any] | None) -> str:
    tier = _text(card.get("decision_tier"))
    pick = card.get("pick")
    if tier == "RECOMMEND" and card.get("lock_eligible") is True and isinstance(pick, Mapping):
        return "OFFICIAL"
    if (
        tier == "ANALYSIS_PICK"
        and card.get("outcome_tracked") is True
        and isinstance(pick, Mapping)
    ):
        return "VALIDATION"
    if shadow_pick:
        return "SHADOW"
    return "NONE"


def _outcome_scope(entry: Mapping[str, Any], side: str) -> str:
    if side == "shadow_pick":
        return "SHADOW"
    scope = _text(entry.get("recommendation_scope")).upper()
    return scope if scope in {"OFFICIAL", "VALIDATION"} else "UNSCOPED"


def _fixture_identity(card: Mapping[str, Any]) -> dict[str, Any]:
    frozen = _mapping(card.get("frozen_artifact_provenance"))
    frozen_identity = _mapping(frozen.get("fixture_identity"))
    return {
        "fixture_id": _text(card.get("fixture_id")),
        "kickoff_utc": _optional_text(card.get("kickoff_utc")),
        "competition_id": _optional_text(card.get("competition_id")),
        "competition_name": _optional_text(card.get("competition_name")),
        "home_team_id": _optional_text(
            frozen_identity.get("home_team_id") or card.get("home_team_id")
        ),
        "home_team_name": _optional_text(card.get("home_team_name")),
        "away_team_id": _optional_text(
            frozen_identity.get("away_team_id") or card.get("away_team_id")
        ),
        "away_team_name": _optional_text(card.get("away_team_name")),
    }


def _quote_provenance(card: Mapping[str, Any]) -> dict[str, Any]:
    audit = _mapping(card.get("quote_identity_audit"))
    markets: dict[str, Any] = {}
    for key in ("ah", "ou", "one_x_two"):
        item = _mapping(audit.get(key))
        if item:
            markets[key] = {
                field: item.get(field)
                for field in (
                    "identity_status",
                    "freshness_status",
                    "captured_at",
                    "provider",
                    "bookmaker_id",
                    "fixture_id",
                    "observation_ids",
                )
                if item.get(field) is not None
            }
    return {
        "schema_version": "w2.quote_provenance.v1",
        "markets": markets,
    }


def _artifact_provenance(card: Mapping[str, Any]) -> dict[str, Any]:
    frozen = _mapping(card.get("frozen_artifact_provenance"))
    return {
        "artifact_hash": _optional_text(
            card.get("artifact_hash") or frozen.get("artifact_hash") or card.get("card_hash")
        ),
        "schema_version": _optional_text(frozen.get("schema_version")),
        "source_hash": _optional_text(frozen.get("source_hash")),
        "checkpoint_namespace": _optional_text(frozen.get("checkpoint_namespace")),
    }


def _probability_identity(card: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = _mapping(card.get("diagnostics"))
    return {
        "probability_source": _optional_text(card.get("probability_source")),
        "market_probabilities": _mapping_copy(card.get("market_probabilities")),
        "model_probabilities": _mapping_copy(
            card.get("model_probabilities") or diagnostics.get("model_probabilities")
        ),
        "model_family": _optional_text(
            _mapping(card.get("model_market_divergence")).get("model_family")
        ),
        "calibration_hash": _optional_text(diagnostics.get("calibration_hash")),
    }


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_copy(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _secondary_picks(card: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = card.get("secondary_picks")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)][:1]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text(value: Any) -> str:
    return _optional_text(value) or ""


def _number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None
