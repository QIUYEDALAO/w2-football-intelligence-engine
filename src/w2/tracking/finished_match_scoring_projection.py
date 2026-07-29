from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.tracking.forward_ledger_performance import CLV_METHOD, fixture_clv
from w2.tracking.performance_scoring import (
    bootstrap_ci,
    brier,
    ece,
    log_loss,
    paired_bootstrap,
    probability_vector,
    reliability_bins,
    rps,
)

SCHEMA_VERSION = "w2.finished_match_scoring_projection.v1"
PROJECTION_VERSION = "eval-01b.v1"
WRITE_CONFIRMATION_PHRASE = "EVAL_01B_WRITE_SCORING_PROJECTION"  # noqa: S105
TERMINAL_STATUSES = {"FT", "AET", "PEN"}
WINDOWS = {"7d": timedelta(days=7), "30d": timedelta(days=30), "90d": timedelta(days=90)}


class FinishedMatchScoringError(ValueError):
    pass


def run_finished_match_scoring_projection(
    *,
    engine: Engine | None = None,
    fixture_ids: Sequence[str] | None = None,
    dry_run: bool = True,
    write_db: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    if dry_run and write_db:
        raise FinishedMatchScoringError("write_db requires dry_run=false")
    resolved_engine = engine or create_engine()
    with Session(resolved_engine) as session:
        results = _results(session, fixture_ids)
        if not results:
            return _empty_result()
        ledger_rows = list(
            session.scalars(
                select(OutcomeLedgerModel).order_by(
                    OutcomeLedgerModel.occurred_at,
                    OutcomeLedgerModel.business_key,
                )
            )
        )
        records = [dict(row.payload) for row in ledger_rows]
        fixture_identities = {
            row.fixture_id: row
            for row in session.scalars(select(MatchdayFixtureIdentityModel))
        }
        dynamic_rows = list(
            session.scalars(select(DynamicPrematchEvaluationModel))
        )
        fixture_payloads: dict[str, dict[str, Any]] = {}
        blockers: list[str] = []
        for result in results:
            payload = _fixture_projection(
                result,
                records=records,
                fixture_identity=fixture_identities.get(result.fixture_id),
                dynamic_rows=[
                    row for row in dynamic_rows if row.fixture_id == result.fixture_id
                ],
            )
            fixture_payloads[result.fixture_id] = payload
            if payload["status"] == "BLOCKED":
                blockers.extend(
                    f"{result.fixture_id}:{reason}"
                    for reason in payload["reason_codes"]
                )

        projected_fixture_payloads = _existing_fixture_payloads(session)
        writes = 0
        skipped = 0
        write_blockers: list[str] = []
        timestamp = (now or datetime.now(UTC)).astimezone(UTC)
        for fixture_id, payload in fixture_payloads.items():
            outcome = _persist_checkpoint(
                session,
                checkpoint_key=f"performance:fixture:{fixture_id}",
                payload=payload,
                source_hash=_source_hash(payload),
                created_at=timestamp,
                write_db=write_db,
                preserve_trusted_on_blocked=True,
            )
            writes += outcome["writes"]
            skipped += outcome["skipped"]
            write_blockers.extend(outcome["blockers"])
            if outcome["accepted"]:
                projected_fixture_payloads[fixture_id] = payload
        cohort_payloads = _cohort_projections(projected_fixture_payloads)
        for key, payload in cohort_payloads.items():
            outcome = _persist_checkpoint(
                session,
                checkpoint_key=key,
                payload=payload,
                source_hash=str(payload["business_projection_hash"]),
                created_at=timestamp,
                write_db=write_db,
                preserve_trusted_on_blocked=False,
            )
            writes += outcome["writes"]
            skipped += outcome["skipped"]
            write_blockers.extend(outcome["blockers"])
        blockers.extend(write_blockers)
        if write_db:
            session.commit()
        else:
            session.rollback()
        counts = Counter(payload["status"] for payload in fixture_payloads.values())
        status = "BLOCKED" if blockers else "PASS"
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "finished_result_count": len(results),
            "fixture_checkpoint_count": len(fixture_payloads),
            "cohort_checkpoint_count": len(cohort_payloads),
            "scored_count": counts["SCORED"],
            "not_scorable_count": counts["NOT_SCORABLE"],
            "blocked_count": counts["BLOCKED"],
            "not_scorable_by_reason": dict(
                sorted(
                    Counter(
                        reason
                        for payload in fixture_payloads.values()
                        if payload["status"] == "NOT_SCORABLE"
                        for reason in payload["reason_codes"]
                    ).items()
                )
            ),
            "eligible_scoring_coverage": 1.0,
            "written": writes if write_db else 0,
            "would_write": writes if not write_db else 0,
            "skipped_existing": skipped,
            "db_writes": writes if write_db else 0,
            "provider_calls": 0,
            "blockers": sorted(set(blockers)),
        }


