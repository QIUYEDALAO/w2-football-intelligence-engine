from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from w2.domain.canonical_decision_projection import project_canonical_decision
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.domain.recommendation_decision_v4 import (
    RecommendationOutcomeV4,
    validate_decision_v4_identity,
)
from w2.tracking.outcome_ledger_repository import (
    CURRENT_FORWARD_RECORD_TYPES,
    OutcomeLedgerRepository,
)

SCHEMA_VERSION = "w2.forward_outcome_ledger.v3"
VOID_STATUSES = {"CANC", "ABD", "AWD", "WO"}
SUPPORTED_MARKETS = {"ASIAN_HANDICAP", "TOTALS"}


def run_forward_outcome_ledger(
    day_view: Mapping[str, Any],
    *,
    repository: OutcomeLedgerRepository | None = None,
    dry_run: bool = True,
    write_db: bool = False,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    resolved_captured_at = (captured_at or datetime.now(UTC)).astimezone(UTC)
    records = build_forward_outcome_records(
        day_view,
        captured_at=resolved_captured_at,
    )
    outcome = (repository or OutcomeLedgerRepository()).append(
        records,
        dry_run=dry_run,
        write_db=write_db,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "dry_run": bool(dry_run),
        "write_db": bool(write_db),
        "provider_calls": 0,
        "db_writes": outcome["db_writes"],
        "lock_capture_write": False,
        "settlement_write": False,
        "source": "outcome_ledger",
        "record_count": len(records),
        "written": outcome["written"],
        "skipped_existing": outcome["already_imported"],
        "records": records if dry_run or not write_db else [],
    }


def append_capture_supersessions(
    targets: Sequence[Mapping[str, Any]],
    *,
    repository: OutcomeLedgerRepository | None = None,
    reason_code: str,
    superseded_at: datetime | None = None,
    dry_run: bool = True,
    write_db: bool = False,
) -> dict[str, Any]:
    """Append invalidations without mutating or deleting original captures."""
    resolved_at = (superseded_at or datetime.now(UTC)).astimezone(UTC)
    timestamp = resolved_at.isoformat().replace("+00:00", "Z")
    records: list[dict[str, Any]] = []
    for target in targets:
        capture_hash = _optional_text(target.get("capture_identity_hash"))
        fixture_id = _optional_text(target.get("fixture_id"))
        if capture_hash is None or fixture_id is None:
            raise ValueError("SUPERSESSION_TARGET_IDENTITY_INCOMPLETE")
        core = {
            "record_type": "supersession",
            "schema_version": SCHEMA_VERSION,
            "supersession_status": "SUPERSEDED",
            "reason_code": reason_code,
            "fixture_id": fixture_id,
            "target_capture_identity_hash": capture_hash,
            "target_decision_hash": _optional_text(target.get("decision_hash")),
            "superseded_at": timestamp,
            "environment": "staging",
            "not_a_lock": True,
            "not_a_settlement": True,
        }
        records.append({**core, "supersession_hash": _canonical_sha256(core)})
    outcome = (repository or OutcomeLedgerRepository()).append(
        records,
        dry_run=dry_run,
        write_db=write_db,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "dry_run": dry_run,
        "write_db": write_db,
        "source": "outcome_ledger",
        "record_count": len(records),
        "written": outcome["written"],
        "skipped_existing": outcome["already_imported"],
        "records": records if dry_run or not write_db else [],
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
        canonical = _validated_v4_projection(card)
        if isinstance(canonical.get("pick"), Mapping):
            capture_candidates = [canonical["pick"]]
        else:
            capture_candidates = _shadow_picks(card)
        for capture_candidate in capture_candidates or [None]:
            capture_pick = _capture_pick(card, capture_candidate)
            recommendation_scope = _recommendation_scope(canonical, capture_pick)
            fixture_identity = _fixture_identity(card)
            quote_provenance = _quote_provenance(card)
            artifact_provenance = _artifact_provenance(card)
            probability_identity = _probability_identity(card)
            lifecycle_metadata = _lifecycle_metadata(card)
            decision_hash = _optional_text(canonical.get("decision_hash"))
            shadow_pick = (
                capture_candidate if _mapping(capture_candidate).get("shadow") is True else None
            )
            capture_identity: dict[str, Any] = {
                "fixture_identity": fixture_identity,
                "recommendation_scope": recommendation_scope,
                "pick": _mapping_copy(capture_pick),
                "secondary_picks": [],
                "shadow_pick": shadow_pick,
                "quote_provenance": quote_provenance,
                "artifact_provenance": artifact_provenance,
                "probability_identity": probability_identity,
                "lifecycle_metadata": lifecycle_metadata,
                "card_hash": _optional_text(card.get("card_hash")),
                "decision_hash": decision_hash,
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
                    "decision_tier": _text(canonical.get("decision_tier") or "NOT_READY"),
                    "data_status": _text(card.get("data_status") or "PARTIAL"),
                    "reason_code": _optional_text(canonical.get("reason_code")),
                    "action": _optional_text(canonical.get("next_action")),
                    "probability_source": _optional_text(card.get("probability_source")),
                    "model_market_divergence": _mapping_copy(card.get("model_market_divergence")),
                    "shadow_pick": shadow_pick,
                    "pick": _mapping_copy(capture_pick),
                    "secondary_picks": [],
                    "non_pick": _mapping_copy(card.get("non_pick")),
                    "current_odds": _market_odds_summary(card.get("current_odds")),
                    "card_hash": _optional_text(card.get("card_hash")),
                    "recommendation_scope": recommendation_scope,
                    "fixture_identity": fixture_identity,
                    "quote_provenance": quote_provenance,
                    "artifact_provenance": artifact_provenance,
                    "probability_identity": probability_identity,
                    "evaluation_tier": lifecycle_metadata["evaluation_tier"],
                    "checkpoint": lifecycle_metadata["checkpoint"],
                    "lineup_input_hash": lifecycle_metadata["lineup_input_hash"],
                    "capture_identity_hash": _canonical_sha256(capture_identity),
                    "outcome_tracked": bool(canonical.get("outcome_tracked")),
                    "lock_eligible": bool(canonical.get("lock_eligible")),
                    "decision_hash": decision_hash,
                    "recommendation_id": _optional_text(card.get("recommendation_id")),
                    "source": _optional_text(card.get("source")),
                    "posthoc_only": True,
                    "not_a_lock": True,
                }
            )
    return rows


def _validated_v4_projection(card: Mapping[str, Any]) -> dict[str, Any]:
    decision = _mapping(card.get("recommendation_decision_v4"))
    if not decision:
        return {}
    try:
        decision_hash = validate_decision_v4_identity(decision)
    except ValueError as exc:
        raise ValueError("FORWARD_CAPTURE_RECOMMENDATION_DECISION_V4_INVALID") from exc
    outcome = _text(decision.get("outcome"))
    if outcome not in {item.value for item in RecommendationOutcomeV4}:
        raise ValueError("FORWARD_CAPTURE_RECOMMENDATION_DECISION_V4_INVALID")
    if _text(decision.get("fixture_id")) != _text(card.get("fixture_id")):
        raise ValueError("FORWARD_CAPTURE_RECOMMENDATION_DECISION_V4_INVALID")
    selected = decision.get("selected_candidate")
    is_pick = outcome in {"ANALYSIS_PICK", "FORMAL_RECOMMEND"}
    if is_pick != isinstance(selected, Mapping):
        raise ValueError("FORWARD_CAPTURE_RECOMMENDATION_DECISION_V4_INVALID")
    return {**project_canonical_decision(decision), "decision_hash": decision_hash}


def backfill_outcomes(
    *,
    repository: OutcomeLedgerRepository | None = None,
    dry_run: bool = True,
    write_db: bool = False,
    settled_at: datetime | None = None,
) -> dict[str, Any]:
    repo = repository or OutcomeLedgerRepository()
    resolved_settled_at = (settled_at or datetime.now(UTC)).astimezone(UTC)
    pending_before = _pending_entries(repo.records(CURRENT_FORWARD_RECORD_TYPES))
    results = repo.result_payloads_for_fixtures(
        _text(entry.get("fixture_id")) for entry, _, _ in pending_before.values()
    )
    outcome_records: list[dict[str, Any]] = []
    for entry, side, item in pending_before.values():
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
            outcome_records.append(record)
    appended = repo.append(outcome_records, dry_run=dry_run, write_db=write_db)

    processed_keys = {_settlement_identity(record) for record in outcome_records}
    processed_fixture_counts: dict[str, int] = {}
    for record in outcome_records:
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
        "write_db": bool(write_db),
        "provider_calls": 0,
        "db_reads": 2,
        "db_writes": appended["db_writes"],
        "lock_capture_write": False,
        "settlement_write": False,
        "source": "outcome_ledger+results",
        "result_fixture_count": len(results),
        "pending_count": len(pending_before),
        "unresolved_count": unresolved_count,
        "record_count": len(outcome_records),
        "processed_fixture_counts": processed_fixture_counts,
        "written": appended["written"],
        "skipped_existing": appended["already_imported"],
        "records": outcome_records if dry_run or not write_db else [],
    }


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
    elif record_type == "supersession":
        parts.extend(
            [
                _text(record.get("target_capture_identity_hash")),
                _text(record.get("reason_code")),
            ]
        )
    elif _text(record.get("recommendation_scope")).upper() == "SHADOW":
        shadow_pick = _mapping(record.get("shadow_pick"))
        parts.extend([_text(shadow_pick.get("market")), _text(shadow_pick.get("selection"))])
    return "|".join(parts)




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
    quote = _captured_quote(item) or _quote(entry, market, selection)
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
    *,
    repository: OutcomeLedgerRepository | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return canonical fixture-market captures that still need an outcome."""
    pending = _pending_entries(
        (repository or OutcomeLedgerRepository()).records(CURRENT_FORWARD_RECORD_TYPES)
    )
    resolved_now = (now or datetime.now(UTC)).astimezone(UTC)
    output: list[dict[str, Any]] = []
    for identity, (entry, side, item) in pending.items():
        kickoff = _parse_time(entry.get("kickoff_utc"))
        due_at = kickoff + timedelta(hours=3) if kickoff else None
        output.append(
            {
                "identity": list(identity),
                "source": "outcome_ledger",
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
    raw_records: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str, str, str, str], tuple[Mapping[str, Any], str, Mapping[str, Any]]]:
    pending: dict[
        tuple[str, str, str, str, str],
        tuple[Mapping[str, Any], str, Mapping[str, Any]],
    ] = {}
    settled: set[tuple[str, str, str, str, str]] = set()
    superseded = _superseded_capture_hashes(raw_records)
    records = [
        record for record in raw_records if not _record_is_superseded(record, superseded)
    ]
    globally_conflicted_validation = _conflicted_validation_fixtures(records)
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
    for entry, side, item in grouped:
        if side == "pick" and _text(entry.get("fixture_id")) in globally_conflicted_validation:
            continue
        identity = _settlement_identity_from_parts(entry, side, item)
        pending.setdefault(identity, (entry, side, item))
    return {identity: value for identity, value in pending.items() if identity not in settled}


def _superseded_capture_hashes(records: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        _text(record.get("target_capture_identity_hash"))
        for record in records
        if _text(record.get("record_type")) == "supersession"
        and _text(record.get("supersession_status")) == "SUPERSEDED"
        and _text(record.get("target_capture_identity_hash"))
    }


def _record_is_superseded(record: Mapping[str, Any], superseded: set[str]) -> bool:
    if not superseded:
        return False
    record_type = _text(record.get("record_type") or "capture")
    if record_type == "capture":
        return _text(record.get("capture_identity_hash")) in superseded
    if record_type == "outcome":
        return bool(
            {
                _text(record.get("capture_identity_hash")),
                _text(record.get("source_capture_hash")),
            }
            & superseded
        )
    return False


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


def _shadow_picks(card: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return one independent, non-display shadow capture per complete market."""
    picks = [_shadow_pick(card), _shadow_totals_pick(card)]
    return [pick for pick in picks if pick is not None]


