from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "w2.forward_outcome_ledger.v1"
DEFAULT_LEDGER_DIR = Path("runtime/forward_outcome_ledger")


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
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
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
                "pick": _mapping_copy(card.get("pick")),
                "non_pick": _mapping_copy(card.get("non_pick")),
                "current_odds": _market_odds_summary(card.get("current_odds")),
                "card_hash": _optional_text(card.get("card_hash")),
                "outcome_tracked": bool(card.get("outcome_tracked") is True),
                "source": _optional_text(card.get("source")),
                "posthoc_only": True,
                "not_a_lock": True,
            }
        )
    return rows


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
    return "|".join(
        [
            _text(record.get("football_day")),
            _text(record.get("environment")),
            _text(record.get("fixture_id")),
            _text(record.get("card_hash") or record.get("captured_at")),
        ]
    )


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


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text(value: Any) -> str:
    return _optional_text(value) or ""