def _results(
    session: Session,
    fixture_ids: Sequence[str] | None,
) -> list[ResultModel]:
    statement = select(ResultModel)
    if fixture_ids is not None:
        statement = statement.where(ResultModel.fixture_id.in_(tuple(fixture_ids)))
    return list(session.scalars(statement.order_by(ResultModel.fixture_id)))


def _fixture_projection(
    result: ResultModel,
    *,
    records: Sequence[Mapping[str, Any]],
    fixture_identity: MatchdayFixtureIdentityModel | None,
    dynamic_rows: Sequence[DynamicPrematchEvaluationModel],
) -> dict[str, Any]:
    related = [
        record
        for record in records
        if _record_type(record) == "capture"
        and _fixture_id(record) == result.fixture_id
    ]
    superseded = {
        _text(record.get("target_capture_identity_hash"))
        for record in records
        if _record_type(record) == "supersession"
        and _text(record.get("supersession_status")).upper() == "SUPERSEDED"
    }
    active = [
        record
        for record in related
        if _text(record.get("capture_identity_hash")) not in superseded
    ]
    capture, status, reasons = _select_capture(active, fixture_identity)
    if result.result_status not in TERMINAL_STATUSES:
        status = "BLOCKED"
        reasons = ["RESULT_IDENTITY_CONFLICT"]
    actual = 0 if result.home_goals > result.away_goals else (
        1 if result.home_goals == result.away_goals else 2
    )
    model = probability_vector(capture or {}, "model_probabilities")
    market = probability_vector(capture or {}, "market_probabilities")
    if status != "BLOCKED":
        missing = []
        if model is None:
            missing.append("MODEL_PROBABILITY_VECTOR_MISSING")
        if market is None:
            missing.append("MARKET_PROBABILITY_VECTOR_MISSING")
        if missing:
            status = "NOT_SCORABLE"
            reasons = missing
        else:
            status = "SCORED"
            reasons = []

    fixture = _fixture_values(capture, fixture_identity, result.fixture_id)
    lifecycle, lifecycle_conflict = _lifecycle_metadata(capture, dynamic_rows)
    if lifecycle_conflict:
        status = "BLOCKED"
        reasons = ["PROBABILITY_IDENTITY_CONFLICT"]
    clv = _fixture_clv(records, capture, result.fixture_id)
    probability_hash = _hash_value(
        capture.get("probability_identity") if capture else {}
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "projection_version": PROJECTION_VERSION,
        "status": status,
        "reason_codes": sorted(set(reasons)),
        "fixture_id": result.fixture_id,
        "competition_id": fixture["competition_id"],
        "competition_name": fixture["competition_name"],
        "kickoff_utc": fixture["kickoff_utc"],
        "scoring_window_anchor": fixture["kickoff_utc"],
        "result_id": result.id,
        "result_identity_hash": result.result_hash,
        "result_status": result.result_status,
        "result_confirmed_at": _iso(result.confirmed_at),
        "home_goals": result.home_goals,
        "away_goals": result.away_goals,
        "actual_outcome": ("HOME", "DRAW", "AWAY")[actual],
        "source_capture_identity_hash": _optional(
            capture.get("capture_identity_hash") if capture else None
        ),
        "source_card_hash": _optional(capture.get("card_hash") if capture else None),
        "source_artifact_hash": _artifact_hash(capture),
        "source_capture_at": _optional(capture.get("captured_at") if capture else None),
        "source_probability_identity_hash": probability_hash if capture else None,
        "model_probabilities": list(model) if model else None,
        "market_probabilities": list(market) if market else None,
        "model_log_loss": log_loss(model, actual) if model else None,
        "market_log_loss": log_loss(market, actual) if market else None,
        "model_minus_market_log_loss": (
            log_loss(model, actual) - log_loss(market, actual)
            if model and market
            else None
        ),
        "model_brier": brier(model, actual) if model else None,
        "market_brier": brier(market, actual) if market else None,
        "model_minus_market_brier": (
            brier(model, actual) - brier(market, actual)
            if model and market
            else None
        ),
        "model_rps": rps(model, actual) if model else None,
        "market_rps": rps(market, actual) if market else None,
        "model_minus_market_rps": (
            rps(model, actual) - rps(market, actual)
            if model and market
            else None
        ),
        "league": fixture["competition_id"] or fixture["competition_name"] or "UNKNOWN",
        "evaluation_tier": lifecycle["evaluation_tier"],
        "checkpoint": lifecycle["checkpoint"],
        "lineup_input_hash": lifecycle["lineup_input_hash"],
        "clv_status": clv["clv_status"],
        "clv_decimal": clv["clv_decimal"],
        "clv_method": CLV_METHOD,
        "source_event_type": "RESULT_MATERIALIZED",
        "source_event_id": result.id,
        "source_event_hash": result.result_hash,
        "source_event_at": _iso(result.confirmed_at),
    }
    payload["business_projection_hash"] = _hash_value(payload)
    return payload


