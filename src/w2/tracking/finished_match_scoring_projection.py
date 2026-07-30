from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from statistics import median
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
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
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.tracking.advisory_blind_spot_policy import (
    POLICY_CHECKPOINT_KEY,
    build_advisory_blind_spot_policy,
)
from w2.tracking.forward_ledger_performance import (
    CLV_METHOD,
    CanonicalSettlementFacts,
    canonical_settlement_facts,
    canonical_settlement_outcome,
    fixture_clv,
)
from w2.tracking.outcome_ledger_repository import (
    ExactFixtureResolver,
    FixtureIdentityConflict,
    payload_sha256,
)
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

SCHEMA_VERSION = "w2.performance_projection.v3"
PROJECTION_VERSION = "eval-02a.v1"
CLV_POPULATION = "SCORABLE_FINISHED_WITH_CANONICAL_CLV"
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
        identity_rows = list(
            session.scalars(select(MatchdayFixtureIdentityModel))
        )
        resolver = ExactFixtureResolver(identity_rows)
        results = _results(session, fixture_ids, resolver)
        if not results:
            return _empty_result()
        resolved_results = _canonical_results(results, resolver)
        finished_fixture_ids = {
            fixture_id for _, fixture_id, _ in resolved_results
        }
        ledger_rows = list(
            session.scalars(
                select(OutcomeLedgerModel).order_by(
                    OutcomeLedgerModel.occurred_at,
                    OutcomeLedgerModel.business_key,
                )
            )
        )
        (
            ledger_payloads,
            envelope_conflicts,
            batch_envelope_conflict,
            ledger_parity,
        ) = _validated_ledger_payloads(
            ledger_rows,
            resolver,
            finished_fixture_ids=finished_fixture_ids,
        )
        records, identity_conflicts = _canonical_records(
            ledger_payloads,
            resolver,
        )
        result_counts = Counter(
            fixture_id for _, fixture_id, _ in resolved_results
        )
        authoritative_results = {
            fixture_id: {
                "fixture_id": fixture_id,
                "status": result.result_status,
                "home_goals": result.home_goals,
                "away_goals": result.away_goals,
                "confirmed_at": _iso(result.confirmed_at),
                "result_hash": result.result_hash,
            }
            for result, fixture_id, identity_conflict in resolved_results
            if not identity_conflict and result_counts[fixture_id] == 1
        }
        legacy_recoveries = {
            fixture_id: record
            for record in records
            if _record_type(record) == "legacy_recovery"
            and (fixture_id := _fixture_id(record))
        }
        canonical_facts = canonical_settlement_facts(
            records,
            authoritative_results,
            legacy_recoveries,
        )
        try:
            lineup_attribution = (
                FutureRefreshDbRepository(engine=resolved_engine)
                .lineup_attribution_evidence_for_fixtures(
                    sorted(finished_fixture_ids)
                )
            )
        except SQLAlchemyError:
            lineup_attribution = {}
        fixture_identities = {
            row.fixture_id: row
            for row in identity_rows
        }
        dynamic_rows, dynamic_conflicts = _canonical_dynamic_rows(
            session.scalars(select(DynamicPrematchEvaluationModel)),
            resolver,
        )
        identity_conflicts.update(dynamic_conflicts)
        fixture_payloads: dict[str, dict[str, Any]] = {}
        blockers = []
        hard_batch_persistence_block = batch_envelope_conflict or (
            ledger_parity["status"] == "BLOCKED"
            and not envelope_conflicts & finished_fixture_ids
        )
        if hard_batch_persistence_block:
            blockers.append(
                "batch:OUTCOME_LEDGER_ENVELOPE_PAYLOAD_CONFLICT"
            )
        for result, fixture_id, result_identity_conflict in resolved_results:
            payload = _fixture_projection(
                result,
                fixture_id=fixture_id,
                records=records,
                fixture_identity=fixture_identities.get(fixture_id),
                dynamic_rows=[
                    row for row in dynamic_rows.get(fixture_id, ())
                ],
                canonical_facts=canonical_facts,
                identity_conflict=(
                    result_identity_conflict
                    or fixture_id in identity_conflicts
                    or result_counts[fixture_id] > 1
                ),
                envelope_conflict=fixture_id in envelope_conflicts,
                lineup_evidence=lineup_attribution.get(fixture_id),
            )
            fixture_payloads[fixture_id] = payload
            if payload["status"] == "BLOCKED":
                blockers.extend(
                    f"{fixture_id}:{reason}"
                    for reason in payload["reason_codes"]
                )

        projected_fixture_payloads = _existing_fixture_payloads(session)
        fixture_writes = 0
        cohort_writes = 0
        policy_writes = 0
        skipped = 0
        write_blockers: list[str] = []
        timestamp = (now or datetime.now(UTC)).astimezone(UTC)
        if hard_batch_persistence_block:
            projected_fixture_payloads.update(fixture_payloads)
        else:
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
                fixture_writes += outcome["writes"]
                skipped += outcome["skipped"]
                write_blockers.extend(outcome["blockers"])
                if outcome["accepted"]:
                    projected_fixture_payloads[fixture_id] = payload
        cohort_payloads = _cohort_projections(projected_fixture_payloads)
        if not hard_batch_persistence_block:
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
                cohort_writes += outcome["writes"]
                skipped += outcome["skipped"]
                write_blockers.extend(outcome["blockers"])
        existing_policy_row = session.scalar(
            select(ReadModelCheckpointModel).where(
                ReadModelCheckpointModel.checkpoint_key == POLICY_CHECKPOINT_KEY
            )
        )
        policy_payload = build_advisory_blind_spot_policy(
            projected_fixture_payloads,
            existing=(
                dict(existing_policy_row.payload)
                if existing_policy_row is not None
                else None
            ),
            now=timestamp,
        )
        if not hard_batch_persistence_block:
            outcome = _persist_checkpoint(
                session,
                checkpoint_key=POLICY_CHECKPOINT_KEY,
                payload=policy_payload,
                source_hash=str(policy_payload["business_projection_hash"]),
                created_at=timestamp,
                write_db=write_db,
                preserve_trusted_on_blocked=False,
            )
            policy_writes += outcome["writes"]
            skipped += outcome["skipped"]
            write_blockers.extend(outcome["blockers"])
        writes = fixture_writes + cohort_writes + policy_writes
        blockers.extend(write_blockers)
        if hard_batch_persistence_block or not write_db:
            session.rollback()
        else:
            session.commit()
        counts = Counter(payload["status"] for payload in fixture_payloads.values())
        status = "BLOCKED" if blockers else "PASS"
        fixture_projection_coverage = len(fixture_payloads) / len(results)
        scorable_fixture_count = counts["SCORED"]
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "finished_result_count": len(results),
            "fixture_checkpoint_count": (
                0
                if hard_batch_persistence_block
                else len(fixture_payloads)
            ),
            "cohort_checkpoint_count": (
                0 if hard_batch_persistence_block else len(cohort_payloads)
            ),
            "projected_fixture_checkpoint_count": len(fixture_payloads),
            "projected_cohort_checkpoint_count": len(cohort_payloads),
            "persisted_fixture_checkpoint_count": (
                fixture_writes if write_db else 0
            ),
            "persisted_cohort_checkpoint_count": (
                cohort_writes if write_db else 0
            ),
            "policy_checkpoint": policy_payload,
            "persisted_policy_checkpoint_count": (
                policy_writes if write_db else 0
            ),
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
            "fixture_projection_coverage": fixture_projection_coverage,
            "scorable_fixture_count": scorable_fixture_count,
            "scorable_rate": scorable_fixture_count / len(results),
            "eligible_scoring_coverage": fixture_projection_coverage,
            "eligible_scoring_coverage_semantics": "CHECKPOINT_COVERAGE_ONLY",
            "written": writes if write_db else 0,
            "would_write": writes if not write_db else 0,
            "skipped_existing": skipped,
            "db_writes": writes if write_db else 0,
            "persistence_gate": (
                "BLOCKED_BATCH_ENVELOPE_CONFLICT"
                if hard_batch_persistence_block
                else "PASS"
            ),
            "persistence_suppressed": hard_batch_persistence_block,
            "provider_calls": 0,
            "blockers": sorted(set(blockers)),
            "ledger_parity": ledger_parity,
        }


