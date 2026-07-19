from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.backtest.ah_formal_evidence import AhFormalEvidenceProtocol, evaluate_ah_formal_evidence


def _protocol() -> AhFormalEvidenceProtocol:
    return AhFormalEvidenceProtocol(
        frozen_at_utc="2026-07-20T00:00:00Z",
        train_end_utc="2024-12-31T23:59:59Z",
        validation_end_utc="2025-12-31T23:59:59Z",
        minimum_train_samples=2,
        minimum_validation_samples=2,
        minimum_holdout_samples=2,
        minimum_stratum_samples=2,
        bootstrap_replicates=50,
    )


def _row(index: int, kickoff: datetime, *, legacy: bool = False) -> dict[str, object]:
    outcome = "WIN" if index % 2 == 0 else "LOSS"
    model = {"WIN": 0.7 if outcome == "WIN" else 0.1, "HALF_WIN": 0.05, "PUSH": 0.1,
             "HALF_LOSS": 0.05, "LOSS": 0.1 if outcome == "WIN" else 0.7}
    market = {"WIN": 0.45, "HALF_WIN": 0.1, "PUSH": 0.1, "HALF_LOSS": 0.1, "LOSS": 0.25}
    return {
        "fixture_id": f"fixture-{index}",
        "identity_trace_id": f"trace-{index}",
        "canonical_cohort": True,
        "legacy_ambiguous": legacy,
        "market": "ASIAN_HANDICAP",
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "as_of_utc": (kickoff - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "settlement_outcome": outcome,
        "model_probabilities": model,
        "market_devig_probabilities": market,
        "selection_odds": 2.0,
        "closing_devig_probability": 0.46,
        "league": "test-league",
        "line": -0.5,
        "selection_side": "HOME",
        "distinct_evidence_groups": ["ratings", "xg", "lineup"],
        "model_version": "frozen-model",
        "calibration_version": "frozen-calibration",
    }


def test_evidence_report_is_deterministic_and_requires_canonical_asof_rows() -> None:
    start = datetime(2024, 1, 10, tzinfo=UTC)
    rows = [
        _row(1, start),
        _row(2, start + timedelta(days=1)),
        _row(3, datetime(2025, 2, 1, tzinfo=UTC)),
        _row(4, datetime(2025, 2, 2, tzinfo=UTC)),
        _row(5, datetime(2026, 2, 1, tzinfo=UTC)),
        _row(6, datetime(2026, 2, 2, tzinfo=UTC)),
        _row(7, datetime(2026, 2, 3, tzinfo=UTC), legacy=True),
    ]

    first = evaluate_ah_formal_evidence(rows, protocol=_protocol(), data_source="frozen-test")
    second = evaluate_ah_formal_evidence(rows, protocol=_protocol(), data_source="frozen-test")

    assert first == second
    assert first["sample"]["canonical_asof_safe_rows"] == 6
    assert first["sample"]["exclusion_counts"] == {"LEGACY_AMBIGUOUS_IDENTITY": 1}
    assert first["sample"]["splits"] == {"train": 2, "validation": 2, "holdout": 2}
    assert first["conclusion"] == "PASS_FOR_SHADOW"
    assert first["formal_ah_enabled"] is False
    assert first["market_baseline_is_evidence"] is False


def test_insufficient_evidence_never_promotes_formal_ah() -> None:
    report = evaluate_ah_formal_evidence(
        [], protocol=_protocol(), data_source="no-frozen-export"
    )

    assert report["conclusion"] == "INSUFFICIENT_EVIDENCE"
    assert "NO_CANONICAL_ASOF_SAFE_AH_OBSERVATIONS" in report["blockers"]
    assert report["formal_ah_enabled"] is False
    assert report["recommendation_lock_enabled"] is False
