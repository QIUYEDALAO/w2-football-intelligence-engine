from __future__ import annotations

from typing import Any

from w2.tracking.canonical_identity import canonical_capture_candidates


def test_repeated_immutable_snapshot_semantics_are_verified_once(monkeypatch: Any) -> None:
    semantic_calls = 0

    monkeypatch.setattr(
        "w2.tracking.canonical_identity.verify_estimate_snapshot",
        lambda _snapshot: True,
    )

    def verify_semantics(_snapshot: object) -> bool:
        nonlocal semantic_calls
        semantic_calls += 1
        return True

    monkeypatch.setattr(
        "w2.tracking.canonical_identity.verify_estimate_semantics",
        verify_semantics,
    )
    monkeypatch.setattr(
        "w2.tracking.canonical_identity.verify_market_quote",
        lambda _quote: True,
    )
    snapshot = {
        "schema_version": "w2.fair_market_estimate_snapshot.v2",
        "estimate_id": "fme_same",
        "integrity": {"estimate_hash": "same"},
    }
    quote = {"quote_id": "quote_same"}
    records = [
        {
            "record_type": "capture",
            "fixture_id": "1",
            "captured_at": captured_at,
            "kickoff_utc": "2026-07-16T12:00:00Z",
            "capture_hash": f"capture-{index}",
            "estimate_id": "fme_same",
            "quote_id": "quote_same",
            "market_quote": quote,
            "fair_market_estimate_snapshots": [snapshot],
            "pick": {
                "market": "ASIAN_HANDICAP",
                "selection": "HOME",
                "estimate_id": "fme_same",
                "quote_id": "quote_same",
            },
            "recommendation_scope": "VALIDATION",
        }
        for index, captured_at in enumerate(
            ("2026-07-16T09:00:00Z", "2026-07-16T10:00:00Z"),
            start=1,
        )
    ]

    candidates = canonical_capture_candidates(records)

    assert len(candidates) == 2
    assert semantic_calls == 1


def test_same_declared_id_with_changed_snapshot_is_verified_again(monkeypatch: Any) -> None:
    semantic_calls = 0

    monkeypatch.setattr(
        "w2.tracking.canonical_identity.verify_estimate_snapshot",
        lambda _snapshot: True,
    )

    def verify_semantics(_snapshot: object) -> bool:
        nonlocal semantic_calls
        semantic_calls += 1
        return True

    monkeypatch.setattr(
        "w2.tracking.canonical_identity.verify_estimate_semantics",
        verify_semantics,
    )
    monkeypatch.setattr(
        "w2.tracking.canonical_identity.verify_market_quote",
        lambda _quote: True,
    )
    records = []
    for index, fair_line in enumerate((-0.5, -0.75), start=1):
        records.append(
            {
                "record_type": "capture",
                "fixture_id": "1",
                "captured_at": f"2026-07-16T{index + 8:02d}:00:00Z",
                "kickoff_utc": "2026-07-16T12:00:00Z",
                "capture_hash": f"capture-{index}",
                "estimate_id": "fme_declared_same",
                "quote_id": "quote_same",
                "market_quote": {"quote_id": "quote_same"},
                "fair_market_estimate_snapshots": [
                    {
                        "estimate_id": "fme_declared_same",
                        "fair_line": fair_line,
                    }
                ],
                "pick": {
                    "market": "ASIAN_HANDICAP",
                    "selection": "HOME",
                    "estimate_id": "fme_declared_same",
                    "quote_id": "quote_same",
                },
                "recommendation_scope": "VALIDATION",
            }
        )

    canonical_capture_candidates(records)

    assert semantic_calls == 2