def _results(
    session: Session,
    fixture_ids: Sequence[str] | None,
    resolver: ExactFixtureResolver,
) -> list[ResultModel]:
    rows = list(
        session.scalars(select(ResultModel).order_by(ResultModel.fixture_id))
    )
    if fixture_ids is None:
        return rows
    requested: set[str] = set()
    for value in fixture_ids:
        candidates = resolver.candidates(str(value))
        if candidates:
            requested.update(candidates)
        elif (resolved := resolver.resolve(str(value))) is not None:
            requested.add(resolved)
    return [
        row
        for row in rows
        if (
            _resolve_without_conflict(resolver, row.fixture_id) in requested
            or bool(resolver.candidates(row.fixture_id) & requested)
        )
    ]


def _canonical_results(
    results: Sequence[ResultModel],
    resolver: ExactFixtureResolver,
) -> list[tuple[ResultModel, str, bool]]:
    resolved: list[tuple[ResultModel, str, bool]] = []
    for row in results:
        try:
            fixture_id = resolver.resolve(row.fixture_id)
        except FixtureIdentityConflict:
            resolved.append((row, row.fixture_id, True))
            continue
        resolved.append((row, fixture_id or row.fixture_id, fixture_id is None))
    return resolved


def _validated_ledger_payloads(
    rows: Sequence[OutcomeLedgerModel],
    resolver: ExactFixtureResolver,
    *,
    finished_fixture_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], set[str], bool, dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    conflicts: set[str] = set()
    batch_conflict = False
    record_types: Counter[str] = Counter()
    schema_versions: Counter[str] = Counter()
    mismatches_by_field: Counter[str] = Counter()
    explicit_conflicts = 0
    unsupported_missing = 0
    for row in rows:
        payload = dict(row.payload)
        (
            effective_record_type,
            record_type_status,
        ) = _effective_payload_record_type(row, payload)
        _, schema_version_status = _effective_payload_schema_version(
            row,
            payload,
        )
        record_types[record_type_status] += 1
        schema_versions[schema_version_status] += 1
        mismatches = _ledger_envelope_mismatches(
            row,
            payload,
            record_type_status=record_type_status,
            schema_version_status=schema_version_status,
        )
        if record_type_status == "EXPLICIT_CONFLICT" or (
            schema_version_status == "EXPLICIT_CONFLICT"
        ):
            explicit_conflicts += 1
        if record_type_status == "MISSING_UNSUPPORTED":
            unsupported_missing += 1
        if not mismatches:
            validated = dict(payload)
            if not _optional(payload.get("record_type")):
                validated["_effective_payload_record_type"] = (
                    effective_record_type
                )
            payloads.append(validated)
            continue
        mismatches_by_field.update(mismatches)
        affected: set[str] = set()
        for raw_fixture_id in {row.fixture_id, _fixture_id(payload)}:
            if not raw_fixture_id:
                continue
            try:
                resolved = resolver.resolve(raw_fixture_id)
            except FixtureIdentityConflict:
                affected.update(resolver.candidates(raw_fixture_id))
            else:
                if resolved is not None:
                    affected.add(resolved)
        if affected:
            conflicts.update(affected)
        else:
            batch_conflict = True
    legacy_count = (
        record_types["LEGACY_INFERRED_CAPTURE"]
        + record_types["LEGACY_DIRECTORY_FORMAL_SNAPSHOT"]
        + record_types["LEGACY_DIRECTORY_FORMAL_SETTLEMENT"]
        + schema_versions["LEGACY_UNKNOWN_NORMALIZATION"]
    )
    parity_status = (
        "BLOCKED"
        if mismatches_by_field
        else (
            "PASS_WITH_LEGACY_NORMALIZATION"
            if legacy_count
            else "PASS"
        )
    )
    finished = finished_fixture_ids or set()
    parity = {
        "status": parity_status,
        "total_row_count": len(rows),
        "explicit_match_count": record_types["EXPLICIT_MATCH"],
        "legacy_inferred_capture_count": record_types[
            "LEGACY_INFERRED_CAPTURE"
        ],
        "legacy_formal_snapshot_count": record_types[
            "LEGACY_DIRECTORY_FORMAL_SNAPSHOT"
        ],
        "legacy_formal_settlement_count": record_types[
            "LEGACY_DIRECTORY_FORMAL_SETTLEMENT"
        ],
        "legacy_unknown_schema_count": schema_versions[
            "LEGACY_UNKNOWN_NORMALIZATION"
        ],
        "explicit_conflict_count": explicit_conflicts,
        "unsupported_missing_count": unsupported_missing,
        "mismatches_by_field": dict(sorted(mismatches_by_field.items())),
        "affected_fixture_count": len(conflicts),
        "finished_result_affected_count": len(conflicts & finished),
    }
    return payloads, conflicts, batch_conflict, parity


