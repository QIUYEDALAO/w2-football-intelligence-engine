# ruff: noqa: E501, S311
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import fmean
from typing import Any, Literal

from w2.markets.settlement_probability import effective_settlement_probability

AH_FORMAL_EVIDENCE_VERSION = "w2.ah_formal_evidence.v1"
AH_OUTCOMES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
_OUTCOME_RETURN = {"WIN": 1.0, "HALF_WIN": 0.5, "PUSH": 0.0, "HALF_LOSS": -0.5, "LOSS": -1.0}
Conclusion = Literal["PASS_FOR_SHADOW", "INSUFFICIENT_EVIDENCE", "FAIL"]


@dataclass(frozen=True, kw_only=True)
class AhFormalEvidenceProtocol:
    frozen_at_utc: str
    train_end_utc: str
    validation_end_utc: str
    minimum_train_samples: int = 300
    minimum_validation_samples: int = 100
    minimum_holdout_samples: int = 100
    minimum_stratum_samples: int = 30
    bootstrap_replicates: int = 1_000
    bootstrap_seed: int = 7
    candidate_ev_threshold: float = 0.035
    candidate_edge_threshold: float = 0.035
    maximum_holdout_log_loss_delta: float = 0.0
    maximum_holdout_brier_delta: float = 0.0
    no_harm_ci_upper_bound: float = 0.0


def canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_ah_formal_evidence(
    rows: Iterable[dict[str, Any]],
    *,
    protocol: AhFormalEvidenceProtocol,
    data_source: str,
) -> dict[str, Any]:
    """Evaluate only immutable, canonical, as-of-safe AH observations.

    This function deliberately has no connection, provider, or persistence dependency.
    Input rows are a frozen export; a row is accepted only when it can be linked to its
    canonical fixture and its pre-kickoff market/model snapshots.
    """

    frozen_rows = [dict(row) for row in rows]
    valid_rows, exclusions = _canonical_rows(frozen_rows, protocol)
    split_rows = _temporal_splits(valid_rows, protocol)
    split_metrics = {name: _metrics(split) for name, split in split_rows.items()}
    holdout = split_rows["holdout"]
    candidate_holdout = _candidate_rows(holdout, protocol)
    bootstrap = _paired_bootstrap(holdout, protocol)
    strata = _strata(holdout, protocol.minimum_stratum_samples)
    evidence_groups = _evidence_groups(holdout, protocol.minimum_stratum_samples)
    ablation = _ablation(holdout, protocol.minimum_stratum_samples)
    residual_correlation = _residual_correlation(holdout)
    blockers = _blockers(
        valid_rows=valid_rows,
        split_rows=split_rows,
        split_metrics=split_metrics,
        bootstrap=bootstrap,
        protocol=protocol,
    )
    conclusion: Conclusion
    if blockers:
        conclusion = "INSUFFICIENT_EVIDENCE"
    elif _no_harm_passes(split_metrics["holdout"], bootstrap, protocol):
        conclusion = "PASS_FOR_SHADOW"
    else:
        conclusion = "FAIL"
    return {
        "report_version": AH_FORMAL_EVIDENCE_VERSION,
        "report_type": "V3_07_AH_FORMAL_OFFLINE_EVIDENCE",
        "mode": "OFFLINE_READ_ONLY",
        "data_source": data_source,
        "frozen_input_sha256": canonical_json_sha256(frozen_rows),
        "protocol": _protocol_dict(protocol),
        "sample": {
            "input_rows": len(frozen_rows),
            "canonical_asof_safe_rows": len(valid_rows),
            "excluded_rows": len(frozen_rows) - len(valid_rows),
            "exclusion_counts": dict(sorted(exclusions.items())),
            "splits": {name: len(split) for name, split in split_rows.items()},
        },
        "metrics": split_metrics,
        "all_holdout_metrics": split_metrics["holdout"],
        "candidate_holdout_metrics": _metrics(candidate_holdout),
        "paired_bootstrap": bootstrap,
        "strata": strata,
        "factor_ablation": ablation,
        "distinct_evidence_groups": evidence_groups,
        "residual_correlation": residual_correlation,
        "market_baseline_is_evidence": False,
        "drift_diagnostics": _drift_diagnostics(valid_rows),
        "blockers": blockers,
        "conclusion": conclusion,
        "formal_ah_enabled": False,
        "formal_ou_enabled": False,
        "recommendation_lock_enabled": False,
        "production_recommendation_enabled": False,
    }


