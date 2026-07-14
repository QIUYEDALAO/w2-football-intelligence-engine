from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Any

from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.models.fair_market_estimate import estimate_snapshots, verify_estimate_snapshot

SCHEMA_VERSION = "w2.forward_outcome_ledger.v2"
DEFAULT_LEDGER_DIR = Path("runtime/forward_outcome_ledger")
FT_STATUSES = {"FT", "AET", "PEN"}
MIN_SHADOW_LINE_DIVERGENCE = 0.25
OFFICIAL_SCOPE = "OFFICIAL"
VALIDATION_SCOPE = "VALIDATION"
SHADOW_SCOPE = "SHADOW"


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
        shadow_picks = _shadow_picks(card)
        record = {
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
            "decision_tier": _text(card.get("decision_tier") or "SKIP"),
            "data_status": _text(card.get("data_status") or "PARTIAL"),
            "reason_code": _optional_text(card.get("reason_code")),
            "action": _optional_text(card.get("action")),
            "probability_source": _optional_text(card.get("probability_source")),
            "model_market_divergence": _mapping_copy(card.get("model_market_divergence")),
            "fair_market_estimates": _mapping_list(card.get("fair_market_estimates")),
            "fair_market_estimate_ids": _string_list(card.get("fair_market_estimate_ids")),
            "fair_market_estimate_snapshots": _mapping_list(
                card.get("fair_market_estimate_snapshots")
            ),
            "estimate_integrity": [
                {
                    "estimate_id": item.get("estimate_id"),
                    "valid": verify_estimate_snapshot(item),
                }
                for item in estimate_snapshots(card)
                if item.get("estimate_id")
            ],
            "analysis_gate": _mapping_copy(card.get("analysis_gate")),
            "analysis_gates": _mapping_list(card.get("analysis_gates")),
            "analysis_gate_v2_shadow": _mapping_copy(card.get("analysis_gate_v2_shadow")),
            "analysis_gate_v2_shadows": _mapping_list(card.get("analysis_gate_v2_shadows")),
            "shadow_pick": shadow_picks[0] if shadow_picks else None,
            "shadow_picks": shadow_picks,
            "pick": _mapping_copy(card.get("pick")),
            "non_pick": _mapping_copy(card.get("non_pick")),
            "current_odds": _market_odds_summary(card.get("current_odds")),
            "card_hash": _optional_text(card.get("card_hash")),
            "outcome_tracked": bool(card.get("outcome_tracked") is True),
            "recommendation_scope": _recommendation_scope(card),
            "source": _optional_text(card.get("source")),
            "posthoc_only": True,
            "not_a_lock": True,
        }
        record["capture_checkpoint"] = _capture_checkpoint(record, captured_at)
        record["evidence_hash"] = _evidence_hash(record)
        rows.append(record)
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
    results, unsettled_missing_fulltime = _finished_results(day_view_or_results_source)
    ledger_rows = _ledger_rows_by_file(root)
    outcome_records: list[tuple[Path, dict[str, Any]]] = []
    for path, records in ledger_rows.items():
        for entry, side, item in _settlement_entries(records, results):
            outcome_records.append(
                (
                    path,
                    _outcome_record(
                        entry,
                        side=side,
                        item=item,
                        result=results[_text(entry.get("fixture_id"))],
                        settled_at=resolved_settled_at,
                    ),
                )
            )

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

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "dry_run": bool(dry_run),
        "write_artifacts": bool(write_artifacts),
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "lock_capture_write": False,
        "settlement_write": False,
        "runtime_root": str(runtime_root),
        "result_fixture_count": len(results),
        "unsettled_missing_fulltime": unsettled_missing_fulltime,
        "record_count": len(outcome_records),
        "written": written,
        "skipped_existing": skipped_existing,
        "records": [record for _, record in outcome_records]
        if dry_run or not write_artifacts
        else [],
    }