def _effective_payload_record_type(
    row: OutcomeLedgerModel,
    payload: Mapping[str, Any],
) -> tuple[str | None, str]:
    envelope = _text(row.record_type).lower()
    explicit = _optional(payload.get("record_type"))
    if explicit is not None:
        normalized = explicit.lower()
        return (
            normalized,
            "EXPLICIT_MATCH"
            if normalized == envelope
            else "EXPLICIT_CONFLICT",
        )
    source = _text(row.source_artifact).replace("\\", "/")
    if (
        source.startswith("forward_outcome_ledger/")
        and source.endswith(".jsonl")
        and _optional(payload.get("fixture_id")) is not None
        and _optional(payload.get("captured_at")) is not None
        and envelope == "capture"
    ):
        return "capture", "LEGACY_INFERRED_CAPTURE"
    source_path = PurePosixPath(source)
    if (
        source_path.parent.as_posix()
        == "formal_recommendation_snapshots"
        and source_path.suffix == ".json"
        and envelope == "formal_snapshot"
    ):
        return "formal_snapshot", "LEGACY_DIRECTORY_FORMAL_SNAPSHOT"
    if (
        source_path.parent.as_posix()
        == "formal_recommendation_settlements"
        and source_path.suffix == ".json"
        and envelope == "formal_settlement"
    ):
        return "formal_settlement", "LEGACY_DIRECTORY_FORMAL_SETTLEMENT"
    return None, "MISSING_UNSUPPORTED"


def _effective_payload_schema_version(
    row: OutcomeLedgerModel,
    payload: Mapping[str, Any],
) -> tuple[str | None, str]:
    envelope = _optional(row.schema_version)
    explicit = _optional(payload.get("schema_version"))
    if explicit is not None:
        return (
            explicit,
            "EXPLICIT_MATCH"
            if explicit == envelope
            else "EXPLICIT_CONFLICT",
        )
    if envelope == "UNKNOWN":
        return "UNKNOWN", "LEGACY_UNKNOWN_NORMALIZATION"
    return None, "EXPLICIT_CONFLICT"


def _ledger_envelope_mismatches(
    row: OutcomeLedgerModel,
    payload: Mapping[str, Any],
    *,
    record_type_status: str,
    schema_version_status: str,
) -> list[str]:
    mismatches: list[str] = []
    if record_type_status in {
        "EXPLICIT_CONFLICT",
        "MISSING_UNSUPPORTED",
    }:
        mismatches.append("record_type")
    if schema_version_status == "EXPLICIT_CONFLICT":
        mismatches.append("schema_version")
    if str(row.fixture_id) != str(payload.get("fixture_id") or ""):
        mismatches.append("fixture_id")
    if _utc(row.captured_at) != _parse_time(payload.get("captured_at")):
        mismatches.append("captured_at")
    for field in (
        "recommendation_scope",
        "capture_identity_hash",
        "decision_hash",
    ):
        if _optional(getattr(row, field)) != _optional(payload.get(field)):
            mismatches.append(field)
    if row.payload_sha256 != payload_sha256(payload):
        mismatches.append("payload_sha256")
    return mismatches


def _canonical_records(
    records: Sequence[Mapping[str, Any]],
    resolver: ExactFixtureResolver,
) -> tuple[list[dict[str, Any]], set[str]]:
    resolved: list[dict[str, Any]] = []
    conflicts: set[str] = set()
    for record in records:
        raw_fixture_id = _fixture_id(record)
        if not raw_fixture_id:
            continue
        try:
            fixture_id = resolver.resolve(raw_fixture_id)
        except FixtureIdentityConflict:
            conflicts.update(resolver.candidates(raw_fixture_id))
            continue
        if fixture_id is None:
            continue
        canonical = dict(record)
        canonical["fixture_id"] = fixture_id
        nested = record.get("fixture_identity")
        if isinstance(nested, Mapping):
            canonical["fixture_identity"] = {
                **nested,
                "fixture_id": fixture_id,
            }
        resolved.append(canonical)
    return resolved, conflicts


def _canonical_dynamic_rows(
    rows: Iterable[DynamicPrematchEvaluationModel],
    resolver: ExactFixtureResolver,
) -> tuple[dict[str, list[DynamicPrematchEvaluationModel]], set[str]]:
    resolved: dict[str, list[DynamicPrematchEvaluationModel]] = defaultdict(list)
    conflicts: set[str] = set()
    for row in rows:
        try:
            fixture_id = resolver.resolve(row.fixture_id)
        except FixtureIdentityConflict:
            conflicts.update(resolver.candidates(row.fixture_id))
            continue
        if fixture_id is not None:
            resolved[fixture_id].append(row)
    return resolved, conflicts


def _resolve_without_conflict(
    resolver: ExactFixtureResolver,
    value: str,
) -> str | None:
    try:
        return resolver.resolve(value)
    except FixtureIdentityConflict:
        return None


