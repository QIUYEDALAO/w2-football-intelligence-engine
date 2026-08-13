from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from w2.domain.canonical_serialization import CURRENT_SERIALIZER_VERSION
from w2.domain.recommendation_decision_v4 import (
    RECOMMENDATION_SCHEMA_VERSION,
    build_recommendation_decision_v4,
    candidate_identity_hash,
)
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
    assert first.snapshot_payload_json["recommendation"]["quote_identity"]["capture_id"] == (
        "capture-1"
    )


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


def test_lock_snapshot_builder_rejects_legacy_v3_formal_without_v4() -> None:
    card = _card()
    card.pop("recommendation_decision_v4")
    card["recommendation_decision_v3"] = {"outcome": "FORMAL_RECOMMEND"}

    with pytest.raises(ValueError, match="LOCK_SNAPSHOT_REQUIRES_VALID_V4"):
        build_recommendation_lock_snapshot(
            recommendation_id="rec-1",
            card=card,
            locked_at=NOW,
            reason="formal prematch lock",
            release_sha="release-sha",
        )


def test_lock_snapshot_builder_rejects_tampered_v4() -> None:
    card = _card()
    selected = card["recommendation_decision_v4"]["selected_candidate"]
    selected["exact_line"] = "0.75"

    with pytest.raises(ValueError, match="LOCK_SNAPSHOT_REQUIRES_VALID_V4"):
        build_recommendation_lock_snapshot(
            recommendation_id="rec-1",
            card=card,
            locked_at=NOW,
            reason="formal prematch lock",
            release_sha="release-sha",
        )


def test_lock_snapshot_builder_requires_v4_formal_outcome() -> None:
    card = _card()
    card["recommendation_decision_v4"] = _decision_v4(capability_status="FORMAL_DISABLED")

    with pytest.raises(ValueError, match="LOCK_SNAPSHOT_REQUIRES_V4_FORMAL_RECOMMEND"):
        build_recommendation_lock_snapshot(
            recommendation_id="rec-1",
            card=card,
            locked_at=NOW,
            reason="formal prematch lock",
            release_sha="release-sha",
        )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("selection", "HOME_AH", "LOCK_SNAPSHOT_V4_SELECTION_CONFLICT"),
        ("line", "0.75", "LOCK_SNAPSHOT_V4_LINE_CONFLICT"),
        ("odds", "1.61", "LOCK_SNAPSHOT_V4_QUOTE_CONFLICT"),
    ],
)
def test_lock_snapshot_builder_requires_recommendation_to_match_v4_candidate(
    field: str,
    value: str,
    error: str,
) -> None:
    card = _card()
    card["recommendation"][field] = value

    with pytest.raises(ValueError, match=error):
        build_recommendation_lock_snapshot(
            recommendation_id="rec-1",
            card=card,
            locked_at=NOW,
            reason="formal prematch lock",
            release_sha="release-sha",
        )


def test_lock_snapshot_builder_rejects_quote_identity_capture_id_mutation() -> None:
    card = _card()
    card["recommendation"]["quote_identity"]["capture_id"] = "capture-other"

    with pytest.raises(ValueError, match="LOCK_SNAPSHOT_V4_QUOTE_IDENTITY_CONFLICT"):
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
        "recommendation_decision_v3": {"outcome": "NOT_READY"},
        "recommendation_decision_v4": _decision_v4(),
        "recommendation": {
            "decision_tier": "RECOMMEND",
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY_AH",
            "selection_label_cn": "Away 受让",
            "line": "0.5",
            "odds": "1.6",
            "expected_value": "0.083",
            "ev_se": "0.21",
            "reverse_factor_value": True,
            "quote_identity": _quote_identity(),
            "ah_settlement_distribution": {
                "win": 0.41,
                "half_win": 0.1,
                "push": 0.0,
                "loss": 0.49,
            },
        },
        "current_odds": {"ah": {"home_price": "2.02", "away_price": "1.6"}},
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


def _decision_v4(*, capability_status: str = "FORMAL_ENABLED") -> dict[str, object]:
    payload: dict[str, object] = {
            "fixture_id": "fixture-1",
            "competition_id": "world_cup_2026",
            "season": "2026",
            "kickoff_utc": "2026-06-22T03:00:00Z",
            "kickoff_revision_or_fixture_identity_hash": "d" * 64,
            "provider": "api-football",
            "bookmaker_id": "unibet",
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY",
            "exact_line": "0.5",
            "capture_id": "capture-1",
            "captured_at": "2026-06-22T00:50:00Z",
            "decision_evaluated_at": "2026-06-22T00:55:00Z",
            "quote_observation_ids": {
                "home": "observation-home",
                "away": "observation-away",
            },
            "raw_payload_sha256": "a" * 64,
            "source_revision": "e" * 40,
            "model_version": "model-v1",
            "calibration_version": "calibration-v1",
            "serializer_version": CURRENT_SERIALIZER_VERSION.value,
            "recommendation_schema_version": RECOMMENDATION_SCHEMA_VERSION,
            "quote_schema_version": "w2.quote_identity.v1",
            "model_input_manifest_hash": "b" * 64,
            "decimal_odds": "1.6",
            "canonical_mainline_identity": {
                "market": "ASIAN_HANDICAP",
                "line": "-0.5",
                "selected_side_line": "0.5",
                "candidate_role": "MARKET_MAINLINE",
                "quote_identity_hash": "c" * 64,
            },
            "settlement_distribution": {
                "WIN": "0.5",
                "HALF_WIN": "0.1",
                "PUSH": "0.1",
                "HALF_LOSS": "0.1",
                "LOSS": "0.2",
            },
            "fair_odds": "1.4545",
            "expected_value": "0.08",
            "uncertainty": "0.01",
            "readiness": {
                "status": "READY",
                "quote_identity_status": "COMPLETE",
                "quote_freshness_status": "COMPLETE",
                "model_status": "READY",
            },
            "capability_status": capability_status,
            "formal_admission": {
                "status": "PASSED" if capability_status == "FORMAL_ENABLED" else "DISABLED",
                "readiness_hash": "f" * 64
                if capability_status == "FORMAL_ENABLED"
                else None,
                "approval_hash": "1" * 64
                if capability_status == "FORMAL_ENABLED"
                else None,
                "candidate_identity_hash": None,
            },
        }
    admission = payload["formal_admission"]
    assert isinstance(admission, dict)
    if capability_status == "FORMAL_ENABLED":
        admission["candidate_identity_hash"] = candidate_identity_hash(payload)
    return build_recommendation_decision_v4(payload).as_dict()


def _quote_identity() -> dict[str, object]:
    decision = _decision_v4()
    authoritative = decision["authoritative_input"]
    mainline = authoritative["canonical_mainline_identity"]
    return {
        "provider": authoritative["provider"],
        "bookmaker_id": authoritative["bookmaker_id"],
        "capture_id": authoritative["capture_id"],
        "captured_at": authoritative["captured_at"],
        "observation_ids": authoritative["quote_observation_ids"],
        "raw_payload_sha256": authoritative["raw_payload_sha256"],
        "source_revision": authoritative["source_revision"],
        "quote_identity_hash": mainline["quote_identity_hash"],
    }
