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
from w2.factor_model.history import materialize_factor_history_from_persisted_raw

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

        def historical_fixture_payloads(self, **_kwargs: Any) -> list[dict[str, Any]]:
            return [{"fixture": {"id": 1, "date": NOW.isoformat()}}]

    repository = Repository()
    batch = materialize_factor_history_from_persisted_raw(
        repository,
        kickoff_from=NOW - timedelta(days=1),
        kickoff_to=NOW,
    )

    assert len(batch.fixture_payloads) == 1
    assert batch.provider_calls == 0
    assert repository.provider_calls == 0


def test_v2_migration_revokes_official_table_writes() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/0070_factor_shadow_v2_gate0.py"
    ).read_text(encoding="utf-8")

    assert "ON ALL TABLES IN SCHEMA public FROM {V2_ROLE}" in migration
    assert "GRANT INSERT, SELECT ON {', '.join(V2_TABLES)}" in migration
