#!/usr/bin/env python3
"""Freeze Gate 1 temporal splits and fit TRAIN-only feature preprocessing."""

from __future__ import annotations

import argparse
import bisect
import json
import math
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.history import (
    API_FOOTBALL_TEAM_ID_NAMESPACE,
    RAW_HISTORY_CORPUS_SCHEMA_VERSION,
    build_pit_history_manifest,
)
from w2.factor_model.pit_dataset import (
    TemporalSplitPolicy,
    build_temporal_split_manifest,
    fit_train_only_preprocessing,
    normalize_pit_feature_snapshot,
)
from w2.factor_model.pit_features import RecursiveRatingPolicy, build_pit_feature_snapshot

EXPECTED_CORPUS_SHA256 = "2f2075104989d07977acec40106084744f181510e44caa8ac7201000d98c00c5"
EXPECTED_CORPUS_SNAPSHOT_AS_OF = datetime(2026, 8, 21, 19, 18, 10, 674088, tzinfo=UTC)
HISTORICAL_REPLAY_CUTOFF = datetime(2026, 8, 21, 19, 18, 10, 674088, tzinfo=UTC)
SPLIT_POLICY = TemporalSplitPolicy(
    version="factor-v2.calendar-years-2024-2026.warmup-200.fixed-cutoff.v3",
    train_start=datetime(2024, 1, 1, tzinfo=UTC),
    train_end=datetime(2025, 1, 1, tzinfo=UTC),
    validation_end=datetime(2026, 1, 1, tzinfo=UTC),
    holdout_end=HISTORICAL_REPLAY_CUTOFF,
)
RATING_POLICY = RecursiveRatingPolicy(
    version="factor-v2.elo-1500-k20-ha60-r400.v1",
    initial_rating=1500.0,
    k_factor=20.0,
    home_advantage_rating=60.0,
    rating_scale=400.0,
)
SPLITS = ("TRAIN", "VALIDATION", "HOLDOUT")
FACTOR_IDS = ("F3_REST_FITNESS", "F6_H2H", "F7_STRENGTH_FORM")
WARMUP_MINIMUM_FEATURE_SCOPE_HISTORY_ROWS = 200
F6_BLOCKED_FACTOR_IDS = ("F6_H2H",)
FORBIDDEN_TIMING_FIELDS = frozenset(
    {"result_first_captured_at", "result_capture_delay_seconds", "late_result_fixture_count"}
)


