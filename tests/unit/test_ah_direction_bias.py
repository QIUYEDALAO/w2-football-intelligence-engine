from __future__ import annotations

from w2.tracking.ah_direction_bias import build_ah_direction_bias


def _row(
    index: int,
    *,
    selection: str = "HOME_AH",
    line: float = -0.75,
    league: str = "premier_league",
    artifact: str = "artifact-1",
) -> dict[str, object]:
    return {
        "record_type": "outcome",
        "fixture_id": f"fixture-{index}",
        "competition_id": "39",
        "market": "ASIAN_HANDICAP",
        "selection": selection,
        "entry_line": line,
        "settled_side": "shadow_pick",
        "strategy_version": "W2_AH_STRICT_SHADOW_V1",
        "estimate_id": f"fme-{index}",
        "quote_id": f"mq-{index}",
        "source_capture_hash": f"capture-{index}",
        "canonical_performance_key": [
            f"fixture-{index}",
            "ASIAN_HANDICAP",
            "SHADOW",
            "W2_AH_STRICT_SHADOW_V1",
        ],
        "source_captured_at": f"2026-08-{index + 1:02d}T10:00:00Z",
        "analysis_gate_v2_shadow": {
            "evidence_eligible": True,
            "semantic_status": "VERIFIED",
            "confirmation_required": True,
            "confirmation_status": "CONFIRMED",
            "artifact_hash": artifact,
        },
        "league": league,
    }


def test_direction_bias_is_insufficient_before_eight_distinct_fixtures() -> None:
    report = build_ah_direction_bias([_row(index) for index in range(7)])

    assert report["overall"]["distinct_fixture_count"] == 7
    assert report["overall"]["status"] == "INSUFFICIENT_SAMPLE"


def test_direction_bias_warns_when_first_eight_are_all_same_direction() -> None:
    report = build_ah_direction_bias([_row(index) for index in range(8)])

    assert report["overall"]["status"] == "EARLY_WARNING"
    assert report["overall"]["home_ah_count"] == 8
    assert report["dimensions"]["handicap_role"]["HOME_FAVORITE"] == 8
    assert report["dimensions"]["line_bucket"]["QUARTER_THREE_QUARTER"] == 8


def test_direction_bias_blocks_nine_of_latest_ten_same_direction() -> None:
    rows = [_row(index) for index in range(9)]
    rows.append(_row(9, selection="AWAY_AH", line=0.75))

    report = build_ah_direction_bias(rows)

    assert report["overall"]["status"] == "BLOCKED"
    assert report["overall"]["latest_10_dominant_count"] == 9


def test_direction_bias_warns_but_does_not_block_at_eight_of_ten() -> None:
    rows = [_row(index) for index in range(8)]
    rows.extend(
        [
            _row(8, selection="AWAY_AH", line=0.75),
            _row(9, selection="AWAY_AH", line=0.75),
        ]
    )

    report = build_ah_direction_bias(rows)

    assert report["overall"]["status"] == "WARNING"
    assert report["overall"]["blocked"] is False


def test_direction_bias_excludes_unconfirmed_or_ineligible_and_dedupes_fixture() -> None:
    valid = [_row(index) for index in range(8)]
    duplicate = _row(0, selection="AWAY_AH", line=0.75)
    duplicate["source_captured_at"] = "2026-09-01T10:00:00Z"
    invalid = _row(20)
    invalid["analysis_gate_v2_shadow"] = {
        "evidence_eligible": True,
        "semantic_status": "VERIFIED",
        "confirmation_required": True,
        "confirmation_status": "PENDING",
    }

    report = build_ah_direction_bias([*valid, duplicate, invalid])

    assert report["overall"]["distinct_fixture_count"] == 8
    assert report["overall"]["home_ah_count"] == 7
    assert report["overall"]["away_ah_count"] == 1
    assert report["excluded_record_count"] == 1
