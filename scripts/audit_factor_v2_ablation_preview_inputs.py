#!/usr/bin/env python3
"""Fail-closed input audit for the F3/F7-only Gate 1 ablation preview."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.pit_dataset import verify_normalized_feature_vector

LABELS = (
    "PREVIEW",
    "F6_EXCLUDED",
    "MUST_RERUN_AFTER_BACKFILL",
    "NOT_GATE1_CONCLUSION",
)
POST_BACKFILL_LABELS = (
    "PREVIEW",
    "F6_EXCLUDED",
    "POST_BACKFILL_RERUN",
    "NOT_GATE1_CONCLUSION",
)
ACTIVE_FACTOR_IDS = ("F3_REST_FITNESS", "F7_STRENGTH_FORM")
REQUIRED_XG_FIELDS = (
    "home_xg_for",
    "home_xg_against",
    "away_xg_for",
    "away_xg_against",
)
REQUIRED_PRODUCTION_LAMBDA_FIELDS = (
    "production_lambda_home",
    "production_lambda_away",
)
SCORING_SPLITS = ("VALIDATION", "HOLDOUT")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(identity_type: str, payload: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {"identity_type": identity_type, **payload},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )


def _target_payloads(
    history_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, tuple[int, int]]]:
    payloads: dict[str, dict[str, Any]] = {}
    scores: dict[str, dict[str, int]] = {}
    for row in history_rows:
        fixture_id = str(row["fixture_id"])
        payload = payloads.setdefault(fixture_id, {})
        for field in (*REQUIRED_XG_FIELDS, *REQUIRED_PRODUCTION_LAMBDA_FIELDS):
            if row.get(field) is not None:
                payload[field] = row[field]
        side = str(row.get("team_side"))
        if side in {"HOME", "AWAY"} and row.get("goals_for") is not None:
            scores.setdefault(fixture_id, {})[side] = int(row["goals_for"])
    outcomes = {
        fixture_id: (score["HOME"], score["AWAY"])
        for fixture_id, score in scores.items()
        if set(score) == {"HOME", "AWAY"}
    }
    return payloads, outcomes


def _factor_coverage(
    *,
    target_ids: Sequence[str],
    normalized_by_fixture: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    for factor_id in ACTIVE_FACTOR_IDS:
        ready = 0
        observed = 0
        missing = 0
        for fixture_id in target_ids:
            vector = normalized_by_fixture.get(fixture_id)
            factor = None if vector is None else vector["factors"].get(factor_id)
            if factor is None or factor.get("status") != "READY":
                continue
            ready += 1
            if factor.get("raw_value") is None:
                missing += 1
            else:
                observed += 1
        coverage[factor_id] = {
            "target_fixture_count": len(target_ids),
            "ready_count": ready,
            "observed_count": observed,
            "missing_imputed_from_train_count": missing,
            "ready_rate": round(ready / len(target_ids), 8) if target_ids else None,
        }
    return coverage


def build_report(
    *,
    corpus: Mapping[str, Any],
    split_manifest: Mapping[str, Any],
    preprocessing: Mapping[str, Any],
    normalized_features: Sequence[dict[str, Any]],
    calibration: Mapping[str, Any],
    source_files: Mapping[str, Path],
    labels: Sequence[str] = LABELS,
) -> dict[str, Any]:
    normalized_by_fixture: dict[str, dict[str, Any]] = {}
    for vector in normalized_features:
        verify_normalized_feature_vector(vector)
        if vector.get("preprocessing_sha256") != preprocessing.get("preprocessing_sha256"):
            raise ValueError("FACTOR_V2_PREVIEW_PREPROCESSING_BINDING_MISMATCH")
        fixture_id = str(vector["target_fixture_id"])
        if fixture_id in normalized_by_fixture:
            raise ValueError("FACTOR_V2_PREVIEW_NORMALIZED_FIXTURE_DUPLICATE")
        normalized_by_fixture[fixture_id] = vector

    if preprocessing.get("blocked_factor_ids") != ["F6_H2H"]:
        raise ValueError("FACTOR_V2_PREVIEW_F6_NOT_BLOCKED_BY_POLICY")
    if preprocessing.get("parameters", {}).get("F6_H2H", {}).get("status") != ("BLOCKED_BY_POLICY"):
        raise ValueError("FACTOR_V2_PREVIEW_F6_NOT_BLOCKED_BY_POLICY")
    if preprocessing.get("split_manifest_sha256") != split_manifest.get("split_manifest_sha256"):
        raise ValueError("FACTOR_V2_PREVIEW_SPLIT_BINDING_MISMATCH")

    targets_by_split = {
        split: [
            str(row["fixture_id"]) for row in split_manifest["targets"] if row["split"] == split
        ]
        for split in ("TRAIN", *SCORING_SPLITS)
    }
    target_payloads, outcomes = _target_payloads(corpus["history_rows"])
    scoring_ids = [fixture_id for split in SCORING_SPLITS for fixture_id in targets_by_split[split]]
    xg_ready = sum(
        all(
            target_payloads.get(fixture_id, {}).get(field) is not None
            for field in REQUIRED_XG_FIELDS
        )
        for fixture_id in scoring_ids
    )
    production_lambda_ready = sum(
        all(
            target_payloads.get(fixture_id, {}).get(field) is not None
            for field in REQUIRED_PRODUCTION_LAMBDA_FIELDS
        )
        for fixture_id in scoring_ids
    )
    outcome_ready = sum(fixture_id in outcomes for fixture_id in scoring_ids)
    calibration_coefficient_names = set(calibration.get("relative_coefficients", {})) | set(
        calibration.get("total_coefficients", {})
    )
    calibrated_factor_ids = {
        name.partition(".")[0] for name in calibration_coefficient_names if "." in name
    }
    calibration_ready = (
        calibration.get("schema_version") == "w2.factor_model.ablation_calibration.v1"
        and calibration.get("fit_split") == "TRAIN"
        and calibration.get("admitted_for_historical_replay") is True
        and calibration.get("preprocessing_sha256") == preprocessing.get("preprocessing_sha256")
        and set(ACTIVE_FACTOR_IDS) <= calibrated_factor_ids
    )

    blockers: list[str] = []
    if xg_ready != len(scoring_ids):
        blockers.append("B0_XG_FOUR_FIELDS_NOT_AVAILABLE_FOR_ALL_SCORING_TARGETS")
    if production_lambda_ready != len(scoring_ids):
        blockers.append("B1_PRODUCTION_LAMBDAS_NOT_AVAILABLE_FOR_ALL_SCORING_TARGETS")
    if not calibration_ready:
        blockers.append("B2_F3_F7_FACTOR_EFFECT_CALIBRATION_NOT_FITTED_OR_ADMITTED")
    if outcome_ready != len(scoring_ids):
        blockers.append("OUTCOME_NOT_AVAILABLE_FOR_ALL_SCORING_TARGETS")

    body = {
        "schema_version": "w2.factor_model.ablation_preview_input_audit.v1",
        "labels": list(labels),
        "status": "BLOCKED_INPUTS_NOT_CLOSED" if blockers else "READY_FOR_PREVIEW",
        "active_factor_ids": list(ACTIVE_FACTOR_IDS),
        "excluded_factor": {
            "factor_id": "F6_H2H",
            "status": "BLOCKED_BY_POLICY",
            "included_in_design_vector": False,
            "default_prior_or_coefficient_applied": False,
        },
        "input_authorities": {
            name: {"path": str(path), "file_sha256": _file_sha256(path)}
            for name, path in sorted(source_files.items())
        },
        "bindings": {
            "corpus_sha256": corpus.get("corpus_sha256"),
            "corpus_snapshot_as_of": corpus.get("snapshot_as_of"),
            "historical_replay_cutoff": split_manifest.get("historical_replay_cutoff"),
            "split_manifest_sha256": split_manifest.get("split_manifest_sha256"),
            "preprocessing_sha256": preprocessing.get("preprocessing_sha256"),
            "calibration_status": calibration.get("status", "ABSENT"),
        },
        "target_counts": {
            split: len(targets_by_split[split]) for split in ("TRAIN", *SCORING_SPLITS)
        },
        "active_factor_coverage_by_split": {
            split: _factor_coverage(
                target_ids=targets_by_split[split],
                normalized_by_fixture=normalized_by_fixture,
            )
            for split in ("TRAIN", *SCORING_SPLITS)
        },
        "required_scoring_input_coverage": {
            "target_fixture_count": len(scoring_ids),
            "outcome_ready_count": outcome_ready,
            "b0_xg_four_fields_ready_count": xg_ready,
            "b1_production_lambdas_ready_count": production_lambda_ready,
            "b2_f3_f7_calibration_ready": calibration_ready,
        },
        "blockers": blockers,
        "engine_contract": {
            "tracks": ["B0_SAME_ENGINE_XG", "B1_CURRENT_PRODUCTION", "B2_FACTOR_V2"],
            "probability_method": "EXACT_13X13_SCORE_MATRIX",
            "max_goals": 12,
            "rho": 0.0,
            "sampling_used": False,
        },
        "execution": {
            "train_factor_effect_fit_executed": False,
            "validation_scoring_executed": False,
            "holdout_scoring_executed": False,
            "ablation_fixture_output_count": 0,
            "provider_calls": 0,
            "database_reads": 0,
            "database_writes": 0,
            "deployment_executed": False,
            "candidate_output_count": 0,
            "notification_output_count": 0,
            "outcome_ledger_write_count": 0,
        },
        "interpretation": (
            "No F3/F7 signal estimate is reportable until B0, B1, and B2 input "
            "authorities are all closed; score-derived xG or zero coefficients are forbidden."
        ),
    }
    return {
        **body,
        "audit_sha256": _hash("FACTOR_MODEL_V2_ABLATION_PREVIEW_INPUT_AUDIT", body),
    }


def _markdown(report: Mapping[str, Any]) -> str:
    inputs = report["required_scoring_input_coverage"]
    lines = [
        "# Factor V2 F3/F7 ablation preview input audit",
        "",
        f"- Labels: `{' / '.join(str(label) for label in report['labels'])}`",
        f"- Status: `{report['status']}`",
        "- F6: `BLOCKED_BY_POLICY`, absent from design vector; no default/prior/coefficient.",
        "- Provider / DB read / DB write / deploy: `0 / 0 / 0 / false`",
        "",
        "## Input closure",
        "",
        f"- Scoring targets: `{inputs['target_fixture_count']}`",
        f"- Outcomes: `{inputs['outcome_ready_count']}`",
        f"- B0 four-field xG: `{inputs['b0_xg_four_fields_ready_count']}`",
        f"- B1 production lambdas: `{inputs['b1_production_lambdas_ready_count']}`",
        f"- B2 F3/F7 calibration ready: `{inputs['b2_f3_f7_calibration_ready']}`",
        "",
        "## Blockers",
        "",
        *(f"- `{blocker}`" for blocker in report["blockers"]),
        "",
        "No signal metric is emitted. Scores are not relabeled as xG, and unfitted "
        "factor coefficients are not replaced by zero.",
    ]
    return "\n".join(lines) + "\n"


def write_artifacts(output_dir: Path, report: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "factor_v2_ablation_preview_input_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "factor_v2_ablation_preview_input_audit.md").write_text(
        _markdown(report), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--preprocessing", type=Path, required=True)
    parser.add_argument("--normalized-features", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--post-backfill", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "calibration": args.calibration,
        "corpus": args.corpus,
        "normalized_features": args.normalized_features,
        "preprocessing": args.preprocessing,
        "split_manifest": args.split_manifest,
    }
    payloads = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}
    report = build_report(
        corpus=payloads["corpus"],
        split_manifest=payloads["split_manifest"],
        preprocessing=payloads["preprocessing"],
        normalized_features=payloads["normalized_features"],
        calibration=payloads["calibration"],
        source_files=paths,
        labels=POST_BACKFILL_LABELS if args.post_backfill else LABELS,
    )
    write_artifacts(args.output_dir, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
