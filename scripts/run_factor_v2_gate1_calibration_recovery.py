#!/usr/bin/env python3
"""Freeze a TRAIN-only Factor V2 calibration-recovery candidate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from math import exp, isfinite, log, sqrt
from pathlib import Path
from typing import Any

from w2.backtest.factor_v2_ablation import fit_poisson_factor_coefficients
from w2.domain.canonical_serialization import HashDomain, canonical_bytes, canonical_sha256
from w2.factor_model.ablation_scoring import design_vector
from w2.features.xg_materialization import (
    XG_METHOD_VERSION,
    XG_PIT_SOURCE_KICKOFF_ONLY,
    TeamXgMatch,
    materialize_rolling_xg,
)
from w2.models.dixon_coles import one_x_two_from_matrix
from w2.strategy.calibration import calibrate_lambdas
from w2.strategy.simulate import exact_score_matrix_from_lambdas

ACTIVE_FACTORS = ("F3_REST_FITNESS", "F7_STRENGTH_FORM")
EXPECTED_SPLIT_HASH = "01a4f593efc3814cf31b6d4a677320513cdc996baf006d59c4c4d029fda243ce"
EXPECTED_PROTOCOL_HASH = "4f01820d83536bcf2b024478b6f8259623fb108bf3e345898b41e83d491da10b"
EXPECTED_CURRENT_XG_HASH = "84ef81e90377014cb9ea9abc93276aebed65e1c63b9d4e5dfa18d47443634909"
EXPECTED_FILE_HASHES = {
    "history": "80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2",
    "split": "72cf04f3303f788c9fe5b66cb8e90f5bc9d77a28cc02318f17b14654eb458406",
    "preprocessing": "ac8eee965a35973ea13a30e62c194031281e2a27dc1ba0d129d4fd46f0e35269",
    "normalized": "ac8cb1708a1355a621cf6cfb7823421985a63c38e96a6624d0583745961d9bdf",
    "visibility": "5dc6c4ca00110fb692f1f3488a67a1887099f6e18e0b85108e09e6cc6e67fc7c",
    "coverage": "0404bb1a6b402e692a87e35f563d43e934230b952846b2d706d4be46f161e705",
    "old_xg": "09d921ffb7b39a88dd67ad5043d0102941b7357effb54487a700c83dc2399d9b",
    "protocol": EXPECTED_PROTOCOL_HASH,
    "current_xg": EXPECTED_CURRENT_XG_HASH,
}
BASE_COMMIT = "cb8f5d22ded2857d09dfcabda3a159bee165bb5f"
SCHEMA = "w2.factor_v2.gate1_calibration_recovery.v1"
ROOT = Path("/Users/liudehua/.hermes/worktrees/w2-model-forecast-validation-ledger")
HISTORY_DIR = ROOT / "reports/factor_model_v2/gate1_history_backfill_20260822T055041929427Z"
DEFAULTS = {
    "history": HISTORY_DIR / "factor_history_corpus.json",
    "coverage": HISTORY_DIR / "factor_history_coverage.json",
    "split_dir": ROOT
    / "reports/factor_model_v2/gate1_split_train_xg_pit_v4_20260822T055041929427Z",
    "old_xg": ROOT / "tmp/factor_model_v2/team_xg_match_readonly_20260822T0622Z.csv",
    "current_xg": Path("/Users/liudehua/.hermes/data/ev_se_drift_v2/team_xg_match.csv"),
    "protocol": Path(__file__).resolve().parents[1]
    / "docs/review_packages/V2_GATE1_CALIBRATION_RECOVERY_01/PROTOCOL_FROZEN_20260827.md",
}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(kind: str, payload: Any) -> str:
    return canonical_sha256(
        {"identity_type": kind, "payload": payload},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _dump(payload: Any) -> bytes:
    return canonical_bytes(
        payload,
        domain=HashDomain.PREMATCH_READ_MODEL_ARTIFACT,
    ) + b"\n"


def _load_old_xg(path: Path) -> dict[tuple[str, str], TeamXgMatch]:
    output: dict[tuple[str, str], TeamXgMatch] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            item = TeamXgMatch(
                fixture_id=row["fixture_id"],
                team_id=row["team_id"],
                opponent_team_id=row["opponent_team_id"],
                kickoff_at=_utc(row["kickoff_at"]),
                captured_at=_utc(row["captured_at"]),
                xg_for=float(row["xg_for"]),
                xg_against=float(row["xg_against"]),
                goals_for=int(row["goals_for"]),
                goals_against=int(row["goals_against"]),
                raw_payload_sha256=row["raw_payload_sha256"],
                source_system=row["source_system"],
            )
            output[(item.fixture_id, item.team_id)] = item
    return output


def _load_current_xg(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "BEGIN" or lines[-1] != "ROLLBACK":
        raise ValueError("RECOVERY_CURRENT_XG_TRANSACTION_SENTINELS_INVALID")
    names = (
        "fixture_id",
        "team_id",
        "kickoff_at",
        "captured_at",
        "xg_for",
        "xg_against",
        "source_system",
    )
    rows = []
    for line in lines[1:-1]:
        values = next(csv.reader([line]))
        if len(values) != len(names):
            raise ValueError("RECOVERY_CURRENT_XG_ROW_INVALID")
        rows.append(dict(zip(names, values, strict=True)))
    return rows


def _history_indexes(
    history: Mapping[str, Any],
) -> tuple[dict[tuple[str, str], Mapping[str, Any]], dict[str, dict[str, Mapping[str, Any]]]]:
    by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    by_fixture: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in history["history_rows"]:
        by_key[(str(row["provider_fixture_id"]), str(row["team_id"]))] = row
        by_fixture[str(row["fixture_id"])][str(row["team_side"])] = row
    return by_key, by_fixture


def _canonical_row(item: TeamXgMatch, reconstruction: str) -> dict[str, Any]:
    return {
        "fixture_id": item.fixture_id,
        "team_id": item.team_id,
        "opponent_team_id": item.opponent_team_id,
        "kickoff_at": item.kickoff_at.isoformat().replace("+00:00", "Z"),
        "captured_at": item.captured_at.isoformat().replace("+00:00", "Z"),
        "xg_for": item.xg_for,
        "xg_against": item.xg_against,
        "goals_for": item.goals_for,
        "goals_against": item.goals_against,
        "raw_payload_sha256": item.raw_payload_sha256,
        "source_system": item.source_system,
        "reconstruction": reconstruction,
    }


def reconstruct_current_corpus(
    current: Sequence[Mapping[str, str]],
    old: Mapping[tuple[str, str], TeamXgMatch],
    history_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[list[TeamXgMatch], dict[str, Any]]:
    admitted: list[TeamXgMatch] = []
    canonical_rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    methods: Counter[str] = Counter()
    for row in current:
        key = (str(row["fixture_id"]), str(row["team_id"]))
        previous = old.get(key)
        history = history_by_key.get(key)
        if previous is not None:
            if (
                previous.kickoff_at != _utc(row["kickoff_at"])
                or previous.xg_for != float(row["xg_for"])
                or previous.xg_against != float(row["xg_against"])
                or previous.source_system != row["source_system"]
            ):
                raise ValueError("RECOVERY_OLD_XG_EXACT_MATCH_CONFLICT")
            item = TeamXgMatch(**{**previous.__dict__, "captured_at": _utc(row["captured_at"])})
            method = "OLD_FULL_XG_EXACT_KEY"
        elif history is not None:
            item = TeamXgMatch(
                fixture_id=row["fixture_id"],
                team_id=row["team_id"],
                opponent_team_id=str(history["opponent_team_id"]),
                kickoff_at=_utc(row["kickoff_at"]),
                captured_at=_utc(row["captured_at"]),
                xg_for=float(row["xg_for"]),
                xg_against=float(row["xg_against"]),
                goals_for=int(history["goals_for"]),
                goals_against=int(history["goals_against"]),
                raw_payload_sha256=str(history["raw_payload_sha256"]),
                source_system=row["source_system"],
            )
            method = "FROZEN_HISTORY_EXACT_FIXTURE_TEAM"
        else:
            excluded.append(
                {
                    **dict(row),
                    "reason": "MISSING_OPPONENT_GOALS_RAW_HASH_EXACT_JOIN",
                    "inferred_fields": [],
                }
            )
            continue
        methods[method] += 1
        admitted.append(item)
        canonical_rows.append(_canonical_row(item, method))
    canonical_rows.sort(key=lambda row: (row["kickoff_at"], row["fixture_id"], row["team_id"]))
    excluded.sort(key=lambda row: (row["kickoff_at"], row["fixture_id"], row["team_id"]))
    evidence = {
        "schema_version": f"{SCHEMA}.current_xg_corpus",
        "source_row_count": len(current),
        "source_fixture_count": len({row["fixture_id"] for row in current}),
        "admitted_row_count": len(admitted),
        "admitted_fixture_count": len({row.fixture_id for row in admitted}),
        "excluded_row_count": len(excluded),
        "excluded_fixture_count": len({row["fixture_id"] for row in excluded}),
        "reconstruction_counts": dict(sorted(methods.items())),
        "excluded_kickoff_min": min(row["kickoff_at"] for row in excluded),
        "excluded_kickoff_max": max(row["kickoff_at"] for row in excluded),
        "excluded_before_train_end_count": sum(
            row["kickoff_at"] < "2025-01-01" for row in excluded
        ),
        "rows": canonical_rows,
        "exclusions": excluded,
    }
    evidence["corpus_sha256"] = _hash("RECOVERY_CURRENT_XG_CORPUS", evidence)
    return admitted, evidence


def _targets(
    history_by_fixture: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    output = {}
    for fixture_id, sides in history_by_fixture.items():
        if set(sides) != {"HOME", "AWAY"}:
            continue
        home, away = sides["HOME"], sides["AWAY"]
        output[fixture_id] = {
            "fixture_id": fixture_id,
            "raw_fixture_id": str(home["provider_fixture_id"]),
            "kickoff": _utc(str(home["kickoff_utc"])),
            "home_team_id": str(home["team_id"]),
            "away_team_id": str(away["team_id"]),
            "home_goals": int(home["goals_for"]),
            "away_goals": int(away["goals_for"]),
        }
    return output


def prepare_train(
    *,
    split: Mapping[str, Any],
    normalized: Sequence[Mapping[str, Any]],
    targets: Mapping[str, Mapping[str, Any]],
    xg_matches: Sequence[TeamXgMatch],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train_members = [row for row in split["targets"] if row["split"] == "TRAIN"]
    normalized_by_id = {str(row["target_fixture_id"]): row for row in normalized}
    by_team: dict[str, list[TeamXgMatch]] = defaultdict(list)
    for item in xg_matches:
        by_team[item.team_id].append(item)
    prepared, ledger = [], []
    for member in train_members:
        fixture_id = str(member["fixture_id"])
        target = targets[fixture_id]
        home = materialize_rolling_xg(
            team_id=target["home_team_id"],
            as_of_fixture_id=target["raw_fixture_id"],
            as_of_time=target["kickoff"],
            matches=by_team[target["home_team_id"]],
            pit_semantics=XG_PIT_SOURCE_KICKOFF_ONLY,
            method_version=XG_METHOD_VERSION,
        )
        away = materialize_rolling_xg(
            team_id=target["away_team_id"],
            as_of_fixture_id=target["raw_fixture_id"],
            as_of_time=target["kickoff"],
            matches=by_team[target["away_team_id"]],
            pit_semantics=XG_PIT_SOURCE_KICKOFF_ONLY,
            method_version=XG_METHOD_VERSION,
        )
        if home is None or away is None:
            ledger.append(
                {
                    "fixture_id": fixture_id,
                    "kickoff": member["kickoff"],
                    "status": "EXCLUDED",
                    "reason": "ROLLING_XG_UNAVAILABLE",
                }
            )
            continue
        ledger.append(
            {
                "fixture_id": fixture_id,
                "kickoff": member["kickoff"],
                "status": "SCORABLE",
                "reason": None,
            }
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
        prepared.append(
            {
                **target,
                "kickoff_text": str(member["kickoff"]),
                "normalized_features": dict(normalized_by_id[fixture_id]),
                "baseline_lambda_home": baseline.lambda_home,
                "baseline_lambda_away": baseline.lambda_away,
            }
        )
    if len(ledger) != 3118:
        raise ValueError("RECOVERY_TRAIN_DENOMINATOR_MISMATCH")
    return prepared, ledger


def _lambdas(row: Mapping[str, Any], fit: Mapping[str, Any]) -> tuple[float, float]:
    vector = design_vector(dict(row["normalized_features"]), active_factor_ids=ACTIVE_FACTORS)
    vector = {
        name: min(
            max(value, float(fit["feature_bounds"][name]["minimum"])),
            float(fit["feature_bounds"][name]["maximum"]),
        )
        for name, value in vector.items()
    }
    relative = sum(
        float(fit["relative_coefficients"][name]) * value for name, value in vector.items()
    )
    total = sum(float(fit["total_coefficients"][name]) * value for name, value in vector.items())
    return (
        float(row["baseline_lambda_home"]) * exp((total + relative) / 2),
        float(row["baseline_lambda_away"]) * exp((total - relative) / 2),
    )


def _temperature_matrix(
    matrix: Mapping[tuple[int, int], float], temperature: float
) -> dict[tuple[int, int], float]:
    powered = {key: value ** (1.0 / temperature) for key, value in matrix.items()}
    total = sum(powered.values())
    result = {key: value / total for key, value in powered.items()}
    if (
        len(result) != 169
        or not all(isfinite(value) and value >= 0 for value in result.values())
        or abs(sum(result.values()) - 1) > 1e-9
    ):
        raise ValueError("RECOVERY_TEMPERATURE_MATRIX_INVALID")
    return result


def _actual(row: Mapping[str, Any]) -> str:
    return (
        "HOME"
        if row["home_goals"] > row["away_goals"]
        else "DRAW"
        if row["home_goals"] == row["away_goals"]
        else "AWAY"
    )


def _nll(
    predictions: Sequence[tuple[Mapping[tuple[int, int], float], str]], temperature: float
) -> float:
    return sum(
        -log(max(one_x_two_from_matrix(_temperature_matrix(matrix, temperature))[actual], 1e-15))
        for matrix, actual in predictions
    ) / len(predictions)


def _ece(
    predictions: Sequence[tuple[Mapping[tuple[int, int], float], str]],
    temperature: float,
    bins: int,
) -> float:
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for matrix, actual in predictions:
        probabilities = one_x_two_from_matrix(_temperature_matrix(matrix, temperature))
        predicted, confidence = max(probabilities.items(), key=lambda item: item[1])
        buckets[min(int(confidence * bins), bins - 1)].append((confidence, predicted == actual))
    return sum(
        len(bucket)
        / len(predictions)
        * abs(
            sum(confidence for confidence, _ in bucket) / len(bucket)
            - sum(correct for _, correct in bucket) / len(bucket)
        )
        for bucket in buckets
        if bucket
    )


def _bounded_temperature(
    predictions: Sequence[tuple[Mapping[tuple[int, int], float], str]],
) -> tuple[float, dict[str, Any]]:
    if not predictions:
        raise ValueError("RECOVERY_TEMPERATURE_INPUT_EMPTY")
    low, high = 0.5, 2.0
    ratio = (sqrt(5) - 1) / 2
    left, right = high - ratio * (high - low), low + ratio * (high - low)
    left_value, right_value = _nll(predictions, left), _nll(predictions, right)
    iterations = 0
    while high - low > 1e-6:
        iterations += 1
        if left_value <= right_value:
            high, right, right_value = right, left, left_value
            left = high - ratio * (high - low)
            left_value = _nll(predictions, left)
        else:
            low, left, left_value = left, right, right_value
            right = low + ratio * (high - low)
            right_value = _nll(predictions, right)
    temperature = round((low + high) / 2, 9)
    return temperature, {
        "optimizer": "GOLDEN_SECTION_STDLIB_V1",
        "bounds": [0.5, 2.0],
        "tolerance": 1e-6,
        "iterations": iterations,
        "oof_prediction_count": len(predictions),
        "oof_nll_t1": round(_nll(predictions, 1.0), 9),
        "oof_nll_selected": round(_nll(predictions, temperature), 9),
        "train_oof_ece_sensitivity": {
            str(bins): {
                "t1": round(_ece(predictions, 1.0, bins), 9),
                "selected": round(_ece(predictions, temperature, bins), 9),
            }
            for bins in (5, 10, 15)
        },
    }


def _fit_identity(
    fit: Mapping[str, Any], upstream: Mapping[str, str], label: str
) -> dict[str, Any]:
    body = {"schema_version": f"{SCHEMA}.model", "label": label, "upstream": dict(upstream), **fit}
    return {**body, "model_sha256": _hash("RECOVERY_FACTOR_MODEL", body)}


def build(
    paths: Mapping[str, Path],
    *,
    history_override: Mapping[str, Any] | None = None,
) -> dict[str, bytes]:
    actual = {name: _file_hash(path) for name, path in paths.items() if name != "split_dir"}
    for name, value in EXPECTED_FILE_HASHES.items():
        if actual[name] != value:
            raise ValueError(f"RECOVERY_{name.upper()}_HASH_MISMATCH")
    history = (
        dict(history_override)
        if history_override is not None
        else json.loads(paths["history"].read_text())
    )
    split = json.loads((paths["split_dir"] / "factor_v2_split_manifest.json").read_text())
    preprocessing = json.loads(
        (paths["split_dir"] / "factor_v2_train_preprocessing.json").read_text()
    )
    normalized = json.loads((paths["split_dir"] / "factor_v2_normalized_features.json").read_text())
    if (
        split.get("split_manifest_sha256") != EXPECTED_SPLIT_HASH
        or split.get("counts", {}).get("TRAIN") != 3118
    ):
        raise ValueError("RECOVERY_SPLIT_AUTHORITY_MISMATCH")
    old = _load_old_xg(paths["old_xg"])
    history_by_key, history_by_fixture = _history_indexes(history)
    current, corpus = reconstruct_current_corpus(
        _load_current_xg(paths["current_xg"]), old, history_by_key
    )
    targets = _targets(history_by_fixture)
    prepared, denominator = prepare_train(
        split=split, normalized=normalized, targets=targets, xg_matches=current
    )
    ordered_members = [row for row in split["targets"] if row["split"] == "TRAIN"]
    block_by_fixture = {
        str(row["fixture_id"]): min(index * 4 // len(ordered_members) + 1, 4)
        for index, row in enumerate(ordered_members)
    }
    split_body = {
        "schema_version": f"{SCHEMA}.split_identity",
        "protocol_sha256": actual["protocol"],
        "current_corpus_sha256": corpus["corpus_sha256"],
        "source_split_file_sha256": actual["split"],
        "semantic_membership_sha256": EXPECTED_SPLIT_HASH,
        "roles": {
            "TRAIN": {"count": 3118, "outcome_visibility": "DEVELOPMENT"},
            "VALIDATION": {"count": 4520, "outcome_visibility": "SEALED_OBSERVED_CONTAMINATED"},
            "HOLDOUT": {"count": 2628, "outcome_visibility": "SEALED_OBSERVED_CONTAMINATED"},
        },
    }
    split_identity = {
        **split_body,
        "recovery_split_sha256": _hash("RECOVERY_SPLIT_IDENTITY", split_body),
    }
    upstream = {
        "protocol_sha256": actual["protocol"],
        "current_xg_sha256": actual["current_xg"],
        "current_corpus_sha256": corpus["corpus_sha256"],
        "split_manifest_sha256": EXPECTED_SPLIT_HASH,
        "recovery_split_sha256": split_identity["recovery_split_sha256"],
        "base_commit": BASE_COMMIT,
    }
    denominator_body = {
        "schema_version": f"{SCHEMA}.denominator",
        "target_count": len(denominator),
        "scorable_count": len(prepared),
        "excluded_count": len(denominator) - len(prepared),
        "rows": denominator,
    }
    denominator_artifact = {
        **denominator_body,
        "denominator_sha256": _hash("RECOVERY_TRAIN_DENOMINATOR", denominator_body),
    }
    preprocessing_body = {
        "schema_version": f"{SCHEMA}.preprocessing_identity",
        "source_file_sha256": actual["preprocessing"],
        "source_semantic_sha256": preprocessing["preprocessing_sha256"],
        "upstream": upstream,
        "reason_unchanged": "ALL_CURRENT_XG_ADDITIONS_KICK_OFF_AFTER_TRAIN",
    }
    preprocessing_identity = {
        **preprocessing_body,
        "recovery_preprocessing_sha256": _hash("RECOVERY_PREPROCESSING", preprocessing_body),
    }
    feature_body = {
        "schema_version": f"{SCHEMA}.feature_identity",
        "source_file_sha256": actual["normalized"],
        "recovery_preprocessing_sha256": preprocessing_identity["recovery_preprocessing_sha256"],
        "train_target_count": 3118,
        "scorable_count": len(prepared),
    }
    feature_identity = {
        **feature_body,
        "recovery_feature_sha256": _hash("RECOVERY_FEATURES", feature_body),
    }
    model_upstream = {
        **upstream,
        "denominator_sha256": denominator_artifact["denominator_sha256"],
        "recovery_feature_sha256": feature_identity["recovery_feature_sha256"],
    }
    predictions: list[tuple[Mapping[tuple[int, int], float], str]] = []
    folds = []
    for block in range(1, 5):
        test = [row for row in prepared if block_by_fixture[row["fixture_id"]] == block]
        if block == 1:
            folds.append(
                {
                    "block": block,
                    "target_count": sum(value == block for value in block_by_fixture.values()),
                    "scorable_count": len(test),
                    "status": "OOF_WARMUP_NOT_CALIBRATION_ELIGIBLE",
                }
            )
            continue
        train = [row for row in prepared if block_by_fixture[row["fixture_id"]] < block]
        fit = fit_poisson_factor_coefficients(train, active_factor_ids=ACTIVE_FACTORS)
        fold_model = _fit_identity(fit, model_upstream, f"OOF_BLOCK_{block}")
        for row in test:
            home, away = _lambdas(row, fit)
            predictions.append(
                (
                    exact_score_matrix_from_lambdas(
                        lambda_home=home, lambda_away=away, rho=0, max_goals=12
                    ),
                    _actual(row),
                )
            )
        folds.append(
            {
                "block": block,
                "target_count": sum(value == block for value in block_by_fixture.values()),
                "fit_count": len(train),
                "scorable_count": len(test),
                "model_sha256": fold_model["model_sha256"],
                "status": "FORWARD_OOF_CALIBRATION_ELIGIBLE",
            }
        )
    temperature, diagnostics = _bounded_temperature(predictions)
    final_fit = fit_poisson_factor_coefficients(prepared, active_factor_ids=ACTIVE_FACTORS)
    model = _fit_identity(final_fit, model_upstream, "FINAL_ALL_SCORABLE_TRAIN")
    calibration_body = {
        "schema_version": f"{SCHEMA}.temperature",
        "upstream": {**upstream, "model_sha256": model["model_sha256"]},
        "method": "GLOBAL_COMPLETE_SCORE_MATRIX_TEMPERATURE",
        "temperature": temperature,
        "selection": "TRAIN_FORWARD_OOF_1X2_NLL_ONLY",
        "folds": folds,
        "diagnostics": diagnostics,
    }
    calibration = {
        **calibration_body,
        "calibration_sha256": _hash("RECOVERY_TEMPERATURE_CALIBRATION", calibration_body),
    }
    matrices = []
    for row in prepared:
        home, away = _lambdas(row, final_fit)
        matrix = _temperature_matrix(
            exact_score_matrix_from_lambdas(
                lambda_home=home, lambda_away=away, rho=0, max_goals=12
            ),
            temperature,
        )
        cells = [
            {"home_goals": key[0], "away_goals": key[1], "probability": round(value, 15)}
            for key, value in sorted(matrix.items())
        ]
        matrices.append(
            {
                "fixture_id": row["fixture_id"],
                "matrix_sha256": _hash("RECOVERY_SCORE_MATRIX", cells),
            }
        )
    matrix_body = {
        "schema_version": f"{SCHEMA}.score_matrices",
        "calibration_sha256": calibration["calibration_sha256"],
        "count": len(matrices),
        "rows": matrices,
    }
    matrix_artifact = {
        **matrix_body,
        "score_matrix_set_sha256": _hash("RECOVERY_SCORE_MATRIX_SET", matrix_body),
    }
    evidence = {
        "schema_version": f"{SCHEMA}.evidence",
        "status": "PROSPECTIVE_CANDIDATE_IDENTITY_ONLY",
        "gate_1": "FAIL",
        "gate_2": "CLOSED",
        "alpha": None,
        "beta": None,
        "source_hashes": actual,
        "upstream": upstream,
        "identities": {
            "split": split_identity["recovery_split_sha256"],
            "preprocessing": preprocessing_identity["recovery_preprocessing_sha256"],
            "features": feature_identity["recovery_feature_sha256"],
            "model": model["model_sha256"],
            "calibration": calibration["calibration_sha256"],
            "score_matrices": matrix_artifact["score_matrix_set_sha256"],
        },
        "execution": {
            "provider_calls": 0,
            "production_reads": 0,
            "production_writes": 0,
            "github_ghcr": 0,
            "migration_apply": 0,
            "collector_start": 0,
            "deployment": 0,
            "candidate_opportunity_outbox_bark": 0,
            "validation_holdout_metric_reads": 0,
        },
    }
    evidence["evidence_sha256"] = _hash("RECOVERY_EVIDENCE", evidence)
    artifacts: dict[str, Any] = {
        "CURRENT_XG_CORPUS.json": corpus,
        "TRAIN_DENOMINATOR.json": denominator_artifact,
        "RECOVERY_SPLIT.json": split_identity,
        "RECOVERY_PREPROCESSING.json": preprocessing_identity,
        "RECOVERY_FEATURES.json": feature_identity,
        "MODEL.json": model,
        "CALIBRATION.json": calibration,
        "SCORE_MATRICES.json": matrix_artifact,
        "EVIDENCE.json": evidence,
    }
    return {name: _dump(payload) for name, payload in artifacts.items()}


def _self_test(paths: Mapping[str, Path]) -> dict[str, Any]:
    original = build(paths)
    split = json.loads((paths["split_dir"] / "factor_v2_split_manifest.json").read_text())
    sealed = Counter(row["split"] for row in split["targets"] if row["split"] != "TRAIN")
    if sealed != {"VALIDATION": 4520, "HOLDOUT": 2628}:
        raise ValueError("RECOVERY_SEALED_COHORT_MISMATCH")
    history = json.loads(paths["history"].read_text())
    split_by_fixture = {str(row["fixture_id"]): str(row["split"]) for row in split["targets"]}
    old_keys = set(_load_old_xg(paths["old_xg"]))
    current_extra_keys = {
        (row["fixture_id"], row["team_id"])
        for row in _load_current_xg(paths["current_xg"])
        if (row["fixture_id"], row["team_id"]) not in old_keys
    }
    sealed_mutation = deepcopy(history)
    sealed_row = next(
        row
        for row in sealed_mutation["history_rows"]
        if split_by_fixture.get(str(row["fixture_id"])) in {"VALIDATION", "HOLDOUT"}
        and (str(row["provider_fixture_id"]), str(row["team_id"])) not in current_extra_keys
    )
    sealed_row["goals_for"] = int(sealed_row["goals_for"]) + 1
    sealed_identical = original == build(paths, history_override=sealed_mutation)
    train_mutation = deepcopy(history)
    scorable_train = {
        row["fixture_id"]
        for row in json.loads(original["TRAIN_DENOMINATOR.json"])["rows"]
        if row["status"] == "SCORABLE"
    }
    train_row = next(
        row
        for row in train_mutation["history_rows"]
        if split_by_fixture.get(str(row["fixture_id"])) == "TRAIN"
        and str(row["fixture_id"]) in scorable_train
    )
    train_row["goals_for"] = int(train_row["goals_for"]) + 7
    changed = build(paths, history_override=train_mutation)
    original_evidence = json.loads(original["EVIDENCE.json"])
    changed_evidence = json.loads(changed["EVIDENCE.json"])
    train_identity_changed = any(
        original_evidence["identities"][name] != changed_evidence["identities"][name]
        for name in ("model", "calibration")
    )
    result = {
        "deterministic": original == build(paths),
        "sealed_outcome_mutation_artifacts_identical": sealed_identical,
        "train_outcome_mutation_changes_model_or_calibration": train_identity_changed,
        "sealed_counts": dict(sealed),
        "source_hash_guards": True,
    }
    if not all(value for key, value in result.items() if key not in {"sealed_counts"}):
        raise ValueError(f"RECOVERY_SELF_TEST_FAILED:{result}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/review_packages/V2_GATE1_CALIBRATION_RECOVERY_01/artifacts"),
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test-check", action="store_true")
    args = parser.parse_args()
    paths = {
        **DEFAULTS,
        "split": DEFAULTS["split_dir"] / "factor_v2_split_manifest.json",
        "preprocessing": DEFAULTS["split_dir"] / "factor_v2_train_preprocessing.json",
        "normalized": DEFAULTS["split_dir"] / "factor_v2_normalized_features.json",
        "visibility": DEFAULTS["split_dir"] / "factor_v2_visibility.json",
    }
    if args.self_test_check:
        print(json.dumps(_self_test(paths), sort_keys=True))
        return
    artifacts = build(paths)
    if args.check:
        mismatches = [
            name
            for name, value in artifacts.items()
            if not (args.output_dir / name).is_file()
            or (args.output_dir / name).read_bytes() != value
        ]
        if mismatches:
            raise SystemExit(f"RECOVERY_ARTIFACT_MISMATCH:{','.join(mismatches)}")
        print(json.dumps({"check": "PASS", "artifact_count": len(artifacts)}, sort_keys=True))
        return
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, value in artifacts.items():
        (args.output_dir / name).write_bytes(value)
    print(
        json.dumps(
            {
                "status": "PROSPECTIVE_CANDIDATE_IDENTITY_ONLY",
                "output_dir": str(args.output_dir),
                "artifact_count": len(artifacts),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
