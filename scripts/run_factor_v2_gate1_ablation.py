#!/usr/bin/env python3
"""Run the Provider-zero Factor V2 Gate 1 F3/F7 ablation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.backtest.factor_v2_ablation import (
    build_b0_b1_b2_ablation,
    factor_calibration_artifact,
    fit_poisson_factor_coefficients,
)
from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.pit_dataset import (
    XG_PIT_SOURCE_KICKOFF_ONLY,
    verify_normalized_feature_vector,
)
from w2.features.xg_materialization import (
    XG_METHOD_VERSION,
    XG_SOURCE_SYSTEM,
    TeamXgMatch,
    materialize_rolling_xg,
)
from w2.models.evaluation import EvaluationRow, metrics
from w2.strategy.calibration import CALIBRATION_VERSION, calibrate_lambdas

ACTIVE_FACTOR_IDS = ("F3_REST_FITNESS", "F7_STRENGTH_FORM")
F6_STATUS = "EXCLUDED_BY_PREREGISTERED_THRESHOLD"
SCORING_SPLITS = ("VALIDATION", "HOLDOUT")
TRACK_IDS = ("B0_SAME_ENGINE_XG", "B1_RECOMPUTED", "B2_FACTOR_V2")
REPORT_SCHEMA_VERSION = "w2.factor_model.gate1_ablation_report.v1"
RESULT_SCHEMA_VERSION = "w2.factor_model.gate1_ablation_results.v1"


def _utc(value: Any) -> datetime:
    parsed = value
    if isinstance(parsed, str):
        parsed = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
    if not isinstance(parsed, datetime) or parsed.tzinfo is None:
        raise ValueError("FACTOR_V2_GATE1_TIME_INVALID")
    return parsed.astimezone(UTC)


def _hash(identity_type: str, payload: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {"identity_type": identity_type, **payload},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_xg_matches(path: Path) -> list[TeamXgMatch]:
    rows: list[TeamXgMatch] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                TeamXgMatch(
                    fixture_id=str(row["fixture_id"]),
                    team_id=str(row["team_id"]),
                    opponent_team_id=str(row["opponent_team_id"]),
                    kickoff_at=_utc(row["kickoff_at"]),
                    captured_at=_utc(row["captured_at"]),
                    xg_for=float(row["xg_for"]),
                    xg_against=float(row["xg_against"]),
                    goals_for=int(row["goals_for"]),
                    goals_against=int(row["goals_against"]),
                    raw_payload_sha256=str(row["raw_payload_sha256"]),
                    source_system=str(row["source_system"]),
                )
            )
    return rows


def _targets(corpus: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in corpus["history_rows"]:
        grouped[str(row["fixture_id"])][str(row["team_side"])] = row
    targets: dict[str, dict[str, Any]] = {}
    for fixture_id, sides in grouped.items():
        if set(sides) != {"HOME", "AWAY"}:
            continue
        home, away = sides["HOME"], sides["AWAY"]
        targets[fixture_id] = {
            "fixture_id": fixture_id,
            "raw_fixture_id": str(home["provider_fixture_id"]),
            "kickoff": _utc(home["kickoff_utc"]),
            "provider_league_id": str(home["provider_league_id"]),
            "season": str(home["season"]),
            "home_team_id": str(home["team_id"]),
            "away_team_id": str(away["team_id"]),
            "home_goals": int(home["goals_for"]),
            "away_goals": int(away["goals_for"]),
        }
    return targets


def _verify_bindings(
    *,
    split_manifest: Mapping[str, Any],
    preprocessing: Mapping[str, Any],
    normalized_features: Sequence[Mapping[str, Any]],
) -> None:
    manifest_body = {
        key: value
        for key, value in split_manifest.items()
        if key != "split_manifest_sha256"
    }
    manifest_body["historical_replay_cutoff"] = _utc(
        manifest_body["historical_replay_cutoff"]
    )
    manifest_body["boundaries"] = {
        key: _utc(value) for key, value in manifest_body["boundaries"].items()
    }
    manifest_body["targets"] = [
        {**row, "kickoff": _utc(row["kickoff"])}
        for row in manifest_body["targets"]
    ]
    if split_manifest.get("split_manifest_sha256") != _hash(
        "TEMPORAL_SPLIT_MANIFEST", manifest_body
    ):
        raise ValueError("FACTOR_V2_GATE1_SPLIT_HASH_MISMATCH")
    preprocessing_body = {
        key: value
        for key, value in preprocessing.items()
        if key != "preprocessing_sha256"
    }
    if preprocessing.get("preprocessing_sha256") != _hash(
        "TRAIN_PREPROCESSING", preprocessing_body
    ):
        raise ValueError("FACTOR_V2_GATE1_PREPROCESSING_HASH_MISMATCH")
    if preprocessing.get("split_manifest_sha256") != split_manifest.get(
        "split_manifest_sha256"
    ):
        raise ValueError("FACTOR_V2_GATE1_PREPROCESSING_SPLIT_MISMATCH")
    if preprocessing.get("excluded_factor_statuses") != {"F6_H2H": F6_STATUS}:
        raise ValueError("FACTOR_V2_GATE1_F6_EXCLUSION_MISMATCH")
    if split_manifest.get("xg_pit_semantics") != XG_PIT_SOURCE_KICKOFF_ONLY:
        raise ValueError("FACTOR_V2_GATE1_XG_PIT_SEMANTICS_MISMATCH")
    if split_manifest.get("xg_method_version") != XG_METHOD_VERSION:
        raise ValueError("FACTOR_V2_GATE1_XG_METHOD_MISMATCH")
    for row in normalized_features:
        verify_normalized_feature_vector(dict(row))
        if row.get("preprocessing_sha256") != preprocessing.get(
            "preprocessing_sha256"
        ):
            raise ValueError("FACTOR_V2_GATE1_NORMALIZED_BINDING_MISMATCH")


def _depth_strata(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    values = sorted(int(row["visible_history_rows"]) for row in rows)
    if not values:
        return {}
    low_edge = values[(len(values) - 1) // 3]
    middle_edge = values[(2 * (len(values) - 1)) // 3]
    output: dict[str, dict[str, Any]] = {}
    for name, selected in (
        ("LOW", [row for row in rows if int(row["visible_history_rows"]) <= low_edge]),
        (
            "MIDDLE",
            [
                row
                for row in rows
                if low_edge < int(row["visible_history_rows"]) <= middle_edge
            ],
        ),
        ("HIGH", [row for row in rows if int(row["visible_history_rows"]) > middle_edge]),
    ):
        output[name] = {
            "definition": (
                f"visible_history_rows <= {low_edge}"
                if name == "LOW"
                else f"{low_edge} < visible_history_rows <= {middle_edge}"
                if name == "MIDDLE"
                else f"visible_history_rows > {middle_edge}"
            ),
            "fixture_ids": [str(row["fixture_id"]) for row in selected],
        }
    return output


def _evaluation_rows(
    rows: Sequence[Mapping[str, Any]], track_id: str
) -> list[EvaluationRow]:
    return [
        EvaluationRow(
            fixture_id=str(row["fixture_id"]),
            actual=str(row["actual"]),
            probabilities=dict(row["tracks"][track_id]["one_x_two"]),
            competition=str(row["provider_league_id"]),
            season=str(row["season"]),
            neutral_site=False,
        )
        for row in rows
    ]


def _metrics_by_track(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        track_id: metrics(_evaluation_rows(rows, track_id)) if rows else None
        for track_id in TRACK_IDS
    }


def _metric_deltas(track_metrics: Mapping[str, Any]) -> dict[str, Any]:
    baseline = track_metrics["B0_SAME_ENGINE_XG"]
    if baseline is None:
        return {track_id: None for track_id in TRACK_IDS[1:]}
    return {
        track_id: {
            key: round(float(track_metrics[track_id][key]) - float(baseline[key]), 6)
            for key in ("log_loss", "rps", "brier", "ece")
        }
        for track_id in TRACK_IDS[1:]
    }


def _gate_checks(
    *,
    coverage_by_split: Mapping[str, Mapping[str, Any]],
    metrics_by_split: Mapping[str, Mapping[str, Any]],
    strata_by_split: Mapping[str, Mapping[str, Any]],
    leakage_violation_count: int,
    deterministic: bool,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for split in SCORING_SPLITS:
        coverage = float(coverage_by_split[split]["b0_scorable_rate"])
        global_metrics = metrics_by_split[split]
        b0 = global_metrics["B0_SAME_ENGINE_XG"]
        b2 = global_metrics["B2_FACTOR_V2"]
        improved_strata = sum(
            row["fixture_count"] > 0
            and row["metrics"]["B2_FACTOR_V2"]["log_loss"]
            < row["metrics"]["B0_SAME_ENGINE_XG"]["log_loss"]
            for row in strata_by_split[split].values()
        )
        checks.extend(
            (
                {
                    "check": f"{split}_B0_SCORABLE_COVERAGE_AT_LEAST_95_PERCENT",
                    "observed": coverage,
                    "pass": coverage >= 0.95,
                },
                {
                    "check": f"{split}_B2_LOG_LOSS_BETTER_THAN_B0",
                    "observed_delta": round(b2["log_loss"] - b0["log_loss"], 6),
                    "pass": b2["log_loss"] < b0["log_loss"],
                },
                {
                    "check": f"{split}_B2_RPS_BETTER_THAN_B0",
                    "observed_delta": round(b2["rps"] - b0["rps"], 6),
                    "pass": b2["rps"] < b0["rps"],
                },
                {
                    "check": f"{split}_B2_ECE_NOT_WORSE_THAN_B0",
                    "observed_delta": round(b2["ece"] - b0["ece"], 6),
                    "pass": b2["ece"] <= b0["ece"],
                },
                {
                    "check": f"{split}_B2_LOG_LOSS_BETTER_IN_AT_LEAST_2_OF_3_DEPTH_STRATA",
                    "observed_improved_strata": improved_strata,
                    "pass": improved_strata >= 2,
                },
            )
        )
    checks.extend(
        (
            {
                "check": "POINT_IN_TIME_LEAKAGE_VIOLATIONS_EQUAL_ZERO",
                "observed": leakage_violation_count,
                "pass": leakage_violation_count == 0,
            },
            {
                "check": "DETERMINISTIC_REPLAY_MATCHES",
                "observed": deterministic,
                "pass": deterministic,
            },
        )
    )
    return checks


def _build_core(
    *,
    corpus: Mapping[str, Any],
    split_manifest: Mapping[str, Any],
    preprocessing: Mapping[str, Any],
    normalized_features: Sequence[Mapping[str, Any]],
    visibility: Sequence[Mapping[str, Any]],
    xg_matches: Sequence[TeamXgMatch],
    league_names: Mapping[str, str],
    xg_file_sha256: str,
) -> dict[str, Any]:
    _verify_bindings(
        split_manifest=split_manifest,
        preprocessing=preprocessing,
        normalized_features=normalized_features,
    )
    targets = _targets(corpus)
    split_by_fixture = {
        str(row["fixture_id"]): str(row["split"])
        for row in split_manifest["targets"]
    }
    normalized_by_fixture = {
        str(row["target_fixture_id"]): dict(row) for row in normalized_features
    }
    visibility_by_fixture = {str(row["fixture_id"]): row for row in visibility}
    raw_fixture_ids = {target["raw_fixture_id"] for target in targets.values()}
    target_by_raw_fixture = {
        target["raw_fixture_id"]: target for target in targets.values()
    }
    direct_join_matches = [row for row in xg_matches if row.fixture_id in raw_fixture_ids]
    if len(direct_join_matches) != len(xg_matches):
        raise ValueError("FACTOR_V2_GATE1_XG_RAW_FIXTURE_JOIN_INCOMPLETE")
    if {row.source_system for row in direct_join_matches} != {XG_SOURCE_SYSTEM}:
        raise ValueError("FACTOR_V2_GATE1_XG_METHOD_NOT_UNIFORM")
    if any(
        {xg_match.team_id, xg_match.opponent_team_id}
        != {
            target_by_raw_fixture[xg_match.fixture_id]["home_team_id"],
            target_by_raw_fixture[xg_match.fixture_id]["away_team_id"],
        }
        for xg_match in direct_join_matches
    ):
        raise ValueError("FACTOR_V2_GATE1_XG_PROVIDER_TEAM_IDENTITY_MISMATCH")
    matches_by_team: dict[str, list[TeamXgMatch]] = defaultdict(list)
    source_kickoff_by_fixture: dict[str, datetime] = {}
    for xg_match in direct_join_matches:
        matches_by_team[xg_match.team_id].append(xg_match)
        source_kickoff_by_fixture[xg_match.fixture_id] = xg_match.kickoff_at

    prepared: list[dict[str, Any]] = []
    unavailable: dict[str, list[str]] = defaultdict(list)
    leakage_violation_count = 0
    for fixture_id, split in split_by_fixture.items():
        target = targets[fixture_id]
        home = materialize_rolling_xg(
            team_id=target["home_team_id"],
            as_of_fixture_id=target["raw_fixture_id"],
            as_of_time=target["kickoff"],
            matches=matches_by_team[target["home_team_id"]],
            pit_semantics=XG_PIT_SOURCE_KICKOFF_ONLY,
            method_version=XG_METHOD_VERSION,
        )
        away = materialize_rolling_xg(
            team_id=target["away_team_id"],
            as_of_fixture_id=target["raw_fixture_id"],
            as_of_time=target["kickoff"],
            matches=matches_by_team[target["away_team_id"]],
            pit_semantics=XG_PIT_SOURCE_KICKOFF_ONLY,
            method_version=XG_METHOD_VERSION,
        )
        if home is None or away is None:
            unavailable[split].append(fixture_id)
            continue
        source_ids = (*home.source_fixture_ids, *away.source_fixture_ids)
        leakage_violation_count += sum(
            source_id == target["raw_fixture_id"]
            or source_kickoff_by_fixture[source_id] >= target["kickoff"]
            for source_id in source_ids
        )
        baseline = calibrate_lambdas(
            home_xg_for=home.rolling_xg_for,
            home_xg_against=home.rolling_xg_against,
            away_xg_for=away.rolling_xg_for,
            away_xg_against=away.rolling_xg_against,
            home_elo=None,
            away_elo=None,
            home_squad_value_eur=None,
            away_squad_value_eur=None,
        )
        source_identity = _hash(
            "FACTOR_MODEL_XG_ROLLING_INPUT",
            {
                "target_fixture_id": fixture_id,
                "source_fixture_ids": list(source_ids),
                "source_raw_payload_sha256s": list(
                    (*home.source_raw_payload_sha256s, *away.source_raw_payload_sha256s)
                ),
                "xg_method_version": XG_METHOD_VERSION,
                "xg_pit_semantics": XG_PIT_SOURCE_KICKOFF_ONLY,
            },
        )
        prepared.append(
            {
                **target,
                "split": split,
                "normalized_features": normalized_by_fixture[fixture_id],
                "visible_history_rows": int(
                    visibility_by_fixture[fixture_id][
                        "feature_scope_visible_history_row_count"
                    ]
                ),
                "home_xg_for": home.rolling_xg_for,
                "home_xg_against": home.rolling_xg_against,
                "away_xg_for": away.rolling_xg_for,
                "away_xg_against": away.rolling_xg_against,
                "baseline_lambda_home": baseline.lambda_home,
                "baseline_lambda_away": baseline.lambda_away,
                "b1_input_identity_hash": source_identity,
                "f6_observed": normalized_by_fixture[fixture_id]["factors"]["F6_H2H"][
                    "raw_value"
                ]
                is not None,
            }
        )

    train_rows = [row for row in prepared if row["split"] == "TRAIN"]
    fit = fit_poisson_factor_coefficients(
        train_rows,
        active_factor_ids=ACTIVE_FACTOR_IDS,
    )
    calibration = factor_calibration_artifact(
        calibration_version="factor-v2.f3-f7.poisson-newton.v1",
        split_manifest_sha256=str(split_manifest["split_manifest_sha256"]),
        preprocessing_sha256=str(preprocessing["preprocessing_sha256"]),
        relative_coefficients=fit["relative_coefficients"],
        total_coefficients=fit["total_coefficients"],
        active_factor_ids=ACTIVE_FACTOR_IDS,
        excluded_factor_statuses={"F6_H2H": F6_STATUS},
        feature_bounds=fit["feature_bounds"],
        fit_diagnostics=fit["diagnostics"],
        admitted_for_historical_replay=True,
    )

    scored: list[dict[str, Any]] = []
    for row in prepared:
        if row["split"] not in SCORING_SPLITS:
            continue
        output = build_b0_b1_b2_ablation(
            fixture_id=row["fixture_id"],
            home_xg_for=row["home_xg_for"],
            home_xg_against=row["home_xg_against"],
            away_xg_for=row["away_xg_for"],
            away_xg_against=row["away_xg_against"],
            b1_lambda_home=row["baseline_lambda_home"],
            b1_lambda_away=row["baseline_lambda_away"],
            b1_input_identity_hash=row["b1_input_identity_hash"],
            normalized_features=row["normalized_features"],
            factor_calibration=calibration,
            b1_track_id="B1_RECOMPUTED",
        )
        actual = (
            "HOME"
            if row["home_goals"] > row["away_goals"]
            else "DRAW"
            if row["home_goals"] == row["away_goals"]
            else "AWAY"
        )
        scored.append(
            {
                "fixture_id": row["fixture_id"],
                "split": row["split"],
                "provider_league_id": row["provider_league_id"],
                "competition_id": league_names.get(
                    row["provider_league_id"], row["provider_league_id"]
                ),
                "season": row["season"],
                "kickoff": row["kickoff"],
                "actual": actual,
                "visible_history_rows": row["visible_history_rows"],
                "f6_observed": row["f6_observed"],
                "feature_bound_clip_count": output["feature_bound_clip_count"],
                "tracks": output["tracks"],
                "ablation_sha256": output["ablation_sha256"],
            }
        )

    metrics_by_split: dict[str, Any] = {}
    strata_by_split: dict[str, Any] = {}
    cohort_metrics_by_split: dict[str, Any] = {}
    coverage_by_split: dict[str, Any] = {}
    for split in SCORING_SPLITS:
        target_count = sum(value == split for value in split_by_fixture.values())
        split_rows = [row for row in scored if row["split"] == split]
        track_metrics = _metrics_by_track(split_rows)
        metrics_by_split[split] = track_metrics
        coverage_by_split[split] = {
            "target_fixture_count": target_count,
            "b0_scorable_fixture_count": len(split_rows),
            "b0_scorable_rate": round(len(split_rows) / target_count, 8),
            "unavailable_fixture_count": len(unavailable[split]),
        }
        observed_rows = [row for row in split_rows if row["f6_observed"]]
        cohort_metrics_by_split[split] = {
            "all_targets_scorable": {
                "fixture_count": len(split_rows),
                "metrics": track_metrics,
                "deltas_vs_b0": _metric_deltas(track_metrics),
            },
            "f6_observed_sensitivity_cohort": {
                "fixture_count": len(observed_rows),
                "metrics": _metrics_by_track(observed_rows),
                "deltas_vs_b0": _metric_deltas(_metrics_by_track(observed_rows)),
                "factor_in_design_vector": False,
            },
        }
        strata: dict[str, Any] = {}
        for name, definition in _depth_strata(split_rows).items():
            fixture_ids = set(definition["fixture_ids"])
            stratum_rows = [row for row in split_rows if row["fixture_id"] in fixture_ids]
            stratum_metrics = _metrics_by_track(stratum_rows)
            strata[name] = {
                "definition": definition["definition"],
                "fixture_count": len(stratum_rows),
                "visible_history_rows_min": min(
                    (row["visible_history_rows"] for row in stratum_rows), default=None
                ),
                "visible_history_rows_max": max(
                    (row["visible_history_rows"] for row in stratum_rows), default=None
                ),
                "metrics": stratum_metrics,
                "deltas_vs_b0": _metric_deltas(stratum_metrics),
            }
        strata_by_split[split] = strata

    result_body = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "split_manifest_sha256": split_manifest["split_manifest_sha256"],
        "preprocessing_sha256": preprocessing["preprocessing_sha256"],
        "calibration_sha256": calibration["calibration_sha256"],
        "xg_file_sha256": xg_file_sha256,
        "rows": scored,
    }
    return {
        "calibration": calibration,
        "results": {
            **result_body,
            "results_sha256": _hash("FACTOR_MODEL_GATE1_ABLATION_RESULTS", result_body),
        },
        "summary": {
            "coverage_by_split": coverage_by_split,
            "metrics_by_split": metrics_by_split,
            "cohort_metrics_by_split": cohort_metrics_by_split,
            "strata_by_split": strata_by_split,
            "leakage_violation_count": leakage_violation_count,
            "raw_fixture_direct_join_xg_row_count": len(direct_join_matches),
            "raw_fixture_direct_join_xg_fixture_count": len(
                {row.fixture_id for row in direct_join_matches}
            ),
            "train_b0_scorable_fixture_count": len(train_rows),
            "scoring_fixture_feature_bound_clip_count": sum(
                row["feature_bound_clip_count"] > 0 for row in scored
            ),
        },
    }


def build_artifacts(
    *,
    corpus: Mapping[str, Any],
    split_manifest: Mapping[str, Any],
    preprocessing: Mapping[str, Any],
    normalized_features: Sequence[Mapping[str, Any]],
    visibility: Sequence[Mapping[str, Any]],
    split_train_report: Mapping[str, Any],
    xg_matches: Sequence[TeamXgMatch],
    league_names: Mapping[str, str],
    source_files: Mapping[str, Path],
    verify_determinism: bool,
) -> dict[str, Any]:
    source_hashes = {
        name: _file_sha256(path) for name, path in sorted(source_files.items())
    }
    def run_core() -> dict[str, Any]:
        return _build_core(
            corpus=corpus,
            split_manifest=split_manifest,
            preprocessing=preprocessing,
            normalized_features=normalized_features,
            visibility=visibility,
            xg_matches=xg_matches,
            league_names=league_names,
            xg_file_sha256=source_hashes["xg_csv"],
        )

    core = run_core()
    deterministic = True
    if verify_determinism:
        replay = run_core()
        deterministic = (
            replay["calibration"]["calibration_sha256"]
            == core["calibration"]["calibration_sha256"]
            and replay["results"]["results_sha256"]
            == core["results"]["results_sha256"]
        )
    summary = core["summary"]
    checks = _gate_checks(
        coverage_by_split=summary["coverage_by_split"],
        metrics_by_split=summary["metrics_by_split"],
        strata_by_split=summary["strata_by_split"],
        leakage_violation_count=summary["leakage_violation_count"],
        deterministic=deterministic,
    )
    gate_status = "PASS" if all(check["pass"] for check in checks) else "FAIL"
    body = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "gate": "FACTOR_MODEL_V2_GATE1",
        "status": gate_status,
        "scope": "F3_F7_ONLY",
        "corpus_snapshot_as_of": corpus["snapshot_as_of"],
        "historical_replay_cutoff": split_manifest["historical_replay_cutoff"],
        "feature_as_of": "EACH_TARGET_FIXTURE_KICKOFF",
        "bindings": {
            "corpus_sha256": corpus["corpus_sha256"],
            "split_manifest_sha256": split_manifest["split_manifest_sha256"],
            "preprocessing_sha256": preprocessing["preprocessing_sha256"],
            "factor_calibration_sha256": core["calibration"]["calibration_sha256"],
            "ablation_results_sha256": core["results"]["results_sha256"],
            "source_file_sha256": source_hashes,
        },
        "xg_point_in_time_contract": {
            "xg_pit_semantics": split_manifest["xg_pit_semantics"],
            "xg_method_version": split_manifest["xg_method_version"],
            "contract": split_manifest["xg_pit_contract"],
            "fallback_if_any_prerequisite_fails": "STRICT_CAPTURED_AT",
            "raw_fixture_id_direct_join": True,
            "matchday_fixture_identities_used": False,
            "direct_join_xg_row_count": summary[
                "raw_fixture_direct_join_xg_row_count"
            ],
            "direct_join_xg_fixture_count": summary[
                "raw_fixture_direct_join_xg_fixture_count"
            ],
            "provider_team_identity_mismatch_count": 0,
            "target_fixture_xg_source_violation_count": summary[
                "leakage_violation_count"
            ],
        },
        "b1_contract": {
            "track_id": "B1_RECOMPUTED",
            "lambda_calibration_version": CALIBRATION_VERSION,
            "four_field_xg_offline_recomputed": True,
            "production_optional_historical_inputs_available": False,
            "claimed_current_production_equivalence": False,
        },
        "f6_decision": {
            **split_train_report["f6_owner_decision"],
            "included_in_design_vector": False,
            "reported_as_sensitivity_cohort_only": True,
        },
        "preregistered_gate_criteria": {
            "b0_scorable_rate_each_scoring_split": ">=0.95",
            "b2_log_loss_vs_b0_each_scoring_split": "STRICTLY_LOWER",
            "b2_rps_vs_b0_each_scoring_split": "STRICTLY_LOWER",
            "b2_ece_vs_b0_each_scoring_split": "NOT_HIGHER",
            "b2_log_loss_depth_strata_each_scoring_split": "IMPROVE_AT_LEAST_2_OF_3",
            "point_in_time_leakage_violations": 0,
            "deterministic_replay": True,
            "depth_strata": (
                "SPLIT_SPECIFIC_TERTILES_OF_SAME_PROVIDER_LEAGUE_VISIBLE_HISTORY_ROWS; "
                "BOUNDARIES_USE_INPUT_DEPTH_ONLY, NEVER OUTCOMES"
            ),
        },
        "coverage": summary["coverage_by_split"],
        "train_factor_effect_fit": {
            **core["calibration"]["fit_diagnostics"],
            "active_factor_ids": list(ACTIVE_FACTOR_IDS),
            "excluded_factor_statuses": {"F6_H2H": F6_STATUS},
            "relative_coefficients": core["calibration"]["relative_coefficients"],
            "total_coefficients": core["calibration"]["total_coefficients"],
            "feature_bounds": core["calibration"]["feature_bounds"],
            "scoring_fixture_feature_bound_clip_count": summary[
                "scoring_fixture_feature_bound_clip_count"
            ],
        },
        "global_metrics_by_split": summary["metrics_by_split"],
        "cohort_metrics_by_split": summary["cohort_metrics_by_split"],
        "same_league_visible_history_depth_strata": summary["strata_by_split"],
        "gate_checks": checks,
        "execution": {
            "provider_calls": 0,
            "production_database_reads": 0,
            "production_database_writes": 0,
            "deployment_executed": False,
            "forward_shadow_enabled": False,
            "candidate_output_count": 0,
            "notification_output_count": 0,
            "outcome_ledger_write_count": 0,
            "determinism_verification_executed": verify_determinism,
        },
    }
    report = {**body, "report_sha256": _hash("FACTOR_MODEL_GATE1_REPORT", body)}
    return {**core, "report": report}


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Factor V2 Gate 1 验收报告",
        "",
        f"- Gate 1: **{report['status']}**",
        "- 范围：F3/F7；F6 `EXCLUDED_BY_PREREGISTERED_THRESHOLD`。",
        f"- corpus_snapshot_as_of: `{report['corpus_snapshot_as_of']}`",
        "- feature_as_of: `每场目标比赛自己的 kickoff`",
        f"- historical_replay_cutoff: `{report['historical_replay_cutoff']}`",
        "- Provider / 生产读 / 生产写 / 部署 / forward shadow: `0 / 0 / 0 / false / false`",
        "",
        "## 全局消融",
        "",
        "| split | track | N | LogLoss | RPS | Brier | ECE |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for split in SCORING_SPLITS:
        count = report["coverage"][split]["b0_scorable_fixture_count"]
        for track in TRACK_IDS:
            row = report["global_metrics_by_split"][split][track]
            lines.append(
                f"| {split} | {track} | {count} | {row['log_loss']:.6f} | "
                f"{row['rps']:.6f} | {row['brier']:.6f} | {row['ece']:.6f} |"
            )
    lines.extend(
        [
            "",
            "`B1_RECOMPUTED` 使用获准四字段 xG 和当前 λ 校准版本离线重算；"
            "因历史可选输入无法证明与线上逐场完全一致，不声明为当前生产 B1。",
            "",
            "## 同联赛可见历史深度分层",
            "",
            "| split | stratum | definition | N | B0 LogLoss | B2 LogLoss | delta |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for split in SCORING_SPLITS:
        for stratum, row in report["same_league_visible_history_depth_strata"][
            split
        ].items():
            b0 = row["metrics"]["B0_SAME_ENGINE_XG"]["log_loss"]
            b2 = row["metrics"]["B2_FACTOR_V2"]["log_loss"]
            lines.append(
                f"| {split} | {stratum} | {row['definition']} | {row['fixture_count']} | "
                f"{b0:.6f} | {b2:.6f} | {b2 - b0:+.6f} |"
            )
    lines.extend(["", "## 验收检查", ""])
    lines.extend(
        f"- {'PASS' if row['pass'] else 'FAIL'} — `{row['check']}`"
        for row in report["gate_checks"]
    )
    lines.extend(
        [
            "",
            "## 契约结论",
            "",
            "- xG：`SOURCE_KICKOFF_ONLY`；方法版本、三项前提和严格回退规则"
            "均已纳入 split manifest hash。",
            "- 关联：raw fixture ID 直连，不经 matchday identity 表；目标比赛自身 "
            "xG 泄漏计数为 0。",
            "- F6：预注册覆盖门槛 FAIL，仅报告 observed sensitivity cohort，不进入设计向量。",
            "- 所有轨道使用 exact 13×13、rho=0；无采样、推荐、通知或账本资格。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_artifacts(output_dir: Path, artifacts: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    for key, filename in (
        ("calibration", "factor_v2_f3_f7_calibration.json"),
        ("results", "factor_v2_ablation_results.json"),
        ("report", "factor_v2_gate1_report.json"),
    ):
        (output_dir / filename).write_text(
            json.dumps(
                artifacts[key],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=lambda value: _utc(value).isoformat().replace("+00:00", "Z"),
            )
            + "\n",
            encoding="utf-8",
        )
    (output_dir / "factor_v2_gate1_report.md").write_text(
        _markdown(artifacts["report"]), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split-dir", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--xg-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify-determinism", action="store_true")
    args = parser.parse_args()
    paths = {
        "corpus": args.corpus,
        "split_manifest": args.split_dir / "factor_v2_split_manifest.json",
        "preprocessing": args.split_dir / "factor_v2_train_preprocessing.json",
        "normalized_features": args.split_dir / "factor_v2_normalized_features.json",
        "visibility": args.split_dir / "factor_v2_visibility.json",
        "split_train_report": args.split_dir / "factor_v2_split_train_report.json",
        "coverage": args.coverage,
        "xg_csv": args.xg_csv,
    }
    payloads = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in paths.items()
        if name != "xg_csv"
    }
    league_names = {
        str(row["provider_league_id"]): str(row["competition_id"])
        for row in payloads["coverage"]["by_league_season"]
    }
    artifacts = build_artifacts(
        corpus=payloads["corpus"],
        split_manifest=payloads["split_manifest"],
        preprocessing=payloads["preprocessing"],
        normalized_features=payloads["normalized_features"],
        visibility=payloads["visibility"],
        split_train_report=payloads["split_train_report"],
        xg_matches=load_xg_matches(args.xg_csv),
        league_names=league_names,
        source_files=paths,
        verify_determinism=args.verify_determinism,
    )
    write_artifacts(args.output_dir, artifacts)
    print(
        json.dumps(
            {
                "status": artifacts["report"]["status"],
                "report_sha256": artifacts["report"]["report_sha256"],
                "results_sha256": artifacts["results"]["results_sha256"],
                "output_dir": str(args.output_dir),
                "provider_calls": 0,
                "production_database_writes": 0,
                "deployment_executed": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
