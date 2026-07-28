from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.models import (
    RecommendationLockModel,
    RecommendationModel,
    SettlementModel,
)
from w2.infrastructure.persistence.recommendation_lock_snapshot import (
    build_recommendation_lock_snapshot,
)
from w2.prematch.simulation_reconciliation import canonical_public_simulation
from w2.settlement.settle import WIN_UNITS, settle_market
from w2.tracking.outcome_ledger_repository import ImportRecord, OutcomeLedgerRepository

MIN_BUCKET_SAMPLES_FOR_RATE = 30
SNAPSHOT_SCHEMA_VERSION = "w2_formal_recommendation_snapshot.v1"
SETTLEMENT_SCHEMA_VERSION = "w2_formal_recommendation_settlement.v1"
REPORT_SCHEMA_VERSION = "w2_formal_tracking_report.v1"
VOID_STATUSES = {"VOID", "POSTPONED", "ABANDONED", "CANCELLED"}


def _formal_import(payload: dict[str, Any], record_type: str) -> ImportRecord:
    return ImportRecord(
        payload=payload,
        record_type=record_type,
        source_artifact="db:formal_tracking",
        source_line_number=None,
    )


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


def existing_snapshot_keys(
    repository: OutcomeLedgerRepository,
) -> set[tuple[str, str, str, str | None]]:
    return {formal_snapshot_key(payload) for payload in load_snapshots(repository)}


