from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap
from w2.models.fair_market_estimate import (
    verify_estimate_semantics,
    verify_estimate_snapshot,
)
from w2.models.market_quote import verify_market_quote
from w2.strategy.analysis_gate_shadow import (
    STRICT_GATE_HASH,
    STRICT_POLICY,
    STRICT_STRATEGY_VERSION,
    confirm_strict_ah_shadow,
)
from w2.tracking.canonical_identity import (
    canonical_capture_candidates,
    performance_key,
)
from w2.tracking.canonical_outcomes import project_canonical_outcomes

SCHEMA_VERSION = "w2.strict_ah_canary_checker.v1"
_FIVE_STATES = {item.value for item in SettlementOutcome}


def check_strict_ah_canary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    canonical_candidates = canonical_capture_candidates(records)
    strict_candidates = [
        enriched
        for item in canonical_candidates
        if str(item.get("recommendation_scope") or "") == "SHADOW"
        and str(item.get("market") or "") == "ASIAN_HANDICAP"
        and str(item.get("strategy_version") or "") == STRICT_STRATEGY_VERSION
        and item.get("exclusion_reason") is None
        for enriched in (_enrich_candidate(item),)
        if _is_corrected_strict_candidate(enriched)
    ]
    if not strict_candidates:
        return _result(
            "NO_CORRECTED_STRICT_CANDIDATE_YET",
            checks=_empty_checks(),
            exit_code=0,
            candidate_count=0,
        )

    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in strict_candidates:
        groups[performance_key(candidate)].append(candidate)
    evaluations = [_evaluate_group(rows) for _, rows in sorted(groups.items())]
    blocked = [item for item in evaluations if item["status"] == "CANARY_BLOCKED"]
    if blocked:
        first = blocked[0]
        return _result(
            "CANARY_BLOCKED",
            checks=first["checks"],
            exit_code=1,
            candidate_count=len(strict_candidates),
            confirmation=first["confirmation"],
            blockers=first["blockers"],
        )

    confirmed = [item for item in evaluations if item["confirmation"].get("status") == "PASS"]
    if not confirmed:
        latest = max(
            evaluations,
            key=lambda item: _parse_time(item["canary_entry"].get("captured_at"))
            or datetime.min.replace(tzinfo=UTC),
        )
        return _result(
            "NO_CORRECTED_STRICT_CANDIDATE_YET",
            checks=latest["checks"],
            exit_code=0,
            candidate_count=len(strict_candidates),
            confirmation=latest["confirmation"],
        )

    selected = min(
        confirmed,
        key=lambda item: _parse_time(item["canary_entry"].get("captured_at"))
        or datetime.max.replace(tzinfo=UTC),
    )
    outcome_result = _check_outcome(
        records=records,
        canonical_candidates=canonical_candidates,
        candidate=selected["canary_entry"],
        checks=dict(selected["checks"]),
    )
    return _result(
        outcome_result["status"],
        checks=outcome_result["checks"],
        exit_code=outcome_result["exit_code"],
        candidate_count=len(strict_candidates),
        confirmation=selected["confirmation"],
        blockers=outcome_result.get("blockers", []),
        canonical_outcome=outcome_result.get("canonical_outcome"),
    )


def _evaluate_group(candidates: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        candidates,
        key=lambda item: _parse_time(item.get("quote_captured_at"))
        or datetime.min.replace(tzinfo=UTC),
    )
    latest = ordered[-1]
    checks = _pre_match_checks(ordered)
    confirmation = confirm_strict_ah_shadow(ordered)
    blockers = [name for name, status in checks.items() if status == "FAIL"]
    structural = {
        "canonical_evidence",
        "snapshot_v2",
        "snapshot_integrity",
        "snapshot_semantics",
        "market_quote",
        "selection_side_line",
        "strict_policy",
        "shadow_isolation",
        "decision_tier_watch",
    }
    return {
        "status": "CANARY_BLOCKED" if structural.intersection(blockers) else "ACCUMULATING",
        "canary_entry": latest,
        "checks": checks,
        "confirmation": confirmation,
        "blockers": blockers,
    }