def _fixture_projection(
    result: ResultModel,
    *,
    fixture_id: str,
    records: Sequence[Mapping[str, Any]],
    fixture_identity: MatchdayFixtureIdentityModel | None,
    dynamic_rows: Sequence[DynamicPrematchEvaluationModel],
    canonical_facts: CanonicalSettlementFacts,
    identity_conflict: bool,
    envelope_conflict: bool,
    lineup_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    related = [
        record
        for record in records
        if _record_type(record) == "capture"
        and _fixture_id(record) == fixture_id
    ]
    superseded = {
        _text(record.get("target_capture_identity_hash"))
        for record in records
        if _record_type(record) == "supersession"
        and _fixture_id(record) == fixture_id
        and _text(record.get("supersession_status")).upper() == "SUPERSEDED"
    }
    active = [
        record
        for record in related
        if _text(record.get("capture_identity_hash")) not in superseded
    ]
    capture, status, reasons, selection = _select_capture(
        active,
        fixture_identity,
        fixture_id,
        dynamic_rows,
    )
    if identity_conflict:
        status = "BLOCKED"
        reasons = ["FIXTURE_IDENTITY_CONFLICT"]
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
        if missing or status == "NOT_SCORABLE":
            status = "NOT_SCORABLE"
            reasons = sorted(set(reasons + missing))
        else:
            status = "SCORED"
            reasons = []

    fixture = _fixture_values(capture, fixture_identity, fixture_id)
    lifecycle, lifecycle_conflicts = _lifecycle_metadata(capture, dynamic_rows)
    if lifecycle_conflicts:
        status = "BLOCKED"
        reasons = lifecycle_conflicts
    if envelope_conflict:
        status = "BLOCKED"
        reasons = ["OUTCOME_LEDGER_ENVELOPE_PAYLOAD_CONFLICT"]
    clv = _fixture_clv(records, fixture_id)
    canonical = _canonical_outcome_payload(canonical_facts, fixture_id)
    blind_spot_attribution = _blind_spot_attribution(
        lineup_requirement=(
            str(lineup_evidence.get("lineup_requirement"))
            if isinstance(lineup_evidence, Mapping)
            and lineup_evidence.get("lineup_requirement") in {"STRICT", "ADVISORY"}
            else lifecycle["evaluation_tier"]
        ),
        lineup_evidence=lineup_evidence,
        canonical=canonical,
    )
    scoring_capture = capture if status == "SCORED" else None
    scored_model = model if scoring_capture else None
    scored_market = market if scoring_capture else None
    probability_hash = (
        _hash_value(scoring_capture.get("probability_identity"))
        if scoring_capture
        else None
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "projection_version": PROJECTION_VERSION,
        "status": status,
        "reason_codes": sorted(set(reasons)),
        "fixture_id": fixture_id,
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
            scoring_capture.get("capture_identity_hash")
            if scoring_capture
            else None
        ),
        "source_capture_group_hash": _optional(
            scoring_capture.get("source_capture_group_hash")
            if scoring_capture
            else None
        ),
        "contributing_capture_identity_hashes": (
            list(
                scoring_capture.get(
                    "contributing_capture_identity_hashes",
                    (),
                )
            )
            if scoring_capture
            else []
        ),
        "source_card_hash": _optional(
            scoring_capture.get("card_hash") if scoring_capture else None
        ),
        "source_artifact_hash": _artifact_hash(scoring_capture),
        "source_capture_at": _optional(
            scoring_capture.get("captured_at") if scoring_capture else None
        ),
        "selected_scoring_capture_at": _optional(
            scoring_capture.get("captured_at") if scoring_capture else None
        ),
        "source_probability_identity_hash": probability_hash,
        "model_probabilities": list(scored_model) if scored_model else None,
        "market_probabilities": list(scored_market) if scored_market else None,
        "model_log_loss": log_loss(scored_model, actual) if scored_model else None,
        "market_log_loss": log_loss(scored_market, actual) if scored_market else None,
        "model_minus_market_log_loss": (
            log_loss(scored_model, actual) - log_loss(scored_market, actual)
            if scored_model and scored_market
            else None
        ),
        "model_brier": brier(scored_model, actual) if scored_model else None,
        "market_brier": brier(scored_market, actual) if scored_market else None,
        "model_minus_market_brier": (
            brier(scored_model, actual) - brier(scored_market, actual)
            if scored_model and scored_market
            else None
        ),
        "model_rps": rps(scored_model, actual) if scored_model else None,
        "market_rps": rps(scored_market, actual) if scored_market else None,
        "model_minus_market_rps": (
            rps(scored_model, actual) - rps(scored_market, actual)
            if scored_model and scored_market
            else None
        ),
        **selection,
        "league": fixture["competition_id"] or fixture["competition_name"] or "UNKNOWN",
        "evaluation_tier": lifecycle["evaluation_tier"],
        "checkpoint": lifecycle["checkpoint"],
        "lineup_input_hash": lifecycle["lineup_input_hash"],
        "clv_status": clv["clv_status"],
        "clv_decimal": clv["clv_decimal"],
        "clv_method": CLV_METHOD,
        **canonical,
        "blind_spot_attribution": blind_spot_attribution,
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
    fixture_id: str,
    dynamic_rows: Sequence[DynamicPrematchEvaluationModel],
) -> tuple[Mapping[str, Any] | None, str, list[str], dict[str, Any]]:
    kickoff = (
        _utc(fixture_identity.kickoff_utc) if fixture_identity is not None else None
    )
    prekickoff: list[Mapping[str, Any]] = []
    for capture in captures:
        captured_at = _parse_time(capture.get("captured_at"))
        capture_kickoff = _parse_time(_fixture_values(capture, None, "")["kickoff_utc"])
        resolved_kickoff = kickoff or capture_kickoff
        if (
            resolved_kickoff is None
            or captured_at is None
            or captured_at >= resolved_kickoff
        ):
            continue
        prekickoff.append(capture)
    if not prekickoff:
        has_capture_kickoff = any(
            _parse_time(_fixture_values(item, None, "")["kickoff_utc"]) is not None
            for item in captures
        )
        has_complete_identity = any(
            _fixture_signature(item, fixture_id) is not None for item in captures
        )
        if kickoff is None and not has_capture_kickoff:
            reason = "KICKOFF_IDENTITY_MISSING"
        elif captures and not has_complete_identity:
            reason = "FIXTURE_IDENTITY_MISSING"
        else:
            reason = "NO_PREKICKOFF_CAPTURE"
        return None, "NOT_SCORABLE", [reason], {
            "latest_prekickoff_at": None,
            "latest_group_capture_count": 0,
            "latest_group_identity_bearing_count": 0,
            "latest_group_identity_missing_count": 0,
            "latest_group_fixture_signature_complete_count": 0,
            "latest_group_fixture_signature_incomplete_count": 0,
            "model_probability_complete": False,
            "market_probability_complete": False,
            "capture_selection_status": reason,
            "total_historical_prekickoff_capture_count": 0,
            "older_identity_missing_capture_count": 0,
        }
    latest_at = max(
        captured_at
        for item in prekickoff
        if (captured_at := _parse_time(item.get("captured_at"))) is not None
    )
    latest = [
        item
        for item in prekickoff
        if _parse_time(item.get("captured_at")) == latest_at
    ]
    identity_bearing = [
        item for item in latest if _text(item.get("capture_identity_hash"))
    ]
    signatures = [_fixture_signature(item, fixture_id) for item in latest]
    model_vectors = [
        probability_vector(item, "model_probabilities") for item in latest
    ]
    market_vectors = [
        probability_vector(item, "market_probabilities") for item in latest
    ]
    signature_complete_count = sum(item is not None for item in signatures)
    model_complete = all(item is not None for item in model_vectors)
    market_complete = all(item is not None for item in market_vectors)
    audit = {
        "latest_prekickoff_at": _iso(latest_at),
        "latest_group_capture_count": len(latest),
        "latest_group_identity_bearing_count": len(identity_bearing),
        "latest_group_identity_missing_count": len(latest) - len(identity_bearing),
        "latest_group_fixture_signature_complete_count": (
            signature_complete_count
        ),
        "latest_group_fixture_signature_incomplete_count": (
            len(latest) - signature_complete_count
        ),
        "model_probability_complete": model_complete,
        "market_probability_complete": market_complete,
        "capture_selection_status": "SELECTED",
        "total_historical_prekickoff_capture_count": len(prekickoff),
        "older_identity_missing_capture_count": sum(
            not _text(item.get("capture_identity_hash"))
            for item in prekickoff
            if _parse_time(item.get("captured_at")) != latest_at
        ),
    }
    conflicts = _latest_group_conflicts(
        latest,
        fixture_id=fixture_id,
        signatures=signatures,
        model_vectors=model_vectors,
        market_vectors=market_vectors,
        dynamic_rows=dynamic_rows,
    )
    if conflicts:
        audit["capture_selection_status"] = conflicts[0]
        return latest[0], "BLOCKED", conflicts, audit
    capture_kickoffs = [
        _parse_time(_fixture_values(item, None, "")["kickoff_utc"])
        for item in latest
    ]
    if kickoff is not None and any(
        value is not None and value != kickoff for value in capture_kickoffs
    ):
        audit["capture_selection_status"] = "FIXTURE_IDENTITY_CONFLICT"
        return latest[0], "BLOCKED", ["FIXTURE_IDENTITY_CONFLICT"], audit
    missing: list[str] = []
    if signature_complete_count == 0:
        missing.append("FIXTURE_IDENTITY_MISSING")
    if not identity_bearing:
        missing.append("CAPTURE_IDENTITY_MISSING")
        if not model_complete:
            missing.append("MODEL_PROBABILITY_VECTOR_MISSING")
        if not market_complete:
            missing.append("MARKET_PROBABILITY_VECTOR_MISSING")
    else:
        if not model_complete:
            missing.append("MODEL_PROBABILITY_VECTOR_MISSING")
        if not market_complete:
            missing.append("MARKET_PROBABILITY_VECTOR_MISSING")
    if missing:
        audit["capture_selection_status"] = (
            "PROBABILITY_INCOMPLETE"
            if identity_bearing
            and signature_complete_count
            and all(reason.endswith("_VECTOR_MISSING") for reason in missing)
            else missing[0]
        )
        return latest[0], "NOT_SCORABLE", missing, audit
    scoring_identities = [
        _scoring_relevant_identity(
            item,
            fixture_id=fixture_id,
            fixture_identity=fixture_identity,
            dynamic_rows=dynamic_rows,
        )
        for item in latest
    ]
    if len({_hash_value(identity) for identity in scoring_identities}) > 1:
        probability_hashes = {
            identity["probability_identity_hash"]
            for identity in scoring_identities
        }
        reason = (
            "PROBABILITY_IDENTITY_CONFLICT"
            if len(probability_hashes) > 1
            else "EQUAL_TIMESTAMP_DIFFERENT_BUSINESS_IDENTITY"
        )
        audit["capture_selection_status"] = reason
        return latest[0], "BLOCKED", [reason], audit
    contributing = sorted(
        {_text(item.get("capture_identity_hash")) for item in latest}
    )
    scoring_identity = scoring_identities[0]
    group_hash = _hash_value(
        {
            "scoring_relevant_identity": scoring_identity,
            "contributing_capture_identity_hashes": contributing,
        }
    )
    capture = dict(latest[0])
    capture["contributing_capture_identity_hashes"] = contributing
    capture["source_capture_group_hash"] = group_hash
    if len(contributing) > 1:
        capture["capture_identity_hash"] = group_hash
    if not model_complete or not market_complete:
        audit["capture_selection_status"] = "PROBABILITY_INCOMPLETE"
    return capture, "SCORED", [], audit


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