def snapshot_id(payload: dict[str, Any]) -> str:
    basis = {
        "fixture_id": payload.get("fixture_id"),
        "as_of": payload.get("as_of"),
        "recommendation": payload.get("recommendation"),
        "pricing_shadow": payload.get("pricing_shadow"),
    }
    return stable_hash(basis)[:24]


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
    simulation = canonical_public_simulation(card)
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
    repository: OutcomeLedgerRepository | None = None,
    dry_run: bool = True,
    write_db: bool = False,
    now: datetime | None = None,
    release_sha: str | None = None,
) -> dict[str, Any]:
    repo = repository or OutcomeLedgerRepository()
    captured_at = now or utc_now()
    keys = existing_snapshot_keys(repo)
    recommendation_ids = {
        recommendation_id
        for card in cards
        if (recommendation_id := _recommendation_id(card)) is not None
    }
    with Session(repo.engine) as session:
        mapped_recommendations = set(
            session.scalars(
                select(RecommendationModel.id).where(
                    RecommendationModel.id.in_(recommendation_ids)
                )
            )
        )
    results: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for card in cards:
        recommendation_id = _recommendation_id(card)
        if recommendation_id in mapped_recommendations:
            counts["MAPPED_TO_RECOMMENDATION_LOCK"] += 1
            continue
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
        snapshots.append(snapshot)
        result = {
            "fixture_id": snapshot["fixture_id"],
            "snapshot_id": snapshot["snapshot_id"],
            "status": "WOULD_WRITE" if dry_run or not write_db else "WRITTEN",
        }
        keys.add(key)
        results.append(result)
    appended = repo._append_imports(
        [
            _formal_import(snapshot, "formal_snapshot")
            for snapshot in snapshots
        ],
        dry_run=dry_run,
        write_db=write_db,
    )
    return {
        "status": "PASS",
        "dry_run": dry_run,
        "write_db": write_db,
        "captured_at": iso(captured_at),
        "eligible_seen": counts["CAPTURED"] + counts["ALREADY_CAPTURED"],
        "written": appended["written"],
        "db_writes": appended["db_writes"],
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
            counts["MISSING_RECOMMENDATION"] += 1
            continue
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
    *,
    repository: OutcomeLedgerRepository | None = None,
    dry_run: bool = True,
    write_db: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    repo = repository or OutcomeLedgerRepository()
    result_by_fixture = repo.result_payloads()
    snapshots = load_snapshots(repo)
    settled_snapshot_ids = {
        str(row.get("snapshot_id") or "") for row in load_settlements(repo)
    }
    results: list[dict[str, Any]] = []
    settlements: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for snapshot in snapshots:
        sid = str(snapshot.get("snapshot_id"))
        if sid in settled_snapshot_ids:
            counts["ALREADY_SETTLED"] += 1
            continue
        fixture_id = str(snapshot.get("fixture_id") or "")
        result = _result_for_fixture(result_by_fixture, fixture_id)
        if result is None:
            counts["PENDING_RESULT"] += 1
            continue
        settlement = settle_snapshot(snapshot, result, now=now)
        settlements.append(settlement)
        counts["SETTLED"] += 1
        row = {
            "fixture_id": snapshot.get("fixture_id"),
            "snapshot_id": sid,
            "status": "WOULD_WRITE" if dry_run or not write_db else "WRITTEN",
            "outcome": settlement["settlement_outcome"],
        }
        results.append(row)
    appended = repo._append_imports(
        [_formal_import(item, "formal_settlement") for item in settlements],
        dry_run=dry_run,
        write_db=write_db,
    )
    return {
        "status": "PASS",
        "dry_run": dry_run,
        "write_db": write_db,
        "written": appended["written"],
        "db_writes": appended["db_writes"],
        "counts": dict(counts),
        "results": results,
        "not_a_formal_gate": True,
        "posthoc_only": True,
    }


def load_snapshots(
    repository: OutcomeLedgerRepository | None = None,
) -> list[dict[str, Any]]:
    repo = repository or OutcomeLedgerRepository()
    rows = repo.records({"formal_snapshot"})
    with Session(repo.engine) as session:
        rows.extend(
            dict(lock.snapshot_payload_json)
            for lock in session.scalars(
                select(RecommendationLockModel).where(
                    RecommendationLockModel.snapshot_payload_json.is_not(None)
                )
            )
            if isinstance(lock.snapshot_payload_json, dict)
        )
    by_id = {str(payload.get("snapshot_id") or stable_hash(payload)): payload for payload in rows}
    return [by_id[key] for key in sorted(by_id)]


def load_settlements(
    repository: OutcomeLedgerRepository | None = None,
) -> list[dict[str, Any]]:
    repo = repository or OutcomeLedgerRepository()
    raw_rows = repo.records({"formal_settlement"})
    snapshots = {
        str(row.get("snapshot_id") or ""): row
        for row in load_snapshots(repo)
    }
    result_by_fixture = repo.result_payloads()
    rows: list[dict[str, Any]] = []
    for item in raw_rows:
        if item.get("settlement_outcome") == "VOID":
            rows.append(item)
            continue
        snapshot = snapshots.get(str(item.get("snapshot_id") or ""))
        result = _result_for_fixture(
            result_by_fixture,
            str(item.get("fixture_id") or ""),
        )
        if snapshot is None or result is None:
            continue
        rows.append(
            settle_snapshot(
                snapshot,
                result,
                now=parse_dt(item.get("evaluated_at")) or utc_now(),
            )
        )
    with Session(repo.engine) as session:
        settlements = list(
            session.scalars(select(SettlementModel).order_by(SettlementModel.settled_at))
        )
        for settlement_model in settlements:
            snapshot = (
                settlement_model.lock.snapshot_payload_json
                if settlement_model.lock is not None
                else None
            )
            if not isinstance(snapshot, dict):
                continue
            rows.append(
                settle_snapshot(
                    snapshot,
                    {
                        "status": settlement_model.result.result_status,
                        "home_goals": settlement_model.result.home_goals,
                        "away_goals": settlement_model.result.away_goals,
                    },
                    now=settlement_model.settled_at,
                )
            )
    return rows


def _result_for_fixture(
    results: dict[str, dict[str, Any]],
    fixture_id: str,
) -> dict[str, Any] | None:
    bare = fixture_id.removeprefix("api_football:")
    return (
        results.get(fixture_id)
        or results.get(bare)
        or results.get(f"api_football:{bare}")
    )


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
    repository: OutcomeLedgerRepository | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    repo = repository or OutcomeLedgerRepository()
    generated_at = now or utc_now()
    snapshots = {str(row.get("snapshot_id")): row for row in load_snapshots(repo)}
    settlements = load_settlements(repo)
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
        "source": "recommendation_locks+results+settlements+outcome_ledger",
        "db_reads": 4,
    }
    return report


def endpoint_summary(
    repository: OutcomeLedgerRepository | None = None,
) -> dict[str, Any]:
    report = build_tracking_report(repository=repository)
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
