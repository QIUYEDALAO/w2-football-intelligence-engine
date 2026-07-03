from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.models import RecommendationLockModel, RecommendationModel
from w2.infrastructure.persistence.recommendation_lock_snapshot import (
    build_recommendation_lock_snapshot,
)
from w2.settlement.settle import WIN_UNITS, settle_market

MIN_BUCKET_SAMPLES_FOR_RATE = 30
SNAPSHOT_SCHEMA_VERSION = "w2_formal_recommendation_snapshot.v1"
SETTLEMENT_SCHEMA_VERSION = "w2_formal_recommendation_settlement.v1"
REPORT_SCHEMA_VERSION = "w2_formal_tracking_report.v1"
SNAPSHOT_DIRNAME = "formal_recommendation_snapshots"
SETTLEMENT_DIRNAME = "formal_recommendation_settlements"
DEFAULT_REPORT_PATH = Path("reports/w2_formal_tracking/latest/report.json")
VOID_STATUSES = {"VOID", "POSTPONED", "ABANDONED", "CANCELLED"}
FINISHED_STATUSES = {"FINISHED", "FT", "AET", "PEN"}


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def runtime_root_from_env() -> Path:
    return Path(os.getenv("W2_RUNTIME_ROOT", "runtime"))


def snapshot_dir(runtime_root: Path | None = None) -> Path:
    return (runtime_root or runtime_root_from_env()) / SNAPSHOT_DIRNAME


def settlement_dir(runtime_root: Path | None = None) -> Path:
    return (runtime_root or runtime_root_from_env()) / SETTLEMENT_DIRNAME


def report_path(path: Path | None = None) -> Path:
    return path or Path(os.getenv("W2_FORMAL_TRACKING_REPORT", str(DEFAULT_REPORT_PATH)))


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def json_paths(path: Path) -> list[Path]:
    try:
        return sorted(path.glob("*.json"))
    except OSError:
        return []


def stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def decimal_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def percent_number(value: Any) -> float | None:
    if isinstance(value, str) and value.endswith("pct"):
        return number(value[:-3])
    return number(value)


def recommendation_side(selection: Any) -> str:
    text = str(selection or "").upper()
    if text.startswith("HOME"):
        return "HOME"
    if text.startswith("AWAY"):
        return "AWAY"
    return "UNKNOWN"


def recommendation_market(market: Any) -> str:
    text = str(market or "").upper()
    if text in {"AH", "ASIAN_HANDICAP"}:
        return "ASIAN_HANDICAP"
    return text or "UNKNOWN"


def first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def formal_snapshot_key(snapshot: dict[str, Any]) -> tuple[str, str, str, str | None]:
    rec = first_dict(snapshot.get("recommendation"))
    return (
        str(snapshot.get("fixture_id", "")),
        str(rec.get("market", "")),
        str(rec.get("selection_side", rec.get("selection", ""))),
        str(rec.get("line")) if rec.get("line") is not None else None,
    )


def existing_snapshot_keys(root: Path | None = None) -> set[tuple[str, str, str, str | None]]:
    keys: set[tuple[str, str, str, str | None]] = set()
    for path in json_paths(snapshot_dir(root)):
        payload = load_json(path, {})
        if isinstance(payload, dict):
            keys.add(formal_snapshot_key(payload))
    return keys


def snapshot_id(payload: dict[str, Any]) -> str:
    basis = {
        "fixture_id": payload.get("fixture_id"),
        "as_of": payload.get("as_of"),
        "recommendation": payload.get("recommendation"),
        "pricing_shadow": payload.get("pricing_shadow"),
    }
    return stable_hash(basis)[:24]


def _result_payload(card: dict[str, Any]) -> dict[str, Any]:
    result = first_dict(card.get("result"))
    status = str(result.get("status") or card.get("status") or "").upper()
    return {
        "status": status,
        "home_goals": result.get("home_goals"),
        "away_goals": result.get("away_goals"),
        "settled_at": result.get("settled_at"),
    }


