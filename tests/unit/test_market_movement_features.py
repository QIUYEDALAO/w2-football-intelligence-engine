from __future__ import annotations

from w2.analysis.market_movement import build_market_divergence, build_market_movement


def timeline(*snapshots: dict) -> dict:
    return {"fixture_id": "fx1", "snapshots": list(snapshots)}


def ah_snapshot(
    checkpoint: str,
    line: float,
    *,
    as_of: str,
    home_price: float = 1.9,
    away_price: float = 1.9,
) -> dict:
    return {
        "checkpoint": checkpoint,
        "market": "ASIAN_HANDICAP",
        "line": line,
        "as_of": as_of,
        "home_price": home_price,
        "away_price": away_price,
        "immutable": True,
    }


def test_home_deepened_when_lock_line_more_negative() -> None:
    movement = build_market_movement(
        timeline(
            ah_snapshot("opening", -0.5, as_of="2026-06-28T12:00:00Z"),
            ah_snapshot("lock", -1.0, as_of="2026-06-28T18:30:00Z"),
        )
    )

    assert movement["status"] == "READY"
    assert movement["line_moved"] is True
    assert movement["line_move_direction"] == "HOME_DEEPENED"
    assert movement["line_move_magnitude"] == 0.5
    assert movement["pattern"] == "JUMP_LINE"


def test_away_deepened_when_lock_line_less_negative() -> None:
    movement = build_market_movement(
        timeline(
            ah_snapshot("opening", -1.0, as_of="2026-06-28T12:00:00Z"),
            ah_snapshot("lock", -0.5, as_of="2026-06-28T18:30:00Z"),
        )
    )

    assert movement["line_move_direction"] == "AWAY_DEEPENED"
    assert movement["line_move_magnitude"] == 0.5


def test_stable_line_reports_water_drift() -> None:
    movement = build_market_movement(
        timeline(
            ah_snapshot(
                "opening",
                -0.5,
                as_of="2026-06-28T12:00:00Z",
                home_price=1.95,
                away_price=1.85,
            ),
            ah_snapshot(
                "lock",
                -0.5,
                as_of="2026-06-28T18:30:00Z",
                home_price=1.89,
                away_price=1.9,
            ),
        )
    )

    assert movement["line_moved"] is False
    assert movement["line_move_direction"] == "STABLE"
    assert movement["water_drift_home"] == -0.06
    assert movement["water_drift_away"] == 0.05


def test_one_way_and_rebound_patterns_are_deterministic() -> None:
    one_way = build_market_movement(
        timeline(
            ah_snapshot("opening", -0.25, as_of="2026-06-28T12:00:00Z"),
            ah_snapshot("T-6h", -0.5, as_of="2026-06-28T13:00:00Z"),
            ah_snapshot("lock", -0.5, as_of="2026-06-28T18:30:00Z"),
        )
    )
    rebound = build_market_movement(
        timeline(
            ah_snapshot("opening", -0.25, as_of="2026-06-28T12:00:00Z"),
            ah_snapshot("T-6h", -0.5, as_of="2026-06-28T13:00:00Z"),
            ah_snapshot("lock", -0.25, as_of="2026-06-28T18:30:00Z"),
        )
    )

    assert one_way["pattern"] == "ONE_WAY"
    assert rebound["pattern"] == "EARLY_DROP_LATE_REBOUND"
    assert build_market_movement({})["status"] == "INSUFFICIENT"


def test_one_checkpoint_is_partial() -> None:
    movement = build_market_movement(
        timeline(ah_snapshot("opening", -0.25, as_of="2026-06-28T12:00:00Z"))
    )

    assert movement["status"] == "PARTIAL"
    assert movement["pattern"] == "INSUFFICIENT"


def test_divergence_uses_home_perspective_formula_without_direction_output() -> None:
    movement = build_market_movement(
        timeline(
            ah_snapshot("opening", -1.0, as_of="2026-06-28T12:00:00Z"),
            ah_snapshot("lock", -1.0, as_of="2026-06-28T18:30:00Z"),
        )
    )
    divergence = build_market_divergence(
        pricing_shadow={
            "fair_ah": -0.25,
            "calibration_version": "UNVALIDATED",
            "team_score": {"home": 0.6, "away": 0.4},
        },
        market_movement=movement,
        timeline=timeline(
            ah_snapshot("opening", -1.0, as_of="2026-06-28T12:00:00Z"),
            ah_snapshot("lock", -1.0, as_of="2026-06-28T18:30:00Z"),
        ),
        home_team_name="Home",
        away_team_name="Away",
    )

    assert divergence["lock_divergence"] == 0.75
    assert divergence["book_deeper_than_factors"] is True
    assert divergence["book_deeper_side"] == "HOME"
    assert divergence["direction_allowed"] is False
    assert divergence["calibration_status"] == "UNVALIDATED"


def test_divergence_insufficient_without_fair_or_market() -> None:
    assert (
        build_market_divergence(
            pricing_shadow={"fair_ah": None},
            market_movement=None,
            timeline={},
        )["status"]
        == "INSUFFICIENT"
    )


def test_positive_market_divergence_case() -> None:
    movement = build_market_movement(
        timeline(
            ah_snapshot("opening", 0.5, as_of="2026-06-28T12:00:00Z"),
            ah_snapshot("lock", 0.5, as_of="2026-06-28T18:30:00Z"),
        )
    )
    divergence = build_market_divergence(
        pricing_shadow={"fair_ah": 0.25, "team_score": {"home": 0.4, "away": 0.6}},
        market_movement=movement,
        timeline=timeline(
            ah_snapshot("opening", 0.5, as_of="2026-06-28T12:00:00Z"),
            ah_snapshot("lock", 0.5, as_of="2026-06-28T18:30:00Z"),
        ),
    )

    assert divergence["open_divergence"] == -0.25
    assert divergence["lock_divergence"] == -0.25
    assert divergence["book_deeper_side"] == "AWAY"