def _canonical_rows(
    rows: list[dict[str, Any]], protocol: AhFormalEvidenceProtocol
) -> tuple[list[dict[str, Any]], Counter[str]]:
    accepted: list[dict[str, Any]] = []
    exclusions: Counter[str] = Counter()
    frozen_at = _parse_utc(protocol.frozen_at_utc)
    for row in rows:
        reason = _exclusion_reason(row, frozen_at)
        if reason is not None:
            exclusions[reason] += 1
            continue
        accepted.append(row)
    return accepted, exclusions


def _exclusion_reason(row: dict[str, Any], frozen_at: datetime) -> str | None:
    if row.get("canonical_cohort") is not True:
        return "NOT_CANONICAL_COHORT"
    if row.get("legacy_ambiguous") is True:
        return "LEGACY_AMBIGUOUS_IDENTITY"
    if not str(row.get("fixture_id") or "") or not str(row.get("identity_trace_id") or ""):
        return "MISSING_CANONICAL_IDENTITY"
    if str(row.get("market") or "") != "ASIAN_HANDICAP":
        return "NOT_ASIAN_HANDICAP"
    if str(row.get("settlement_outcome") or "") not in AH_OUTCOMES:
        return "MISSING_OR_NONDECISIVE_AH_SETTLEMENT"
    try:
        kickoff = _parse_utc(str(row["kickoff_utc"]))
        as_of = _parse_utc(str(row["as_of_utc"]))
    except (KeyError, TypeError, ValueError):
        return "MISSING_ASOF_TIMESTAMP"
    if as_of > kickoff or as_of > frozen_at:
        return "ASOF_VIOLATION"
    if not _probabilities(row.get("model_probabilities")):
        return "MISSING_MODEL_SETTLEMENT_DISTRIBUTION"
    if not _probabilities(row.get("market_devig_probabilities")):
        return "MISSING_DEVIG_MARKET_DISTRIBUTION"
    if not isinstance(row.get("selection_odds"), (int, float)) or float(row["selection_odds"]) <= 1:
        return "MISSING_SELECTION_ODDS"
    if row.get("entry_devig_probability") is None:
        return "MISSING_ENTRY_DEVIG_PROBABILITY"
    derived_reason = _derived_metric_conflict(row)
    if derived_reason is not None:
        return derived_reason
    if row.get("closing_devig_probability") is not None and (
        not str(row.get("closing_quote_identity_hash") or "")
        or not str(row.get("closing_quote_captured_at") or "")
    ):
        return "INCOMPLETE_CLV_FIELDS"
    if row.get("closing_devig_probability") is not None:
        closing_at = _parse_utc(str(row.get("closing_quote_captured_at")))
        if closing_at >= kickoff:
            return "POST_KICKOFF_CLOSING_QUOTE"
        if str(row.get("closing_market") or "ASIAN_HANDICAP") != "ASIAN_HANDICAP":
            return "CLV_MARKET_IDENTITY_CONFLICT"
        if str(row.get("closing_selection") or row.get("selection") or "") != str(
            row.get("selection") or ""
        ):
            return "CLV_SELECTION_IDENTITY_CONFLICT"
        if str(row.get("closing_line") or row.get("line") or "") != str(row.get("line") or ""):
            return "CLV_LINE_IDENTITY_CONFLICT"
    if row.get("model_expected_value") is None:
        return "MISSING_MODEL_EXPECTED_VALUE"
    if row.get("model_market_probability_delta") is None:
        return "MISSING_MODEL_MARKET_PROBABILITY_DELTA"
    return None


def _derived_metric_conflict(row: dict[str, Any]) -> str | None:
    model = row["model_probabilities"]
    market = row["market_devig_probabilities"]
    odds = float(row["selection_odds"])
    model_probability = effective_settlement_probability(model)
    market_probability = effective_settlement_probability(market)
    if model_probability is None or market_probability is None:
        return "DERIVED_METRIC_IDENTITY_CONFLICT"
    if not _close(float(row["entry_devig_probability"]), market_probability):
        return "ENTRY_DEVIG_PROBABILITY_CONFLICT"
    if not _close(float(row["model_expected_value"]), _expected_return(model, odds)):
        return "DERIVED_METRIC_IDENTITY_CONFLICT"
    if not _close(
        float(row["model_market_probability_delta"]),
        round(model_probability - market_probability, 6),
    ):
        return "DERIVED_METRIC_IDENTITY_CONFLICT"
    return None


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, abs_tol=1e-6)