def _select_capture(
    captures: Sequence[Mapping[str, Any]],
    fixture_identity: MatchdayFixtureIdentityModel | None,
) -> tuple[Mapping[str, Any] | None, str, list[str]]:
    kickoff = (
        _utc(fixture_identity.kickoff_utc) if fixture_identity is not None else None
    )
    complete: list[Mapping[str, Any]] = []
    signatures: set[tuple[str, ...]] = set()
    identities: dict[str, str] = {}
    for capture in captures:
        signature = _fixture_signature(capture)
        captured_at = _parse_time(capture.get("captured_at"))
        capture_kickoff = _parse_time(_fixture_values(capture, None, "")["kickoff_utc"])
        resolved_kickoff = kickoff or capture_kickoff
        if resolved_kickoff is None:
            continue
        if signature is None or captured_at is None or captured_at >= resolved_kickoff:
            continue
        if kickoff is not None and capture_kickoff != kickoff:
            return None, "BLOCKED", ["FIXTURE_IDENTITY_CONFLICT"]
        identity = _text(capture.get("capture_identity_hash"))
        if not identity:
            return None, "BLOCKED", ["PROBABILITY_IDENTITY_CONFLICT"]
        digest = _hash_value(capture)
        if identity in identities and identities[identity] != digest:
            return None, "BLOCKED", ["PROBABILITY_IDENTITY_CONFLICT"]
        identities[identity] = digest
        signatures.add(signature)
        complete.append(capture)
    if len(signatures) > 1:
        return None, "BLOCKED", ["FIXTURE_IDENTITY_CONFLICT"]
    if not complete:
        has_capture_kickoff = any(
            _parse_time(_fixture_values(item, None, "")["kickoff_utc"]) is not None
            for item in captures
        )
        has_complete_identity = any(
            _fixture_signature(item) is not None for item in captures
        )
        if kickoff is None and not has_capture_kickoff:
            reason = "KICKOFF_IDENTITY_MISSING"
        elif captures and not has_complete_identity:
            reason = "FIXTURE_IDENTITY_MISSING"
        else:
            reason = "NO_PREKICKOFF_CAPTURE"
        return None, "NOT_SCORABLE", [reason]
    complete_times = [
        captured_at
        for item in complete
        if (captured_at := _parse_time(item.get("captured_at"))) is not None
    ]
    latest_at = max(complete_times)
    latest = [
        item for item in complete if _parse_time(item.get("captured_at")) == latest_at
    ]
    latest_identities = {
        _text(item.get("capture_identity_hash")) for item in latest
    }
    if len(latest_identities) > 1:
        return None, "BLOCKED", ["EQUAL_TIMESTAMP_DIFFERENT_BUSINESS_IDENTITY"]
    return latest[0], "SCORED", []


