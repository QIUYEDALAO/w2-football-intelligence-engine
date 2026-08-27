from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.audit_factor_v2_ablation_preview_inputs import (
    POST_BACKFILL_LABELS,
    build_report,
    write_artifacts,
)

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.pit_dataset import NORMALIZED_FEATURE_SCHEMA_VERSION


def _normalized(fixture_id: str) -> dict[str, Any]:
    body = {
        "schema_version": NORMALIZED_FEATURE_SCHEMA_VERSION,
        "target_fixture_id": fixture_id,
        "feature_snapshot_sha256": "a" * 64,
        "preprocessing_sha256": "b" * 64,
        "factors": {
            "F3_REST_FITNESS": {
                "status": "READY",
                "raw_value": 1.0,
                "normalized_value": 0.5,
                "missing_indicator": 0,
                "imputation_applied": False,
            },
            "F6_H2H": {
                "status": "UNAVAILABLE",
                "raw_value": None,
                "normalized_value": None,
                "missing_indicator": 1,
                "imputation_applied": False,
            },
            "F7_STRENGTH_FORM": {
                "status": "READY",
                "raw_value": 2.0,
                "normalized_value": 1.0,
                "missing_indicator": 0,
                "imputation_applied": False,
            },
        },
        "numeric_effect_enabled": False,
    }
    return {
        **body,
        "normalized_features_sha256": canonical_sha256(
            {"identity_type": "NORMALIZED_FEATURES", **body},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
    }


def _source_files(tmp_path: Path) -> dict[str, Path]:
    paths = {name: tmp_path / f"{name}.json" for name in ("a", "b")}
    for path in paths.values():
        path.write_text("{}\n", encoding="utf-8")
    return paths


def test_preview_audit_excludes_f6_and_blocks_missing_baselines(tmp_path: Path) -> None:
    report = build_report(
        corpus={
            "corpus_sha256": "c" * 64,
            "snapshot_as_of": "2026-08-21T19:18:10Z",
            "history_rows": [
                {
                    "fixture_id": "api_football:1",
                    "team_side": "HOME",
                    "goals_for": 2,
                },
                {
                    "fixture_id": "api_football:1",
                    "team_side": "AWAY",
                    "goals_for": 1,
                },
            ],
        },
        split_manifest={
            "historical_replay_cutoff": "2026-08-21T19:18:10Z",
            "split_manifest_sha256": "d" * 64,
            "targets": [
                {"fixture_id": "api_football:1", "split": "VALIDATION"},
            ],
        },
        preprocessing={
            "preprocessing_sha256": "b" * 64,
            "split_manifest_sha256": "d" * 64,
            "blocked_factor_ids": ["F6_H2H"],
            "parameters": {"F6_H2H": {"status": "BLOCKED_BY_POLICY"}},
        },
        normalized_features=[_normalized("api_football:1")],
        calibration={"status": "UNFITTED", "coefficients": {}},
        source_files=_source_files(tmp_path),
    )

    assert report["status"] == "BLOCKED_INPUTS_NOT_CLOSED"
    assert report["labels"] == [
        "PREVIEW",
        "F6_EXCLUDED",
        "MUST_RERUN_AFTER_BACKFILL",
        "NOT_GATE1_CONCLUSION",
    ]
    assert report["excluded_factor"] == {
        "factor_id": "F6_H2H",
        "status": "BLOCKED_BY_POLICY",
        "included_in_design_vector": False,
        "default_prior_or_coefficient_applied": False,
    }
    assert report["required_scoring_input_coverage"] == {
        "target_fixture_count": 1,
        "outcome_ready_count": 1,
        "b0_xg_four_fields_ready_count": 0,
        "b1_production_lambdas_ready_count": 0,
        "b2_f3_f7_calibration_ready": False,
    }
    assert report["execution"]["ablation_fixture_output_count"] == 0
    assert report["execution"]["provider_calls"] == 0
    assert report["execution"]["database_writes"] == 0

    output = tmp_path / "output"
    write_artifacts(output, report)
    payload = json.loads((output / "factor_v2_ablation_preview_input_audit.json").read_text())
    assert payload["audit_sha256"] == report["audit_sha256"]


def test_post_backfill_preview_uses_completed_rerun_label(tmp_path: Path) -> None:
    report = build_report(
        corpus={
            "corpus_sha256": "c" * 64,
            "snapshot_as_of": "2026-08-22T05:50:41Z",
            "history_rows": [],
        },
        split_manifest={
            "historical_replay_cutoff": "2026-08-21T19:18:10Z",
            "split_manifest_sha256": "d" * 64,
            "targets": [],
        },
        preprocessing={
            "preprocessing_sha256": "b" * 64,
            "split_manifest_sha256": "d" * 64,
            "blocked_factor_ids": ["F6_H2H"],
            "parameters": {"F6_H2H": {"status": "BLOCKED_BY_POLICY"}},
        },
        normalized_features=[],
        calibration={"status": "UNFITTED", "coefficients": {}},
        source_files=_source_files(tmp_path),
        labels=POST_BACKFILL_LABELS,
    )

    assert report["labels"] == [
        "PREVIEW",
        "F6_EXCLUDED",
        "POST_BACKFILL_RERUN",
        "NOT_GATE1_CONCLUSION",
    ]