def _fixture_signature(
    record: Mapping[str, Any],
    fixture_id: str,
) -> tuple[str, ...] | None:
    signature = _fixture_comparison(record, fixture_id)
    return tuple(item or "" for item in signature) if all(signature) else None


def _fixture_comparison(
    record: Mapping[str, Any],
    fixture_id: str,
) -> tuple[str | None, ...]:
    values = _fixture_values(record, None, "")
    return (
        _optional(fixture_id),
        _iso(_parse_time(values["kickoff_utc"])),
        _optional(values["competition_id"]),
        _optional(values["home_team_name"]),
        _optional(values["away_team_name"]),
    )


def _latest_group_conflicts(
    latest: Sequence[Mapping[str, Any]],
    *,
    fixture_id: str,
    signatures: Sequence[tuple[str, ...] | None],
    model_vectors: Sequence[tuple[float, float, float] | None],
    market_vectors: Sequence[tuple[float, float, float] | None],
    dynamic_rows: Sequence[DynamicPrematchEvaluationModel],
) -> list[str]:
    reasons: list[str] = []
    complete_signatures = [item for item in signatures if item is not None]
    if 0 < len(complete_signatures) < len(signatures):
        reasons.append("COMPLETE_INCOMPLETE_SIBLING_CONFLICT")
    elif len(set(complete_signatures)) > 1:
        reasons.append("FIXTURE_IDENTITY_CONFLICT")
    elif not complete_signatures:
        fixture_values = [
            _fixture_comparison(item, fixture_id) for item in latest
        ]
        if any(
            len({value for value in column if value is not None}) > 1
            for column in zip(*fixture_values, strict=True)
        ):
            reasons.append("FIXTURE_IDENTITY_CONFLICT")

    if len({item for item in model_vectors if item is not None}) > 1:
        reasons.append("MODEL_PROBABILITY_VECTOR_CONFLICT")
    if len({item for item in market_vectors if item is not None}) > 1:
        reasons.append("MARKET_PROBABILITY_VECTOR_CONFLICT")

    lifecycles: list[dict[str, Any]] = []
    for capture in latest:
        lifecycle, dynamic_conflicts = _lifecycle_metadata(
            capture,
            dynamic_rows,
        )
        lifecycles.append(lifecycle)
        reasons.extend(dynamic_conflicts)
    if len({_optional(item.get("checkpoint")) for item in lifecycles} - {None}) > 1:
        reasons.append("DYNAMIC_CHECKPOINT_CONFLICT")
    if (
        len({_optional(item.get("lineup_input_hash")) for item in lifecycles} - {None})
        > 1
    ):
        reasons.append("DYNAMIC_LINEUP_HASH_CONFLICT")
    if len({_optional(item.get("evaluation_tier")) for item in lifecycles} - {None}) > 1:
        reasons.append("EQUAL_TIMESTAMP_DIFFERENT_BUSINESS_IDENTITY")

    cards = [_optional(item.get("card_hash")) for item in latest]
    artifacts = [_artifact_identity_hash(item) for item in latest]
    if (
        len({item for item in cards if item is not None}) > 1
        or len({item for item in artifacts if item is not None}) > 1
    ):
        reasons.append("EQUAL_TIMESTAMP_DIFFERENT_BUSINESS_IDENTITY")

    presence_columns = (
        signatures,
        model_vectors,
        market_vectors,
        cards,
        artifacts,
        [_optional(item.get("capture_identity_hash")) for item in latest],
        [_optional(item.get("checkpoint")) for item in lifecycles],
        [_optional(item.get("lineup_input_hash")) for item in lifecycles],
    )
    if any(
        any(item is not None for item in column)
        and not all(item is not None for item in column)
        for column in presence_columns
    ):
        reasons.append("COMPLETE_INCOMPLETE_SIBLING_CONFLICT")
    return list(dict.fromkeys(reasons))


