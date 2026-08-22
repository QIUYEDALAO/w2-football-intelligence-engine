from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import scripts.freeze_factor_v2_split_and_train as cli

from w2.factor_model.history import RAW_HISTORY_CORPUS_SCHEMA_VERSION


def _pair(index: int, kickoff: datetime) -> list[dict[str, Any]]:
    fixture_id = f"api_football:{index}"
    captured_at = kickoff + timedelta(days=40)
    common = {
        "fixture_id": fixture_id,
        "provider": "api_football",
        "provider_fixture_id": str(index),
        "provider_league_id": "140",
        "season": str(kickoff.year),
        "kickoff_utc": kickoff,
        "fixture_status": "FT",
        "team_identity_namespace": "api_football.provider_team_id.v1",
        "result_identity_hash": f"{index:064x}",
        "raw_payload_sha256": f"{index + 10:064x}",
        "raw_captured_at": captured_at,
        "result_first_captured_at": captured_at,
        "result_capture_delay_seconds": 40 * 24 * 60 * 60,
    }
    return [
        {
            **common,
            "team_side": "HOME",
            "team_id": "10",
            "opponent_team_id": "20",
            "goals_for": 2,
            "goals_against": 1,
            "history_hash": f"{index + 20:064x}",
        },
        {
            **common,
            "team_side": "AWAY",
            "team_id": "20",
            "opponent_team_id": "10",
            "goals_for": 1,
            "goals_against": 2,
            "history_hash": f"{index + 30:064x}",
        },
    ]


def _corpus() -> dict[str, Any]:
    snapshot = datetime(2026, 8, 24, tzinfo=UTC)
    body = {
        "schema_version": RAW_HISTORY_CORPUS_SCHEMA_VERSION,
        "provider": "api_football",
        "team_identity_namespace": "api_football.provider_team_id.v1",
        "snapshot_as_of": snapshot,
        "kickoff_from": datetime(2023, 1, 1, tzinfo=UTC),
        "kickoff_to": snapshot,
        "seasons": ["2023", "2024", "2025", "2026"],
        "history_rows": (
            _pair(0, datetime(2023, 5, 1, tzinfo=UTC))
            + _pair(1, datetime(2024, 5, 1, tzinfo=UTC))
            + _pair(2, datetime(2024, 6, 1, tzinfo=UTC))
            + _pair(3, datetime(2025, 6, 1, tzinfo=UTC))
            + _pair(4, datetime(2026, 6, 1, tzinfo=UTC))
        ),
    }
    return {
        **body,
        "corpus_sha256": cli._hash("FACTOR_MODEL_GATE1_RAW_HISTORY_CORPUS", body),
    }


def test_split_train_report_separates_snapshot_and_feature_times(tmp_path: Path) -> None:
    corpus = _corpus()

    artifacts = cli.build_artifacts(
        corpus,
        expected_corpus_sha256=corpus["corpus_sha256"],
        expected_snapshot_as_of=corpus["snapshot_as_of"],
        warmup_minimum_feature_scope_history_rows=2,
    )
    report = artifacts["report"]

    assert report["corpus_binding"]["corpus_snapshot_as_of"] == corpus["snapshot_as_of"]
    assert report["feature_time_contract"]["feature_as_of_policy"] == (
        "TARGET_FIXTURE_KICKOFF_UTC"
    )
    assert report["split_policy"]["counts"] == {
        "TRAIN": 2,
        "VALIDATION": 1,
        "HOLDOUT": 1,
    }
    assert report["corpus_binding"]["total_source_fixture_count"] == 5
    assert report["corpus_binding"]["total_fixture_count"] == 4
    assert artifacts["visibility"][0]["global_visible_history_row_count"] == 2
    assert report["split_policy"]["historical_replay_cutoff"] == (
        cli.HISTORICAL_REPLAY_CUTOFF
    )
    assert report["split_policy"]["historical_replay_cutoff"] < corpus["snapshot_as_of"]
    assert report["split_policy"]["historical_replay_cutoff_in_split_manifest_hash"] is True
    assert report["feature_time_contract"][
        "source_kickoff_gte_feature_as_of_violation_count"
    ] == 0
    assert report["missing_feature_contract"][
        "zero_feature_scope_visible_history_fixture_ids"
    ] == []
    assert report["missing_feature_contract"]["full_corpus_mean_imputation_used"] is False
    assert report["late_result_policy"] == {
        "backfilled_fixture_count_over_36h": 5,
        "provider_sla_interpretation": False,
        "included_in_feature_values": False,
        "used_for_visibility_or_timeliness_decisions": False,
        "forbidden_timing_field_occurrence_count_in_feature_snapshots": 0,
    }
    assert report["train_calibration"]["fit_split"] == "TRAIN"
    assert report["train_calibration"]["validation_or_holdout_used_for_fit"] is False
    assert report["f6_owner_decision"]["status"] == (
        "OPTION_B_APPROVED_BACKFILL_COVERAGE_REVIEW_PENDING"
    )
    assert report["f6_owner_decision"]["selected_option"] == "B"
    assert report["f6_owner_decision"]["after_warmup_observed_rate"] is not None
    assert report["f6_owner_decision"]["defaults_or_priors_applied"] is False
    assert report["contracts"]["ablation_scoring_executed"] is False

    output = tmp_path / "artifacts"
    cli.write_artifacts(output, artifacts)
    assert len(list(output.iterdir())) == 7
