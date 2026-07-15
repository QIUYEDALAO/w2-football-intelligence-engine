from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from scripts.audit_w2_canonical_denominators import audit_denominators

from w2.infrastructure.atomic_files import read_jsonl
from w2.tracking.canonical_outcomes import (
    legacy_performance_candidates,
    project_canonical_outcomes,
)


def test_two_legacy_outcomes_from_different_capture_hashes_count_once() -> None:
    capture = _capture("2026-07-15T09:00:00Z", "capture-final")
    outcomes = [
        _outcome("WIN", source_hash="capture-a"),
        _outcome("WIN", source_hash="capture-b", settled_at="2026-07-15T13:05:00Z"),
    ]

    projection = project_canonical_outcomes(
        [capture, *outcomes],
        candidates=(),
    )

    assert len(projection.raw_outcomes) == 2
    assert len(projection.canonical_outcomes) == 1
    assert len(projection.audit_only_outcomes) == 1
    assert len(projection.duplicate_outcomes) == 1
    assert projection.metrics["canonical_duplicate_count"] == 0


def test_same_outcome_duplicates_collapse_deterministically() -> None:
    capture = _capture("2026-07-15T09:00:00Z", "capture-final")
    outcome = _outcome("WIN", source_hash="capture-final")

    first = project_canonical_outcomes([capture, outcome, deepcopy(outcome)], candidates=())
    second = project_canonical_outcomes([capture, deepcopy(outcome), outcome], candidates=())

    assert first.canonical_outcomes == second.canonical_outcomes
    assert first.metrics["raw_exact_duplicate_count"] == 1
    assert first.metrics["duplicate_audit_row_count"] == 0


def test_last_prematch_selection_wins_after_direction_flip() -> None:
    earlier = _capture("2026-07-15T08:00:00Z", "earlier", selection="OVER")
    final = _capture("2026-07-15T09:00:00Z", "final", selection="UNDER")
    rows = [
        earlier,
        final,
        _outcome("WIN", selection="OVER", source_hash="earlier"),
        _outcome("LOSS", selection="UNDER", source_hash="final"),
    ]

    projection = project_canonical_outcomes(rows, candidates=())

    assert [row["selection"] for row in projection.canonical_outcomes] == ["UNDER"]
    assert [row["settlement_outcome"] for row in projection.canonical_outcomes] == ["LOSS"]
    assert len(projection.audit_only_outcomes) == 1
    assert projection.audit_only_outcomes[0]["audit_reason"] in {
        "NON_CANONICAL_CAPTURE",
        "NON_CANONICAL_SELECTION",
    }


def test_identity_aware_exact_match_wins_over_legacy() -> None:
    corrected = _corrected_candidate()
    legacy = _capture("2026-07-15T09:00:00Z", "legacy")
    exact = _outcome(
        "WIN",
        source_hash="corrected",
        strategy_version="DECISION_CONTRACT_V2",
        estimate_id="estimate-v2",
        quote_id="quote-v2",
    )
    compatibility = _outcome("LOSS", source_hash="legacy")

    projection = project_canonical_outcomes(
        [legacy, exact, compatibility],
        candidates=[corrected],
    )

    assert len(projection.canonical_outcomes) == 1
    assert projection.canonical_outcomes[0]["settlement_outcome"] == "WIN"
    assert projection.canonical_outcomes[0]["corrected_evidence"] is True
    assert projection.metrics["identity_aware_matched_count"] == 1


def test_unmatched_identity_aware_outcome_is_not_counted() -> None:
    outcome = _outcome(
        "WIN",
        source_hash="missing",
        strategy_version="DECISION_CONTRACT_V2",
        estimate_id="estimate-v2",
        quote_id="quote-v2",
    )

    projection = project_canonical_outcomes([outcome], candidates=())

    assert projection.canonical_outcomes == ()
    assert len(projection.unmatched_identity_outcomes) == 1
    assert projection.unmatched_identity_outcomes[0]["audit_reason"] == (
        "IDENTITY_AWARE_OUTCOME_UNMATCHED"
    )
    assert projection.metrics["identity_aware_unmatched_count"] == 1
    assert projection.metrics["status"] == "BLOCKED"