def _utc(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("FACTOR_V2_TRAIN_TIME_INVALID")
    return value.astimezone(UTC)


def _hash(identity_type: str, payload: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {"identity_type": identity_type, **payload},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )


def _normalized_corpus(
    payload: Mapping[str, Any],
    *,
    expected_corpus_sha256: str,
    expected_snapshot_as_of: datetime,
) -> dict[str, Any]:
    if payload.get("schema_version") != RAW_HISTORY_CORPUS_SCHEMA_VERSION:
        raise ValueError("FACTOR_V2_TRAIN_CORPUS_SCHEMA_INVALID")
    rows = payload.get("history_rows")
    if not isinstance(rows, list):
        raise ValueError("FACTOR_V2_TRAIN_CORPUS_ROWS_INVALID")
    normalized_rows: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("FACTOR_V2_TRAIN_CORPUS_ROW_INVALID")
        row = dict(raw)
        for field in ("kickoff_utc", "raw_captured_at", "result_first_captured_at"):
            row[field] = _utc(row[field])
        normalized_rows.append(row)
    normalized = {
        **payload,
        "snapshot_as_of": _utc(payload["snapshot_as_of"]),
        "kickoff_from": _utc(payload["kickoff_from"]),
        "kickoff_to": _utc(payload["kickoff_to"]),
        "history_rows": normalized_rows,
    }
    body = {key: value for key, value in normalized.items() if key != "corpus_sha256"}
    if normalized.get("corpus_sha256") != _hash(
        "FACTOR_MODEL_GATE1_RAW_HISTORY_CORPUS", body
    ):
        raise ValueError("FACTOR_V2_TRAIN_CORPUS_HASH_MISMATCH")
    if normalized["corpus_sha256"] != expected_corpus_sha256:
        raise ValueError("FACTOR_V2_TRAIN_CORPUS_NOT_FROZEN_INPUT")
    if normalized["snapshot_as_of"] != expected_snapshot_as_of:
        raise ValueError("FACTOR_V2_TRAIN_CORPUS_SNAPSHOT_NOT_FROZEN_INPUT")
    return normalized


def _targets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        side = str(row.get("team_side") or "")
        if side not in {"HOME", "AWAY"} or side in grouped[str(row["fixture_id"])]:
            raise ValueError("FACTOR_V2_TRAIN_FIXTURE_PAIR_INVALID")
        grouped[str(row["fixture_id"])][side] = row
    targets: list[dict[str, Any]] = []
    for fixture_id, pair in grouped.items():
        if set(pair) != {"HOME", "AWAY"}:
            raise ValueError("FACTOR_V2_TRAIN_FIXTURE_PAIR_INCOMPLETE")
        home = pair["HOME"]
        away = pair["AWAY"]
        same = ("provider_league_id", "season", "kickoff_utc", "result_identity_hash")
        if any(home[field] != away[field] for field in same):
            raise ValueError("FACTOR_V2_TRAIN_FIXTURE_PAIR_CONFLICT")
        targets.append(
            {
                "fixture_id": fixture_id,
                "provider_league_id": str(home["provider_league_id"]),
                "season": str(home["season"]),
                "kickoff_utc": _utc(home["kickoff_utc"]),
                "home_team_id": str(home["team_id"]),
                "away_team_id": str(away["team_id"]),
            }
        )
    return sorted(targets, key=lambda row: (row["kickoff_utc"], row["fixture_id"]))


def _split(kickoff: datetime) -> str:
    if SPLIT_POLICY.train_start <= kickoff < SPLIT_POLICY.train_end:
        return "TRAIN"
    if SPLIT_POLICY.train_end <= kickoff < SPLIT_POLICY.validation_end:
        return "VALIDATION"
    if SPLIT_POLICY.validation_end <= kickoff < SPLIT_POLICY.holdout_end:
        return "HOLDOUT"
    raise ValueError("FACTOR_V2_TRAIN_TARGET_OUTSIDE_FROZEN_SPLIT")


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _distribution(rows: list[dict[str, Any]], numerator: str, denominator: str) -> dict[str, Any]:
    counts = [float(row[numerator]) for row in rows]
    ratios = [float(row[numerator]) / float(row[denominator]) for row in rows]
    return {
        "target_fixture_count": len(rows),
        "visible_history_row_count": {
            "min": int(min(counts)),
            "p50": int(_nearest_rank(counts, 0.5)),
            "p90": int(_nearest_rank(counts, 0.9)),
            "max": int(max(counts)),
            "zero_count": sum(value == 0 for value in counts),
        },
        "visible_history_row_ratio": {
            "min": round(min(ratios), 8),
            "p50": round(_nearest_rank(ratios, 0.5), 8),
            "p90": round(_nearest_rank(ratios, 0.9), 8),
            "max": round(max(ratios), 8),
        },
        "quantile_method": "NEAREST_RANK_CEILING",
    }


def _contains_forbidden_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(FORBIDDEN_TIMING_FIELDS & set(value)) or any(
            _contains_forbidden_field(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_field(item) for item in value)
    return False


def build_artifacts(
    corpus_payload: Mapping[str, Any],
    *,
    expected_corpus_sha256: str = EXPECTED_CORPUS_SHA256,
    expected_snapshot_as_of: datetime = EXPECTED_CORPUS_SNAPSHOT_AS_OF,
    warmup_minimum_feature_scope_history_rows: int = (
        WARMUP_MINIMUM_FEATURE_SCOPE_HISTORY_ROWS
    ),
) -> dict[str, Any]:
    corpus = _normalized_corpus(
        corpus_payload,
        expected_corpus_sha256=expected_corpus_sha256,
        expected_snapshot_as_of=expected_snapshot_as_of,
    )
    rows = list(corpus["history_rows"])
    source_fixtures = _targets(rows)
    targets = [
        target
        for target in source_fixtures
        if SPLIT_POLICY.train_start
        <= target["kickoff_utc"]
        < SPLIT_POLICY.holdout_end
    ]
    rows_by_league: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_league[str(row["provider_league_id"])].append(row)
    kickoff_index = sorted(target["kickoff_utc"] for target in source_fixtures)

    snapshots: list[dict[str, Any]] = []
    visibility: list[dict[str, Any]] = []
    zero_feature_history_fixture_ids: list[str] = []
    leakage_violation_count = 0
    forbidden_timing_field_occurrence_count = 0
    for target in targets:
        league_id = str(target["provider_league_id"])
        feature_as_of = target["kickoff_utc"]
        manifest = build_pit_history_manifest(
            rows_by_league[league_id],
            target_fixture_id=str(target["fixture_id"]),
            target_kickoff=target["kickoff_utc"],
            feature_as_of=feature_as_of,
            team_identity_namespace=API_FOOTBALL_TEAM_ID_NAMESPACE,
            immutable_fact_backfill=True,
        )
        leakage_violation_count += sum(
            _utc(source["kickoff_utc"]) >= feature_as_of
            for source in manifest["source_fixtures"]
        )
        snapshot = build_pit_feature_snapshot(
            manifest,
            home_team_id=str(target["home_team_id"]),
            away_team_id=str(target["away_team_id"]),
            team_identity_namespace=API_FOOTBALL_TEAM_ID_NAMESPACE,
            rating_policy=RATING_POLICY,
        )
        forbidden_timing_field_occurrence_count += int(
            _contains_forbidden_field(snapshot)
        )
        split = _split(feature_as_of)
        global_visible = bisect.bisect_left(kickoff_index, feature_as_of) * 2
        feature_visible = int(manifest["source_history_row_count"])
        feature_missing = feature_visible == 0
        if feature_missing:
            zero_feature_history_fixture_ids.append(str(target["fixture_id"]))
            if any(snapshot["factors"][factor]["missing"] is not True for factor in FACTOR_IDS):
                raise ValueError("FACTOR_V2_ZERO_VISIBLE_HISTORY_NOT_MISSING")
        snapshots.append(snapshot)
        visibility.append(
            {
                "fixture_id": str(target["fixture_id"]),
                "provider_league_id": league_id,
                "season": str(target["season"]),
                "split": split,
                "feature_as_of": feature_as_of,
                "global_visible_history_row_count": global_visible,
                "global_total_history_row_count": len(rows),
                "feature_scope_visible_history_row_count": feature_visible,
                "feature_scope_total_history_row_count": len(rows_by_league[league_id]),
                "feature_history_missing": feature_missing,
                "historical_replay_eligible": (
                    feature_visible >= warmup_minimum_feature_scope_history_rows
                ),
                "historical_replay_exclusion_reason": (
                    None
                    if feature_visible >= warmup_minimum_feature_scope_history_rows
                    else "WARMUP_INSUFFICIENT_SAME_LEAGUE_HISTORY"
                ),
            }
        )

    eligible_fixture_ids = {
        row["fixture_id"] for row in visibility if row["historical_replay_eligible"]
    }
    eligible_snapshots = [
        snapshot
        for snapshot in snapshots
        if str(snapshot["target_fixture_id"]) in eligible_fixture_ids
    ]
    split_manifest = build_temporal_split_manifest(
        eligible_snapshots, policy=SPLIT_POLICY
    )
    preprocessing = fit_train_only_preprocessing(
        split_manifest,
        eligible_snapshots,
        blocked_factor_ids=F6_BLOCKED_FACTOR_IDS,
    )
    normalized_features = [
        normalize_pit_feature_snapshot(snapshot, preprocessing)
        for snapshot in eligible_snapshots
    ]
    normalized_by_fixture = {
        str(row["target_fixture_id"]): row for row in normalized_features
    }
    for fixture_id in zero_feature_history_fixture_ids:
        if fixture_id in normalized_by_fixture:
            raise ValueError("FACTOR_V2_ZERO_VISIBLE_HISTORY_WARMUP_ADMISSION_INVALID")

    by_split_before = {
        split: [row for row in visibility if row["split"] == split] for split in SPLITS
    }
    by_split_after = {
        split: [row for row in by_split_before[split] if row["historical_replay_eligible"]]
        for split in SPLITS
    }
    snapshots_by_fixture = {
        str(snapshot["target_fixture_id"]): snapshot for snapshot in snapshots
    }

    def factor_observed(rows_for_split: list[dict[str, Any]]) -> dict[str, int]:
        return {
            factor: sum(
                snapshots_by_fixture[row["fixture_id"]]["factors"][factor]["missing"]
                is not True
                for row in rows_for_split
            )
            for factor in FACTOR_IDS
        }

    factor_missing_by_split = {
        split: {
            factor: sum(
                snapshots_by_fixture[row["fixture_id"]]["factors"][factor]["missing"]
                is True
                for row in by_split_after[split]
            )
            for factor in FACTOR_IDS
        }
        for split in SPLITS
    }
    warmup_candidates = []
    train_before = by_split_before["TRAIN"]
    for threshold in (0, 100, 200, 300, 400, 600, 800, 1000):
        retained = [
            row
            for row in train_before
            if row["feature_scope_visible_history_row_count"] >= threshold
        ]
        warmup_candidates.append(
            {
                "minimum_feature_scope_history_row_count": threshold,
                "retained_train_fixture_count": len(retained),
                "retained_provider_league_count": len(
                    {row["provider_league_id"] for row in retained}
                ),
            }
        )
    train_retention_by_provider_league = []
    for league_id in sorted({row["provider_league_id"] for row in train_before}, key=int):
        before_count = sum(row["provider_league_id"] == league_id for row in train_before)
        after_count = sum(
            row["provider_league_id"] == league_id for row in by_split_after["TRAIN"]
        )
        train_retention_by_provider_league.append(
            {
                "provider_league_id": league_id,
                "before_fixture_count": before_count,
                "after_fixture_count": after_count,
            }
        )

    def p50(rows_for_split: list[dict[str, Any]], field: str) -> float:
        return _nearest_rank([float(row[field]) for row in rows_for_split], 0.5)

    train_global_p50_before = p50(train_before, "global_visible_history_row_count")
    train_global_p50_after = p50(
        by_split_after["TRAIN"], "global_visible_history_row_count"
    )
    holdout_global_p50 = p50(
        by_split_after["HOLDOUT"], "global_visible_history_row_count"
    )
    train_scope_p50_before = p50(train_before, "feature_scope_visible_history_row_count")
    train_scope_p50_after = p50(
        by_split_after["TRAIN"], "feature_scope_visible_history_row_count"
    )
    holdout_scope_p50 = p50(
        by_split_after["HOLDOUT"], "feature_scope_visible_history_row_count"
    )

    def ratio(numerator: float, denominator: float) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    late_fixture_ids = {
        str(row["fixture_id"])
        for row in rows
        if int(row.get("result_capture_delay_seconds") or 0) > 36 * 60 * 60
    }
    report_body = {
        "schema_version": "w2.factor_model.gate1_split_train_report.v2",
        "corpus_binding": {
            "corpus_snapshot_as_of": corpus["snapshot_as_of"],
            "corpus_sha256": str(corpus["corpus_sha256"]),
            "total_fixture_count": len(targets),
            "total_source_fixture_count": len(source_fixtures),
            "total_history_row_count": len(rows),
        },
        "feature_time_contract": {
            "feature_as_of_policy": "TARGET_FIXTURE_KICKOFF_UTC",
            "feature_as_of_equals_target_kickoff": True,
            "visibility_policy": (
                "IMMUTABLE_FACTS_STRICT_SOURCE_KICKOFF_BEFORE_FEATURE_AS_OF"
            ),
            "source_kickoff_gte_feature_as_of_violation_count": leakage_violation_count,
        },
        "split_policy": {
            "policy_version": SPLIT_POLICY.version,
            "assignment_field": "target_fixture_kickoff_utc",
            "interval_semantics": "HALF_OPEN",
            "train_start": SPLIT_POLICY.train_start,
            "train_end": SPLIT_POLICY.train_end,
            "validation_end": SPLIT_POLICY.validation_end,
            "holdout_end": SPLIT_POLICY.holdout_end,
            "historical_replay_cutoff": SPLIT_POLICY.holdout_end,
            "post_cutoff_assignment": (
                "FORWARD_ONLY_EXCLUDED_FROM_HISTORICAL_SPLITS"
            ),
            "historical_replay_cutoff_in_split_manifest_hash": True,
            "counts": split_manifest["counts"],
            "split_manifest_sha256": split_manifest["split_manifest_sha256"],
        },
        "visibility_distribution_by_split": {
            split: {
                "population": "BEFORE_WARMUP",
                "global_corpus": _distribution(
                    by_split_before[split],
                    "global_visible_history_row_count",
                    "global_total_history_row_count",
                ),
                "feature_scope_same_provider_league": _distribution(
                    by_split_before[split],
                    "feature_scope_visible_history_row_count",
                    "feature_scope_total_history_row_count",
                ),
            }
            for split in SPLITS
        },
        "warmup_policy": {
            "status": "FROZEN_INPUT_COVERAGE_RULE",
            "minimum_feature_scope_history_row_count": (
                warmup_minimum_feature_scope_history_rows
            ),
            "history_row_semantics": "TWO_TEAM_ROWS_PER_SOURCE_FIXTURE",
            "selection_basis": (
                "FROZEN_PRE_BACKFILL_INPUT_COVERAGE_GUARD;"
                "REEVALUATE_WITHOUT_OUTCOME_OR_ABLATION_METRICS"
            ),
            "candidate_threshold_evidence": warmup_candidates,
            "train_retention_by_provider_league": train_retention_by_provider_league,
            "residual_distribution_shift": {
                "status": "MITIGATED_NOT_ELIMINATED",
                "global_p50_holdout_to_train_before": ratio(
                    holdout_global_p50, train_global_p50_before
                ),
                "global_p50_holdout_to_train_after": ratio(
                    holdout_global_p50, train_global_p50_after
                ),
                "feature_scope_p50_holdout_to_train_before": ratio(
                    holdout_scope_p50, train_scope_p50_before
                ),
                "feature_scope_p50_holdout_to_train_after": ratio(
                    holdout_scope_p50, train_scope_p50_after
                ),
                "future_ablation_reporting_requirement": (
                    "STRATIFY_BY_FEATURE_SCOPE_VISIBLE_HISTORY_DEPTH"
                ),
            },
            "before_after_by_split": {
                split: {
                    "excluded_fixture_count": len(by_split_before[split])
                    - len(by_split_after[split]),
                    "before": {
                        "global_corpus": _distribution(
                            by_split_before[split],
                            "global_visible_history_row_count",
                            "global_total_history_row_count",
                        ),
                        "feature_scope_same_provider_league": _distribution(
                            by_split_before[split],
                            "feature_scope_visible_history_row_count",
                            "feature_scope_total_history_row_count",
                        ),
                        "factor_observed_count": factor_observed(by_split_before[split]),
                    },
                    "after": {
                        "global_corpus": _distribution(
                            by_split_after[split],
                            "global_visible_history_row_count",
                            "global_total_history_row_count",
                        ),
                        "feature_scope_same_provider_league": _distribution(
                            by_split_after[split],
                            "feature_scope_visible_history_row_count",
                            "feature_scope_total_history_row_count",
                        ),
                        "factor_observed_count": factor_observed(by_split_after[split]),
                    },
                }
                for split in SPLITS
            },
        },
        "missing_feature_contract": {
            "zero_feature_scope_visible_history_fixture_count": len(
                zero_feature_history_fixture_ids
            ),
            "zero_feature_scope_visible_history_fixture_ids": sorted(
                zero_feature_history_fixture_ids
            ),
            "zero_feature_scope_visible_history_admitted_count": 0,
            "raw_feature_value_preserved_as_missing": True,
            "full_corpus_mean_imputation_used": False,
            "normalization_imputation_source": "TRAIN_OBSERVED_MEAN_ONLY",
            "missing_indicator_preserved": True,
            "factor_missing_count_by_split": factor_missing_by_split,
        },
        "feature_field_policy": {
            "immutable_fact_fields": [
                "kickoff_utc",
                "home_team_id",
                "away_team_id",
                "home_goals",
                "away_goals",
            ],
            "lineage_only_fields": ["raw_payload_sha256", "raw_captured_at"],
            "derived_or_post_event_source_fields_used": [],
            "derived_feature_justifications": {
                "F3_REST_FITNESS": (
                    "target kickoff minus each team's latest strictly earlier kickoff"
                ),
                "F6_H2H": "side-adjusted mean from strictly earlier immutable score facts",
                "F7_STRENGTH_FORM": (
                    "recursive ratings from strictly earlier score facts; same-kickoff "
                    "fixtures update as one batch"
                ),
            },
        },
        "late_result_policy": {
            "backfilled_fixture_count_over_36h": len(late_fixture_ids),
            "provider_sla_interpretation": False,
            "included_in_feature_values": False,
            "used_for_visibility_or_timeliness_decisions": False,
            "forbidden_timing_field_occurrence_count_in_feature_snapshots": (
                forbidden_timing_field_occurrence_count
            ),
        },
        "train_calibration": {
            "scope": "FEATURE_PREPROCESSING_PARAMETERS",
            "fit_split": "TRAIN",
            "validation_or_holdout_used_for_fit": False,
            "preprocessing_sha256": preprocessing["preprocessing_sha256"],
            "missing_strategy": preprocessing["missing_strategy"],
            "parameters": preprocessing["parameters"],
            "blocked_factor_ids": list(F6_BLOCKED_FACTOR_IDS),
            "factor_effect_coefficients_fitted": False,
            "factor_effect_coefficients_status": (
                "DEFERRED_UNTIL_BASELINE_RESIDUAL_INPUTS_ARE_ASOF_JUSTIFIED"
            ),
        },
        "f6_owner_decision": {
            "status": "OPTION_B_APPROVED_BACKFILL_COVERAGE_REVIEW_PENDING",
            "selected_option": "B",
            "before_warmup_observed_count": factor_observed(train_before)["F6_H2H"],
            "before_warmup_train_fixture_count": len(train_before),
            "before_warmup_observed_rate": ratio(
                factor_observed(train_before)["F6_H2H"], len(train_before)
            ),
            "after_warmup_observed_count": factor_observed(by_split_after["TRAIN"])[
                "F6_H2H"
            ],
            "after_warmup_train_fixture_count": len(by_split_after["TRAIN"]),
            "after_warmup_observed_rate": ratio(
                factor_observed(by_split_after["TRAIN"])["F6_H2H"],
                len(by_split_after["TRAIN"]),
            ),
            "defaults_or_priors_applied": False,
            "preprocessing_status": preprocessing["parameters"]["F6_H2H"]["status"],
            "approved_backfill_seasons": ["2022", "2023"],
            "fallback_if_still_below_usable_coverage": (
                "OPTION_A_EXCLUDE_F6_WITHOUT_DEFAULT_OR_PRIOR"
            ),
        },
        "rating_policy": {
            "version": RATING_POLICY.version,
            "initial_rating": RATING_POLICY.initial_rating,
            "k_factor": RATING_POLICY.k_factor,
            "home_advantage_rating": RATING_POLICY.home_advantage_rating,
            "rating_scale": RATING_POLICY.rating_scale,
            "selection_basis": "EXISTING_GATE1_EXECUTABLE_CONTRACT_NOT_OUTCOME_TUNED",
        },
        "contracts": {
            "provider_calls": 0,
            "database_writes": 0,
            "training_source_split": "TRAIN",
            "validation_scoring_executed": False,
            "holdout_scoring_executed": False,
            "ablation_scoring_executed": False,
            "deployment_executed": False,
            "forward_shadow_enabled": False,
        },
    }
    report = {
        **report_body,
        "report_sha256": _hash("FACTOR_MODEL_GATE1_SPLIT_TRAIN_REPORT", report_body),
    }
    return {
        "split_manifest": split_manifest,
        "feature_snapshots": snapshots,
        "visibility": visibility,
        "preprocessing": preprocessing,
        "normalized_features": normalized_features,
        "report": report,
    }


def _json(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raise TypeError(f"FACTOR_V2_TRAIN_JSON_VALUE_INVALID:{type(value).__name__}")


def _markdown(report: Mapping[str, Any]) -> str:
    residual_shift = report["warmup_policy"]["residual_distribution_shift"]
    lines = [
        "# Gate 1 split freeze + TRAIN preprocessing calibration",
        "",
        f"- corpus_snapshot_as_of: `{_json(report['corpus_binding']['corpus_snapshot_as_of'])}`",
        "- feature_as_of: `each target fixture kickoff_utc`",
        "- historical_replay_cutoff: "
        f"`{_json(report['split_policy']['historical_replay_cutoff'])}`",
        f"- split counts: `{report['split_policy']['counts']}`",
        "- post-cutoff fixtures: `forward-only; excluded from historical splits`",
        "- Provider calls / database writes / deployment: `0 / 0 / false`",
        "",
        "## Warmup before / after",
        "",
        "- Rule: require at least "
        f"`{report['warmup_policy']['minimum_feature_scope_history_row_count']}` "
        "visible same-provider-league history rows "
        f"(`{report['warmup_policy']['minimum_feature_scope_history_row_count'] // 2}` "
        "source fixtures).",
        "- Selection: preserve the frozen pre-backfill input-coverage guard, then "
        "re-evaluate candidate thresholds without outcome or ablation metrics.",
        "",
        "| split | stage | targets | global visible rows min/p50/p90/max | "
        "feature-scope visible rows min/p50/p90/max |",
        "|---|---|---:|---|---|",
    ]
    for split in SPLITS:
        comparison = report["warmup_policy"]["before_after_by_split"][split]
        for stage in ("before", "after"):
            row = comparison[stage]
            global_counts = row["global_corpus"]["visible_history_row_count"]
            scope_counts = row["feature_scope_same_provider_league"][
                "visible_history_row_count"
            ]
            lines.append(
                f"| {split} | {stage} | "
                f"{row['global_corpus']['target_fixture_count']} | "
                f"{global_counts['min']}/{global_counts['p50']}/"
                f"{global_counts['p90']}/{global_counts['max']} | "
                f"{scope_counts['min']}/{scope_counts['p50']}/"
                f"{scope_counts['p90']}/{scope_counts['max']} |"
            )
    lines.extend(
        (
            "",
            "- Residual HOLDOUT/TRAIN p50 ratios after warmup: global corpus "
            f"`{residual_shift['global_p50_holdout_to_train_after']}`; "
            "same-league feature scope "
            f"`{residual_shift['feature_scope_p50_holdout_to_train_after']}`.",
            "- The shift is mitigated, not eliminated; any later ablation report must "
            "stratify by feature-scope visible-history depth.",
            "",
            "## Leakage and field policy",
            "",
            "- source kickoff >= feature_as_of violations: "
            f"`{report['feature_time_contract']['source_kickoff_gte_feature_as_of_violation_count']}`",
            "- Immutable facts: `kickoff_utc, home_team_id, away_team_id, home_goals, away_goals`.",
            "- Raw capture timestamps are lineage only; >36h delay is neither a "
            "feature nor a timing decision.",
            "- Zero visible feature-scope history remains raw-feature missing; "
            "normalization may only use TRAIN observed means plus a missing indicator.",
            "- Factor-effect coefficients remain deferred until baseline residual "
            "inputs have a separate AS-OF justification.",
            "- F6 option B is approved, but remains preprocessing-blocked until the "
            "2022/2023 backfill coverage review; no default, prior, mean, "
            "coefficient, or ablation value is applied.",
        )
    )
    return "\n".join(lines) + "\n"


def write_artifacts(output_dir: Path, artifacts: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    names = {
        "split_manifest": "factor_v2_split_manifest.json",
        "feature_snapshots": "factor_v2_feature_snapshots.json",
        "visibility": "factor_v2_visibility.json",
        "preprocessing": "factor_v2_train_preprocessing.json",
        "normalized_features": "factor_v2_normalized_features.json",
        "report": "factor_v2_split_train_report.json",
    }
    for key, name in names.items():
        (output_dir / name).write_text(
            json.dumps(
                artifacts[key],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=_json,
            )
            + "\n",
            encoding="utf-8",
        )
    (output_dir / "factor_v2_split_train_report.md").write_text(
        _markdown(artifacts["report"]), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-corpus-sha256", default=EXPECTED_CORPUS_SHA256)
    parser.add_argument(
        "--expected-corpus-snapshot-as-of",
        default=_json(EXPECTED_CORPUS_SNAPSHOT_AS_OF),
    )
    parser.add_argument(
        "--warmup-minimum-feature-scope-history-rows",
        type=int,
        default=WARMUP_MINIMUM_FEATURE_SCOPE_HISTORY_ROWS,
    )
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    if not isinstance(corpus, Mapping):
        raise ValueError("FACTOR_V2_TRAIN_CORPUS_JSON_INVALID")
    artifacts = build_artifacts(
        corpus,
        expected_corpus_sha256=args.expected_corpus_sha256,
        expected_snapshot_as_of=_utc(args.expected_corpus_snapshot_as_of),
        warmup_minimum_feature_scope_history_rows=(
            args.warmup_minimum_feature_scope_history_rows
        ),
    )
    write_artifacts(args.output_dir, artifacts)
    report = artifacts["report"]
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "split_counts": report["split_policy"]["counts"],
                "preprocessing_sha256": report["train_calibration"][
                    "preprocessing_sha256"
                ],
                "report_sha256": report["report_sha256"],
                "provider_calls": 0,
                "database_writes": 0,
                "deployment_executed": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
