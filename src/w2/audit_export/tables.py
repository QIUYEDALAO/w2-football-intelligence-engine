from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.forward_ops_models import ForwardMarketSnapshotModel
from w2.infrastructure.persistence.models import RecommendationLockModel, SettlementModel

AUDIT_TABLE_NAMES = (
    "prematch_recommendations",
    "market_timeline_snapshots",
    "locked_recommendation_snapshots",
    "settlement_history",
)


@dataclass(frozen=True)
class AuditExport:
    tables: dict[str, list[dict[str, Any]]]
    manifest: dict[str, Any]


def build_audit_export(
    dashboard_payload: dict[str, Any],
    *,
    session: Session | None = None,
    generated_at: datetime | None = None,
) -> AuditExport:
    exported_at = generated_at or datetime.now(UTC)
    matches = [item for item in _list(dashboard_payload.get("all")) if isinstance(item, dict)]
    tables = {
        "prematch_recommendations": _prematch_recommendations(dashboard_payload, matches),
        "market_timeline_snapshots": _market_timeline_snapshots(matches),
        "locked_recommendation_snapshots": _locked_recommendation_snapshots(matches),
        "settlement_history": _settlement_history(matches),
    }
    if session is not None:
        tables["market_timeline_snapshots"].extend(_db_market_timeline_snapshots(session))
        tables["locked_recommendation_snapshots"].extend(_db_locked_snapshots(session))
        tables["settlement_history"].extend(_db_settlement_history(session))
    manifest = {
        "schema_version": "w2.audit_export.v1",
        "exported_at": _iso(exported_at),
        "source": (
            "dashboard_payload+existing_models" if session is not None else "dashboard_payload"
        ),
        "selected_football_day": dashboard_payload.get("selected_football_day")
        or dashboard_payload.get("selected_date")
        or dashboard_payload.get("date"),
        "payload_generated_at": dashboard_payload.get("generated_at"),
        "web_git_sha": dashboard_payload.get("web_git_sha"),
        "api_git_sha": dashboard_payload.get("api_git_sha"),
        "table_counts": {name: len(rows) for name, rows in tables.items()},
        "read_only": True,
        "provider_calls": 0,
        "db_writes": 0,
    }
    return AuditExport(tables=tables, manifest=manifest)