def ledger_fixture_ids(runtime_root: Path) -> list[str]:
    root = runtime_root / "forward_outcome_ledger"
    fixture_ids: dict[str, None] = {}
    for records in _ledger_rows_by_file(root).values():
        for record in records:
            if _text(record.get("record_type") or "capture") != "capture":
                continue
            fixture_id = _text(record.get("fixture_id"))
            if fixture_id:
                fixture_ids.setdefault(fixture_id, None)
    return list(fixture_ids)


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
    capture_identity = _text(record.get("card_hash") or record.get("captured_at"))
    if record_type == "capture" and record.get("evidence_hash"):
        capture_identity = "|".join(
            [
                _text(record.get("capture_checkpoint") or "EVIDENCE_CHANGE"),
                _text(record.get("evidence_hash")),
            ]
        )
    parts = [
        _text(record.get("football_day")),
        _text(record.get("environment")),
        _text(record.get("fixture_id")),
        capture_identity,
        record_type,
    ]
    if record_type == "outcome":
        parts.extend(
            [
                _text(record.get("settled_side")),
                _text(record.get("recommendation_scope")),
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
    grouped: dict[
        tuple[str, str, str, str, str],
        list[tuple[Mapping[str, Any], Mapping[str, Any]]],
    ] = {}
    for record in records:
        if _text(record.get("record_type") or "capture") != "capture":
            continue
        fixture_id = _text(record.get("fixture_id"))
        if fixture_id not in results:
            continue
        settlement_items: list[tuple[str, Any]] = [("pick", record.get("pick"))]
        shadow_picks = record.get("shadow_picks")
        if isinstance(shadow_picks, Sequence) and not isinstance(
            shadow_picks, str | bytes | bytearray
        ):
            settlement_items.extend(("shadow_pick", item) for item in shadow_picks)
        else:
            settlement_items.append(("shadow_pick", record.get("shadow_pick")))
        for side, item in settlement_items:
            if not isinstance(item, Mapping):
                continue
            market = _text(item.get("market"))
            selection = _text(item.get("selection"))
            if market not in {"ASIAN_HANDICAP", "TOTALS"} or not selection:
                continue
            scope = SHADOW_SCOPE if side == "shadow_pick" else _recommendation_scope(record)
            if side == "pick" and scope is None:
                continue
            grouped.setdefault((fixture_id, side, _text(scope), market, selection), []).append(
                (record, item)
            )

    entries: list[tuple[Mapping[str, Any], str, Mapping[str, Any]]] = []
    for (_, side, _, _, _), items in grouped.items():
        ordered = sorted(
            items,
            key=lambda pair: (
                _parse_time(pair[0].get("captured_at")) or datetime.min.replace(tzinfo=UTC)
            ),
        )
        entry = (
            _final_prematch_record([pair[0] for pair in ordered])
            if side == "pick"
            else _entry_record([pair[0] for pair in ordered])
        )
        if entry is None:
            continue
        pick_item = next(item for record, item in ordered if record is entry)
        entries.append((entry, side, pick_item))
    return entries


def _outcome_record(
    entry: Mapping[str, Any],
    *,
    side: str,
    item: Mapping[str, Any],
    result: Mapping[str, Any],
    settled_at: datetime,
) -> dict[str, Any]:
    market = _text(item.get("market"))
    selection = _text(item.get("selection"))
    quote = _quote(entry, market, selection)
    home_goals = int(result["home_goals"])
    away_goals = int(result["away_goals"])
    final_score = {
        "home": home_goals,
        "away": away_goals,
        "status": _text(result.get("status") or "FT"),
    }
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
        "source_capture_hash": _optional_text(
            entry.get("evidence_hash") or entry.get("card_hash")
        ),
        "source_captured_at": _optional_text(entry.get("captured_at")),
        "market": market,
        "selection": selection,
        "estimate_id": _optional_text(item.get("estimate_id")),
        "analysis_gate_v2_shadow": _shadow_gate_for_item(entry, item),
        "settled_side": side,
        "recommendation_scope": (
            SHADOW_SCOPE if side == "shadow_pick" else _recommendation_scope(entry)
        ),
        "final_score": final_score,
        "provider_calls": 0,
        "db_writes": 0,
        "lock_capture_write": False,
        "settlement_write": False,
    }
    if quote is None:
        return {
            **base,
            "settlement_outcome": "VOID",
            "void_reason": "MISSING_ENTRY_LINE_OR_PRICE",
        }
    line, _price = quote
    settlement_selection = _settlement_selection(selection)
    decimal_line = _decimal(line)
    if settlement_selection is None or decimal_line is None:
        return {
            **base,
            "entry_line": line,
            "entry_price": _price,
            "settlement_outcome": "VOID",
            "void_reason": "INVALID_ENTRY_LINE_OR_SELECTION",
        }
    if market == "ASIAN_HANDICAP":
        outcome = settle_asian_handicap(
            home_goals,
            away_goals,
            settlement_selection,
            decimal_line,
        )
    elif market == "TOTALS":
        outcome = settle_total_goals(
            home_goals + away_goals,
            settlement_selection,
            decimal_line,
        )
    else:
        return {
            **base,
            "entry_line": line,
            "entry_price": _price,
            "settlement_outcome": "VOID",
            "void_reason": "INVALID_ENTRY_MARKET",
        }
    return {
        **base,
        "entry_line": line,
        "entry_price": _price,
        "settlement_outcome": outcome.value,
    }


def _shadow_gate_for_item(
    entry: Mapping[str, Any],
    item: Mapping[str, Any],
) -> dict[str, Any]:
    estimate_id = _text(item.get("estimate_id"))
    market = _text(item.get("market"))
    rows = entry.get("analysis_gate_v2_shadows")
    if isinstance(rows, Sequence) and not isinstance(rows, str | bytes | bytearray):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            if estimate_id and _text(row.get("estimate_id")) == estimate_id:
                return dict(row)
            if not estimate_id and _text(row.get("market")) == market:
                return dict(row)
    primary = entry.get("analysis_gate_v2_shadow")
    return dict(primary) if isinstance(primary, Mapping) else {}


def _finished_results(source: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], int]:
    results: dict[str, dict[str, Any]] = {}
    unsettled_missing_fulltime = 0
    candidates: list[Mapping[str, Any]] = []
    for key in ("cards", "results", "fixtures", "all"):
        value = source.get(key)
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            candidates.extend(item for item in value if isinstance(item, Mapping))
    if not candidates and source:
        candidates.append(source)
    for item in candidates:
        fixture_id = _fixture_id(item)
        status = _status(item)
        if not fixture_id or status not in FT_STATUSES:
            continue
        score = _score(item, status=status)
        if score is None:
            if status in {"AET", "PEN"}:
                unsettled_missing_fulltime += 1
            continue
        home_goals, away_goals = score
        results[fixture_id] = {
            "fixture_id": fixture_id,
            "status": status,
            "home_goals": home_goals,
            "away_goals": away_goals,
        }
    return results, unsettled_missing_fulltime


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