def _scoring_relevant_identity(
    capture: Mapping[str, Any],
    *,
    fixture_id: str,
    fixture_identity: MatchdayFixtureIdentityModel | None,
    dynamic_rows: Sequence[DynamicPrematchEvaluationModel],
) -> dict[str, Any]:
    lifecycle, _ = _lifecycle_metadata(capture, dynamic_rows)
    values = _fixture_values(capture, fixture_identity, fixture_id)
    return {
        "fixture_id": fixture_id,
        "kickoff_utc": _iso(_parse_time(values["kickoff_utc"])),
        "captured_at": _iso(_parse_time(capture.get("captured_at"))),
        "card_hash": _optional(capture.get("card_hash")),
        "artifact_identity_hash": _artifact_identity_hash(capture),
        "probability_identity_hash": _hash_value(
            capture.get("probability_identity")
        ),
        "evaluation_tier": lifecycle["evaluation_tier"],
        "checkpoint": lifecycle["checkpoint"],
        "lineup_input_hash": lifecycle["lineup_input_hash"],
    }


def _lifecycle_metadata(
    capture: Mapping[str, Any] | None,
    rows: Sequence[DynamicPrematchEvaluationModel],
) -> tuple[dict[str, Any], list[str]]:
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
    conflicts = []
    if len(checkpoints) > 1:
        conflicts.append("DYNAMIC_CHECKPOINT_CONFLICT")
    if len(lineup_hashes) > 1:
        conflicts.append("DYNAMIC_LINEUP_HASH_CONFLICT")
    return {
        "evaluation_tier": tier
        if tier in {"STRICT", "ADVISORY"}
        else "UNKNOWN",
        "checkpoint": _optional(record.get("checkpoint"))
        or (next(iter(checkpoints)) if len(checkpoints) == 1 else None),
        "lineup_input_hash": _optional(record.get("lineup_input_hash"))
        or (next(iter(lineup_hashes)) if len(lineup_hashes) == 1 else None),
    }, conflicts


def _fixture_clv(
    records: Sequence[Mapping[str, Any]],
    fixture_id: str,
) -> dict[str, Any]:
    superseded = {
        _text(record.get("target_capture_identity_hash"))
        for record in records
        if _record_type(record) == "supersession"
        and _fixture_id(record) == fixture_id
        and _text(record.get("supersession_status")).upper() == "SUPERSEDED"
    }
    active_records = [
        record
        for record in records
        if _record_type(record) != "capture"
        or _text(record.get("capture_identity_hash")) not in superseded
    ]
    canonical_picks: set[tuple[str, str]] = set()
    for record in active_records:
        pick = record.get("pick")
        if (
            _record_type(record) != "capture"
            or _fixture_id(record) != fixture_id
            or _text(record.get("recommendation_scope")).upper()
            not in {"OFFICIAL", "VALIDATION"}
            or not isinstance(pick, Mapping)
        ):
            continue
        market = _text(pick.get("market"))
        selection = _text(pick.get("selection"))
        if market and selection:
            canonical_picks.add((market, selection))
    if not canonical_picks:
        return {"clv_status": "NOT_APPLICABLE_NO_PICK", "clv_decimal": None}
    if len(canonical_picks) > 1:
        return {"clv_status": "CANONICAL_PICK_CONFLICT", "clv_decimal": None}
    market, selection = next(iter(canonical_picks))
    clv = fixture_clv(
        active_records,
        fixture_id=fixture_id,
        market=market,
        selection=selection,
    )
    if clv is None:
        return {"clv_status": "INSUFFICIENT_SNAPSHOTS", "clv_decimal": None}
    return {
        "clv_status": clv.get("clv_status"),
        "clv_decimal": clv.get("clv_decimal"),
    }


