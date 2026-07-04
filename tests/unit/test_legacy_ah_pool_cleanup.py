from __future__ import annotations

from scripts.clean_w2_legacy_ah_pool import classify_legacy_ah_label


def test_legacy_ah_pool_cleanup_keeps_only_full_time_ah_in_mainline_pool() -> None:
    assert classify_legacy_ah_label("Asian Handicap") == "ASIAN_HANDICAP"
    assert classify_legacy_ah_label("Cards Asian Handicap") == "CARDS_ASIAN_HANDICAP"
    assert classify_legacy_ah_label("Corners Asian Handicap") == "CORNERS_ASIAN_HANDICAP"
    assert classify_legacy_ah_label("First Half Asian Handicap") == "FIRST_HALF_ASIAN_HANDICAP"
    assert classify_legacy_ah_label("") == "LEGACY_UNSCOPED_ASIAN_HANDICAP"