def _score(item: Mapping[str, Any], *, status: str) -> tuple[int, int] | None:
    fulltime = _fulltime_score(item)
    if fulltime is not None:
        return fulltime
    if status in {"AET", "PEN"}:
        return None
    direct = _score_pair(item.get("home_score"), item.get("away_score"))
    if direct is not None:
        return direct
    goals = item.get("goals")
    if isinstance(goals, Mapping):
        pair = _score_pair(goals.get("home"), goals.get("away"))
        if pair is not None:
            return pair
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
    result = item.get("result")
    if isinstance(result, Mapping):
        return _score_pair(result.get("home_goals"), result.get("away_goals"))
    return None


def _fulltime_score(item: Mapping[str, Any]) -> tuple[int, int] | None:
    score = item.get("score")
    if isinstance(score, Mapping):
        for key in ("fulltime", "full_time", "ft"):
            value = score.get(key)
            if isinstance(value, Mapping):
                pair = _score_pair(value.get("home"), value.get("away"))
                if pair is not None:
                    return pair
    result = item.get("result")
    if isinstance(result, Mapping):
        for key in ("fulltime", "full_time", "ft"):
            value = result.get(key)
            if isinstance(value, Mapping):
                pair = _score_pair(value.get("home"), value.get("away"))
                if pair is not None:
                    return pair
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