def _fixture_values(
    capture: Mapping[str, Any] | None,
    identity: MatchdayFixtureIdentityModel | None,
    fixture_id: str,
) -> dict[str, Any]:
    record = capture or {}
    nested = record.get("fixture_identity")
    nested = nested if isinstance(nested, Mapping) else record
    return {
        "fixture_id": nested.get("fixture_id") or record.get("fixture_id") or fixture_id,
        "kickoff_utc": nested.get("kickoff_utc")
        or record.get("kickoff_utc")
        or (_iso(identity.kickoff_utc) if identity else None),
        "competition_id": nested.get("competition_id")
        or record.get("competition_id")
        or (identity.competition_id if identity else None),
        "competition_name": nested.get("competition_name")
        or record.get("competition_name"),
        "home_team_name": nested.get("home_team_name")
        or record.get("home_team_name"),
        "away_team_name": nested.get("away_team_name")
        or record.get("away_team_name"),
    }


def _fixture_signature(record: Mapping[str, Any]) -> tuple[str, ...] | None:
    values = _fixture_values(record, None, "")
    signature = tuple(
        _text(values[key])
        for key in (
            "fixture_id",
            "kickoff_utc",
            "competition_id",
            "home_team_name",
            "away_team_name",
        )
    )
    return signature if all(signature) else None


def _lifecycle_metadata(
    capture: Mapping[str, Any] | None,
    rows: Sequence[DynamicPrematchEvaluationModel],
) -> tuple[dict[str, Any], bool]:
    record = capture or {}
    captured_at = _parse_time(record.get("captured_at"))
    exact = [
        row
        for row in rows
        if captured_at is not None
        and (
            _utc(row.capture_at) == captured_at
            or _utc(row.evaluated_at) == captured_at
        )
    ]
    checkpoints = {row.checkpoint for row in exact if row.checkpoint}
    lineup_hashes = {
        row.lineup_input_hash for row in exact if row.lineup_input_hash
    }
    tier = _text(record.get("evaluation_tier")).upper()
    return (
        {
            "evaluation_tier": tier
            if tier in {"STRICT", "ADVISORY"}
            else "UNKNOWN",
            "checkpoint": _optional(record.get("checkpoint"))
            or (next(iter(checkpoints)) if len(checkpoints) == 1 else None),
            "lineup_input_hash": _optional(record.get("lineup_input_hash"))
            or (next(iter(lineup_hashes)) if len(lineup_hashes) == 1 else None),
        },
        len(checkpoints) > 1 or len(lineup_hashes) > 1,
    )


def _fixture_clv(
    records: Sequence[Mapping[str, Any]],
    capture: Mapping[str, Any] | None,
    fixture_id: str,
) -> dict[str, Any]:
    pick = capture.get("pick") if capture else None
    if (
        not isinstance(pick, Mapping)
        or _text(capture.get("recommendation_scope") if capture else "").upper()
        not in {"OFFICIAL", "VALIDATION"}
    ):
        return {"clv_status": "NOT_APPLICABLE_NO_PICK", "clv_decimal": None}
    market = _text(pick.get("market"))
    selection = _text(pick.get("selection"))
    if not market or not selection:
        return {"clv_status": "NOT_APPLICABLE_NO_PICK", "clv_decimal": None}
    superseded = {
        _text(record.get("target_capture_identity_hash"))
        for record in records
        if _record_type(record) == "supersession"
        and _text(record.get("supersession_status")).upper() == "SUPERSEDED"
    }
    active_records = [
        record
        for record in records
        if _record_type(record) != "capture"
        or _text(record.get("capture_identity_hash")) not in superseded
    ]
    row = fixture_clv(
        active_records,
        fixture_id=fixture_id,
        market=market,
        selection=selection,
    )
    if row is None:
        return {"clv_status": "INSUFFICIENT_SNAPSHOTS", "clv_decimal": None}
    return {
        "clv_status": row.get("clv_status"),
        "clv_decimal": row.get("clv_decimal"),
    }


def _existing_fixture_payloads(session: Session) -> dict[str, dict[str, Any]]:
    rows = session.scalars(
        select(ReadModelCheckpointModel).where(
            ReadModelCheckpointModel.checkpoint_key.like("performance:fixture:%")
        )
    )
    return {
        row.checkpoint_key.removeprefix("performance:fixture:"): dict(row.payload)
        for row in rows
    }


