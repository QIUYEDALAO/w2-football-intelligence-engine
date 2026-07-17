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

from w2.domain.environment_policy import build_environment_policy_stamp
from w2.infrastructure.persistence.forward_ops_models import ForwardMarketSnapshotModel
from w2.infrastructure.persistence.models import RecommendationLockModel, SettlementModel
from w2.reporting.match_decision import MatchDecisionState, decide_match
from w2.tracking.calibration_report import build_calibration_report

AUDIT_TABLE_NAMES = (
    "prematch_recommendations",
    "market_timeline_snapshots",
    "locked_recommendation_snapshots",
    "settlement_history",
    "calibration_report",
)

AUDIT_TABLE_COLUMNS = {
    "prematch_recommendations": (
        "source",
        "environment",
        "policy_version",
        "lock_policy_name",
        "fixture_id",
        "kickoff_utc",
        "teams",
        "competition",
        "as_of",
        "fixture_status",
        "report_state",
        "decision_tier",
        "data_status",
        "missing_fields",
        "stale_fields",
        "lifecycle_status",
        "outcome_tracked",
        "lock_eligible",
        "decision_contract_reason_code",
        "decision_contract_action",
        "decision_contract_next_eval_at",
        "provider_budget_status",
        "reason_code",
        "reason_cn",
        "formal_recommendation",
        "recommendation_tier",
        "recommendation_market",
        "recommendation_selection",
        "recommendation_line",
        "recommendation_odds",
        "ev_se",
        "formal_blockers",
        "fair_ah",
        "market_ah",
        "edge_ah",
        "market_ah_display",
        "home_display_line",
        "away_display_line",
        "independent_signal_count",
        "missing_independent_sources",
        "model_version",
        "calibration_version",
        "data_profile",
        "raw_recommendation_json",
    ),
    "market_timeline_snapshots": (
        "source",
        "fixture_id",
        "teams",
        "kickoff_utc",
        "checkpoint",
        "checkpoint_status",
        "captured_at",
        "as_of",
        "phase",
        "status",
        "pattern",
        "verified",
        "direction_allowed",
        "market_comparable",
        "line",
        "home_price",
        "away_price",
        "bookmaker_count",
        "snapshot_json",
        "raw_timeline_json",
    ),
    "locked_recommendation_snapshots": (
        "source",
        "lock_id",
        "recommendation_id",
        "fixture_id",
        "teams",
        "captured_at",
        "locked_at",
        "as_of",
        "kickoff_utc",
        "status",
        "tier",
        "pick_side",
        "pick_line",
        "recommendation_market",
        "recommendation_selection",
        "recommendation_line",
        "recommendation_odds",
        "fair_ah",
        "market_ah",
        "home_price",
        "away_price",
        "expected_value",
        "ev_se",
        "reproducible",
        "legacy_marker_only",
        "snapshot_payload_hash",
        "release_sha",
        "data_profile",
        "market_timeline_json",
        "ah_settlement_distribution_json",
        "snapshot_payload_json",
        "raw_locked_snapshot_json",
    ),
    "settlement_history": (
        "source",
        "settlement_id",
        "recommendation_id",
        "lock_id",
        "lock_snapshot_status",
        "fixture_id",
        "teams",
        "result_id",
        "status",
        "outcome",
        "result",
        "pnl",
        "settled_at",
        "matched_recommendation",
        "tier",
        "movement_pattern",
        "raw_settlement_json",
    ),
    "calibration_report": (
        "schema_version",
        "generated_at",
        "as_of",
        "release_sha",
        "bucket",
        "tier",
        "movement_pattern",
        "line_bucket",
        "sample_count",
        "min_bucket_samples_for_rate",
        "status",
        "label",
        "not_a_formal_gate",
        "posthoc_only",
        "predicted_cover_probability",
        "actual_cover_probability",
        "brier",
        "log_loss",
    ),
}


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
    exported_at = (
        _iso(generated_at) if generated_at is not None else _payload_as_of(dashboard_payload)
    )
    environment_policy = _audit_environment_policy(dashboard_payload)
    matches = [item for item in _list(dashboard_payload.get("all")) if isinstance(item, dict)]
    locked_rows = _locked_recommendation_snapshots(matches)
    settlement_rows = _settlement_history(matches)
    tables = {
        "prematch_recommendations": _prematch_recommendations(
            dashboard_payload,
            matches,
            environment_policy=environment_policy,
        ),
        "market_timeline_snapshots": _market_timeline_snapshots(matches),
        "locked_recommendation_snapshots": locked_rows,
        "settlement_history": settlement_rows,
        "calibration_report": [],
    }
    if session is not None:
        tables["market_timeline_snapshots"].extend(_db_market_timeline_snapshots(session))
        tables["locked_recommendation_snapshots"].extend(_db_locked_snapshots(session))
        tables["settlement_history"].extend(_db_settlement_history(session))
    tables["calibration_report"] = build_calibration_report(
        lock_rows=tables["locked_recommendation_snapshots"],
        settlement_rows=tables["settlement_history"],
        generated_at=exported_at,
    )
    tables = _normalize_tables(tables)
    manifest = {
        "status": "PASS",
        "schema_version": "w2.audit_export.v1",
        "environment": environment_policy["environment"],
        "policy_version": environment_policy["policy_version"],
        "lock_policy_name": _dict(environment_policy.get("lock_policy")).get("name"),
        "environment_policy": environment_policy,
        "exported_at": exported_at,
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
    *,
    environment_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    payload_as_of = _payload_as_of(payload)
    lock_policy = _dict(environment_policy.get("lock_policy"))
    rows = []
    for match in matches:
        decision = decide_match(match)
        recommendation = _dict(match.get("recommendation"))
        recommendation_for_export = (
            recommendation if decision.state == MatchDecisionState.FORMAL else {}
        )
        pricing = _dict(match.get("pricing_shadow"))
        ah = _dict(_dict(match.get("current_odds")).get("ah"))
        rows.append(
            {
                "source": "dashboard_payload",
                "environment": environment_policy.get("environment"),
                "policy_version": environment_policy.get("policy_version"),
                "lock_policy_name": lock_policy.get("name"),
                "fixture_id": match.get("fixture_id"),
                "kickoff_utc": match.get("kickoff_utc"),
                "teams": _teams(match),
                "competition": match.get("competition") or match.get("competition_name"),
                "as_of": _as_of(match, payload_as_of),
                "fixture_status": match.get("status"),
                "report_state": decision.state.value,
                "decision_tier": match.get("decision_tier"),
                "data_status": match.get("data_status"),
                "missing_fields": match.get("missing_fields"),
                "stale_fields": match.get("stale_fields"),
                "lifecycle_status": match.get("lifecycle_status"),
                "outcome_tracked": match.get("outcome_tracked"),
                "lock_eligible": match.get("lock_eligible"),
                "decision_contract_reason_code": match.get("reason_code"),
                "decision_contract_action": match.get("action"),
                "decision_contract_next_eval_at": match.get("next_eval_at"),
                "provider_budget_status": match.get("provider_budget_status"),
                "reason_code": decision.reason,
                "reason_cn": decision.label_cn,
                "formal_recommendation": match.get("formal_recommendation"),
                "recommendation_tier": recommendation_for_export.get("tier"),
                "recommendation_market": recommendation_for_export.get("market"),
                "recommendation_selection": recommendation_for_export.get("selection"),
                "recommendation_line": recommendation_for_export.get("line"),
                "recommendation_odds": recommendation_for_export.get("odds"),
                "ev_se": recommendation_for_export.get("ev_se"),
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
                "raw_recommendation_json": recommendation_for_export or None,
            }
        )
    return rows


def _audit_environment_policy(payload: dict[str, Any]) -> dict[str, Any]:
    policy = _dict(payload.get("environment_policy"))
    if policy:
        return policy
    environment = str(payload.get("environment") or payload.get("env") or "staging")
    return build_environment_policy_stamp(environment)


def _market_timeline_snapshots(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for match in matches:
        timeline = _dict(match.get("market_timeline"))
        if not timeline:
            continue
        checkpoints = [
            ("open", timeline.get("open")),
            ("current", timeline.get("current")),
        ]
        for name, snapshot in checkpoints:
            snapshot_fields = _market_snapshot_fields(snapshot)
            rows.append(
                {
                    "source": "dashboard_payload",
                    "fixture_id": match.get("fixture_id"),
                    "teams": _teams(match),
                    "kickoff_utc": match.get("kickoff_utc"),
                    "checkpoint": name,
                    "checkpoint_status": "READY" if snapshot is not None else "MISSING",
                    "captured_at": _dict(snapshot).get("captured_at"),
                    "as_of": _dict(snapshot).get("as_of") or timeline.get("as_of"),
                    "phase": None,
                    "status": timeline.get("status"),
                    "pattern": timeline.get("pattern"),
                    "verified": timeline.get("verified"),
                    "direction_allowed": timeline.get("direction_allowed"),
                    "market_comparable": None,
                    "line": snapshot_fields["line"],
                    "home_price": snapshot_fields["home_price"],
                    "away_price": snapshot_fields["away_price"],
                    "bookmaker_count": snapshot_fields["bookmaker_count"],
                    "snapshot_json": snapshot,
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
                "lock_id": locked.get("lock_id"),
                "recommendation_id": locked.get("recommendation_id"),
                "fixture_id": locked.get("fixture_id") or match.get("fixture_id"),
                "teams": _teams(match),
                "captured_at": locked.get("captured_at"),
                "locked_at": locked.get("locked_at"),
                "as_of": locked.get("as_of"),
                "kickoff_utc": locked.get("kickoff_utc") or match.get("kickoff_utc"),
                "status": locked.get("status"),
                "tier": recommendation.get("tier"),
                "pick_side": recommendation.get("selection"),
                "pick_line": recommendation.get("line"),
                "recommendation_market": recommendation.get("market"),
                "recommendation_selection": recommendation.get("selection"),
                "recommendation_line": recommendation.get("line"),
                "recommendation_odds": recommendation.get("odds"),
                "fair_ah": locked.get("fair_ah"),
                "market_ah": locked.get("market_ah"),
                "home_price": locked.get("home_price"),
                "away_price": locked.get("away_price"),
                "expected_value": recommendation.get("expected_value"),
                "ev_se": recommendation.get("ev_se"),
                "reproducible": locked.get("reproducible"),
                "legacy_marker_only": locked.get("legacy_marker_only"),
                "snapshot_payload_hash": locked.get("snapshot_payload_hash"),
                "release_sha": locked.get("release_sha"),
                "data_profile": locked.get("data_profile"),
                "market_timeline_json": locked.get("market_timeline"),
                "ah_settlement_distribution_json": locked.get("ah_settlement_distribution"),
                "snapshot_payload_json": locked.get("snapshot_payload"),
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
                "settlement_id": settlement.get("settlement_id"),
                "recommendation_id": locked.get("recommendation_id"),
                "lock_id": locked.get("lock_id"),
                "lock_snapshot_status": _lock_snapshot_status(locked.get("lock_id")),
                "fixture_id": locked.get("fixture_id") or match.get("fixture_id"),
                "teams": _teams(match),
                "result_id": settlement.get("result_id"),
                "status": settlement.get("status"),
                "outcome": settlement.get("outcome"),
                "result": settlement.get("result"),
                "pnl": settlement.get("pnl"),
                "settled_at": settlement.get("settled_at"),
                "matched_recommendation": settlement.get("matched_recommendation"),
                "tier": settlement.get("tier"),
                "movement_pattern": settlement.get("movement_pattern"),
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
        snapshot_fields = _market_snapshot_fields(payload)
        rows.append(
            {
                "source": "forward_market_snapshot_model",
                "fixture_id": item.fixture_id,
                "checkpoint": item.phase,
                "checkpoint_status": "READY",
                "phase": item.phase,
                "captured_at": item.captured_at,
                "market_comparable": item.market_comparable,
                "as_of": payload.get("as_of") if isinstance(payload, dict) else None,
                "status": payload.get("status") if isinstance(payload, dict) else None,
                "pattern": payload.get("pattern") if isinstance(payload, dict) else None,
                "verified": payload.get("verified") if isinstance(payload, dict) else None,
                "direction_allowed": (
                    payload.get("direction_allowed") if isinstance(payload, dict) else None
                ),
                "line": snapshot_fields["line"],
                "home_price": snapshot_fields["home_price"],
                "away_price": snapshot_fields["away_price"],
                "bookmaker_count": snapshot_fields["bookmaker_count"],
                "snapshot_json": payload,
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
                "ev_se": _snapshot_recommendation_field(item.snapshot_payload_json, "ev_se"),
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
                "lock_snapshot_status": _lock_snapshot_status(item.lock_id),
                "result_id": item.result_id,
                "status": None,
                "outcome": item.outcome,
                "result": None,
                "pnl": None,
                "settled_at": item.settled_at,
                "matched_recommendation": item.matched_recommendation,
                "tier": item.tier,
                "movement_pattern": item.movement_pattern,
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    table_name = path.stem
    fieldnames = list(AUDIT_TABLE_COLUMNS[table_name])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _cell(row.get(key)) for key in fieldnames})


def _normalize_tables(tables: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {
        table_name: [
            {column: row.get(column) for column in AUDIT_TABLE_COLUMNS[table_name]}
            for row in rows
        ]
        for table_name, rows in tables.items()
    }


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


def _payload_as_of(payload: dict[str, Any]) -> str:
    value = (
        payload.get("generated_at")
        or payload.get("as_of")
        or payload.get("asof")
        or payload.get("build_time")
        or payload.get("api_build_time")
        or payload.get("web_build_time")
    )
    if not value:
        raise ValueError("dashboard payload missing generated_at/as_of")
    return str(value)


def _lock_snapshot_status(lock_id: Any) -> str:
    return "READY" if lock_id not in {None, ""} else "MISSING_LOCK_SNAPSHOT"


def _snapshot_recommendation_field(snapshot_payload: Any, field: str) -> Any:
    recommendation = _dict(_dict(snapshot_payload).get("recommendation"))
    return recommendation.get(field)


def _market_snapshot_fields(snapshot: Any) -> dict[str, Any]:
    payload = _dict(snapshot)
    return {
        "line": _first_present(payload, "line", "home_line", "market_ah"),
        "home_price": payload.get("home_price"),
        "away_price": payload.get("away_price"),
        "bookmaker_count": payload.get("bookmaker_count"),
    }


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return None


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