def _temporal_splits(
    rows: list[dict[str, Any]], protocol: AhFormalEvidenceProtocol
) -> dict[str, list[dict[str, Any]]]:
    train_end = _parse_utc(protocol.train_end_utc)
    validation_end = _parse_utc(protocol.validation_end_utc)
    result: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "holdout": []}
    for row in sorted(rows, key=lambda value: str(value["kickoff_utc"])):
        kickoff = _parse_utc(str(row["kickoff_utc"]))
        if kickoff <= train_end:
            result["train"].append(row)
        elif kickoff <= validation_end:
            result["validation"].append(row)
        else:
            result["holdout"].append(row)
    return result


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return _empty_metrics()
    model_log = [_log_loss(row["model_probabilities"], str(row["settlement_outcome"])) for row in rows]
    market_log = [_log_loss(row["market_devig_probabilities"], str(row["settlement_outcome"])) for row in rows]
    model_brier = [_brier(row["model_probabilities"], str(row["settlement_outcome"])) for row in rows]
    market_brier = [_brier(row["market_devig_probabilities"], str(row["settlement_outcome"])) for row in rows]
    model_ev = [_expected_return(row["model_probabilities"], float(row["selection_odds"])) for row in rows]
    market_ev = [_expected_return(row["market_devig_probabilities"], float(row["selection_odds"])) for row in rows]
    clv_rows = [
        row
        for row in rows
        if isinstance(row.get("entry_devig_probability"), (int, float))
        and isinstance(row.get("closing_devig_probability"), (int, float))
    ]
    clv = [
        float(row["closing_devig_probability"]) - float(row["entry_devig_probability"])
        for row in clv_rows
    ]
    model_ece = _multiclass_ece(rows, "model_probabilities")
    market_ece = _multiclass_ece(rows, "market_devig_probabilities")
    return {
        "sample_count": len(rows),
        "model_log_loss": _round(fmean(model_log)),
        "market_devig_log_loss": _round(fmean(market_log)),
        "delta_log_loss_model_minus_market": _round(fmean(model_log) - fmean(market_log)),
        "model_multiclass_brier": _round(fmean(model_brier)),
        "market_devig_multiclass_brier": _round(fmean(market_brier)),
        "delta_brier_model_minus_market": _round(fmean(model_brier) - fmean(market_brier)),
        "ece_method": "CLASSWISE_MULTICLASS_ECE_10_EQUAL_WIDTH_BINS",
        "ece_bin_count": 10,
        "model_ece": _round(float(model_ece["ece"])),
        "market_ece": _round(float(market_ece["ece"])),
        "market_devig_ece": _round(float(market_ece["ece"])),
        "per_class_ece": {
            "model": model_ece["per_class_ece"],
            "market": market_ece["per_class_ece"],
        },
        "model_expected_return": _round(fmean(model_ev)),
        "market_expected_return": _round(fmean(market_ev)),
        "mean_clv_probability_delta": _round(fmean(clv)) if clv else None,
        "clv_sample_count": len(clv),
        "missing_clv_count": len(rows) - len(clv),
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "sample_count": 0,
        "model_log_loss": None,
        "market_devig_log_loss": None,
        "delta_log_loss_model_minus_market": None,
        "model_multiclass_brier": None,
        "market_devig_multiclass_brier": None,
        "delta_brier_model_minus_market": None,
        "model_ece": None,
        "market_ece": None,
        "market_devig_ece": None,
        "ece_method": "CLASSWISE_MULTICLASS_ECE_10_EQUAL_WIDTH_BINS",
        "ece_bin_count": 10,
        "per_class_ece": None,
        "model_expected_return": None,
        "market_expected_return": None,
        "mean_clv_probability_delta": None,
        "clv_sample_count": 0,
        "missing_clv_count": 0,
    }


def _paired_bootstrap(rows: list[dict[str, Any]], protocol: AhFormalEvidenceProtocol) -> dict[str, Any]:
    if not rows:
        return {"method": "PAIRED_BOOTSTRAP_PERCENTILE", "replicates": protocol.bootstrap_replicates,
                "seed": protocol.bootstrap_seed, "sample_count": 0, "delta_log_loss_ci_95": None,
                "delta_brier_ci_95": None, "mean_delta_log_loss": None, "mean_delta_brier": None}
    log_delta = [
        _log_loss(row["model_probabilities"], str(row["settlement_outcome"]))
        - _log_loss(row["market_devig_probabilities"], str(row["settlement_outcome"]))
        for row in rows
    ]
    brier_delta = [
        _brier(row["model_probabilities"], str(row["settlement_outcome"]))
        - _brier(row["market_devig_probabilities"], str(row["settlement_outcome"]))
        for row in rows
    ]
    rng = random.Random(protocol.bootstrap_seed)
    indices = range(len(rows))
    log_samples = [fmean(log_delta[rng.choice(indices)] for _ in indices) for _ in range(protocol.bootstrap_replicates)]
    brier_samples = [fmean(brier_delta[rng.choice(indices)] for _ in indices) for _ in range(protocol.bootstrap_replicates)]
    return {
        "method": "PAIRED_BOOTSTRAP_PERCENTILE",
        "replicates": protocol.bootstrap_replicates,
        "seed": protocol.bootstrap_seed,
        "sample_count": len(rows),
        "mean_delta_log_loss": _round(fmean(log_delta)),
        "mean_delta_brier": _round(fmean(brier_delta)),
        "delta_log_loss_ci_95": _ci(log_samples),
        "delta_brier_ci_95": _ci(brier_samples),
    }