def test_nonunique_canonical_candidate_blocks_performance() -> None:
    first = _corrected_candidate(capture_hash="capture-a")
    second = _corrected_candidate(capture_hash="capture-b")

    projection = project_canonical_outcomes([], candidates=[first, second])

    assert projection.metrics["canonical_candidate_nonunique_count"] == 1
    assert projection.metrics["status"] == "BLOCKED"


def test_historical_version_label_without_complete_identity_is_audit_only() -> None:
    capture = _capture("2026-07-15T09:00:00Z", "legacy")
    outcome = _outcome(
        "WIN",
        source_hash="legacy",
        strategy_version="DECISION_CONTRACT_V2",
    )

    projection = project_canonical_outcomes([capture, outcome], candidates=())

    assert projection.canonical_outcomes == ()
    assert projection.unmatched_identity_outcomes == ()
    assert projection.audit_only_outcomes[0]["audit_reason"] == (
        "HISTORICAL_INCOMPLETE_IDENTITY"
    )
    assert projection.metrics["historical_incomplete_identity_count"] == 1
    assert projection.metrics["status"] == "PASS_WITH_LEGACY_AUDIT"


def test_conflicting_outcomes_block_performance() -> None:
    capture = _capture("2026-07-15T09:00:00Z", "final")

    projection = project_canonical_outcomes(
        [capture, _outcome("WIN"), _outcome("LOSS", settled_at="2026-07-15T13:05:00Z")],
        candidates=(),
    )

    assert projection.canonical_outcomes == ()
    assert len(projection.conflicting_outcomes) == 2
    assert projection.metrics["outcome_conflict_count"] == 1
    assert projection.metrics["status"] == "BLOCKED"


def test_validation_and_official_never_cross() -> None:
    validation = _capture("2026-07-15T09:00:00Z", "validation")
    official = _capture(
        "2026-07-15T09:30:00Z",
        "official",
        recommendation_scope="OFFICIAL",
    )
    validation_outcome = _outcome("WIN", recommendation_scope="VALIDATION")

    projection = project_canonical_outcomes(
        [validation, official, validation_outcome],
        candidates=(),
    )

    assert len(projection.canonical_outcomes) == 1
    assert projection.canonical_outcomes[0]["recommendation_scope"] == "VALIDATION"
    assert projection.metrics["cross_track_contamination_count"] == 0


def test_strategy_versions_have_separate_denominators() -> None:
    wide_v1 = _capture(
        "2026-07-15T08:00:00Z",
        "wide-v1",
        recommendation_scope="SHADOW",
        strategy_version="WIDE_SHADOW_V1",
        shadow=True,
    )
    wide_v2 = _capture(
        "2026-07-15T09:00:00Z",
        "wide-v2",
        recommendation_scope="SHADOW",
        strategy_version="WIDE_SHADOW_V2",
        shadow=True,
    )

    candidates = legacy_performance_candidates([wide_v1, wide_v2])

    assert {row["strategy_version"] for row in candidates} == {
        "WIDE_SHADOW_V1",
        "WIDE_SHADOW_V2",
    }


def test_wide_and_strict_never_cross() -> None:
    wide = _corrected_candidate(
        capture_hash="wide",
        scope="SHADOW",
        strategy="WIDE_SHADOW_V1",
        estimate_id="estimate-wide",
        quote_id="quote-wide",
    )
    strict = _corrected_candidate(
        capture_hash="strict",
        scope="SHADOW",
        strategy="W2_AH_STRICT_SHADOW_V1",
        estimate_id="estimate-strict",
        quote_id="quote-strict",
    )
    outcomes = [
        _outcome(
            "WIN",
            source_hash=str(candidate["capture_hash"]),
            recommendation_scope="SHADOW",
            strategy_version=str(candidate["strategy_version"]),
            estimate_id=str(candidate["estimate_id"]),
            quote_id=str(candidate["quote_id"]),
        )
        for candidate in (wide, strict)
    ]

    projection = project_canonical_outcomes(outcomes, candidates=[wide, strict])

    assert len(projection.canonical_outcomes) == 2
    assert {row["strategy_version"] for row in projection.canonical_outcomes} == {
        "WIDE_SHADOW_V1",
        "W2_AH_STRICT_SHADOW_V1",
    }
    assert projection.metrics["cross_track_contamination_count"] == 0