def _cohort_projections(
    fixture_payloads: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    rows = [
        dict(payload)
        for payload in fixture_payloads.values()
        if _parse_time(payload.get("kickoff_utc")) is not None
    ]
    if not rows:
        return {}
    kickoff_times = [
        kickoff
        for row in rows
        if (kickoff := _parse_time(row["kickoff_utc"])) is not None
    ]
    anchor = max(kickoff_times)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        league = _text(row.get("league")) or "UNKNOWN"
        tier = _text(row.get("evaluation_tier")).upper()
        tier = tier if tier in {"STRICT", "ADVISORY"} else "UNKNOWN"
        groups["performance:cohort:all"].append(row)
        groups[f"performance:cohort:league:{league}"].append(row)
        groups[f"performance:cohort:tier:{tier}"].append(row)
        groups[f"performance:cohort:league-tier:{league}:{tier}"].append(row)
    return {
        key: _cohort_payload(key, values, anchor)
        for key, values in sorted(groups.items())
    }


def _cohort_payload(
    checkpoint_key: str,
    rows: Sequence[Mapping[str, Any]],
    anchor: datetime,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "projection_version": PROJECTION_VERSION,
        "checkpoint_key": checkpoint_key,
        "scoring_window_anchor": _iso(anchor),
        "windows": {
            name: _window_metrics(
                [
                    row
                    for row in rows
                    if anchor - duration
                    <= (_parse_time(row.get("kickoff_utc")) or datetime.min.replace(tzinfo=UTC))
                    <= anchor
                ]
            )
            for name, duration in WINDOWS.items()
        },
    }
    payload["business_projection_hash"] = _hash_value(payload)
    return payload


def _window_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row.get("status") == "SCORED"]
    statuses = Counter(_text(row.get("status")) for row in rows)
    model_observations = _observations(scored, "model_probabilities")
    market_observations = _observations(scored, "market_probabilities")
    pairs = [
        (float(row["model_log_loss"]), float(row["market_log_loss"]))
        for row in scored
        if _is_number(row.get("model_log_loss"))
        and _is_number(row.get("market_log_loss"))
    ]
    clv_values = [
        float(row["clv_decimal"])
        for row in scored
        if _is_number(row.get("clv_decimal"))
    ]
    return {
        "finished_result_count": len(rows),
        "fixture_checkpoint_count": len(rows),
        "scored_count": statuses["SCORED"],
        "not_scorable_count": statuses["NOT_SCORABLE"],
        "blocked_count": statuses["BLOCKED"],
        "not_scorable_by_reason": dict(
            sorted(
                Counter(
                    reason
                    for row in rows
                    if row.get("status") == "NOT_SCORABLE"
                    for reason in row.get("reason_codes", [])
                ).items()
            )
        ),
        "model_log_loss": _mean(scored, "model_log_loss"),
        "market_log_loss": _mean(scored, "market_log_loss"),
        "model_minus_market_log_loss": _mean(scored, "model_minus_market_log_loss"),
        "model_brier": _mean(scored, "model_brier"),
        "market_brier": _mean(scored, "market_brier"),
        "model_minus_market_brier": _mean(scored, "model_minus_market_brier"),
        "model_rps": _mean(scored, "model_rps"),
        "market_rps": _mean(scored, "market_rps"),
        "model_minus_market_rps": _mean(scored, "model_minus_market_rps"),
        "paired_log_loss_bootstrap": paired_bootstrap(pairs),
        "model_ece": ece(model_observations),
        "market_ece": ece(market_observations),
        "model_reliability_bins": reliability_bins(model_observations),
        "market_reliability_bins": reliability_bins(market_observations),
        "clv_sample_count": len(clv_values),
        "clv_mean": sum(clv_values) / len(clv_values) if clv_values else None,
        "clv_median": median(clv_values) if clv_values else None,
        "clv_positive_count": len([value for value in clv_values if value > 0]),
        "clv_positive_share": (
            len([value for value in clv_values if value > 0]) / len(clv_values)
            if clv_values
            else None
        ),
        "clv_ci95": bootstrap_ci(clv_values),
        "clv_method": CLV_METHOD,
    }


