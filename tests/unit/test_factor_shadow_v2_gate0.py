from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from w2.domain.factor_registry import load_factor_registry
from w2.domain.factor_shadow_calibration import load_unfitted_factor_shadow_calibration
from w2.domain.factor_shadow_v2 import (
    FactorShadowSourceMode,
    factor_shadow_forecast_contract,
    factor_shadow_forecast_outcome_identity,
    factor_shadow_market_attempt_identity,
    factor_shadow_market_opportunity_identity,
)
from w2.factor_model.history import (
    build_pit_history_manifest,
    materialize_factor_history_from_persisted_raw,
)

NOW = datetime(2026, 8, 21, 12, tzinfo=UTC)


def _forward_forecast() -> dict[str, Any]:
    return factor_shadow_forecast_contract(
        fixture_id="api_football:1570351",
        model_family="w2.factor-shadow",
        model_version="factor-model-v2.unfitted",
        feature_registry_version="factor-model-v2.v1.unadmitted",
        calibration_version="factor-model-v2.unfitted",
        pit_input_identity_hash="a" * 64,
        captured_at=NOW,
        feature_as_of=NOW,
        source_mode=FactorShadowSourceMode.FORWARD_SHADOW,
        production_capture_identity_hash="b" * 64,
        production_captured_at=NOW,
    )


def test_forecast_identity_excludes_market_checkpoint_and_quote() -> None:
    forecast = _forward_forecast()

    assert forecast["probability_method"] == "EXACT_MATRIX"
    assert forecast["sampling_used"] is False
    assert {"market", "checkpoint", "quote_identity_hash"}.isdisjoint(forecast)

    opportunity = factor_shadow_market_opportunity_identity(
        forecast_identity_hash=forecast["forecast_identity_hash"],
        evaluation_policy_version="candidate-eval.v2",
        evaluation_slot_id="T30_VALIDATION_LOCK",
        market="TOTALS",
    )
    attempt = factor_shadow_market_attempt_identity(
        opportunity_identity_hash=opportunity,
        quote_identity_hash="c" * 64,
        source_event_identity="capture:event",
    )
    outcome = factor_shadow_forecast_outcome_identity(
        forecast_identity_hash=forecast["forecast_identity_hash"],
        authoritative_result_identity="d" * 64,
    )

    assert len({forecast["forecast_identity_hash"], opportunity, attempt, outcome}) == 4


def test_forward_forecast_requires_exact_production_capture_pair() -> None:
    with pytest.raises(ValueError, match="FORWARD_CAPTURE_PAIR_REQUIRED"):
        factor_shadow_forecast_contract(
            fixture_id="api_football:1570351",
            model_family="w2.factor-shadow",
            model_version="factor-model-v2.unfitted",
            feature_registry_version="factor-model-v2.v1.unadmitted",
            calibration_version="factor-model-v2.unfitted",
            pit_input_identity_hash="a" * 64,
            captured_at=NOW,
            feature_as_of=NOW,
            source_mode="FORWARD_SHADOW",
            production_capture_identity_hash="b" * 64,
            production_captured_at=NOW + timedelta(seconds=1),
        )


def test_historical_replay_cannot_bind_production_capture() -> None:
    with pytest.raises(ValueError, match="HISTORY_PRODUCTION_CAPTURE_FORBIDDEN"):
        factor_shadow_forecast_contract(
            fixture_id="api_football:1570351",
            model_family="w2.factor-shadow",
            model_version="factor-model-v2.unfitted",
            feature_registry_version="factor-model-v2.v1.unadmitted",
            calibration_version="factor-model-v2.unfitted",
            pit_input_identity_hash="a" * 64,
            captured_at=NOW,
            feature_as_of=NOW,
            source_mode="HISTORICAL_REPLAY",
            production_capture_identity_hash="b" * 64,
            production_captured_at=NOW,
        )


def test_v2_registry_is_independent_and_unadmitted() -> None:
    v1 = load_factor_registry("v1")
    v2 = load_factor_registry("factor-model-v2")

    assert v1["F9_TRUE_XG"]["lifecycle"] == "ACTIVE"
    assert len(v2) == 11
    assert all(row["numeric_effect_enabled"] is False for row in v2.values())
    assert v2["F3_REST_FITNESS"]["lambda_channel"] == "RELATIVE"
    assert v2["F4_MATCH_IMPORTANCE"]["lambda_channel"] == "NONE"
    assert v2["F5_RECENT_AH_COVER"]["lifecycle"] == "RETIRED"


def test_v2_calibration_is_separate_unfitted_artifact() -> None:
    artifact = load_unfitted_factor_shadow_calibration()

    assert artifact["calibration_version"] == "factor-model-v2.unfitted"
    assert artifact["coefficients"] == {}
    assert artifact["admitted_for_historical_replay"] is False
    assert artifact["admitted_for_forward_shadow"] is False
    assert len(artifact["artifact_sha256"]) == 64


def test_historical_materialization_has_no_provider_capability() -> None:
    class Repository:
        provider_calls = 0

        def request_live(self, *_args: Any, **_kwargs: Any) -> None:
            self.provider_calls += 1
            raise AssertionError("Provider must not be called")

        def fixture_payloads(self, **_kwargs: Any) -> list[dict[str, Any]]:
            return [
                {"fixture": {"id": 1, "date": (NOW - timedelta(hours=1)).isoformat()}},
                {"fixture": {"id": 2, "date": NOW.isoformat()}},
            ]

    repository = Repository()
    batch = materialize_factor_history_from_persisted_raw(
        repository,
        kickoff_from=NOW - timedelta(days=1),
        kickoff_to=NOW + timedelta(days=1),
        as_of=NOW,
    )

    assert len(batch.fixture_payloads) == 1
    assert batch.source_scope == "KICKOFF_BEFORE_AS_OF"
    assert batch.provider_calls == 0
    assert repository.provider_calls == 0