def test_sanitized_staging_regression_fixture_reproduces_canonical_denominators() -> None:
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures/forward_ledger/staging_denominator_regression_20260715.jsonl"
    )

    audit = audit_denominators(read_jsonl(fixture).records)

    assert audit["by_scope"]["VALIDATION"] == {
        "raw_outcome_row_count": 43,
        "canonical_outcome_count": 16,
        "audit_only_outcome_count": 27,
    }
    assert audit["by_scope"]["SHADOW"] == {
        "raw_outcome_row_count": 60,
        "canonical_outcome_count": 22,
        "audit_only_outcome_count": 38,
    }
    integrity = audit["performance_integrity"]
    assert integrity["duplicate_audit_row_count"] == 14
    assert integrity["canonical_duplicate_count"] == 0
    assert integrity["cross_track_contamination_count"] == 0
    assert integrity["outcome_conflict_count"] == 0
    assert integrity["status"] == "PASS_WITH_LEGACY_AUDIT"


def _capture(
    captured_at: str,
    capture_hash: str,
    *,
    selection: str = "OVER",
    recommendation_scope: str = "VALIDATION",
    strategy_version: str | None = None,
    shadow: bool = False,
) -> dict[str, object]:
    selection_payload = {
        "market": "TOTALS",
        "selection": selection,
    }
    row: dict[str, object] = {
        "record_type": "capture",
        "fixture_id": "fixture-1",
        "captured_at": captured_at,
        "kickoff_utc": "2026-07-15T12:00:00Z",
        "capture_hash": capture_hash,
        "recommendation_scope": recommendation_scope,
        "decision_tier": "ANALYSIS_PICK" if recommendation_scope == "VALIDATION" else "WATCH",
    }
    if strategy_version:
        row["strategy_version"] = strategy_version
    if shadow:
        row["shadow_picks"] = [{**selection_payload, "strategy_version": strategy_version}]
    else:
        row["pick"] = selection_payload
    return row


def _outcome(
    settlement: str,
    *,
    selection: str = "OVER",
    source_hash: str | None = None,
    recommendation_scope: str = "VALIDATION",
    strategy_version: str | None = None,
    estimate_id: str | None = None,
    quote_id: str | None = None,
    settled_at: str = "2026-07-15T13:00:00Z",
) -> dict[str, object]:
    row: dict[str, object] = {
        "record_type": "outcome",
        "fixture_id": "fixture-1",
        "market": "TOTALS",
        "selection": selection,
        "recommendation_scope": recommendation_scope,
        "settled_side": "shadow_pick" if recommendation_scope == "SHADOW" else "pick",
        "settlement_outcome": settlement,
        "settled_at": settled_at,
    }
    if source_hash:
        row["source_capture_hash"] = source_hash
    if strategy_version:
        row["strategy_version"] = strategy_version
    if estimate_id:
        row["estimate_id"] = estimate_id
    if quote_id:
        row["quote_id"] = quote_id
    return row


def _corrected_candidate(
    *,
    capture_hash: str = "corrected",
    scope: str = "VALIDATION",
    strategy: str = "DECISION_CONTRACT_V2",
    estimate_id: str = "estimate-v2",
    quote_id: str = "quote-v2",
) -> dict[str, object]:
    candidate = _capture(
        "2026-07-15T10:00:00Z",
        capture_hash,
        recommendation_scope=scope,
        strategy_version=strategy,
        shadow=scope == "SHADOW",
    )
    candidate.update(
        market="TOTALS",
        selection="OVER",
        estimate_id=estimate_id,
        quote_id=quote_id,
        canonical_candidate=True,
        audit_only=False,
        exclusion_reason=None,
        evidence_eligible=True,
    )
    return deepcopy(candidate)