def write_audit_export(
    export: AuditExport,
    output_dir: Path,
    *,
    output_format: str = "csv",
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    manifest_path = output_dir / "manifest.json"
    _write_json(manifest_path, export.manifest)
    written.append(manifest_path)
    formats = ("csv", "json") if output_format == "both" else (output_format,)
    for table_name in AUDIT_TABLE_NAMES:
        rows = export.tables[table_name]
        if "csv" in formats:
            path = output_dir / f"{table_name}.csv"
            _write_csv(path, rows)
            written.append(path)
        if "json" in formats:
            path = output_dir / f"{table_name}.json"
            _write_json(path, rows)
            written.append(path)
    return written


def _prematch_recommendations(
    payload: dict[str, Any],
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payload_as_of = payload.get("generated_at") or payload.get("as_of") or payload.get("asof")
    rows = []
    for match in matches:
        recommendation = _dict(match.get("recommendation"))
        pricing = _dict(match.get("pricing_shadow"))
        ah = _dict(_dict(match.get("current_odds")).get("ah"))
        rows.append(
            {
                "source": "dashboard_payload",
                "fixture_id": match.get("fixture_id"),
                "kickoff_utc": match.get("kickoff_utc"),
                "teams": _teams(match),
                "competition": match.get("competition") or match.get("competition_name"),
                "as_of": _as_of(match, payload_as_of),
                "status": match.get("status"),
                "formal_recommendation": match.get("formal_recommendation"),
                "recommendation_tier": recommendation.get("tier"),
                "recommendation_market": recommendation.get("market"),
                "recommendation_selection": recommendation.get("selection"),
                "recommendation_line": recommendation.get("line"),
                "recommendation_odds": recommendation.get("odds"),
                "formal_blockers": pricing.get("formal_blockers"),
                "fair_ah": pricing.get("fair_ah"),
                "market_ah": pricing.get("market_ah"),
                "edge_ah": pricing.get("edge_ah"),
                "market_ah_display": ah.get("display_line_cn"),
                "home_display_line": ah.get("home_display_line_cn"),
                "away_display_line": ah.get("away_display_line_cn"),
                "independent_signal_count": pricing.get("independent_signal_count"),
                "missing_independent_sources": pricing.get("missing_independent_sources"),
                "model_version": pricing.get("model_version"),
                "calibration_version": pricing.get("calibration_version"),
                "data_profile": match.get("data_profile") or payload.get("data_profile"),
                "raw_recommendation_json": recommendation or None,
            }
        )
    return rows


def _market_timeline_snapshots(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for match in matches:
        timeline = _dict(match.get("market_timeline"))
        if not timeline:
            continue
        rows.append(
            {
                "source": "dashboard_payload",
                "fixture_id": match.get("fixture_id"),
                "teams": _teams(match),
                "kickoff_utc": match.get("kickoff_utc"),
                "status": timeline.get("status"),
                "as_of": timeline.get("as_of"),
                "pattern": timeline.get("pattern"),
                "verified": timeline.get("verified"),
                "direction_allowed": timeline.get("direction_allowed"),
                "open_json": timeline.get("open"),
                "current_json": timeline.get("current"),
                "checkpoints_seen_json": timeline.get("checkpoints_seen"),
                "raw_timeline_json": timeline,
            }
        )
    return rows


def _locked_recommendation_snapshots(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for match in matches:
        locked = _dict(match.get("locked_pre_match_recommendation"))
        if not locked:
            continue
        recommendation = _dict(locked.get("recommendation"))
        rows.append(
            {
                "source": "dashboard_payload",
                "fixture_id": locked.get("fixture_id") or match.get("fixture_id"),
                "teams": _teams(match),
                "captured_at": locked.get("captured_at"),
                "as_of": locked.get("as_of"),
                "status": locked.get("status"),
                "recommendation_market": recommendation.get("market"),
                "recommendation_selection": recommendation.get("selection"),
                "recommendation_line": recommendation.get("line"),
                "recommendation_odds": recommendation.get("odds"),
                "reproducible": locked.get("reproducible"),
                "snapshot_payload_hash": locked.get("snapshot_payload_hash"),
                "raw_locked_snapshot_json": locked,
            }
        )
    return rows


def _settlement_history(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for match in matches:
        locked = _dict(match.get("locked_pre_match_recommendation"))
        settlement = _dict(locked.get("settlement"))
        if not settlement:
            continue
        rows.append(
            {
                "source": "dashboard_payload",
                "fixture_id": locked.get("fixture_id") or match.get("fixture_id"),
                "teams": _teams(match),
                "status": settlement.get("status"),
                "result": settlement.get("result"),
                "pnl": settlement.get("pnl"),
                "raw_settlement_json": settlement,
            }
        )
    return rows


def _db_market_timeline_snapshots(session: Session) -> list[dict[str, Any]]:
    rows = []
    for item in session.scalars(
        select(ForwardMarketSnapshotModel).order_by(
            ForwardMarketSnapshotModel.fixture_id,
            ForwardMarketSnapshotModel.captured_at,
        )
    ):
        payload = item.payload or {}
        rows.append(
            {
                "source": "forward_market_snapshot_model",
                "fixture_id": item.fixture_id,
                "phase": item.phase,
                "captured_at": item.captured_at,
                "market_comparable": item.market_comparable,
                "as_of": payload.get("as_of") if isinstance(payload, dict) else None,
                "pattern": payload.get("pattern") if isinstance(payload, dict) else None,
                "raw_timeline_json": payload,
            }
        )
    return rows


def _db_locked_snapshots(session: Session) -> list[dict[str, Any]]:
    rows = []
    for item in session.scalars(
        select(RecommendationLockModel).order_by(
            RecommendationLockModel.fixture_id,
            RecommendationLockModel.locked_at,
        )
    ):
        rows.append(
            {
                "source": "recommendation_lock_model",
                "lock_id": item.id,
                "recommendation_id": item.recommendation_id,
                "fixture_id": item.fixture_id,
                "status": item.status,
                "locked_at": item.locked_at,
                "as_of": item.as_of,
                "kickoff_utc": item.kickoff_utc,
                "tier": item.tier,
                "pick_side": item.pick_side,
                "pick_line": item.pick_line,
                "fair_ah": item.our_fair_ah,
                "market_ah": item.market_ah,
                "home_price": item.home_price,
                "away_price": item.away_price,
                "expected_value": item.expected_value,
                "snapshot_payload_hash": item.snapshot_payload_hash,
                "release_sha": item.release_sha,
                "reproducible": item.reproducible,
                "legacy_marker_only": item.legacy_marker_only,
                "data_profile": item.data_profile,
                "market_timeline_json": item.market_timeline_json,
                "ah_settlement_distribution_json": item.ah_settlement_distribution_json,
                "snapshot_payload_json": item.snapshot_payload_json,
            }
        )
    return rows


def _db_settlement_history(session: Session) -> list[dict[str, Any]]:
    rows = []
    for item in session.scalars(select(SettlementModel).order_by(SettlementModel.settled_at)):
        rows.append(
            {
                "source": "settlement_model",
                "settlement_id": item.id,
                "recommendation_id": item.recommendation_id,
                "lock_id": item.lock_id,
                "result_id": item.result_id,
                "outcome": item.outcome,
                "settled_at": item.settled_at,
                "matched_recommendation": item.matched_recommendation,
                "tier": item.tier,
                "movement_pattern": item.movement_pattern,
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _cell(row.get(key)) for key in fieldnames})


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _as_of(match: dict[str, Any], payload_as_of: Any) -> Any:
    refresh = _dict(match.get("data_refresh"))
    recommendation = _dict(match.get("recommendation"))
    return (
        refresh.get("as_of")
        or refresh.get("locked_at")
        or recommendation.get("generated_at")
        or payload_as_of
    )


def _teams(match: dict[str, Any]) -> str:
    home = match.get("home_team_name") or "主队"
    away = match.get("away_team_name") or "客队"
    return f"{home} vs {away}"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _cell(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