def _capture_as_of(card: dict[str, Any], now: datetime) -> datetime | None:
    movement = first_dict(card.get("market_movement"))
    recommendation = first_dict(card.get("recommendation"))
    candidates = [
        movement.get("as_of_latest"),
        recommendation.get("generated_at"),
        card.get("generated_at"),
    ]
    for candidate in candidates:
        parsed = parse_dt(candidate)
        if parsed is not None:
            return parsed
    return now


def snapshot_from_card(
    card: dict[str, Any],
    *,
    now: datetime | None = None,
    release_sha: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    captured_at = now or utc_now()
    recommendation = first_dict(card.get("recommendation"))
    pricing_shadow = first_dict(card.get("pricing_shadow"))
    if card.get("formal_recommendation") is not True or recommendation.get("tier") != "FORMAL":
        return None, "NOT_FORMAL"
    kickoff = parse_dt(card.get("kickoff_utc"))
    as_of = _capture_as_of(card, captured_at)
    if kickoff is None or as_of is None:
        return None, "MISSING_TIME"
    if as_of >= kickoff or captured_at >= kickoff:
        return None, "NOT_PREMATCH"
    market = recommendation_market(recommendation.get("market"))
    side = recommendation_side(recommendation.get("selection"))
    line = decimal_text(recommendation.get("line"))
    if market != "ASIAN_HANDICAP" or side == "UNKNOWN" or line is None:
        return None, "UNSUPPORTED_FORMAL_MARKET"
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "fixture_id": str(card.get("fixture_id")),
        "captured_at": iso(captured_at),
        "as_of": iso(as_of),
        "kickoff_utc": iso(kickoff),
        "home_team_name": card.get("home_team_name"),
        "away_team_name": card.get("away_team_name"),
        "competition": card.get("competition_name"),
        "recommendation": {
            "tier": "FORMAL",
            "market": market,
            "selection": recommendation.get("selection"),
            "selection_side": side,
            "selection_label_cn": recommendation.get("selection_label_cn"),
            "line": line,
            "odds": decimal_text(recommendation.get("odds")),
            "risk_adjusted_ev": recommendation.get("risk_adjusted_ev"),
            "reverse_factor_value": bool(recommendation.get("reverse_factor_value")),
        },
        "pricing_shadow": {
            "model_version": pricing_shadow.get("model_version"),
            "calibration_version": pricing_shadow.get("calibration_version"),
            "simulation_model_version": pricing_shadow.get("simulation_model_version"),
            "simulation_calibration_version": pricing_shadow.get("simulation_calibration_version"),
            "fair_ah": number(pricing_shadow.get("fair_ah")),
            "market_ah": number(pricing_shadow.get("market_ah")),
            "edge_ah": number(pricing_shadow.get("edge_ah")),
            "coverage": number(pricing_shadow.get("coverage")),
            "asof_market_snapshot_id": pricing_shadow.get("asof_market_snapshot_id"),
            "devig_method": pricing_shadow.get("devig_method"),
            "beats_market": False,
        },
        "market_movement": first_dict(card.get("market_movement")),
        "market_divergence": first_dict(card.get("market_divergence")),
        "bookmaker_hypothesis": first_dict(card.get("bookmaker_hypothesis")),
        "formal_result_tracking": {
            "not_a_formal_gate": True,
            "posthoc_only": True,
            "min_bucket_samples_for_rate": MIN_BUCKET_SAMPLES_FOR_RATE,
        },
        "scoreline_reference": first_dict(card.get("scoreline_reference")) or None,
        "simulation_evidence": _simulation_evidence(card),
        "candidate": False,
        "formal_recommendation": True,
        "release_sha": release_sha,
        "immutable": True,
    }
    snapshot["snapshot_id"] = snapshot_id(snapshot)
    snapshot["prediction_hash"] = stable_hash(
        {
            "fixture_id": snapshot["fixture_id"],
            "as_of": snapshot["as_of"],
            "recommendation": snapshot["recommendation"],
        }
    )
    return snapshot, None