def _canonical_outcome_payload(
    facts: CanonicalSettlementFacts,
    fixture_id: str,
) -> dict[str, Any]:
    accepted = facts.accepted_by_fixture.get(fixture_id)
    if accepted is not None:
        pick = accepted.get("pick")
        pick = pick if isinstance(pick, Mapping) else {}
        outcome = canonical_settlement_outcome(
            _settlement_outcome(accepted)
        )
        if outcome is not None:
            return {
                "canonical_pick_status": "AVAILABLE",
                "canonical_settlement_outcome": outcome,
                "canonical_decisive": outcome in {"HIT", "MISS"},
                "canonical_exclusion_reason": None,
                "canonical_pick_market": _optional(pick.get("market")),
                "canonical_pick_selection": _optional(pick.get("selection")),
            }
    if reason := facts.excluded_by_fixture.get(fixture_id):
        return {
            "canonical_pick_status": "CANONICAL_PICK_CONFLICT",
            "canonical_settlement_outcome": None,
            "canonical_decisive": None,
            "canonical_exclusion_reason": reason,
            "canonical_pick_market": None,
            "canonical_pick_selection": None,
        }
    if fixture_id not in facts.candidate_by_fixture:
        return {
            "canonical_pick_status": "NOT_APPLICABLE_NO_CANONICAL_PICK",
            "canonical_settlement_outcome": None,
            "canonical_decisive": None,
            "canonical_exclusion_reason": None,
            "canonical_pick_market": None,
            "canonical_pick_selection": None,
        }
    return {
        "canonical_pick_status": "SETTLEMENT_MISSING",
        "canonical_settlement_outcome": None,
        "canonical_decisive": None,
        "canonical_exclusion_reason": "SETTLEMENT_MISSING",
        "canonical_pick_market": None,
        "canonical_pick_selection": None,
    }


def _blind_spot_attribution(
    *,
    lineup_requirement: str,
    lineup_evidence: Mapping[str, Any] | None,
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = lineup_evidence if isinstance(lineup_evidence, Mapping) else {}
    home = evidence.get("home")
    away = evidence.get("away")
    home = home if isinstance(home, Mapping) else {}
    away = away if isinstance(away, Mapping) else {}
    home_prior = home.get("rotation_prior")
    away_prior = away.get("rotation_prior")
    home_prior = home_prior if isinstance(home_prior, Mapping) else {}
    away_prior = away_prior if isinstance(away_prior, Mapping) else {}
    home_continuity = _optional_number(home.get("starter_continuity"))
    away_continuity = _optional_number(away.get("starter_continuity"))
    home_deviation = (
        1 - home_continuity if home_continuity is not None else None
    )
    away_deviation = (
        1 - away_continuity if away_continuity is not None else None
    )
    market = _text(canonical.get("canonical_pick_market")).upper()
    selection = _text(canonical.get("canonical_pick_selection")).upper()
    selected_deviation = (
        home_deviation
        if market in {"AH", "ASIAN_HANDICAP"} and "HOME" in selection
        else away_deviation
        if market in {"AH", "ASIAN_HANDICAP"} and "AWAY" in selection
        else max(
            value
            for value in (home_deviation, away_deviation)
            if value is not None
        )
        if market in {"OU", "TOTALS"} and any(
            value is not None for value in (home_deviation, away_deviation)
        )
        else None
    )
    high_rotation = any(
        prior.get("status") == "READY"
        and prior.get("classification") == "HIGH_ROTATION"
        for prior in (home_prior, away_prior)
    )
    blockers = [str(item) for item in evidence.get("blockers", []) if item]
    outcome = canonical.get("canonical_settlement_outcome")
    if lineup_requirement == "STRICT":
        applicability = "NOT_APPLICABLE_STRICT"
        attribution = "NOT_APPLICABLE_STRICT"
    elif outcome != "MISS":
        applicability = "APPLICABLE"
        attribution = "NOT_LOSS"
    elif selected_deviation is None or evidence.get("status") != "READY":
        applicability = "APPLICABLE"
        attribution = "INSUFFICIENT_EVIDENCE"
    elif selected_deviation >= 4 / 11 or high_rotation:
        applicability = "APPLICABLE"
        attribution = "ROTATION_ASSOCIATED"
    else:
        applicability = "APPLICABLE"
        attribution = "NON_ROTATION_RESIDUAL"
    payload = {
        "schema_version": "w2.blind_spot_attribution.v1",
        "applicability": applicability,
        "lineup_requirement": lineup_requirement,
        "home_rotation_prior": dict(home_prior) if home_prior else None,
        "away_rotation_prior": dict(away_prior) if away_prior else None,
        "home_starter_continuity": home_continuity,
        "away_starter_continuity": away_continuity,
        "home_lineup_deviation": home_deviation,
        "away_lineup_deviation": away_deviation,
        "selected_side_lineup_deviation": selected_deviation,
        "high_rotation_prior": high_rotation,
        "canonical_settlement_outcome": outcome,
        "attribution": attribution,
        "causal_claim": False,
        "blockers": sorted(set(blockers)),
    }
    return {**payload, "input_hash": _hash_value(payload)}


def _settlement_outcome(record: Mapping[str, Any]) -> str:
    for key in ("settlement_outcome", "outcome", "result_outcome"):
        if value := _text(record.get(key)):
            return value
    settlement = record.get("settlement")
    if isinstance(settlement, Mapping):
        return _text(
            settlement.get("outcome") or settlement.get("settlement")
        )
    validation = record.get("validation")
    if isinstance(validation, Mapping):
        return _text(validation.get("settlement"))
    return ""


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
    leagues = {
        _text(row.get("league")) or "UNKNOWN"
        for row in rows
    }
    groups: dict[str, list[dict[str, Any]]] = {
        "performance:cohort:all": [],
        "performance:cohort:tier:STRICT": [],
        "performance:cohort:tier:ADVISORY": [],
    }
    for league in leagues:
        groups[f"performance:cohort:league:{league}"] = []
        groups[f"performance:cohort:league-tier:{league}:STRICT"] = []
        groups[f"performance:cohort:league-tier:{league}:ADVISORY"] = []
    for row in rows:
        league = _text(row.get("league")) or "UNKNOWN"
        tier = _text(row.get("evaluation_tier")).upper()
        tier = tier if tier in {"STRICT", "ADVISORY"} else "UNKNOWN"
        groups["performance:cohort:all"].append(row)
        groups[f"performance:cohort:league:{league}"].append(row)
        groups.setdefault(f"performance:cohort:tier:{tier}", []).append(row)
        groups.setdefault(
            f"performance:cohort:league-tier:{league}:{tier}",
            [],
        ).append(row)
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
        if row.get("clv_status") == "AVAILABLE"
        and _is_number(row.get("clv_decimal"))
    ]
    canonical_outcomes = Counter(
        _text(row.get("canonical_settlement_outcome")).upper()
        for row in rows
        if _text(row.get("canonical_settlement_outcome")).upper()
        in {"HIT", "MISS", "PUSH", "VOID"}
    )
    canonical_settled_count = sum(canonical_outcomes.values())
    canonical_decisive_count = (
        canonical_outcomes["HIT"] + canonical_outcomes["MISS"]
    )
    attributions = [
        value
        for row in rows
        if isinstance(
            value := row.get("blind_spot_attribution"),
            Mapping,
        )
    ]
    attribution_counts = Counter(
        _text(value.get("attribution")) for value in attributions
    )
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
        "clv_population": CLV_POPULATION,
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
        "canonical_settled_count": canonical_settled_count,
        "canonical_hit_count": canonical_outcomes["HIT"],
        "canonical_miss_count": canonical_outcomes["MISS"],
        "canonical_push_count": canonical_outcomes["PUSH"],
        "canonical_void_count": canonical_outcomes["VOID"],
        "canonical_decisive_count": canonical_decisive_count,
        "canonical_hit_rate": (
            canonical_outcomes["HIT"] / canonical_decisive_count
            if canonical_decisive_count >= 5
            else None
        ),
        "canonical_hit_rate_status": (
            "AVAILABLE"
            if canonical_decisive_count >= 5
            else "INSUFFICIENT_SAMPLE"
        ),
        "sample_target": 200,
        "sample_progress": min(canonical_settled_count / 200, 1.0),
        "sample_progress_status": (
            "TARGET_REACHED"
            if canonical_settled_count >= 200
            else "ACCUMULATING"
        ),
        "blind_spot_attribution_sample_count": sum(
            attribution_counts[value]
            for value in (
                "ROTATION_ASSOCIATED",
                "NON_ROTATION_RESIDUAL",
                "INSUFFICIENT_EVIDENCE",
            )
        ),
        "rotation_associated_miss_count": attribution_counts[
            "ROTATION_ASSOCIATED"
        ],
        "non_rotation_residual_miss_count": attribution_counts[
            "NON_ROTATION_RESIDUAL"
        ],
        "insufficient_attribution_count": attribution_counts[
            "INSUFFICIENT_EVIDENCE"
        ],
        "high_rotation_prior_fixture_count": sum(
            value.get("high_rotation_prior") is True for value in attributions
        ),
        "lineup_unobservable_fixture_count": sum(
            value.get("lineup_requirement") == "ADVISORY"
            for value in attributions
        ),
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
            "schema_version": payload.get("schema_version"),
            "projection_version": payload.get("projection_version"),
            "result_identity_hash": payload.get("result_identity_hash"),
            "source_capture_identity_hash": payload.get("source_capture_identity_hash"),
            "source_capture_group_hash": payload.get("source_capture_group_hash"),
            "contributing_capture_identity_hashes": payload.get(
                "contributing_capture_identity_hashes"
            ),
            "source_probability_identity_hash": payload.get(
                "source_probability_identity_hash"
            ),
            "latest_prekickoff_at": payload.get("latest_prekickoff_at"),
            "latest_group_capture_count": payload.get(
                "latest_group_capture_count"
            ),
            "latest_group_identity_bearing_count": payload.get(
                "latest_group_identity_bearing_count"
            ),
            "latest_group_identity_missing_count": payload.get(
                "latest_group_identity_missing_count"
            ),
            "latest_group_fixture_signature_complete_count": payload.get(
                "latest_group_fixture_signature_complete_count"
            ),
            "latest_group_fixture_signature_incomplete_count": payload.get(
                "latest_group_fixture_signature_incomplete_count"
            ),
            "capture_selection_status": payload.get(
                "capture_selection_status"
            ),
            "total_historical_prekickoff_capture_count": payload.get(
                "total_historical_prekickoff_capture_count"
            ),
            "older_identity_missing_capture_count": payload.get(
                "older_identity_missing_capture_count"
            ),
            "status": payload.get("status"),
            "reason_codes": payload.get("reason_codes"),
            "canonical_pick_status": payload.get("canonical_pick_status"),
            "canonical_settlement_outcome": payload.get(
                "canonical_settlement_outcome"
            ),
            "canonical_decisive": payload.get("canonical_decisive"),
            "canonical_exclusion_reason": payload.get(
                "canonical_exclusion_reason"
            ),
            "canonical_pick_market": payload.get("canonical_pick_market"),
            "canonical_pick_selection": payload.get(
                "canonical_pick_selection"
            ),
            "blind_spot_attribution": payload.get("blind_spot_attribution"),
        }
    )