def _strata(rows: list[dict[str, Any]], minimum: int) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[f"league:{row.get('league') or 'UNKNOWN'}"].append(row)
        buckets[f"line_range:{_line_range(row.get('line'))}"].append(row)
        buckets[f"side:{row.get('selection_side') or 'UNKNOWN'}"].append(row)
    return {key: _stratum(value, minimum) for key, value in sorted(buckets.items())}


def _evidence_groups(rows: list[dict[str, Any]], minimum: int) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups = row.get("distinct_evidence_groups")
        count = len(set(groups)) if isinstance(groups, list) else 0
        key = "3_PLUS" if count >= 3 else str(count)
        buckets[key].append(row)
    return {key: _stratum(value, minimum) for key, value in sorted(buckets.items())}


def _ablation(rows: list[dict[str, Any]], minimum: int) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        values = row.get("ablation_probabilities")
        if not isinstance(values, dict):
            continue
        for factor_name, probabilities in values.items():
            if _probabilities(probabilities):
                copied = dict(row)
                copied["model_probabilities"] = probabilities
                buckets[str(factor_name)].append(copied)
    return {key: _stratum(value, minimum) for key, value in sorted(buckets.items())}


def _stratum(rows: list[dict[str, Any]], minimum: int) -> dict[str, Any]:
    return {"sample_count": len(rows), "minimum_sample_count": minimum,
            "status": "EVALUABLE" if len(rows) >= minimum else "INSUFFICIENT_SAMPLE",
            "metrics": _metrics(rows)}


def _residual_correlation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs: list[tuple[float, float]] = []
    for row in rows:
        residual = _selection_probability(row["model_probabilities"]) - _selection_probability(row["market_devig_probabilities"])
        group_count = len(set(row.get("distinct_evidence_groups", []))) if isinstance(row.get("distinct_evidence_groups"), list) else 0
        pairs.append((residual, float(group_count)))
    return {"method": "PEARSON_MODEL_MARKET_RESIDUAL_VS_EVIDENCE_GROUP_COUNT",
            "sample_count": len(pairs), "correlation": _pearson(pairs) if len(pairs) >= 2 else None}


def _drift_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    versions = Counter(str(row.get("model_version") or "MISSING") for row in rows)
    calibration = Counter(str(row.get("calibration_version") or "MISSING") for row in rows)
    return {"model_versions": dict(sorted(versions.items())), "calibration_versions": dict(sorted(calibration.items())),
            "multiple_model_versions": len(versions) > 1, "multiple_calibration_versions": len(calibration) > 1}


def _blockers(*, valid_rows: list[dict[str, Any]], split_rows: dict[str, list[dict[str, Any]]], split_metrics: dict[str, dict[str, Any]], bootstrap: dict[str, Any], protocol: AhFormalEvidenceProtocol) -> list[str]:
    blockers: list[str] = []
    minima = {"train": protocol.minimum_train_samples, "validation": protocol.minimum_validation_samples, "holdout": protocol.minimum_holdout_samples}
    for split, minimum in minima.items():
        if len(split_rows[split]) < minimum:
            blockers.append(f"INSUFFICIENT_{split.upper()}_SAMPLE")
    if not valid_rows:
        blockers.append("NO_CANONICAL_ASOF_SAFE_AH_OBSERVATIONS")
        blockers.append("INSUFFICIENT_EVIDENCE")
    if split_metrics["holdout"]["clv_sample_count"] != len(split_rows["holdout"]):
        blockers.append("INCOMPLETE_HOLDOUT_CLV")
    if bootstrap["sample_count"] == 0:
        blockers.append("NO_HOLDOUT_BOOTSTRAP")
    versions = _version_blockers(valid_rows)
    blockers.extend(versions)
    return blockers