def _simulation_evidence(card: dict[str, Any]) -> dict[str, Any] | None:
    pricing_shadow = first_dict(card.get("pricing_shadow"))
    simulation = first_dict(card.get("simulation"), pricing_shadow.get("simulation"))
    if not simulation:
        return None
    runs = (
        simulation.get("simulations")
        or simulation.get("simulation_runs")
        or simulation.get("runs")
    )
    source = (
        "formal_simulation"
        if simulation.get("status") == "READY"
        else simulation.get("source")
    )
    return {
        "simulations": runs,
        "source": source,
        "model_version": simulation.get("model_version"),
        "calibration_version": simulation.get("calibration_version"),
    }


def capture_formal_snapshots(
    cards: list[dict[str, Any]],
    *,
    dry_run: bool = True,
    write_artifacts: bool = False,
    runtime_root: Path | None = None,
    now: datetime | None = None,
    release_sha: str | None = None,
) -> dict[str, Any]:
    captured_at = now or utc_now()
    keys = existing_snapshot_keys(runtime_root)
    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for card in cards:
        snapshot, blocker = snapshot_from_card(card, now=captured_at, release_sha=release_sha)
        if snapshot is None:
            counts[blocker or "SKIPPED"] += 1
            continue
        key = formal_snapshot_key(snapshot)
        if key in keys:
            counts["ALREADY_CAPTURED"] += 1
            results.append({"fixture_id": snapshot["fixture_id"], "status": "ALREADY_CAPTURED"})
            continue
        counts["CAPTURED"] += 1
        result = {
            "fixture_id": snapshot["fixture_id"],
            "snapshot_id": snapshot["snapshot_id"],
            "status": "WOULD_WRITE" if dry_run or not write_artifacts else "WRITTEN",
        }
        if write_artifacts and not dry_run:
            write_json_atomic(
                snapshot_dir(runtime_root) / f"{snapshot['snapshot_id']}.json",
                snapshot,
            )
            keys.add(key)
        results.append(result)
    return {
        "status": "PASS",
        "dry_run": dry_run,
        "write_artifacts": write_artifacts,
        "captured_at": iso(captured_at),
        "eligible_seen": counts["CAPTURED"] + counts["ALREADY_CAPTURED"],
        "written": sum(1 for row in results if row["status"] == "WRITTEN"),
        "already_captured": counts["ALREADY_CAPTURED"],
        "blockers": dict(counts),
        "results": results,
        "not_a_formal_gate": True,
        "posthoc_only": True,
    }


def capture_formal_locks(
    cards: list[dict[str, Any]],
    *,
    session: Session,
    now: datetime | None = None,
    release_sha: str | None = None,
) -> dict[str, Any]:
    captured_at = now or utc_now()
    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for card in cards:
        recommendation = first_dict(card.get("recommendation"))
        recommendation_id = _recommendation_id(card)
        if recommendation_id is None:
            if card.get("formal_recommendation") is True or recommendation.get("tier") == "FORMAL":
                counts["MISSING_RECOMMENDATION_ID"] += 1
            else:
                counts["NOT_FORMAL"] += 1
            continue
        existing = session.scalars(
            select(RecommendationLockModel).where(
                RecommendationLockModel.recommendation_id == recommendation_id
            )
        ).first()
        if existing is not None:
            counts["ALREADY_LOCKED"] += 1
            results.append(
                {
                    "fixture_id": card.get("fixture_id"),
                    "recommendation_id": recommendation_id,
                    "lock_id": existing.id,
                    "status": "ALREADY_LOCKED",
                }
            )
            continue
        recommendation_marker = session.get(RecommendationModel, recommendation_id)
        if recommendation_marker is None:
            fixture_id = card.get("fixture_id")
            if not isinstance(fixture_id, str) or not fixture_id:
                counts["MISSING_FIXTURE_ID"] += 1
                continue
            recommendation_marker = RecommendationModel(
                id=recommendation_id,
                fixture_id=fixture_id,
                prediction_id=None,
                status="FORMAL",
                created_at=captured_at,
            )
            session.add(recommendation_marker)
            session.flush()
            counts["RECOMMENDATION_MARKER_CREATED"] += 1
        try:
            lock = build_recommendation_lock_snapshot(
                recommendation_id=recommendation_id,
                card=card,
                locked_at=captured_at,
                reason="formal prematch lock",
                release_sha=release_sha,
            )
        except ValueError as exc:
            counts[str(exc)] += 1
            continue
        session.add(lock)
        session.flush()
        counts["LOCKED"] += 1
        results.append(
            {
                "fixture_id": card.get("fixture_id"),
                "recommendation_id": recommendation_id,
                "lock_id": lock.id,
                "snapshot_payload_hash": lock.snapshot_payload_hash,
                "status": "LOCKED",
            }
        )
    return {
        "status": "PASS",
        "captured_at": iso(captured_at),
        "written": counts["LOCKED"],
        "already_locked": counts["ALREADY_LOCKED"],
        "blockers": dict(counts),
        "results": results,
        "not_a_formal_gate": True,
        "posthoc_only": True,
    }