def _artifact_hash(capture: Mapping[str, Any] | None) -> str | None:
    artifact = capture.get("artifact_provenance") if capture else None
    return (
        _optional(artifact.get("artifact_hash"))
        if isinstance(artifact, Mapping)
        else None
    )


def _artifact_identity_hash(capture: Mapping[str, Any]) -> str | None:
    artifact = capture.get("artifact_provenance")
    return _hash_value(artifact) if isinstance(artifact, Mapping) else None


def _record_type(record: Mapping[str, Any]) -> str:
    return _text(
        record.get("record_type")
        or record.get("_effective_payload_record_type")
        or "capture"
    ).lower()


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


def _optional_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and abs(parsed) != float("inf") else None


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
        "fixture_projection_coverage": 1.0,
        "scorable_fixture_count": 0,
        "scorable_rate": 0.0,
        "eligible_scoring_coverage": 1.0,
        "eligible_scoring_coverage_semantics": "CHECKPOINT_COVERAGE_ONLY",
        "written": 0,
        "would_write": 0,
        "skipped_existing": 0,
        "db_writes": 0,
        "provider_calls": 0,
        "blockers": [],
        "ledger_parity": {
            "status": "PASS",
            "total_row_count": 0,
            "explicit_match_count": 0,
            "legacy_inferred_capture_count": 0,
            "legacy_formal_snapshot_count": 0,
            "legacy_formal_settlement_count": 0,
            "legacy_unknown_schema_count": 0,
            "explicit_conflict_count": 0,
            "unsupported_missing_count": 0,
            "mismatches_by_field": {},
            "affected_fixture_count": 0,
            "finished_result_affected_count": 0,
        },
    }