def _pre_match_checks(candidates: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    snapshots = [item.get("estimate_snapshot") for item in candidates]
    quotes = [item.get("market_quote") for item in candidates]
    latest_two = list(candidates[-2:])
    interval = _interval_ok(latest_two)
    distinct_quotes = len(latest_two) >= 2 and len(
        {str(item.get("quote_id") or "") for item in latest_two}
    ) == 2
    same_basis = len(latest_two) >= 2 and len(
        {str(item.get("model_basis_id") or "") for item in latest_two}
    ) == 1
    same_direction = len(latest_two) >= 2 and len(
        {str(item.get("selection") or "") for item in latest_two}
    ) == 1
    return {
        "canonical_evidence": _pass(
            all(item.get("exclusion_reason") is None for item in candidates)
        ),
        "snapshot_v2": _pass(
            all(
                isinstance(snapshot, Mapping)
                and snapshot.get("schema_version") == "w2.fme_snapshot.v2"
                for snapshot in snapshots
            )
        ),
        "snapshot_integrity": _pass(
            all(
                isinstance(snapshot, Mapping) and verify_estimate_snapshot(snapshot)
                for snapshot in snapshots
            )
        ),
        "snapshot_semantics": _pass(
            all(
                isinstance(snapshot, Mapping) and verify_estimate_semantics(snapshot)
                for snapshot in snapshots
            )
        ),
        "market_quote": _pass(
            all(isinstance(quote, Mapping) and verify_market_quote(quote) for quote in quotes)
        ),
        "same_model_basis": _pass(same_basis),
        "distinct_quote_ids": _pass(distinct_quotes),
        "minimum_interval": _pass(interval),
        "same_direction": _pass(same_direction),
        "selection_side_line": _pass(all(_selection_line_matches(item) for item in candidates)),
        "strict_policy": _pass(all(_strict_policy_matches(item) for item in candidates)),
        "shadow_isolation": _pass(all(_shadow_isolated(item) for item in candidates)),
        "decision_tier_watch": _pass(
            all(str(item.get("decision_tier") or "") == "WATCH" for item in candidates)
        ),
        "single_settlement": "PENDING",
        "five_state_settlement": "PENDING",
        "identity_aware_outcome": "PENDING",
        "validation_contamination": "PASS",
        "official_contamination": "PASS",
        "duplicate_denominator": "PENDING",
    }


def _check_outcome(
    *,
    records: Sequence[Mapping[str, Any]],
    canonical_candidates: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    checks: dict[str, str],
) -> dict[str, Any]:
    validation_contamination = any(
        _targets_candidate(record, candidate)
        and str(record.get("recommendation_scope") or "") == "VALIDATION"
        for record in records
        if str(record.get("record_type") or "") == "outcome"
    )
    official_contamination = any(
        _targets_candidate(record, candidate)
        and str(record.get("recommendation_scope") or "") == "OFFICIAL"
        for record in records
        if str(record.get("record_type") or "") == "outcome"
    )
    checks["validation_contamination"] = _pass(not validation_contamination)
    checks["official_contamination"] = _pass(not official_contamination)
    if validation_contamination or official_contamination:
        return {
            "status": "CANARY_BLOCKED",
            "exit_code": 1,
            "checks": checks,
            "blockers": [
                name
                for name in ("validation_contamination", "official_contamination")
                if checks[name] == "FAIL"
            ],
        }

    projection = project_canonical_outcomes(records, canonical_candidates)
    outcomes = [
        item
        for item in projection.canonical_outcomes
        if tuple(item.get("canonical_performance_key") or ()) == performance_key(candidate)
    ]
    raw_shadow = [
        item
        for item in records
        if str(item.get("record_type") or "") == "outcome"
        and str(item.get("recommendation_scope") or "") == "SHADOW"
        and _targets_candidate(item, candidate)
    ]
    single = len(raw_shadow) <= 1 and len(outcomes) <= 1
    checks["single_settlement"] = _pass(single)
    checks["duplicate_denominator"] = _pass(single)
    if not single:
        return {
            "status": "CANARY_BLOCKED",
            "exit_code": 1,
            "checks": checks,
            "blockers": ["single_settlement", "duplicate_denominator"],
        }
    if not outcomes:
        return {"status": "PREMATCH_CANARY_PASS", "exit_code": 0, "checks": checks}

    outcome = outcomes[0]
    five_state = str(outcome.get("settlement_outcome") or "") in _FIVE_STATES
    settlement_correct = five_state and _expected_settlement(outcome) == outcome.get(
        "settlement_outcome"
    )
    identity_aware = outcome.get("match_type") == "IDENTITY_AWARE"
    final_capture = outcome.get("source_capture_hash") == candidate.get("capture_hash")
    checks["five_state_settlement"] = _pass(settlement_correct)
    checks["identity_aware_outcome"] = _pass(identity_aware and final_capture)
    if not settlement_correct or not identity_aware or not final_capture:
        return {
            "status": "CANARY_BLOCKED",
            "exit_code": 1,
            "checks": checks,
            "blockers": [
                name
                for name in ("five_state_settlement", "identity_aware_outcome")
                if checks[name] == "FAIL"
            ],
        }
    return {
        "status": "SETTLED_CANARY_PASS",
        "exit_code": 0,
        "checks": checks,
        "canonical_outcome": dict(outcome),
    }


def _enrich_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    estimate_id = str(candidate.get("estimate_id") or "")
    quote_id = str(candidate.get("quote_id") or "")
    snapshots = candidate.get("fair_market_estimate_snapshots")
    snapshot = next(
        (
            item
            for item in snapshots or ()
            if isinstance(item, Mapping) and str(item.get("estimate_id") or "") == estimate_id
        ),
        None,
    )
    identities = candidate.get("audit_capture_identities")
    identity = next(
        (
            item
            for item in identities or ()
            if isinstance(item, Mapping)
            and str(item.get("estimate_id") or "") == estimate_id
            and str(item.get("quote_id") or "") == quote_id
            and str(item.get("strategy_version") or "") == STRICT_STRATEGY_VERSION
        ),
        {},
    )
    gates = candidate.get("analysis_gate_v2_shadows")
    gate = next(
        (
            item
            for item in gates or ()
            if isinstance(item, Mapping)
            and str(item.get("estimate_id") or "") == estimate_id
            and str(item.get("strategy_version") or "") == STRICT_STRATEGY_VERSION
        ),
        {},
    )
    quote = identity.get("market_quote") if isinstance(identity, Mapping) else None
    return {
        **dict(candidate),
        **dict(gate),
        "capture_hash": candidate.get("capture_hash"),
        "captured_at": candidate.get("captured_at"),
        "decision_tier": candidate.get("decision_tier"),
        "exclusion_reason": candidate.get("exclusion_reason"),
        "canonical_candidate": candidate.get("canonical_candidate"),
        "canonical_estimate_id": estimate_id,
        "canonical_quote_id": quote_id,
        "canonical_model_basis_id": candidate.get("model_basis_id"),
        "recommendation_scope": "SHADOW",
        "strategy_version": STRICT_STRATEGY_VERSION,
        "estimate_snapshot": snapshot,
        "market_quote": quote,
    }


def _is_corrected_strict_candidate(candidate: Mapping[str, Any]) -> bool:
    return (
        candidate.get("candidate_pass") is True
        and candidate.get("evidence_eligible") is True
        and candidate.get("semantic_status") == "VERIFIED"
        and candidate.get("strict_gate_hash") == STRICT_GATE_HASH
        and candidate.get("quote_id") == candidate.get("canonical_quote_id")
        and candidate.get("estimate_id") == candidate.get("canonical_estimate_id")
        and (
            not candidate.get("canonical_model_basis_id")
            or candidate.get("model_basis_id") == candidate.get("canonical_model_basis_id")
        )
    )


def _selection_line_matches(candidate: Mapping[str, Any]) -> bool:
    quote = candidate.get("market_quote")
    if not isinstance(quote, Mapping):
        return False
    try:
        return Decimal(str(candidate.get("selection_line"))) == Decimal(
            str(quote.get("selection_line"))
        )
    except InvalidOperation:
        return False


def _strict_policy_matches(candidate: Mapping[str, Any]) -> bool:
    return (
        candidate.get("strategy_version") == STRICT_STRATEGY_VERSION
        and candidate.get("strict_gate_hash") == STRICT_GATE_HASH
    )


def _shadow_isolated(candidate: Mapping[str, Any]) -> bool:
    return (
        candidate.get("shadow_only") is True
        and candidate.get("affects_decision") is False
        and candidate.get("affects_tier") is False
    )


def _interval_ok(candidates: Sequence[Mapping[str, Any]]) -> bool:
    if len(candidates) < 2:
        return False
    first = _parse_time(candidates[-2].get("quote_captured_at"))
    second = _parse_time(candidates[-1].get("quote_captured_at"))
    minimum = int(STRICT_POLICY["confirmation"]["minimum_interval_minutes"])
    return first is not None and second is not None and second - first >= timedelta(minutes=minimum)


def _targets_candidate(record: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    if str(record.get("fixture_id") or "") != str(candidate.get("fixture_id") or ""):
        return False
    return any(
        value
        and value
        in {
            str(candidate.get("capture_hash") or ""),
            str(candidate.get("estimate_id") or ""),
            str(candidate.get("quote_id") or ""),
            STRICT_STRATEGY_VERSION,
        }
        for value in (
            str(record.get("source_capture_hash") or ""),
            str(record.get("estimate_id") or ""),
            str(record.get("quote_id") or ""),
            str(record.get("strategy_version") or ""),
        )
    )


def _expected_settlement(outcome: Mapping[str, Any]) -> str | None:
    score = outcome.get("final_score")
    if not isinstance(score, Mapping):
        return None
    selection = str(outcome.get("selection") or "")
    side = "HOME" if selection == "HOME_AH" else "AWAY" if selection == "AWAY_AH" else None
    if side is None:
        return None
    try:
        return settle_asian_handicap(
            int(score["home"]),
            int(score["away"]),
            side,
            Decimal(str(outcome.get("entry_line"))),
        ).value
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return None


def _empty_checks() -> dict[str, str]:
    return {
        "canonical_evidence": "PENDING",
        "snapshot_v2": "PENDING",
        "snapshot_integrity": "PENDING",
        "snapshot_semantics": "PENDING",
        "market_quote": "PENDING",
        "same_model_basis": "PENDING",
        "distinct_quote_ids": "PENDING",
        "minimum_interval": "PENDING",
        "same_direction": "PENDING",
        "selection_side_line": "PENDING",
        "strict_policy": "PENDING",
        "shadow_isolation": "PENDING",
        "decision_tier_watch": "PENDING",
        "single_settlement": "PENDING",
        "five_state_settlement": "PENDING",
        "identity_aware_outcome": "PENDING",
        "validation_contamination": "PASS",
        "official_contamination": "PASS",
        "duplicate_denominator": "PENDING",
    }


def _result(
    status: str,
    *,
    checks: Mapping[str, str],
    exit_code: int,
    candidate_count: int,
    confirmation: Mapping[str, Any] | None = None,
    blockers: Sequence[str] = (),
    canonical_outcome: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "exit_code": exit_code,
        "candidate_count": candidate_count,
        "strict_strategy_version": STRICT_STRATEGY_VERSION,
        "strict_gate_hash": STRICT_GATE_HASH,
        "checks": dict(checks),
        "confirmation": dict(confirmation or {}),
        "blockers": list(blockers),
        "canonical_outcome": dict(canonical_outcome) if canonical_outcome else None,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "deployment": False,
    }


def _pass(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


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
