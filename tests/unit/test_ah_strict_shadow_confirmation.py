from __future__ import annotations

from copy import deepcopy

from w2.strategy.analysis_gate_shadow import confirm_strict_ah_shadow


def _candidate(
    *,
    captured_at: str,
    quote_id: str,
    selection: str = "HOME_AH",
    model_basis_id: str = "fmb-1",
    candidate_pass: bool = True,
) -> dict[str, object]:
    return {
        "fixture_id": "fixture-1",
        "kickoff_utc": "2026-07-16T12:00:00Z",
        "market": "ASIAN_HANDICAP",
        "selection": selection,
        "model_basis_id": model_basis_id,
        "estimate_id": f"estimate-{quote_id}",
        "quote_id": quote_id,
        "quote_captured_at": captured_at,
        "candidate_pass": candidate_pass,
        "evidence_eligible": True,
        "semantic_status": "VERIFIED",
        "selection_line": -0.75 if selection == "HOME_AH" else 0.75,
        "odds": 1.92,
        "net_ev": 0.04,
        "loss_probability": 0.30,
        "downside_probability": 0.45,
    }


def test_strict_ah_requires_two_distinct_quotes_at_least_fifteen_minutes_apart() -> None:
    result = confirm_strict_ah_shadow(
        [
            _candidate(captured_at="2026-07-16T10:00:00Z", quote_id="mq-1"),
            _candidate(captured_at="2026-07-16T10:15:00Z", quote_id="mq-2"),
        ]
    )

    assert result["status"] == "PASS"
    assert result["confirmation_status"] == "CONFIRMED"
    assert result["strict_gate_hash"]
    assert result["evidence_bindings"] == [
        {"estimate_id": "estimate-mq-1", "quote_id": "mq-1"},
        {"estimate_id": "estimate-mq-2", "quote_id": "mq-2"},
    ]
    assert result["shadow_only"] is True
    assert result["visible_eligible"] is False
    assert result["affects_decision"] is False
    assert result["affects_pick"] is False
    assert result["affects_tier"] is False


def test_strict_ah_one_snapshot_is_confirmation_pending() -> None:
    result = confirm_strict_ah_shadow(
        [_candidate(captured_at="2026-07-16T10:00:00Z", quote_id="mq-1")]
    )

    assert result["status"] == "CONFIRMATION_PENDING"
    assert result["reason"] == "SECOND_SNAPSHOT_REQUIRED"


def test_strict_ah_direction_reversal_fails() -> None:
    result = confirm_strict_ah_shadow(
        [
            _candidate(captured_at="2026-07-16T10:00:00Z", quote_id="mq-1"),
            _candidate(
                captured_at="2026-07-16T10:20:00Z",
                quote_id="mq-2",
                selection="AWAY_AH",
            ),
        ]
    )

    assert result["status"] == "FAIL"
    assert result["reason"] == "DIRECTION_REVERSAL"


def test_strict_ah_model_basis_change_resets_confirmation_window() -> None:
    result = confirm_strict_ah_shadow(
        [
            _candidate(captured_at="2026-07-16T10:00:00Z", quote_id="mq-1"),
            _candidate(
                captured_at="2026-07-16T10:20:00Z",
                quote_id="mq-2",
                model_basis_id="fmb-2",
            ),
        ]
    )

    assert result["status"] == "CONFIRMATION_PENDING"
    assert result["reason"] == "MODEL_BASIS_CHANGED_CONFIRMATION_RESET"


def test_strict_ah_latest_snapshot_must_still_pass() -> None:
    latest = _candidate(
        captured_at="2026-07-16T10:20:00Z",
        quote_id="mq-2",
        candidate_pass=False,
    )
    latest["net_ev"] = 0.01

    result = confirm_strict_ah_shadow(
        [_candidate(captured_at="2026-07-16T10:00:00Z", quote_id="mq-1"), latest]
    )

    assert result["status"] == "FAIL"
    assert result["reason"] == "LATEST_THRESHOLDS_NOT_MET"


def test_strict_ah_rejects_snapshots_outside_t24_to_t30_window() -> None:
    early = deepcopy(_candidate(captured_at="2026-07-15T11:00:00Z", quote_id="mq-1"))
    result = confirm_strict_ah_shadow([early])

    assert result["status"] == "FAIL"
    assert result["reason"] == "OUTSIDE_CONFIRMATION_WINDOW"
