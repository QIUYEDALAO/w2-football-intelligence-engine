from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from w2.infrastructure.persistence.recommendation_lock_snapshot import (
    build_recommendation_lock_snapshot,
    canonical_snapshot_hash,
)

NOW = datetime(2026, 6, 22, 1, 0, tzinfo=UTC)


def test_lock_snapshot_builder_creates_reproducible_payload_hash() -> None:
    card = _card()
    first = build_recommendation_lock_snapshot(
        recommendation_id="rec-1",
        card=card,
        locked_at=NOW,
        reason="formal prematch lock",
        release_sha="release-sha",
    )
    second = build_recommendation_lock_snapshot(
        recommendation_id="rec-1",
        card=card,
        locked_at=NOW,
        reason="formal prematch lock",
        release_sha="release-sha",
    )

    assert first.reproducible is True
    assert first.legacy_marker_only is False
    assert first.snapshot_payload_json["recommendation"]["selection"] == "AWAY_AH"
    assert first.snapshot_payload_json["recommendation"]["ev_se"] == "0.21"
    assert first.snapshot_payload_hash == second.snapshot_payload_hash
    assert first.snapshot_payload_hash == canonical_snapshot_hash(first.snapshot_payload_json)
    assert first.release_sha == "release-sha"
    assert first.market_timeline_json["pattern"] == "ONE_WAY_MOVE"
    assert first.ah_settlement_distribution_json["win"] == 0.41


def test_lock_snapshot_hash_changes_when_freeze_payload_changes() -> None:
    card = _card()
    changed = deepcopy(card)
    changed["market_timeline"]["pattern"] = "REVERSAL"

    first = build_recommendation_lock_snapshot(
        recommendation_id="rec-1",
        card=card,
        locked_at=NOW,
        reason="formal prematch lock",
        release_sha="release-sha",
    )
    second = build_recommendation_lock_snapshot(
        recommendation_id="rec-1",
        card=changed,
        locked_at=NOW,
        reason="formal prematch lock",
        release_sha="release-sha",
    )

    assert first.snapshot_payload_hash != second.snapshot_payload_hash


def test_lock_snapshot_builder_rejects_invalid_formal_payload() -> None:
    card = _card()
    card["recommendation"]["selection"] = "UNKNOWN"

    with pytest.raises(ValueError, match="LOCK_SNAPSHOT_REQUIRES_AH_SELECTION"):
        build_recommendation_lock_snapshot(
            recommendation_id="rec-1",
            card=card,
            locked_at=NOW,
            reason="formal prematch lock",
            release_sha="release-sha",
        )


def test_lock_snapshot_builder_requires_release_sha() -> None:
    card = _card()

    with pytest.raises(ValueError, match="LOCK_SNAPSHOT_REQUIRES_RELEASE_SHA"):
        build_recommendation_lock_snapshot(
            recommendation_id="rec-1",
            card=card,
            locked_at=NOW,
            reason="formal prematch lock",
            release_sha=None,
        )


def test_lock_snapshot_builder_requires_data_profile() -> None:
    card = _card()
    card.pop("data_profile")

    with pytest.raises(ValueError, match="LOCK_SNAPSHOT_REQUIRES_DATA_PROFILE"):
        build_recommendation_lock_snapshot(
            recommendation_id="rec-1",
            card=card,
            locked_at=NOW,
            reason="formal prematch lock",
            release_sha="release-sha",
        )


def test_lock_snapshot_builder_rejects_post_kickoff_freeze() -> None:
    card = _card()

    with pytest.raises(ValueError, match="LOCK_SNAPSHOT_REQUIRES_PREMATCH"):
        build_recommendation_lock_snapshot(
            recommendation_id="rec-1",
            card=card,
            locked_at=datetime(2026, 6, 22, 3, 1, tzinfo=UTC),
            reason="formal prematch lock",
            release_sha="release-sha",
        )


def _card() -> dict[str, object]:
    return {
        "fixture_id": "fixture-1",
        "generated_at": "2026-06-22T01:00:00Z",
        "kickoff_utc": "2026-06-22T03:00:00Z",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "competition_name": "World Cup",
        "formal_recommendation": True,
        "recommendation": {
            "tier": "FORMAL",
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY_AH",
            "selection_label_cn": "Away 受让",
            "line": "0.75",
            "odds": "1.87",
            "expected_value": "0.083",
            "ev_se": "0.21",
            "reverse_factor_value": True,
            "ah_settlement_distribution": {
                "win": 0.41,
                "half_win": 0.1,
                "push": 0.0,
                "loss": 0.49,
            },
        },
        "current_odds": {"ah": {"home_price": "2.02", "away_price": "1.87"}},
        "pricing_shadow": {
            "fair_ah": "-0.25",
            "market_ah": "-0.75",
            "edge_ah": "0.50",
            "devig_method": "POWER",
            "team_score_home": "6.2",
            "team_score_away": "5.8",
            "factors": [{"id": "F8_SQUAD_VALUE", "status": "READY"}],
            "independent_signal_count": 5,
            "independent_signal_groups": ["xg", "rating", "squad_value"],
            "missing_independent_sources": [],
            "model_version": "w2.formal.mc_poisson.v1",
            "calibration_version": "w2.formal.lambda_baseline_prior.v1",
            "coherent": True,
        },
        "scoreline_reference": {
            "direction_top3": [{"scoreline": "1-1", "probability": 0.13}],
        },
        "market_timeline": {
            "label": "盘口时间线 · 参照 · 未验证",
            "verified": False,
            "direction_allowed": False,
            "pattern": "ONE_WAY_MOVE",
            "as_of": "2026-06-22T01:00:00Z",
        },
        "data_refresh": {"lineups_status": "READY", "xg_status": "READY"},
        "data_profile": "real-db",
    }