def _final_prematch_record(
    records: list[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Return the last valid capture strictly before kickoff."""
    prematch = [
        record
        for record in records
        if (kickoff := _parse_time(record.get("kickoff_utc"))) is not None
        and (captured := _parse_time(record.get("captured_at"))) is not None
        and captured < kickoff
    ]
    if prematch:
        return max(
            prematch,
            key=lambda record: _parse_time(record.get("captured_at"))
            or datetime.min.replace(tzinfo=UTC),
        )
    return None


def _recommendation_scope(record: Mapping[str, Any]) -> str | None:
    explicit = _text(record.get("recommendation_scope")).upper()
    if explicit in {OFFICIAL_SCOPE, VALIDATION_SCOPE, SHADOW_SCOPE}:
        return explicit
    tier = _text(record.get("decision_tier")).upper()
    if tier == "ANALYSIS_PICK":
        return VALIDATION_SCOPE
    if tier in {"RECOMMEND", "FORMAL", "CANDIDATE"}:
        return OFFICIAL_SCOPE
    if isinstance(record.get("pick"), Mapping):
        # Historical captures predate recommendation_scope and remain official.
        return OFFICIAL_SCOPE
    return None


def _settlement_selection(selection: str) -> str | None:
    if selection == "HOME_AH":
        return "HOME"
    if selection == "AWAY_AH":
        return "AWAY"
    if selection in {"OVER", "UNDER"}:
        return selection
    return None


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
    picks: list[dict[str, Any]] = []
    estimates = estimate_snapshots(card)
    if estimates:
        odds = _mapping(card.get("current_odds"))
        for estimate in estimates:
            if not isinstance(estimate, Mapping) or _text(estimate.get("status")) != "READY":
                continue
            market = _text(estimate.get("market"))
            fair_line = _number(estimate.get("fair_line"))
            market_line = _estimate_market_line(odds, market)
            if fair_line is None or market_line is None:
                continue
            delta = fair_line - market_line
            if abs(delta) < MIN_SHADOW_LINE_DIVERGENCE:
                continue
            selection = (
                ("HOME_AH" if delta < 0 else "AWAY_AH")
                if market == "ASIAN_HANDICAP"
                else ("OVER" if delta > 0 else "UNDER")
            )
            payload = _shadow_pick_payload(
                card,
                market=market,
                selection=selection,
                fair_line=fair_line,
                market_line=market_line,
                delta=delta,
                derived_from="fair_market_estimate_snapshot",
            )
            payload["estimate_id"] = _optional_text(estimate.get("estimate_id"))
            semantic_status = _text(
                estimate.get("semantic_status")
                or "LEGACY_DISTRIBUTION_CONTEXT_UNVERIFIED"
            )
            evidence_eligible = (
                estimate.get("schema_version") == "w2.fme_snapshot.v2"
                and semantic_status == "PASS"
                and estimate.get("evidence_eligible") is True
                and verify_estimate_snapshot(estimate)
            )
            payload.update(
                {
                    "raw_shadow_capture": True,
                    "diagnostic_only": not evidence_eligible,
                    "evidence_eligible": evidence_eligible,
                    "semantic_status": semantic_status,
                }
            )
            for field in (
                "model_family",
                "artifact_hash",
                "artifact_version",
                "train_cutoff",
                "feature_as_of",
            ):
                if estimate.get(field) is not None:
                    payload[field] = estimate[field]
            picks.append(payload)
        return picks

    divergence = _mapping(card.get("model_market_divergence"))
    fair_line = _number(divergence.get("model_fair_line"))
    market_line = _number(divergence.get("market_line"))
    if fair_line is not None and market_line is not None:
        delta = fair_line - market_line
        if abs(delta) >= MIN_SHADOW_LINE_DIVERGENCE:
            picks.append(
                _shadow_pick_payload(
                    card,
                    market="ASIAN_HANDICAP",
                    selection="HOME_AH" if delta < 0 else "AWAY_AH",
                    fair_line=fair_line,
                    market_line=market_line,
                    delta=delta,
                    derived_from="model_market_divergence",
                )
            )

    return picks


def _estimate_market_line(odds: Mapping[str, Any], market: str) -> float | None:
    if market == "ASIAN_HANDICAP":
        return _number(_mapping(odds.get("ah")).get("home_line"))
    if market == "TOTALS":
        return _number(_mapping(odds.get("ou")).get("line"))
    return None


def _shadow_pick_payload(
    card: Mapping[str, Any],
    *,
    market: str,
    selection: str,
    fair_line: float,
    market_line: float,
    delta: float,
    derived_from: str,
) -> dict[str, Any]:
    return {
        "market": market,
        "selection": selection,
        "model_fair_line": fair_line,
        "market_line_at_capture": market_line,
        "divergence_line_units": round(delta, 4),
        "derived_from": derived_from,
        "display_tier_at_capture": _text(card.get("decision_tier") or "SKIP"),
        "shadow": True,
        "not_a_recommendation": True,
        "not_displayed": True,
        "raw_shadow_capture": True,
        "diagnostic_only": True,
        "evidence_eligible": False,
        "semantic_status": "LEGACY_DISTRIBUTION_CONTEXT_UNVERIFIED",
    }


def _capture_checkpoint(record: Mapping[str, Any], captured_at: datetime) -> str:
    kickoff = _parse_time(record.get("kickoff_utc"))
    if kickoff is None:
        return "EVIDENCE_CHANGE"
    seconds = (kickoff - captured_at.astimezone(UTC)).total_seconds()
    if 23 * 3600 <= seconds <= 25 * 3600:
        return "T_MINUS_24H"
    if 45 * 60 <= seconds <= 75 * 60:
        return "T_MINUS_1H"
    if 0 <= seconds < 45 * 60:
        return "LOCK_WINDOW"
    return "EVIDENCE_CHANGE"


def _evidence_hash(record: Mapping[str, Any]) -> str:
    evidence = {
        "fixture_id": record.get("fixture_id"),
        "kickoff_utc": record.get("kickoff_utc"),
        "decision_tier": record.get("decision_tier"),
        "data_status": record.get("data_status"),
        "reason_code": record.get("reason_code"),
        "probability_source": record.get("probability_source"),
        "model_market_divergence": record.get("model_market_divergence"),
        "shadow_picks": record.get("shadow_picks"),
        "pick": record.get("pick"),
        "non_pick": record.get("non_pick"),
        "current_odds": record.get("current_odds"),
        "analysis_gate": record.get("analysis_gate"),
    }
    canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


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
                    "as_of",
                )
                if item.get(field) is not None
            }
    return summary


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_copy(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [str(item) for item in value if item]


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
