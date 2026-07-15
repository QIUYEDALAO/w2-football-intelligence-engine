from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot
from w2.models.market_quote import MarketQuote
from w2.tracking.canonical_identity import (
    candidate_for_outcome,
    canonical_capture_candidates,
)
from w2.tracking.forward_ledger_performance import forward_ledger_performance


def test_canonical_candidate_is_last_valid_prematch_then_capture_hash() -> None:
    first = _capture("2026-07-15T09:00:00Z", "hash-a")
    last_a = _capture("2026-07-15T10:00:00Z", "hash-a")
    last_b = _capture("2026-07-15T10:00:00Z", "hash-b")

    candidates = canonical_capture_candidates([first, last_b, last_a])

    selected = [row for row in candidates if row["canonical_candidate"] is True]
    assert len(selected) == 1
    assert selected[0]["capture_hash"] == "hash-b"
    assert len([row for row in candidates if row["audit_only"] is True]) == 2


def test_canonical_candidate_rejects_postkickoff_invalid_and_ineligible_evidence() -> None:
    postkickoff = _capture("2026-07-15T13:00:00Z", "late")
    invalid_snapshot = _capture("2026-07-15T10:00:00Z", "snapshot")
    invalid_snapshot["fair_market_estimate_snapshots"][0]["home_mu"] = 99  # type: ignore[index]
    invalid_quote = _capture("2026-07-15T10:00:00Z", "quote")
    invalid_quote["audit_capture_identities"][0]["market_quote"]["selection_price"] = 9  # type: ignore[index]
    ineligible = _capture("2026-07-15T10:00:00Z", "ineligible")
    ineligible["audit_capture_identities"][0]["evidence_eligible"] = False  # type: ignore[index]

    candidates = canonical_capture_candidates(
        [postkickoff, invalid_snapshot, invalid_quote, ineligible]
    )

    assert {row["exclusion_reason"] for row in candidates} == {
        "NOT_PREMATCH",
        "INVALID_SNAPSHOT",
        "INVALID_QUOTE",
        "EVIDENCE_INELIGIBLE",
    }
    assert not any(row["canonical_candidate"] for row in candidates)


def test_scopes_and_shadow_strategy_versions_never_collapse() -> None:
    validation = _capture("2026-07-15T10:00:00Z", "validation")
    official = deepcopy(validation)
    official["capture_hash"] = "official"
    official["audit_capture_identities"][0]["recommendation_scope"] = "OFFICIAL"  # type: ignore[index]
    wide = deepcopy(validation)
    wide["capture_hash"] = "wide"
    wide["audit_capture_identities"][0].update(  # type: ignore[index]
        recommendation_scope="SHADOW", strategy_version="WIDE_SHADOW_V1"
    )
    strict_v1 = deepcopy(wide)
    strict_v1["capture_hash"] = "strict-v1"
    strict_v1["audit_capture_identities"][0][  # type: ignore[index]
        "strategy_version"
    ] = "w2.analysis_gate_v2_shadow.v1"
    strict_v2 = deepcopy(strict_v1)
    strict_v2["capture_hash"] = "strict-v2"
    strict_v2["audit_capture_identities"][0][  # type: ignore[index]
        "strategy_version"
    ] = "w2.analysis_gate_v2_shadow.v2"

    candidates = canonical_capture_candidates([validation, official, wide, strict_v1, strict_v2])

    assert len([row for row in candidates if row["canonical_candidate"]]) == 5


def test_outcome_requires_source_capture_hash_and_complete_strategy_identity() -> None:
    capture = _capture("2026-07-15T10:00:00Z", "capture")
    candidates = canonical_capture_candidates([capture])
    identity = capture["audit_capture_identities"][0]  # type: ignore[index]
    outcome = {
        "fixture_id": "fixture-1",
        "market": "TOTALS",
        "selection": "OVER",
        "recommendation_scope": "VALIDATION",
        "strategy_version": "DECISION_CONTRACT_V2",
        "source_capture_hash": "capture",
        "estimate_id": identity["estimate_id"],
        "quote_id": identity["quote_id"],
    }

    assert candidate_for_outcome(candidates, outcome) is not None
    assert candidate_for_outcome(candidates, {"fixture_id": "fixture-1"}) is None


def test_performance_counts_only_outcome_for_canonical_capture(tmp_path: Path) -> None:
    earlier = _capture("2026-07-15T09:00:00Z", "earlier")
    canonical = _capture("2026-07-15T10:00:00Z", "canonical")
    identity = canonical["audit_capture_identities"][0]  # type: ignore[index]
    outcomes = [
        {
            "record_type": "outcome",
            "fixture_id": "fixture-1",
            "market": "TOTALS",
            "selection": "OVER",
            "recommendation_scope": "VALIDATION",
            "strategy_version": "DECISION_CONTRACT_V2",
            "estimate_id": identity["estimate_id"],
            "quote_id": identity["quote_id"],
            "source_capture_hash": source,
            "settled_side": "pick",
            "settlement_outcome": result,
        }
        for source, result in (("earlier", "LOSS"), ("canonical", "WIN"))
    ]
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    (root / "ledger.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in [earlier, canonical, *outcomes]),
        encoding="utf-8",
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["outcomes_validation"]["settled_sample_count"] == 1
    assert payload["outcomes_validation"]["hit_count"] == 1
    assert payload["outcomes_validation"]["miss_count"] == 0


def _capture(captured_at: str, capture_hash: str) -> dict[str, object]:
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="fixture-1",
        estimate=FairMarketEstimate(
            market="TOTALS",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=2.75,
            probabilities={"OVER": 0.52, "UNDER": 0.48},
            home_mu=1.6,
            away_mu=1.1,
            feature_as_of="2026-07-15T08:00:00Z",
            train_cutoff="2026-06-30T00:00:00Z",
            artifact_hash="artifact",
            artifact_version="r4.1",
        ),
        odds_snapshot={"ou": {"line": 2.5, "over_price": 1.95, "under_price": 1.95}},
        feature_snapshot={"home_xg": 1.6, "away_xg": 1.1},
        created_at=captured_at,
    ).as_dict()
    quote = MarketQuote.create(
        fixture_id="fixture-1",
        market="TOTALS",
        selection="OVER",
        odds={"line": 2.5, "over_price": 1.95, "under_price": 1.95},
        captured_at=captured_at,
    ).as_dict()
    return {
        "record_type": "capture",
        "fixture_id": "fixture-1",
        "kickoff_utc": "2026-07-15T12:00:00Z",
        "captured_at": captured_at,
        "capture_hash": capture_hash,
        "fair_market_estimate_snapshots": [snapshot],
        "audit_capture_identities": [
            {
                "market": "TOTALS",
                "selection": "OVER",
                "recommendation_scope": "VALIDATION",
                "strategy_version": "DECISION_CONTRACT_V2",
                "estimate_id": snapshot["estimate_id"],
                "quote_id": quote["quote_id"],
                "market_quote": quote,
                "evidence_eligible": True,
            }
        ],
    }
