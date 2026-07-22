from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from w2.models.evaluation import EvaluationRow, metrics
from w2.models.independent import (
    AsOfFeatureBuilder,
    MatchRecord,
    ModelFamily,
    predict_from_features,
)


@dataclass(frozen=True, kw_only=True)
class CorrectionEvaluationConfig:
    train_size: int = 12
    model: ModelFamily = ModelFamily.TIME_DECAY_ATTACK_DEFENCE
    bootstrap_samples: int = 1_000
    bootstrap_seed: int = 7


def load_fixed_snapshot(payload: list[dict[str, Any]]) -> list[MatchRecord]:
    records = [
        MatchRecord(
            fixture_id=str(row["fixture_id"]),
            competition=str(row.get("competition") or "R2_FIXED_DIXON_COLES_FIXTURE"),
            season=str(row.get("season") or str(row["kickoff_utc"])[:4]),
            kickoff_utc=datetime.fromisoformat(str(row["kickoff_utc"]).replace("Z", "+00:00")),
            home_team=str(row["home_team"]),
            away_team=str(row["away_team"]),
            home_goals=int(row["home_goals"]),
            away_goals=int(row["away_goals"]),
            neutral_site=bool(row.get("neutral_site", False)),
        )
        for row in payload
    ]
    ordered = sorted(records, key=lambda row: (row.kickoff_utc, row.fixture_id))
    if records != ordered:
        raise ValueError("fixed evaluation snapshot must be chronologically ordered")
    if len({row.fixture_id for row in records}) != len(records):
        raise ValueError("fixed evaluation snapshot fixture identities must be unique")
    return records


def evaluate_r2_corrections(
    records: list[MatchRecord],
    *,
    config: CorrectionEvaluationConfig | None = None,
) -> dict[str, Any]:
    resolved = config or CorrectionEvaluationConfig()
    if not 1 <= resolved.train_size < len(records):
        raise ValueError("train_size must leave non-empty train and validation splits")

    baseline = AsOfFeatureBuilder()
    candidate = AsOfFeatureBuilder()
    for record in records[: resolved.train_size]:
        _update_legacy_rolling_form(baseline, record)
        candidate.update(record)

    baseline_rows: list[EvaluationRow] = []
    candidate_rows: list[EvaluationRow] = []
    feature_changed = 0
    prediction_changed = 0
    for record in records[resolved.train_size :]:
        baseline_features = baseline.features(record)
        candidate_features = candidate.features(record)
        if (
            baseline_features["rolling_home_form"]
            != candidate_features["rolling_home_form"]
            or baseline_features["rolling_away_form"]
            != candidate_features["rolling_away_form"]
        ):
            feature_changed += 1
        baseline_prediction = predict_from_features(
            record.fixture_id,
            resolved.model,
            baseline_features,
            record.kickoff_utc,
        )
        candidate_prediction = predict_from_features(
            record.fixture_id,
            resolved.model,
            candidate_features,
            record.kickoff_utc,
        )
        if baseline_prediction.one_x_two != candidate_prediction.one_x_two:
            prediction_changed += 1
        baseline_rows.append(_evaluation_row(record, baseline_prediction.one_x_two))
        candidate_rows.append(_evaluation_row(record, candidate_prediction.one_x_two))
        _update_legacy_rolling_form(baseline, record)
        candidate.update(record)

    baseline_metrics = metrics(baseline_rows)
    candidate_metrics = metrics(candidate_rows)
    metric_deltas = {
        name: round(candidate_metrics[name] - baseline_metrics[name], 6)
        for name in ("log_loss", "brier", "rps", "ece")
    }
    return {
        "schema_version": "w2.r2-offline-correction-evaluation.v1",
        "evaluation_status": "SHADOW_CANDIDATE_ONLY",
        "promotion": {
            "champion_changed": False,
            "recommend_lock_changed": False,
            "production_changed": False,
        },
        "split": {
            "policy": "chronological_fixed_holdout",
            "train_count": resolved.train_size,
            "validation_count": len(candidate_rows),
            "train_fixture_ids": [row.fixture_id for row in records[: resolved.train_size]],
            "validation_fixture_ids": [
                row.fixture_id for row in records[resolved.train_size :]
            ],
        },
        "model": resolved.model.value,
        "coverage": {
            "baseline": round(len(baseline_rows) / len(records[resolved.train_size :]), 6),
            "candidate": round(len(candidate_rows) / len(records[resolved.train_size :]), 6),
        },
        "feature_change": {
            "rolling_form_rows_changed": feature_changed,
            "prediction_rows_changed": prediction_changed,
        },
        "metrics": {
            "baseline": baseline_metrics,
            "candidate": candidate_metrics,
            "candidate_minus_baseline": metric_deltas,
        },
        "paired_bootstrap": _paired_bootstrap_metrics(
            candidate_rows,
            baseline_rows,
            samples=resolved.bootstrap_samples,
            seed=resolved.bootstrap_seed,
        ),
        "strata": {
            outcome: {
                "count": len([row for row in candidate_rows if row.actual == outcome]),
                "baseline": metrics([row for row in baseline_rows if row.actual == outcome]),
                "candidate": metrics([row for row in candidate_rows if row.actual == outcome]),
            }
            for outcome in ("HOME", "DRAW", "AWAY")
            if any(row.actual == outcome for row in candidate_rows)
        },
        "interpretation": {
            "probability_metrics_changed": prediction_changed > 0,
            "claim": (
                "The rolling-form state correction changes stored features but the selected "
                "model does not currently consume those features, so paired probability metrics "
                "are unchanged on this fixed snapshot."
            ),
            "not_production_hit_rate": True,
        },
    }


def stable_evaluation_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _update_legacy_rolling_form(builder: AsOfFeatureBuilder, record: MatchRecord) -> None:
    builder.update(record)
    builder.states[record.home_team].form_points.clear()
    builder.states[record.away_team].form_points.clear()


def _evaluation_row(record: MatchRecord, probabilities: dict[str, float]) -> EvaluationRow:
    return EvaluationRow(
        fixture_id=record.fixture_id,
        actual=record.outcome,
        probabilities=probabilities,
        competition=record.competition,
        season=record.season,
        neutral_site=record.neutral_site,
    )


def _paired_bootstrap_metrics(
    candidate: list[EvaluationRow],
    baseline: list[EvaluationRow],
    *,
    samples: int,
    seed: int,
) -> dict[str, dict[str, float]]:
    if len(candidate) != len(baseline) or not candidate:
        raise ValueError("paired bootstrap requires aligned non-empty rows")
    rng = random.Random(seed)  # noqa: S311 - deterministic evaluation bootstrap.
    deltas: dict[str, list[float]] = {
        "log_loss": [],
        "brier": [],
        "rps": [],
        "ece": [],
    }
    for _ in range(samples):
        indexes = [rng.randrange(len(candidate)) for _ in candidate]
        candidate_sample = [candidate[index] for index in indexes]
        baseline_sample = [baseline[index] for index in indexes]
        candidate_metrics = metrics(candidate_sample)
        baseline_metrics = metrics(baseline_sample)
        for name in deltas:
            deltas[name].append(candidate_metrics[name] - baseline_metrics[name])
    return {name: _interval(values) for name, values in deltas.items()}


def _interval(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "mean_delta": round(sum(ordered) / len(ordered), 6),
        "ci_low": round(ordered[math.floor(len(ordered) * 0.025)], 6),
        "ci_high": round(ordered[max(math.ceil(len(ordered) * 0.975) - 1, 0)], 6),
    }
