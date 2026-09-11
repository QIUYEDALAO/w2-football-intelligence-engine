from __future__ import annotations

from decimal import Decimal

from scripts.audit_v1_market_shape import clamp_fixture_ids, fair_line_at_even_odds


def test_fair_lines_use_five_state_cashflow() -> None:
    matrix = {(2, 0): Decimal("0.5"), (0, 1): Decimal("0.5")}

    ah_line, ah_ev = fair_line_at_even_odds(matrix, market="ASIAN_HANDICAP", anchor=Decimal("-0.5"))
    total_line, total_ev = fair_line_at_even_odds(matrix, market="TOTALS", anchor=Decimal("1.5"))

    assert ah_line == Decimal("-0.5")
    assert ah_ev == 0
    assert total_line == Decimal("1.5")
    assert total_ev == 0


def test_clamp_detection_uses_delta_shift_and_total_invariance() -> None:
    tracks = [
        {"fixture_id": "clean", "track": "X", "lambda_home": 1.2, "lambda_away": 1.0},
        {"fixture_id": "clean", "track": "Y", "lambda_home": 1.29, "lambda_away": 0.91},
        {"fixture_id": "clamped", "track": "X", "lambda_home": 1.2, "lambda_away": 0.16},
        {"fixture_id": "clamped", "track": "Y", "lambda_home": 1.29, "lambda_away": 0.15},
    ]

    assert clamp_fixture_ids(tracks) == {"clamped"}