def _shadow_pick(card: Mapping[str, Any]) -> dict[str, Any] | None:
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


def _shadow_totals_pick(card: Mapping[str, Any]) -> dict[str, Any] | None:
    pricing = _mapping(card.get("pricing_shadow"))
    fair_line = _number(pricing.get("fair_ou"))
    market_line = _number(pricing.get("market_ou"))
    odds = _mapping(_mapping(card.get("current_odds")).get("ou"))
    quote_line = _number(odds.get("line"))
    over_price = _number(odds.get("over_price"))
    under_price = _number(odds.get("under_price"))
    if (
        fair_line is None
        or market_line is None
        or quote_line is None
        or abs(quote_line - market_line) > 0.005
        or over_price is None
        or under_price is None
        or over_price <= 1
        or under_price <= 1
    ):
        return None
    delta = fair_line - market_line
    if abs(delta) <= 0.005:
        return None
    return {
        "market": "TOTALS",
        "selection": "OVER" if delta > 0 else "UNDER",
        "model_fair_line": fair_line,
        "market_line_at_capture": market_line,
        "divergence_line_units": round(delta, 4),
        "derived_from": "pricing_shadow_same_line_ou",
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


def _capture_pick(
    card: Mapping[str, Any],
    candidate: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    return _normalize_pick_for_capture(card, candidate) if candidate is not None else None


def _normalize_pick_for_capture(
    card: Mapping[str, Any],
    pick: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = _mapping_copy(pick)
    market = _text(normalized.get("market")).upper()
    selection = _normalized_capture_selection(market, normalized.get("selection"))
    if selection:
        normalized["selection"] = selection
        selected_line = normalized.get("exact_line") or normalized.get("line")
        selected_price = normalized.get("decimal_odds") or normalized.get("odds")
        if _optional_text(selected_line) is not None and _number(selected_price) is not None:
            normalized["line"] = selected_line
            normalized["entry_line"] = selected_line
            normalized["odds"] = selected_price
            normalized["entry_price"] = selected_price
            return normalized
        quote = _quote(
            {"current_odds": _market_odds_summary(card.get("current_odds"))},
            market,
            selection,
        )
        if quote is not None:
            line, price = quote
            normalized.setdefault("line", line)
            normalized.setdefault("entry_line", line)
            if normalized.get("odds") is None:
                normalized["odds"] = price
            normalized.setdefault("entry_price", price)
    return normalized


def _captured_quote(item: Mapping[str, Any]) -> tuple[str, float] | None:
    return _line_price(item.get("entry_line"), item.get("entry_price"))


def _normalized_capture_selection(market: str, selection: Any) -> str:
    raw = _text(selection).upper()
    if market == "ASIAN_HANDICAP":
        if raw in {"HOME", "HOME_AH"}:
            return "HOME_AH"
        if raw in {"AWAY", "AWAY_AH"}:
            return "AWAY_AH"
    if market == "TOTALS" and raw in {"OVER", "UNDER"}:
        return raw
    return raw


def _recommendation_scope(
    canonical: Mapping[str, Any],
    capture_pick: Mapping[str, Any] | None,
) -> str:
    if capture_pick and capture_pick.get("shadow") is True:
        return "SHADOW"
    outcome = _text(canonical.get("outcome"))
    if outcome == "FORMAL_RECOMMEND" and isinstance(capture_pick, Mapping):
        return "OFFICIAL"
    if outcome == "ANALYSIS_PICK" and isinstance(capture_pick, Mapping):
        return "VALIDATION"
    if capture_pick:
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
        "home_team_name": _optional_text(
            card.get("home_team_name") or card.get("home_name") or card.get("home_cn")
        ),
        "away_team_id": _optional_text(
            frozen_identity.get("away_team_id") or card.get("away_team_id")
        ),
        "away_team_name": _optional_text(
            card.get("away_team_name") or card.get("away_name") or card.get("away_cn")
        ),
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


def _lifecycle_metadata(card: Mapping[str, Any]) -> dict[str, str | None]:
    lineup = _mapping(card.get("lineup_provenance"))
    requirement = _text(
        card.get("evaluation_tier") or lineup.get("requirement")
    ).upper()
    return {
        "evaluation_tier": requirement
        if requirement in {"STRICT", "ADVISORY"}
        else "UNKNOWN",
        "checkpoint": _optional_text(card.get("checkpoint")),
        "lineup_input_hash": _optional_text(
            card.get("lineup_input_hash") or lineup.get("lineup_input_hash")
        ),
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