def _no_harm_passes(metrics: dict[str, Any], bootstrap: dict[str, Any], protocol: AhFormalEvidenceProtocol) -> bool:
    log_delta = metrics["delta_log_loss_model_minus_market"]
    brier_delta = metrics["delta_brier_model_minus_market"]
    log_ci = bootstrap["delta_log_loss_ci_95"]
    return bool(isinstance(log_delta, float) and isinstance(brier_delta, float) and isinstance(log_ci, list)
                and log_delta <= protocol.maximum_holdout_log_loss_delta
                and brier_delta <= protocol.maximum_holdout_brier_delta
                and log_ci[1] <= protocol.no_harm_ci_upper_bound)


def _probabilities(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != set(AH_OUTCOMES):
        return False
    try:
        return all(float(value[outcome]) >= 0 for outcome in AH_OUTCOMES) and math.isclose(sum(float(value[outcome]) for outcome in AH_OUTCOMES), 1.0, abs_tol=1e-6)
    except (TypeError, ValueError):
        return False


def _log_loss(probabilities: dict[str, Any], outcome: str) -> float:
    return -math.log(max(float(probabilities[outcome]), 1e-15))


def _brier(probabilities: dict[str, Any], outcome: str) -> float:
    return sum((float(probabilities[key]) - float(key == outcome)) ** 2 for key in AH_OUTCOMES)


def _expected_return(probabilities: dict[str, Any], odds: float) -> float:
    return sum(float(probabilities[key]) * (_OUTCOME_RETURN[key] * (odds - 1 if key in {"WIN", "HALF_WIN"} else 1)) for key in AH_OUTCOMES)


def _selection_probability(probabilities: dict[str, Any]) -> float:
    value = effective_settlement_probability(probabilities)
    if value is None:
        raise ValueError("invalid settlement distribution")
    return value


def _multiclass_ece(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    if not rows:
        return {"ece": None, "per_class_ece": {}}
    per_class: dict[str, float] = {}
    for outcome in AH_OUTCOMES:
        bins: list[list[tuple[float, float]]] = [[] for _ in range(10)]
        for row in rows:
            probability = float(row[key][outcome])
            observed = 1.0 if str(row["settlement_outcome"]) == outcome else 0.0
            index = min(9, int(probability * 10))
            bins[index].append((probability, observed))
        per_class[outcome] = _round(
            sum(
                len(bucket)
                / len(rows)
                * abs(fmean(value[0] for value in bucket) - fmean(value[1] for value in bucket))
                for bucket in bins
                if bucket
            )
        )
    return {"ece": _round(fmean(per_class.values())), "per_class_ece": per_class}


def _candidate_rows(rows: list[dict[str, Any]], protocol: AhFormalEvidenceProtocol) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        ev = row.get("model_expected_value")
        edge = row.get("model_market_probability_delta")
        if (
            isinstance(ev, (int, float))
            and isinstance(edge, (int, float))
            and float(ev) >= protocol.candidate_ev_threshold
            and float(edge) >= protocol.candidate_edge_threshold
        ):
            candidates.append(row)
    return candidates


def _version_blockers(rows: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    checks = (
        ("model_version", "MIXED_MODEL_VERSION"),
        ("calibration_version", "MIXED_CALIBRATION_VERSION"),
        ("factor_registry_sha", "MIXED_FACTOR_REGISTRY_VERSION"),
    )
    for key, blocker in checks:
        values = {str(row.get(key) or "MISSING") for row in rows}
        if len(values) > 1:
            blockers.append(blocker)
    return blockers


def _ci(values: list[float]) -> list[float]:
    ordered = sorted(values)
    return [_round(ordered[int(0.025 * (len(ordered) - 1))]), _round(ordered[int(0.975 * (len(ordered) - 1))])]


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    xs, ys = zip(*pairs, strict=True)
    x_mean, y_mean = fmean(xs), fmean(ys)
    denominator = math.sqrt(sum((x - x_mean) ** 2 for x in xs) * sum((y - y_mean) ** 2 for y in ys))
    return None if denominator == 0 else _round(sum((x - x_mean) * (y - y_mean) for x, y in pairs) / denominator)


def _line_range(value: object) -> str:
    if not isinstance(value, (int, float, str)):
        return "UNKNOWN"
    try:
        line = abs(float(value))
    except (TypeError, ValueError):
        return "UNKNOWN"
    if line <= 0.25:
        return "0_TO_0.25"
    if line <= 0.75:
        return "0.5_TO_0.75"
    return "1_PLUS"


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def _round(value: float) -> float:
    return round(value, 6)


def _protocol_dict(protocol: AhFormalEvidenceProtocol) -> dict[str, object]:
    return {field: getattr(protocol, field) for field in protocol.__dataclass_fields__}