def test_v2_migration_revokes_official_table_writes() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/0070_factor_shadow_v2_gate0.py"
    ).read_text(encoding="utf-8")

    assert "ON ALL TABLES IN SCHEMA public FROM {V2_ROLE}" in migration
    assert "GRANT INSERT, SELECT ON {', '.join(V2_TABLES)}" in migration


def _history_pair(
    fixture_id: str,
    *,
    kickoff: datetime,
    captured_at: datetime,
    status: str = "FT",
) -> list[dict[str, Any]]:
    common = {
        "fixture_id": fixture_id,
        "provider": "api_football",
        "provider_fixture_id": fixture_id.rsplit(":", 1)[-1],
        "competition_id": "competition:140",
        "season": "2025",
        "kickoff_utc": kickoff,
        "fixture_status": status,
        "result_identity_hash": f"result:{fixture_id}",
        "source_raw_hash": f"raw:{fixture_id}",
        "captured_at": captured_at,
    }
    return [
        {
            **common,
            "history_id": f"{fixture_id}:home",
            "history_hash": f"history:{fixture_id}:home",
            "team_side": "HOME",
            "team_w2_id": "team:home",
            "opponent_w2_id": "team:away",
            "goals_for": 2,
            "goals_against": 1,
        },
        {
            **common,
            "history_id": f"{fixture_id}:away",
            "history_hash": f"history:{fixture_id}:away",
            "team_side": "AWAY",
            "team_w2_id": "team:away",
            "opponent_w2_id": "team:home",
            "goals_for": 1,
            "goals_against": 2,
        },
    ]


def test_pit_history_manifest_includes_only_results_known_before_target() -> None:
    prior = _history_pair(
        "api_football:prior",
        kickoff=NOW - timedelta(days=2),
        captured_at=NOW - timedelta(days=1),
    )
    same_kickoff = _history_pair(
        "api_football:same",
        kickoff=NOW,
        captured_at=NOW - timedelta(hours=1),
    )
    late_result = _history_pair(
        "api_football:late",
        kickoff=NOW - timedelta(days=3),
        captured_at=NOW,
    )
    unfinished = _history_pair(
        "api_football:unfinished",
        kickoff=NOW - timedelta(days=4),
        captured_at=NOW - timedelta(days=3),
        status="NS",
    )

    manifest = build_pit_history_manifest(
        prior + same_kickoff + late_result + unfinished,
        target_fixture_id="api_football:target",
        target_kickoff=NOW,
        feature_as_of=NOW,
    )

    assert [row["fixture_id"] for row in manifest["source_fixtures"]] == [
        "api_football:prior"
    ]
    assert manifest["source_fixture_count"] == 1
    assert manifest["source_history_row_count"] == 2
    assert manifest["excluded_fixture_counts"] == {
        "NOT_BEFORE_TARGET_KICKOFF": 1,
        "RESULT_NOT_KNOWN_AT_ASOF": 1,
        "UNFINISHED_FIXTURE": 1,
    }


def test_pit_history_manifest_rejects_incomplete_and_conflicting_identities() -> None:
    incomplete = _history_pair(
        "api_football:incomplete",
        kickoff=NOW - timedelta(days=2),
        captured_at=NOW - timedelta(days=1),
    )[:1]
    conflict = _history_pair(
        "api_football:conflict",
        kickoff=NOW - timedelta(days=3),
        captured_at=NOW - timedelta(days=2),
    )
    conflict[1]["opponent_w2_id"] = "team:other"

    manifest = build_pit_history_manifest(
        incomplete + conflict,
        target_fixture_id="api_football:target",
        target_kickoff=NOW,
        feature_as_of=NOW,
    )

    assert manifest["source_fixtures"] == []
    assert manifest["excluded_fixture_counts"] == {
        "IDENTITY_CONFLICT": 1,
        "INCOMPLETE_FIXTURE_IDENTITY": 1,
    }


def test_pit_history_manifest_is_order_independent_and_deduplicates_exact_rows() -> None:
    rows = _history_pair(
        "api_football:prior",
        kickoff=NOW - timedelta(days=2),
        captured_at=NOW - timedelta(days=1),
    )

    first = build_pit_history_manifest(
        rows + [dict(rows[0])],
        target_fixture_id="api_football:target",
        target_kickoff=NOW,
        feature_as_of=NOW,
    )
    second = build_pit_history_manifest(
        list(reversed(rows)),
        target_fixture_id="api_football:target",
        target_kickoff=NOW,
        feature_as_of=NOW,
    )

    assert first == second
    assert len(first["manifest_sha256"]) == 64


def test_pit_history_manifest_forbids_features_after_target_kickoff() -> None:
    with pytest.raises(ValueError, match="FEATURE_ASOF_AFTER_TARGET_KICKOFF"):
        build_pit_history_manifest(
            [],
            target_fixture_id="api_football:target",
            target_kickoff=NOW,
            feature_as_of=NOW + timedelta(seconds=1),
        )
