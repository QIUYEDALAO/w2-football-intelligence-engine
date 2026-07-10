from __future__ import annotations

from w2.models.r4_1_features import (
    R4_1_WINDOW_MATCHES,
    r4_1_strength_features,
    r4_1_strength_features_from_rolling,
)


def test_offline_and_serving_strength_features_share_the_same_transform() -> None:
    histories = {
        ("allsvenskan", "home"): [(1.4, 0.9)] * R4_1_WINDOW_MATCHES,
        ("allsvenskan", "away"): [(1.1, 1.3)] * R4_1_WINDOW_MATCHES,
    }

    offline = r4_1_strength_features(
        competition_id="allsvenskan",
        histories=histories,
        home_key=("allsvenskan", "home"),
        away_key=("allsvenskan", "away"),
    )
    serving = r4_1_strength_features_from_rolling(
        home_for=1.4,
        home_against=0.9,
        away_for=1.1,
        away_against=1.3,
        league_for=1.25,
        league_against=1.1,
    )

    assert offline == serving