def _observations(
    rows: Sequence[Mapping[str, Any]],
    key: str,
) -> list[tuple[tuple[float, float, float], int]]:
    result = []
    for row in rows:
        raw = row.get(key)
        outcome = _text(row.get("actual_outcome"))
        if (
            isinstance(raw, Sequence)
            and not isinstance(raw, str | bytes | bytearray)
            and len(raw) == 3
            and outcome in {"HOME", "DRAW", "AWAY"}
        ):
            result.append(
                (
                    (float(raw[0]), float(raw[1]), float(raw[2])),
                    ("HOME", "DRAW", "AWAY").index(outcome),
                )
            )
    return result


def _persist_checkpoint(
    session: Session,
    *,
    checkpoint_key: str,
    payload: Mapping[str, Any],
    source_hash: str,
    created_at: datetime,
    write_db: bool,
    preserve_trusted_on_blocked: bool,
) -> dict[str, Any]:
    existing = session.scalar(
        select(ReadModelCheckpointModel).where(
            ReadModelCheckpointModel.checkpoint_key == checkpoint_key
        )
    )
    candidate = dict(payload)
    if existing is not None:
        current = dict(existing.payload)
        if existing.source_hash == source_hash:
            if current != candidate:
                return {
                    "writes": 0,
                    "skipped": 0,
                    "blockers": [f"{checkpoint_key}:SAME_SOURCE_PAYLOAD_CONFLICT"],
                    "accepted": False,
                }
            return {
                "writes": 0,
                "skipped": 1,
                "blockers": [],
                "accepted": True,
            }
        if preserve_trusted_on_blocked and candidate.get("status") == "BLOCKED":
            return {
                "writes": 0,
                "skipped": 1,
                "blockers": [f"{checkpoint_key}:TRUSTED_CHECKPOINT_PRESERVED"],
                "accepted": False,
            }
        if write_db:
            existing.source_hash = source_hash
            existing.created_at = created_at
            existing.payload = candidate
        return {"writes": 1, "skipped": 0, "blockers": [], "accepted": True}
    if write_db:
        session.add(
            ReadModelCheckpointModel(
                checkpoint_key=checkpoint_key,
                source_hash=source_hash,
                created_at=created_at,
                payload=candidate,
            )
        )
    return {"writes": 1, "skipped": 0, "blockers": [], "accepted": True}


def _source_hash(payload: Mapping[str, Any]) -> str:
    return _hash_value(
        {
            "result_identity_hash": payload.get("result_identity_hash"),
            "source_capture_identity_hash": payload.get("source_capture_identity_hash"),
            "source_probability_identity_hash": payload.get(
                "source_probability_identity_hash"
            ),
            "status": payload.get("status"),
            "reason_codes": payload.get("reason_codes"),
        }
    )


def _artifact_hash(capture: Mapping[str, Any] | None) -> str | None:
    artifact = capture.get("artifact_provenance") if capture else None
    return (
        _optional(artifact.get("artifact_hash"))
        if isinstance(artifact, Mapping)
        else None
    )


def _record_type(record: Mapping[str, Any]) -> str:
    return _text(record.get("record_type") or "capture").lower()


def _fixture_id(record: Mapping[str, Any]) -> str:
    nested = record.get("fixture_identity")
    if isinstance(nested, Mapping) and nested.get("fixture_id"):
        return _text(nested.get("fixture_id"))
    return _text(record.get("fixture_id"))


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(parsed)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    parsed = _utc(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else None


def _hash_value(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).hexdigest()


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _optional(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if _is_number(row.get(key))]
    return sum(values) / len(values) if values else None


def _empty_result() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "NO_DUE_WORK",
        "finished_result_count": 0,
        "fixture_checkpoint_count": 0,
        "cohort_checkpoint_count": 0,
        "scored_count": 0,
        "not_scorable_count": 0,
        "blocked_count": 0,
        "not_scorable_by_reason": {},
        "eligible_scoring_coverage": 1.0,
        "written": 0,
        "would_write": 0,
        "skipped_existing": 0,
        "db_writes": 0,
        "provider_calls": 0,
        "blockers": [],
    }