def _recommendation_id(card: dict[str, Any]) -> str | None:
    recommendation = first_dict(card.get("recommendation"))
    for value in (
        recommendation.get("recommendation_id"),
        recommendation.get("id"),
        card.get("recommendation_id"),
    ):
        if isinstance(value, str) and value:
            return value
    return None


def snapshot_to_result(card: dict[str, Any]) -> dict[str, Any] | None:
    result = _result_payload(card)
    status = result["status"]
    if status not in FINISHED_STATUSES and status not in VOID_STATUSES:
        return None
    return result


def settle_snapshot(
    snapshot: dict[str, Any],
    result: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    evaluated_at = now or utc_now()
    status = str(result.get("status") or "").upper()
    home_goals = result.get("home_goals")
    away_goals = result.get("away_goals")
    rec = first_dict(snapshot.get("recommendation"))
    if status in VOID_STATUSES:
        outcome = "VOID"
    else:
        if not isinstance(home_goals, int) or not isinstance(away_goals, int):
            raise ValueError("finished result requires integer home_goals and away_goals")
        outcome = settle_market(
            market=str(rec.get("market")),
            selection=str(rec.get("selection_side") or rec.get("selection")),
            line=str(rec.get("line")),
            home_goals_90=home_goals,
            away_goals_90=away_goals,
        )
    settled_units = WIN_UNITS[outcome]
    settlement = {
        "schema_version": SETTLEMENT_SCHEMA_VERSION,
        "fixture_id": snapshot.get("fixture_id"),
        "snapshot_id": snapshot.get("snapshot_id"),
        "prediction_hash": snapshot.get("prediction_hash"),
        "market": rec.get("market"),
        "selection_side": rec.get("selection_side"),
        "line": rec.get("line"),
        "final_score": {
            "home_goals": home_goals,
            "away_goals": away_goals,
            "status": status,
        },
        "settlement_outcome": outcome,
        "settled_units": str(settled_units),
        "sample_included": outcome != "VOID",
        "win_included": outcome in {"WIN", "HALF_WIN"},
        "evaluated_at": iso(evaluated_at),
        "asof_market_snapshot_id": first_dict(snapshot.get("pricing_shadow")).get(
            "asof_market_snapshot_id"
        ),
        "devig_method": first_dict(snapshot.get("pricing_shadow")).get("devig_method"),
        "not_a_formal_gate": True,
        "posthoc_only": True,
        "candidate": False,
        "formal_recommendation": True,
    }
    settlement["settlement_id"] = stable_hash(
        {
            "snapshot_id": settlement["snapshot_id"],
            "final_score": settlement["final_score"],
            "outcome": outcome,
        }
    )[:24]
    return settlement


def settle_formal_snapshots(
    cards: list[dict[str, Any]],
    *,
    dry_run: bool = True,
    write_artifacts: bool = False,
    runtime_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    result_by_fixture = {
        str(card.get("fixture_id")): result
        for card in cards
        if (result := snapshot_to_result(card)) is not None
    }
    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for path in json_paths(snapshot_dir(runtime_root)):
        snapshot = load_json(path, {})
        if not isinstance(snapshot, dict):
            counts["BAD_SNAPSHOT"] += 1
            continue
        sid = str(snapshot.get("snapshot_id"))
        out_path = settlement_dir(runtime_root) / f"{sid}.json"
        if out_path.exists():
            counts["ALREADY_SETTLED"] += 1
            continue
        result = result_by_fixture.get(str(snapshot.get("fixture_id")))
        if result is None:
            counts["PENDING_RESULT"] += 1
            continue
        settlement = settle_snapshot(snapshot, result, now=now)
        counts["SETTLED"] += 1
        row = {
            "fixture_id": snapshot.get("fixture_id"),
            "snapshot_id": sid,
            "status": "WOULD_WRITE" if dry_run or not write_artifacts else "WRITTEN",
            "outcome": settlement["settlement_outcome"],
        }
        if write_artifacts and not dry_run:
            write_json_atomic(out_path, settlement)
        results.append(row)
    return {
        "status": "PASS",
        "dry_run": dry_run,
        "write_artifacts": write_artifacts,
        "written": sum(1 for row in results if row["status"] == "WRITTEN"),
        "counts": dict(counts),
        "results": results,
        "not_a_formal_gate": True,
        "posthoc_only": True,
    }


def load_snapshots(root: Path | None = None) -> list[dict[str, Any]]:
    return [
        payload
        for path in json_paths(snapshot_dir(root))
        if isinstance((payload := load_json(path, {})), dict)
    ]


def load_settlements(root: Path | None = None) -> list[dict[str, Any]]:
    return [
        payload
        for path in json_paths(settlement_dir(root))
        if isinstance((payload := load_json(path, {})), dict)
    ]


def line_bucket(line: Any) -> str:
    text = str(line) if line is not None else "UNKNOWN"
    return f"AH_{text.replace('+', '').replace('-', 'minus_').replace('.', '_')}"


def value_bucket(value: Any) -> str:
    parsed = percent_number(value)
    if parsed is None:
        return "UNKNOWN"
    if parsed < 0:
        return "NEGATIVE"
    if parsed < 5:
        return "0_5pct"
    if parsed < 10:
        return "5_10pct"
    return "10pct_plus"


def divergence_bucket(snapshot: dict[str, Any]) -> str:
    divergence = first_dict(snapshot.get("market_divergence"))
    values = [
        abs(v)
        for v in [
            number(divergence.get("lock_divergence")),
            number(divergence.get("open_divergence")),
        ]
        if v is not None
    ]
    if not values:
        return "UNKNOWN"
    value = max(values)
    if value <= 0.25:
        return "0_0.25"
    if value <= 0.5:
        return "0.25_0.5"
    if value <= 1.0:
        return "0.5_1.0"
    return "1.0_plus"


def bucket_row(
    name: str,
    sample_count: int,
    win_count: int,
    settled_units: Decimal,
) -> dict[str, Any]:
    ready = sample_count >= MIN_BUCKET_SAMPLES_FOR_RATE
    return {
        "bucket": name,
        "sample_count": sample_count,
        "win_count": win_count,
        "status": "READY" if ready else "OBSERVING",
        "label": (
            f"样本已达标 · {sample_count}/{MIN_BUCKET_SAMPLES_FOR_RATE}"
            if ready
            else f"观察中 · {sample_count}/{MIN_BUCKET_SAMPLES_FOR_RATE}"
        ),
        "win_rate": (win_count / sample_count if ready and sample_count else None),
        "roi": (float(settled_units / Decimal(sample_count)) if ready and sample_count else None),
    }


def report_summary(settlements: list[dict[str, Any]]) -> dict[str, Any]:
    included = [row for row in settlements if row.get("sample_included") is True]
    wins = [row for row in included if row.get("win_included") is True]
    settled_units = sum(
        (Decimal(str(row.get("settled_units", "0"))) for row in included),
        Decimal("0"),
    )
    return bucket_row("portfolio", len(included), len(wins), settled_units)


def build_tracking_report(
    *,
    runtime_root: Path | None = None,
    output_report: Path | None = None,
    write: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or utc_now()
    snapshots = {str(row.get("snapshot_id")): row for row in load_snapshots(runtime_root)}
    settlements = load_settlements(runtime_root)
    included_settlements = [row for row in settlements if row.get("sample_included") is True]
    summary = report_summary(settlements)
    buckets: dict[str, defaultdict[str, list[dict[str, Any]]]] = {
        "market": defaultdict(list),
        "selection_side": defaultdict(list),
        "reverse_factor_value": defaultdict(list),
        "market_movement_pattern": defaultdict(list),
        "divergence_bucket": defaultdict(list),
        "value_bucket": defaultdict(list),
        "simulation_calibration_version": defaultdict(list),
        "line_bucket": defaultdict(list),
    }
    for settlement in included_settlements:
        snapshot = snapshots.get(str(settlement.get("snapshot_id")), {})
        rec = first_dict(snapshot.get("recommendation"))
        movement = first_dict(snapshot.get("market_movement"))
        pricing = first_dict(snapshot.get("pricing_shadow"))
        bucket_values = {
            "market": str(rec.get("market") or "UNKNOWN"),
            "selection_side": str(rec.get("selection_side") or "UNKNOWN"),
            "reverse_factor_value": str(bool(rec.get("reverse_factor_value"))).lower(),
            "market_movement_pattern": str(movement.get("pattern") or "INSUFFICIENT"),
            "divergence_bucket": divergence_bucket(snapshot),
            "value_bucket": value_bucket(rec.get("risk_adjusted_ev")),
            "simulation_calibration_version": str(
                pricing.get("simulation_calibration_version") or "UNKNOWN"
            ),
            "line_bucket": line_bucket(rec.get("line")),
        }
        for dimension, bucket in bucket_values.items():
            buckets[dimension][bucket].append(settlement)
    rendered_buckets: dict[str, list[dict[str, Any]]] = {}
    for dimension, rows_by_bucket in buckets.items():
        rendered_buckets[dimension] = []
        for name, rows in sorted(rows_by_bucket.items()):
            wins = sum(1 for row in rows if row.get("win_included") is True)
            units = sum((Decimal(str(row.get("settled_units", "0"))) for row in rows), Decimal("0"))
            rendered_buckets[dimension].append(bucket_row(name, len(rows), wins, units))
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": iso(generated_at),
        "status": summary["status"],
        "label": summary["label"],
        "min_bucket_samples_for_rate": MIN_BUCKET_SAMPLES_FOR_RATE,
        "snapshot_count": len(snapshots),
        "settlement_count": len(settlements),
        "sample_count": summary["sample_count"],
        "win_count": summary["win_count"],
        "win_rate": summary["win_rate"],
        "roi": summary["roi"],
        "buckets": rendered_buckets,
        "not_a_formal_gate": True,
        "posthoc_only": True,
    }
    if write:
        write_json_atomic(report_path(output_report), report)
    return report


def load_tracking_report(
    path: Path | None = None,
    runtime_root: Path | None = None,
) -> dict[str, Any]:
    target = report_path(path)
    payload = load_json(target, {})
    if isinstance(payload, dict) and payload:
        return payload
    return build_tracking_report(runtime_root=runtime_root, output_report=target, write=False)


def endpoint_summary(path: Path | None = None, runtime_root: Path | None = None) -> dict[str, Any]:
    report = load_tracking_report(path=path, runtime_root=runtime_root)
    return {
        "generated_at": report.get("generated_at"),
        "status": report.get("status", "OBSERVING"),
        "label": report.get("label", f"观察中 · 0/{MIN_BUCKET_SAMPLES_FOR_RATE}"),
        "min_bucket_samples_for_rate": report.get(
            "min_bucket_samples_for_rate",
            MIN_BUCKET_SAMPLES_FOR_RATE,
        ),
        "snapshot_count": report.get("snapshot_count", 0),
        "settlement_count": report.get("settlement_count", 0),
        "sample_count": report.get("sample_count", 0),
        "win_count": report.get("win_count", 0),
        "win_rate": report.get("win_rate"),
        "roi": report.get("roi"),
        "buckets": report.get("buckets", {}),
        "not_a_formal_gate": True,
        "posthoc_only": True,
    }
