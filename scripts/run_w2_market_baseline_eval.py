"""W2 market-baseline eval (read-only, offline, $0 provider calls).

Purpose (2026-07 architecture review follow-up):
  1. MODEL phase (local caches only):
     a. Replicate #193 big-5 fitted-lambda numbers from the Understat cache.
     b. NEW: run the exact #193 fit protocol (fitted lambdas + temperature,
        walk-forward, train-only fitting) on the in-season national leagues
        using the cached API-Football statistics xG. The ledger's "~1.05"
        numbers came from the UNFITTED hand-prior model
        (build_walk_forward_predictions -> INDEPENDENT_POISSON stage7.v1),
        so the fitted model has never been evaluated on these leagues.
     c. Emit per-fixture prediction manifests used by the MARKET phase join.
  2. MARKET phase (needs football-data.co.uk CSVs dropped into
     runtime/market_baseline_eval/football_data/ -- see FOOTBALL_DATA_FILES):
     de-vig closing odds, join to the SAME fixtures, and produce the
     per-league "model log loss vs market log loss" table plus a
     market-anchored blend experiment (weight fitted on train rows only).

Red lines respected: no provider calls, no DB writes, no enable, no deploy,
no changes to any live decision path. Everything lands under
runtime/market_baseline_eval/.

Run:
  python3 scripts/run_w2_market_baseline_eval.py --phase model
  python3 scripts/run_w2_market_baseline_eval.py --phase market
  python3 scripts/run_w2_market_baseline_eval.py --phase all
"""

# mypy: ignore-errors
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from w2.backtest.free_tier_2024 import (  # noqa: E402
    MIN_LAMBDA_FIT_SAMPLE,
    OfflineLambdaModel,
    OfflineModelSample,
    _clamp,
    _fit_offline_lambda_model,
    _fit_temperature,
    _model_iteration_predictions,
    _offline_model_samples,
    _prediction_row,
    _temperature_scaled_predictions,
    load_fixture_statistics,
    load_historical_fixtures,
    load_understat_fixture_dataset,
)
from w2.competitions.league_whitelist_scope import (  # noqa: E402
    IN_SEASON_NATIONAL_LEAGUES,
    TOP_FIVE_COMPETITIONS,
)
from w2.competitions.registry import CompetitionRegistry  # noqa: E402
from w2.models.divergence_champion import (  # noqa: E402
    DivergenceModelFamily,
    select_divergence_champion_probabilities,
)
from w2.models.dixon_coles import one_x_two_from_matrix, tau_correction  # noqa: E402
from w2.models.independent import AsOfFeatureBuilder, MatchRecord  # noqa: E402

OUT_DIR = REPO_ROOT / "runtime" / "market_baseline_eval"
MANIFEST_DIR = OUT_DIR / "manifests"
FOOTBALL_DATA_DIR = OUT_DIR / "football_data"
UNDERSTAT_DIRS = (REPO_ROOT / "runtime" / "w2_understat_model_iter1" / "understat",)
PRO_DAY1_RAW = REPO_ROOT / "runtime" / "w2_pro_day1_provider_data" / "raw"
PRO_DAY1_DIRS = tuple(
    PRO_DAY1_RAW / sub for sub in ("", "fixtures", "statistics", "odds", "lineups")
)

BIG5_SEASONS = ("2023", "2024")
IN_SEASON_SEASONS = ("2024", "2025")
MIN_HISTORY = 5
COLD_START_MATCHES = 6
R4_1_WINDOW_MATCHES = 8
R4_1_TIME_DECAY_HALF_LIFE_DAYS = 365.0
R4_1_TARGET_LEAGUES = {
    "bundesliga",
    "brasileirao_serie_a",
    "chinese_super_league",
    "allsvenskan",
}

# football-data.co.uk files the MARKET phase expects (user drops them in
# FOOTBALL_DATA_DIR; filenames must match exactly).
# big-5: per-season files from https://www.football-data.co.uk/mmz4281/<ss>/<code>.csv
# new leagues: cumulative files from https://www.football-data.co.uk/new/<code>.csv
FOOTBALL_DATA_FILES: dict[str, dict[str, object]] = {
    "premier_league": {"kind": "big5", "files": {"2023": "E0_2324.csv", "2024": "E0_2425.csv"}},
    "la_liga": {"kind": "big5", "files": {"2023": "SP1_2324.csv", "2024": "SP1_2425.csv"}},
    "bundesliga": {"kind": "big5", "files": {"2023": "D1_2324.csv", "2024": "D1_2425.csv"}},
    "serie_a": {"kind": "big5", "files": {"2023": "I1_2324.csv", "2024": "I1_2425.csv"}},
    "ligue_1": {"kind": "big5", "files": {"2023": "F1_2324.csv", "2024": "F1_2425.csv"}},
    "brasileirao_serie_a": {"kind": "new", "file": "BRA.csv"},
    "chinese_super_league": {"kind": "new", "file": "CHN.csv"},
    "allsvenskan": {"kind": "new", "file": "SWE.csv"},
    "eliteserien": {"kind": "new", "file": "NOR.csv"},
    "argentina_primera": {"kind": "new", "file": "ARG.csv"},
    "mls": {"kind": "new", "file": "USA.csv"},
}

TEAM_ALIASES = {
    # Understat name -> football-data name (big-5). Fuzzy matching covers the
    # rest; add here only when the unmatched report says so.
    "manchester united": "man united",
    "manchester city": "man city",
    "wolverhampton wanderers": "wolves",
    "nottingham forest": "nottm forest",
    "paris saint germain": "paris sg",
    "athletic club": "ath bilbao",
    "atletico madrid": "ath madrid",
    "real sociedad": "sociedad",
    "real betis": "betis",
    "celta vigo": "celta",
    "rayo vallecano": "vallecano",
    "borussia m gladbach": "mgladbach",
    "borussia monchengladbach": "mgladbach",
    "rasenballsport leipzig": "rb leipzig",
    "eintracht frankfurt": "ein frankfurt",
    "fc cologne": "fc koln",
    "bayer leverkusen": "leverkusen",
    "vfb stuttgart": "stuttgart",
    "ac milan": "milan",
    "saint etienne": "st etienne",
    "parma calcio 1913": "parma",
    "athletic": "ath bilbao",
    "cologne": "fc koln",
    # Brazil: API-Football legacy vs football-data spellings
    "atletico paranaense": "athletico pr",
    "atletico mineiro": "atletico mg",
    "atletico goianiense": "atletico go",
    # Sweden / Norway
    "aik stockholm": "aik",
    "odd ballklubb": "odd",
    # CSL: API-Football legacy sponsor names -> football-data current names
    "chengdu better city": "chengdu rongcheng",
    "dalian zhixing": "dalian yingbo",
    "hangzhou greentown": "zhejiang professional",
    "henan jianye": "henan songshan longmen",
    "meizhou kejia": "meizhou hakka",
    "qingdao jonoon": "qingdao hainiu",
    "qingdao youth island": "qingdao west coast",
    "shanghai sipg": "shanghai port",
    "shandong luneng": "shandong taishan",
    "shijiazhuang y j": "cangzhou",
    "sichuan jiuniu": "shenzhen xinpengcheng",
    "tianjin teda": "tianjin jinmen tiger",
}

GENERIC_TEAM_WORDS = {
    "fc", "cf", "sc", "ac", "afc", "cd", "ca", "club", "clube", "cr", "ec",
    "if", "fk", "bk", "ff", "aif", "ik", "sk", "il", "de", "do", "da",
    "regatas", "esporte", "futebol", "deportivo", "atletico" if False else "zzz",
}


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def log_loss(rows: list[dict]) -> float:
    total = 0.0
    for row in rows:
        p = max(float(row["probabilities"][row["actual"]]), 1e-12)
        total += -math.log(p)
    return total / len(rows) if rows else float("nan")


def brier(rows: list[dict]) -> float:
    total = 0.0
    for row in rows:
        for key in ("HOME", "DRAW", "AWAY"):
            y = 1.0 if row["actual"] == key else 0.0
            total += (float(row["probabilities"][key]) - y) ** 2
    return total / len(rows) if rows else float("nan")


def rps(rows: list[dict]) -> float:
    total = 0.0
    for row in rows:
        cum_p = 0.0
        cum_y = 0.0
        acc = 0.0
        for key in ("HOME", "DRAW", "AWAY")[:2]:
            cum_p += float(row["probabilities"][key])
            cum_y += 1.0 if row["actual"] == key else 0.0
            acc += (cum_p - cum_y) ** 2
        total += acc / 2.0
    return total / len(rows) if rows else float("nan")


def ece_top(rows: list[dict], bins: int = 10) -> float:
    """Expected calibration error on the argmax class, 10 equal-width bins."""
    if not rows:
        return float("nan")
    bucketed: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        probs = row["probabilities"]
        top = max(probs, key=lambda k: float(probs[k]))
        p = float(probs[top])
        hit = 1.0 if row["actual"] == top else 0.0
        bucketed[min(int(p * bins), bins - 1)].append((p, hit))
    total = 0.0
    for items in bucketed.values():
        avg_p = sum(p for p, _ in items) / len(items)
        avg_hit = sum(h for _, h in items) / len(items)
        total += abs(avg_p - avg_hit) * len(items)
    return total / len(rows)


def metric_block(rows: list[dict]) -> dict:
    return {
        "n": len(rows),
        "log_loss": round(log_loss(rows), 6) if rows else None,
        "brier": round(brier(rows), 6) if rows else None,
        "rps": round(rps(rows), 6) if rows else None,
        "ece_top": round(ece_top(rows), 6) if rows else None,
    }


# --------------------------------------------------------------------------
# MODEL phase
# --------------------------------------------------------------------------
def fit_and_predict(train_samples, val_samples) -> dict:
    """#193 protocol: fit lambdas on train, temperature on train, apply to val."""
    model = _fit_offline_lambda_model(train_samples)
    train_pred = _model_iteration_predictions(train_samples, model)
    val_pred = _model_iteration_predictions(val_samples, model)
    temperature = _fit_temperature(train_pred["fitted_raw"])
    train_pred["fitted_calibrated"] = _temperature_scaled_predictions(
        train_pred["fitted_raw"], temperature=temperature
    )
    val_pred["fitted_calibrated"] = _temperature_scaled_predictions(
        val_pred["fitted_raw"], temperature=temperature
    )
    return {
        "model": model,
        "temperature": temperature,
        "train": train_pred,
        "validation": val_pred,
    }


def fit_and_predict_r4_1(train_samples, val_samples) -> dict:
    """R4.1 eval-only variant: time decay, league home terms, DC rho."""
    model = _fit_r4_1_lambda_model(train_samples)
    train_raw = _r4_1_predictions(train_samples, model)
    val_raw = _r4_1_predictions(val_samples, model)
    temperature = _fit_temperature(train_raw)
    train_calibrated = _temperature_scaled_predictions(train_raw, temperature=temperature)
    val_calibrated = _temperature_scaled_predictions(val_raw, temperature=temperature)
    return {
        "model": model,
        "temperature": temperature,
        "train_raw": train_raw,
        "validation_raw": val_raw,
        "train_calibrated": train_calibrated,
        "validation_calibrated": val_calibrated,
    }


def _fit_r4_1_lambda_model(samples: list[OfflineModelSample]) -> OfflineLambdaModel:
    if len(samples) < MIN_LAMBDA_FIT_SAMPLE:
        return OfflineLambdaModel(
            coefficients=(math.log(1.25), 0.0, 0.0, 0.0, 0.0),
            feature_names=(
                "intercept",
                "home_field",
                "attack_xg_for",
                "opponent_xg_against",
                "elo_gap",
            ),
            l2=0.004,
            iterations=0,
            learning_rate=0.0,
        )
    ordered = sorted(samples, key=lambda s: (s.fixture.kickoff_utc, s.fixture.fixture_id))
    competitions = tuple(sorted({sample.fixture.competition_id for sample in ordered}))
    feature_names = (
        "intercept",
        "home_field",
        "attack_xg_for",
        "opponent_xg_against",
        "elo_gap",
        *(f"home_field__{competition}" for competition in competitions),
    )
    beta = [math.log(1.25), 0.06, 0.08, 0.08, 0.04, *([0.0] * len(competitions))]
    learning_rate = 0.020
    l2 = 0.004
    cutoff = max(sample.fixture.kickoff_utc for sample in ordered)
    rows: list[tuple[list[float], float, float]] = []
    for sample in ordered:
        rows.extend(_r4_1_goal_fit_rows(sample, competitions=competitions, cutoff=cutoff))
    total_weight = sum(weight for _, _, weight in rows) or 1.0
    for _ in range(1400):
        gradient = [0.0 for _ in beta]
        for features, goals, weight in rows:
            log_mu = _clamp(
                sum(coef * value for coef, value in zip(beta, features, strict=True)),
                -3.0,
                2.0,
            )
            mu = math.exp(log_mu)
            error = (mu - goals) * weight
            for index, value in enumerate(features):
                gradient[index] += error * value
        for index in range(len(beta)):
            penalty = 0.0 if index == 0 else l2 * beta[index]
            beta[index] -= learning_rate * (gradient[index] / total_weight + penalty)
    rho = _fit_r4_1_rho(ordered, beta, competitions)
    return OfflineLambdaModel(
        coefficients=tuple(beta),
        feature_names=(*feature_names, f"dixon_coles_rho={rho:.2f}"),
        l2=l2,
        iterations=1400,
        learning_rate=learning_rate,
    )


def _r4_1_goal_fit_rows(
    sample: OfflineModelSample,
    *,
    competitions: tuple[str, ...],
    cutoff: datetime,
) -> list[tuple[list[float], float, float]]:
    home_features, away_features = _r4_1_feature_rows(sample, competitions)
    age_days = max((cutoff - sample.fixture.kickoff_utc).total_seconds() / 86400.0, 0.0)
    weight = 0.5 ** (age_days / R4_1_TIME_DECAY_HALF_LIFE_DAYS)
    return [
        (home_features, float(sample.fixture.home_goals), weight),
        (away_features, float(sample.fixture.away_goals), weight),
    ]


def _r4_1_feature_rows(
    sample: OfflineModelSample,
    competitions: tuple[str, ...],
) -> tuple[list[float], list[float]]:
    fixture = sample.fixture
    features = sample.true_features
    elo_gap = float(features["elo_diff"]) / 400.0
    league_home = [
        1.0 if fixture.competition_id == competition else 0.0
        for competition in competitions
    ]
    home_row = [
        1.0,
        float(features["home_field"]),
        float(features["home_attack_strength"]),
        float(features["away_defence_strength"]),
        elo_gap,
        *league_home,
    ]
    away_row = [
        1.0,
        0.0,
        float(features["away_attack_strength"]),
        float(features["home_defence_strength"]),
        -elo_gap,
        *([0.0] * len(competitions)),
    ]
    return home_row, away_row


def _fit_r4_1_rho(
    samples: list[OfflineModelSample],
    beta: list[float],
    competitions: tuple[str, ...],
) -> float:
    best_rho = 0.0
    best_loss = float("inf")
    candidates = tuple(round(-0.20 + step * 0.01, 2) for step in range(41))
    for rho in candidates:
        loss = 0.0
        for sample in samples:
            home_mu, away_mu = _r4_1_lambdas(sample, beta, competitions)
            probability = _dc_score_probability(
                sample.fixture.home_goals,
                sample.fixture.away_goals,
                home_mu,
                away_mu,
                rho,
            )
            loss += -math.log(max(probability, 1e-12))
        if loss < best_loss:
            best_loss = loss
            best_rho = rho
    return best_rho


def _r4_1_lambdas(
    sample: OfflineModelSample,
    coefficients: list[float] | tuple[float, ...],
    competitions: tuple[str, ...],
) -> tuple[float, float]:
    home_row, away_row = _r4_1_feature_rows(sample, competitions)
    lambdas = []
    for row in (home_row, away_row):
        log_mu = _clamp(
            sum(coef * value for coef, value in zip(coefficients, row, strict=True)),
            -3.0,
            2.0,
        )
        lambdas.append(_clamp(math.exp(log_mu), 0.05, 4.25))
    return lambdas[0], lambdas[1]


def _r4_1_predictions(
    samples: list[OfflineModelSample],
    model: OfflineLambdaModel,
) -> list[dict]:
    rho = _rho_from_model(model)
    competitions = tuple(
        name.removeprefix("home_field__")
        for name in model.feature_names
        if name.startswith("home_field__")
    )
    rows = []
    for sample in samples:
        coefficients = model.coefficients[: 5 + len(competitions)]
        home_mu, away_mu = _r4_1_lambdas(sample, coefficients, competitions)
        probabilities = _dc_one_x_two(home_mu, away_mu, rho)
        rows.append(_prediction_row(fixture=sample.fixture, probabilities=probabilities))
    return rows


def _rho_from_model(model: OfflineLambdaModel) -> float:
    for name in model.feature_names:
        if name.startswith("dixon_coles_rho="):
            return float(name.split("=", 1)[1])
    return 0.0


def _dc_score_probability(
    home_goals: int,
    away_goals: int,
    home_mu: float,
    away_mu: float,
    rho: float,
) -> float:
    base = math.exp(-home_mu) * (home_mu**home_goals) / math.factorial(home_goals)
    base *= math.exp(-away_mu) * (away_mu**away_goals) / math.factorial(away_goals)
    return max(base * tau_correction(home_goals, away_goals, home_mu, away_mu, rho), 0.0)


def _dc_one_x_two(
    home_mu: float,
    away_mu: float,
    rho: float,
    *,
    max_goals: int = 10,
) -> dict[str, float]:
    matrix = {
        (home, away): _dc_score_probability(home, away, home_mu, away_mu, rho)
        for home in range(max_goals + 1)
        for away in range(max_goals + 1)
    }
    total = sum(matrix.values())
    if total <= 0:
        return {"HOME": 1 / 3, "DRAW": 1 / 3, "AWAY": 1 / 3}
    normalized = {score: probability / total for score, probability in matrix.items()}
    return one_x_two_from_matrix(normalized)


def enrich_rows(pred_rows: list[dict], samples, split: str) -> list[dict]:
    """Attach kickoff/team names (needed for the market join) to prediction rows."""
    by_id = {sample.fixture.fixture_id: sample.fixture for sample in samples}
    out = []
    for row in pred_rows:
        fixture = by_id[row["fixture_id"]]
        enriched = dict(row)
        enriched["kickoff_utc"] = fixture.kickoff_utc.isoformat()
        enriched["home_team"] = fixture.home_team
        enriched["away_team"] = fixture.away_team
        enriched["split"] = split
        out.append(enriched)
    return out


def eval_protocol(
    samples,
    train_filter,
    val_filter,
    protocol: str,
    competition: str,
    r4_1_samples: list[OfflineModelSample] | None = None,
) -> dict:
    train_samples = [s for s in samples if train_filter(s)]
    val_samples = [s for s in samples if val_filter(s)]
    if len(train_samples) < MIN_LAMBDA_FIT_SAMPLE or len(val_samples) < 30:
        return {
            "protocol": protocol,
            "competition": competition,
            "status": "INSUFFICIENT_SAMPLE",
            "train_n": len(train_samples),
            "validation_n": len(val_samples),
        }
    result = fit_and_predict(train_samples, val_samples)
    r4_1_result = None
    if r4_1_samples is not None:
        train_ids = {sample.fixture.fixture_id for sample in train_samples}
        val_ids = {sample.fixture.fixture_id for sample in val_samples}
        r4_1_train = [s for s in r4_1_samples if s.fixture.fixture_id in train_ids]
        r4_1_val = [s for s in r4_1_samples if s.fixture.fixture_id in val_ids]
        if len(r4_1_train) >= MIN_LAMBDA_FIT_SAMPLE and len(r4_1_val) >= 30:
            r4_1_result = fit_and_predict_r4_1(r4_1_train, r4_1_val)
    manifest_rows: list[dict] = []
    for split, samp in (("train", train_samples), ("validation", val_samples)):
        variants = result[split if split == "train" else "validation"]
        base = {
            row["fixture_id"]: dict(row) for row in enrich_rows(
                variants["fitted_calibrated"], samp, split
            )
        }
        for variant in ("baseline_prior", "elo_only", "uniform"):
            for row in variants[variant]:
                base[row["fixture_id"]][f"probabilities_{variant}"] = row["probabilities"]
        if r4_1_result is not None:
            r4_1_rows = (
                r4_1_result["train_calibrated"]
                if split == "train"
                else r4_1_result["validation_calibrated"]
            )
            for row in r4_1_rows:
                if row["fixture_id"] in base:
                    base[row["fixture_id"]]["probabilities_r4_1_calibrated"] = row[
                        "probabilities"
                    ]
        _attach_divergence_champion_rows(list(base.values()))
        manifest_rows.extend(base.values())
    validation_manifest_rows = [
        row for row in manifest_rows if row.get("split") == "validation"
    ]
    validation_champion = (
        metric_block(
            [
                {**row, "probabilities": row["probabilities_divergence_champion"]}
                for row in validation_manifest_rows
            ]
        )
        if validation_manifest_rows
        and all("probabilities_divergence_champion" in row for row in validation_manifest_rows)
        else None
    )
    report = {
        "protocol": protocol,
        "competition": competition,
        "status": "OK",
        "temperature": result["temperature"],
        "coefficients": [round(c, 6) for c in result["model"].coefficients],
        "train": {
            "fitted_calibrated": metric_block(result["train"]["fitted_calibrated"]),
        },
        "validation": {
            variant: metric_block(result["validation"][variant])
            for variant in ("fitted_calibrated", "baseline_prior", "elo_only", "uniform")
        },
    }
    if validation_champion is not None:
        report["validation"]["divergence_champion"] = validation_champion
    if r4_1_result is not None:
        report["r4_1"] = {
            "temperature": r4_1_result["temperature"],
            "coefficients": [round(c, 6) for c in r4_1_result["model"].coefficients],
            "feature_names": list(r4_1_result["model"].feature_names),
            "policy": {
                "dixon_coles_rho": _rho_from_model(r4_1_result["model"]),
                "time_decay_half_life_days": R4_1_TIME_DECAY_HALF_LIFE_DAYS,
                "window_matches": R4_1_WINDOW_MATCHES,
                "league_specific_home_terms": True,
                "opponent_strength_adjusted_xg": True,
            },
            "validation": metric_block(r4_1_result["validation_calibrated"]),
            "delta_log_loss_vs_fitted": (
                round(
                    metric_block(r4_1_result["validation_calibrated"])["log_loss"]
                    - report["validation"]["fitted_calibrated"]["log_loss"],
                    6,
                )
                if report["validation"]["fitted_calibrated"]["log_loss"] is not None
                else None
            ),
        }
    return {"report": report, "manifest_rows": manifest_rows}


def _attach_divergence_champion_rows(rows: list[dict]) -> None:
    for row in rows:
        fitted = row.get("probabilities")
        if not isinstance(fitted, dict):
            continue
        r4_1 = row.get("probabilities_r4_1_calibrated")
        selection = select_divergence_champion_probabilities(
            competition_id=str(row.get("competition_id") or ""),
            fitted_calibrated=fitted,
            r4_1_calibrated=r4_1 if isinstance(r4_1, dict) else None,
        )
        row["probabilities_divergence_champion"] = dict(selection.probabilities)
        row["divergence_model_family"] = selection.family.value
        if selection.fallback_reason:
            row["divergence_model_fallback_reason"] = selection.fallback_reason


def r4_1_offline_model_samples(
    *,
    fixtures,
    statistics_by_fixture: dict[str, dict[str, float]],
    min_history: int,
) -> list[OfflineModelSample]:
    builders: dict[str, AsOfFeatureBuilder] = {}
    histories: dict[tuple[str, str], list[tuple[float, float]]] = {}
    samples: list[OfflineModelSample] = []
    for fixture in sorted(
        fixtures,
        key=lambda item: (item.kickoff_utc, item.competition_id, item.fixture_id),
    ):
        builder = builders.setdefault(fixture.competition_id, AsOfFeatureBuilder())
        match = MatchRecord(
            fixture_id=fixture.fixture_id,
            competition=fixture.competition_id,
            season=fixture.season,
            kickoff_utc=fixture.kickoff_utc,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            home_goals=fixture.home_goals,
            away_goals=fixture.away_goals,
            neutral_site=fixture.neutral_site,
        )
        proxy_features = builder.features(match)
        home_key = (fixture.competition_id, fixture.home_team)
        away_key = (fixture.competition_id, fixture.away_team)
        home_history = histories.get(home_key, [])
        away_history = histories.get(away_key, [])
        current_xg = statistics_by_fixture.get(fixture.fixture_id)
        if current_xg and len(home_history) >= min_history and len(away_history) >= min_history:
            true_features = dict(proxy_features)
            true_features.update(
                _r4_1_strength_features(
                    competition_id=fixture.competition_id,
                    histories=histories,
                    home_key=home_key,
                    away_key=away_key,
                )
            )
            samples.append(
                OfflineModelSample(
                    fixture=fixture,
                    proxy_features=dict(proxy_features),
                    true_features=true_features,
                )
            )
        builder.update(match)
        if current_xg is not None:
            home_xg = current_xg.get(fixture.home_team)
            away_xg = current_xg.get(fixture.away_team)
            if home_xg is not None and away_xg is not None:
                histories.setdefault(home_key, []).append((home_xg, away_xg))
                histories.setdefault(away_key, []).append((away_xg, home_xg))
    return samples


def _r4_1_strength_features(
    *,
    competition_id: str,
    histories: dict[tuple[str, str], list[tuple[float, float]]],
    home_key: tuple[str, str],
    away_key: tuple[str, str],
) -> dict[str, float]:
    home_recent = histories[home_key][-R4_1_WINDOW_MATCHES:]
    away_recent = histories[away_key][-R4_1_WINDOW_MATCHES:]
    league_recent = [
        item
        for (league, _team), history in histories.items()
        if league == competition_id
        for item in history[-R4_1_WINDOW_MATCHES:]
    ]
    league_for = _mean([item[0] for item in league_recent], default=1.25)
    league_against = _mean([item[1] for item in league_recent], default=1.25)
    home_for = _mean([item[0] for item in home_recent], default=league_for)
    home_against = _mean([item[1] for item in home_recent], default=league_against)
    away_for = _mean([item[0] for item in away_recent], default=league_for)
    away_against = _mean([item[1] for item in away_recent], default=league_against)
    home_attack = home_for * _safe_ratio(away_against, league_against)
    away_attack = away_for * _safe_ratio(home_against, league_against)
    home_defence = home_against * _safe_ratio(away_for, league_for)
    away_defence = away_against * _safe_ratio(home_for, league_for)
    return {
        "home_attack_strength": _clamp(home_attack, 0.25, 3.5),
        "away_attack_strength": _clamp(away_attack, 0.25, 3.5),
        "home_defence_strength": _clamp(home_defence, 0.25, 3.5),
        "away_defence_strength": _clamp(away_defence, 0.25, 3.5),
        "rolling_home_xg": round(home_for, 6),
        "rolling_away_xg": round(away_for, 6),
    }


def _mean(values: list[float], *, default: float) -> float:
    return sum(values) / len(values) if values else default


def _safe_ratio(value: float, denominator: float) -> float:
    return value / denominator if denominator > 0 else 1.0


def run_model_phase() -> dict:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    registry_entries = CompetitionRegistry().entries()
    outputs: list[dict] = []
    manifests: dict[str, list[dict]] = {}

    # --- big-5 (Understat cache, replicating #193/#196) ---
    big5_fixtures, big5_stats = load_understat_fixture_dataset(
        raw_dirs=UNDERSTAT_DIRS,
        seasons=BIG5_SEASONS,
        competitions=list(TOP_FIVE_COMPETITIONS),
    )
    big5_samples = _offline_model_samples(
        fixtures=big5_fixtures, statistics_by_fixture=big5_stats, min_history=MIN_HISTORY
    )
    big5_r4_1_samples = r4_1_offline_model_samples(
        fixtures=big5_fixtures, statistics_by_fixture=big5_stats, min_history=MIN_HISTORY
    )
    # P0 replicate: pooled big-5, chronological 70/30 (single split).
    split_at = max(MIN_LAMBDA_FIT_SAMPLE, int(len(big5_samples) * 0.7))
    indexed = {id(s): i for i, s in enumerate(big5_samples)}
    res = eval_protocol(
        big5_samples,
        lambda s: indexed[id(s)] < split_at,
        lambda s: indexed[id(s)] >= split_at,
        "big5_pooled_70_30",
        "big5_pooled",
        r4_1_samples=big5_r4_1_samples,
    )
    outputs.append(res["report"] if "report" in res else res)
    if "manifest_rows" in res:
        manifests["big5_pooled_70_30"] = res["manifest_rows"]

    # P1 cross-season 2023 -> 2024 (primary market-phase protocol for big-5:
    # train fully precedes validation; validation season = 2024/25 CSVs).
    res = eval_protocol(
        big5_samples,
        lambda s: s.fixture.season == "2023",
        lambda s: s.fixture.season == "2024",
        "big5_cross_season_2023_to_2024",
        "big5_pooled",
        r4_1_samples=big5_r4_1_samples,
    )
    outputs.append(res["report"] if "report" in res else res)
    if "manifest_rows" in res:
        manifests["big5_cross_season_2023_to_2024"] = res["manifest_rows"]
        # per-league validation slices
        for competition in TOP_FIVE_COMPETITIONS:
            rows = [
                r for r in res["manifest_rows"]
                if r["competition_id"] == competition and r["split"] == "validation"
            ]
            if rows:
                outputs.append(
                    {
                        "protocol": "big5_cross_season_2023_to_2024",
                        "competition": competition,
                        "status": "OK_SLICE",
                        "validation": {
                            "fitted_calibrated": metric_block(rows),
                            "divergence_champion": metric_block(
                                [
                                    {**r, "probabilities": r["probabilities_divergence_champion"]}
                                    for r in rows
                                    if "probabilities_divergence_champion" in r
                                ]
                            ),
                            "baseline_prior": metric_block(
                                [
                                    {**r, "probabilities": r["probabilities_baseline_prior"]}
                                    for r in rows
                                ]
                            ),
                            "uniform": metric_block(
                                [{**r, "probabilities": r["probabilities_uniform"]} for r in rows]
                            ),
                        },
                    }
                )

    # --- in-season national leagues (API-Football cache; NEW experiment) ---
    stats = load_fixture_statistics(list(PRO_DAY1_DIRS))
    for competition in IN_SEASON_NATIONAL_LEAGUES:
        fixtures = []
        for season in IN_SEASON_SEASONS:
            fixtures.extend(
                load_historical_fixtures(
                    raw_dirs=list(PRO_DAY1_DIRS),
                    entries=registry_entries,
                    season=season,
                    competitions=[competition],
                )
            )
        samples = _offline_model_samples(
            fixtures=fixtures, statistics_by_fixture=stats, min_history=MIN_HISTORY
        )
        r4_1_samples = r4_1_offline_model_samples(
            fixtures=fixtures,
            statistics_by_fixture=stats,
            min_history=MIN_HISTORY,
        )
        by_season = defaultdict(int)
        for s in samples:
            by_season[s.fixture.season] += 1
        # P2 cross-season 2024 -> 2025 (primary; mirrors ledger's cross-season proof)
        res = eval_protocol(
            samples,
            lambda s: s.fixture.season == "2024",
            lambda s: s.fixture.season == "2025",
            "inseason_cross_season_2024_to_2025",
            competition,
            r4_1_samples=r4_1_samples,
        )
        report = res["report"] if "report" in res else res
        report["samples_by_season"] = dict(by_season)
        outputs.append(report)
        if "manifest_rows" in res:
            manifests[f"inseason_cross_2024_2025__{competition}"] = res["manifest_rows"]

    # pooled continuity run (all in-season leagues, matches S10 pooling style)
    all_fixtures = []
    for season in IN_SEASON_SEASONS:
        all_fixtures.extend(
            load_historical_fixtures(
                raw_dirs=list(PRO_DAY1_DIRS),
                entries=registry_entries,
                season=season,
                competitions=list(IN_SEASON_NATIONAL_LEAGUES),
            )
        )
    pooled_samples = _offline_model_samples(
        fixtures=all_fixtures, statistics_by_fixture=stats, min_history=MIN_HISTORY
    )
    pooled_r4_1_samples = r4_1_offline_model_samples(
        fixtures=all_fixtures, statistics_by_fixture=stats, min_history=MIN_HISTORY
    )
    res = eval_protocol(
        pooled_samples,
        lambda s: s.fixture.season == "2024",
        lambda s: s.fixture.season == "2025",
        "inseason_pooled_cross_season",
        "inseason_pooled",
        r4_1_samples=pooled_r4_1_samples,
    )
    outputs.append(res["report"] if "report" in res else res)
    if "manifest_rows" in res:
        manifests["inseason_pooled_cross_season"] = res["manifest_rows"]
        # Per-league validation slices under the pooled fit (small leagues
        # cannot reach MIN_LAMBDA_FIT_SAMPLE=200 alone; pooling the fit across
        # leagues mirrors how #193 pooled the big-5 fit).
        for competition in IN_SEASON_NATIONAL_LEAGUES:
            rows = [
                r for r in res["manifest_rows"]
                if r["competition_id"] == competition and r["split"] == "validation"
            ]
            if rows:
                outputs.append(
                    {
                        "protocol": "inseason_pooled_fit_league_slice",
                        "competition": competition,
                        "status": "OK_SLICE",
                        "validation": {
                            "fitted_calibrated": metric_block(rows),
                            "divergence_champion": metric_block(
                                [
                                    {**r, "probabilities": r["probabilities_divergence_champion"]}
                                    for r in rows
                                    if "probabilities_divergence_champion" in r
                                ]
                            ),
                            "baseline_prior": metric_block(
                                [
                                    {**r, "probabilities": r["probabilities_baseline_prior"]}
                                    for r in rows
                                ]
                            ),
                            "uniform": metric_block(
                                [{**r, "probabilities": r["probabilities_uniform"]} for r in rows]
                            ),
                        },
                    }
                )
            # market join should use the pooled-fit manifest for these leagues
            manifests[f"inseason_pooled_fit__{competition}"] = [
                r for r in res["manifest_rows"] if r["competition_id"] == competition
            ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in manifests.items():
        with (MANIFEST_DIR / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    report = {
        "schema_version": "w2.market_baseline_eval.model_phase.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "read_only": True,
        "provider_calls": 0,
        "notes": [
            "big5 source: Understat cache (runtime/w2_understat_model_iter1).",
            "in-season source: API-Football Pro day1 cache (fixtures + statistics xG).",
            "fitted model protocol identical to #193: train-only lambda fit + temperature.",
            "R4.1 variant is eval-only: Dixon-Coles rho, time-decay weights,"
            " league-specific home coefficients, and windowed opponent-adjusted xG.",
            "Ledger's in-season ~1.05 came from the unfitted hand-prior walk-forward model;"
            " the fitted numbers here are the first like-for-like comparison.",
        ],
        "results": outputs,
    }
    (OUT_DIR / "model_phase_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )
    return report


# --------------------------------------------------------------------------
# MARKET phase
# --------------------------------------------------------------------------
def normalize_name(name: str, *, drop_generic_words: bool = True) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    words = text.split()
    if drop_generic_words:
        words = [word for word in words if word not in GENERIC_TEAM_WORDS]
    return " ".join(words).strip()


def canonical(name: str) -> str:
    # Alias lookup must run before generic-word removal too, otherwise names
    # like "Athletic Club" / "FC Cologne" lose their distinguishing word
    # before they can be aliased.
    full = normalize_name(name, drop_generic_words=False)
    if full in TEAM_ALIASES:
        return normalize_name(TEAM_ALIASES[full])
    norm = normalize_name(name)
    return normalize_name(TEAM_ALIASES.get(norm, norm))


def parse_fd_date(raw: str) -> datetime | None:
    raw = raw.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def load_football_data_rows(competition: str, spec: dict, seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    if spec["kind"] == "big5":
        for season, filename in spec["files"].items():
            if season not in seasons:
                continue
            path = FOOTBALL_DATA_DIR / filename
            if not path.exists():
                continue
            rows.extend(_read_fd_csv(path, season=season, big5=True))
    else:
        path = FOOTBALL_DATA_DIR / str(spec["file"])
        if path.exists():
            rows.extend(
                r for r in _read_fd_csv(path, season=None, big5=False) if r["season"] in seasons
            )
    return rows


def _read_fd_csv(path: Path, *, season: str | None, big5: bool) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        for record in csv.DictReader(fh):
            record = {k.strip(): (v or "").strip() for k, v in record.items() if k}
            date = parse_fd_date(record.get("Date", ""))
            if date is None:
                continue
            home = record.get("HomeTeam") or record.get("Home") or ""
            away = record.get("AwayTeam") or record.get("Away") or ""
            goals_h = record.get("FTHG") or record.get("HG")
            goals_a = record.get("FTAG") or record.get("AG")
            if not home or not away or goals_h in ("", None) or goals_a in ("", None):
                continue
            odds, odds_source = None, None
            for prefix, label in (("PSC", "pinnacle_closing"), ("AvgC", "avg_closing"),
                                  ("PS", "pinnacle"), ("Avg", "avg"), ("B365C", "b365_closing"),
                                  ("B365", "b365")):
                try:
                    trio = (
                        float(record.get(f"{prefix}H", "")),
                        float(record.get(f"{prefix}D", "")),
                        float(record.get(f"{prefix}A", "")),
                    )
                    if all(v > 1.0 for v in trio):
                        odds, odds_source = trio, label
                        break
                except (TypeError, ValueError):
                    continue
            if odds is None:
                continue
            inv = [1.0 / v for v in odds]
            overround = sum(inv)
            out.append(
                {
                    "date": date,
                    "season": season or record.get("Season", ""),
                    "home_raw": home,
                    "away_raw": away,
                    "home": canonical(home),
                    "away": canonical(away),
                    "result": "HOME" if int(goals_h) > int(goals_a) else
                              "AWAY" if int(goals_h) < int(goals_a) else "DRAW",
                    "market_probabilities": {
                        "HOME": inv[0] / overround,
                        "DRAW": inv[1] / overround,
                        "AWAY": inv[2] / overround,
                    },
                    "overround": overround,
                    "odds_source": odds_source,
                }
            )
    return out


def fuzzy_equal(a: str, b: str) -> bool:
    if a == b:
        return True
    if a and b and (a in b or b in a) and min(len(a), len(b)) >= 5:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.78


def join_manifest_to_market(
    manifest_rows: list[dict], market_rows: list[dict]
) -> tuple[list[dict], dict]:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in market_rows:
        by_date[row["date"].strftime("%Y-%m-%d")].append(row)
    joined, unmatched, result_conflicts = [], [], 0
    for row in manifest_rows:
        kickoff = datetime.fromisoformat(str(row["kickoff_utc"]))
        home, away = canonical(row["home_team"]), canonical(row["away_team"])
        candidates = []
        for delta in (0, -1, 1):
            key = (kickoff + timedelta(days=delta)).strftime("%Y-%m-%d")
            candidates.extend(by_date.get(key, []))
        match = None
        for cand in candidates:
            if fuzzy_equal(home, cand["home"]) and fuzzy_equal(away, cand["away"]):
                match = cand
                break
        if match is None:
            unmatched.append({"home": row["home_team"], "away": row["away_team"],
                              "kickoff": str(row["kickoff_utc"])})
            continue
        if match["result"] != row["actual"]:
            result_conflicts += 1  # wrong join guard: drop
            continue
        merged = dict(row)
        merged["market_probabilities"] = match["market_probabilities"]
        merged["overround"] = match["overround"]
        merged["odds_source"] = match["odds_source"]
        joined.append(merged)
    diagnostics = {
        "manifest_rows": len(manifest_rows),
        "joined": len(joined),
        "unmatched": len(unmatched),
        "result_conflicts_dropped": result_conflicts,
        "join_rate": round(len(joined) / len(manifest_rows), 4) if manifest_rows else None,
        "unmatched_examples": unmatched[:12],
    }
    return joined, diagnostics


def blend_probs(p_model: dict, p_market: dict, w: float) -> dict:
    blended = {
        k: max(float(p_model[k]), 1e-12) ** (1 - w) * max(float(p_market[k]), 1e-12) ** w
        for k in ("HOME", "DRAW", "AWAY")
    }
    total = sum(blended.values())
    return {k: v / total for k, v in blended.items()}


def eval_market_league(joined: list[dict]) -> dict:
    train = [r for r in joined if r["split"] == "train"]
    val = [r for r in joined if r["split"] == "validation"]
    if len(val) < 30:
        return {
            "status": "INSUFFICIENT_JOINED_VALIDATION",
            "train_n": len(train),
            "val_n": len(val),
        }

    def rows_with(rows, key) -> list[dict]:
        return [{**r, "probabilities": r[key]} for r in rows]

    # blend weight fit on train only
    best_w, best_ll = 0.0, float("inf")
    if len(train) >= 50:
        for step in range(0, 21):
            w = step / 20.0
            ll = log_loss(
                [
                    {**r, "probabilities": blend_probs(
                        r["probabilities"], r["market_probabilities"], w)}
                    for r in train
                ]
            )
            if ll < best_ll:
                best_ll, best_w = ll, w
    else:
        best_w = None

    val_model = metric_block(val)
    val_r4_1 = (
        metric_block(rows_with(val, "probabilities_r4_1_calibrated"))
        if all("probabilities_r4_1_calibrated" in r for r in val)
        else None
    )
    val_champion = (
        metric_block(rows_with(val, "probabilities_divergence_champion"))
        if all("probabilities_divergence_champion" in r for r in val)
        else val_model
    )
    val_market = metric_block(rows_with(val, "market_probabilities"))
    val_prior = metric_block(rows_with(val, "probabilities_baseline_prior"))
    fitted_gap = (
        round(val_model["log_loss"] - val_market["log_loss"], 6)
        if val_model["log_loss"] is not None and val_market["log_loss"] is not None
        else None
    )
    r4_1_gap = (
        round(val_r4_1["log_loss"] - val_market["log_loss"], 6)
        if val_r4_1 and val_r4_1["log_loss"] is not None and val_market["log_loss"] is not None
        else None
    )
    champion_gap = (
        round(val_champion["log_loss"] - val_market["log_loss"], 6)
        if val_champion["log_loss"] is not None and val_market["log_loss"] is not None
        else None
    )
    champion_families = {
        str(r.get("divergence_model_family") or DivergenceModelFamily.FITTED_CALIBRATED.value)
        for r in val
    }
    champion_family = (
        next(iter(champion_families))
        if len(champion_families) == 1
        else "MIXED"
    )
    out = {
        "status": "OK",
        "train_n": len(train),
        "validation_n": len(val),
        "odds_source": val[0]["odds_source"] if val else None,
        "mean_overround": round(sum(r["overround"] for r in val) / len(val), 4),
        "validation": {
            "fitted_calibrated": val_model,
            "r4_1_calibrated": val_r4_1,
            "divergence_champion": val_champion,
            "market_devig": val_market,
            "baseline_prior": val_prior,
            "uniform": metric_block(rows_with(val, "probabilities_uniform")),
        },
        "gap_model_minus_market_log_loss": fitted_gap,
        "gap_r4_1_minus_market_log_loss": r4_1_gap,
        "gap_divergence_champion_minus_market_log_loss": champion_gap,
        "divergence_champion_model_family": champion_family,
        "divergence_champion_gap_delta_vs_fitted": (
            round(champion_gap - fitted_gap, 6)
            if champion_gap is not None and fitted_gap is not None
            else None
        ),
        "r4_1_gap_delta_vs_fitted": (
            round(r4_1_gap - fitted_gap, 6)
            if r4_1_gap is not None and fitted_gap is not None
            else None
        ),
        "r4_1_league_gate": (
            "PASS_GAP_DECREASED"
            if r4_1_gap is not None and fitted_gap is not None and r4_1_gap < fitted_gap
            else "FAIL_GAP_NOT_DECREASED"
            if r4_1_gap is not None and fitted_gap is not None
            else "NOT_EVALUATED"
        ),
    }
    if best_w is not None:
        blended_val = [
            {**r, "probabilities": blend_probs(
                r["probabilities"], r["market_probabilities"], best_w)}
            for r in val
        ]
        out["blend"] = {
            "w_market_fit_on_train": best_w,
            "validation_blend": metric_block(blended_val),
        }
    # cold-start slice: either team has < COLD_START_MATCHES prior matches that
    # season (within the manifest ordering, which is walk-forward).
    season_counts: dict[tuple[str, str], int] = defaultdict(int)
    cold_rows, warm_rows = [], []
    for r in sorted(val + train, key=lambda x: str(x["kickoff_utc"])):
        season = r["season"]
        h_key, a_key = (season, r["home_team"]), (season, r["away_team"])
        is_cold = season_counts[h_key] < COLD_START_MATCHES or (
            season_counts[a_key] < COLD_START_MATCHES
        )
        if r["split"] == "validation":
            (cold_rows if is_cold else warm_rows).append(r)
        season_counts[h_key] += 1
        season_counts[a_key] += 1
    if cold_rows and warm_rows:
        out["cold_start"] = {
            "cold_n": len(cold_rows),
            "model_cold": metric_block(cold_rows),
            "market_cold": metric_block(rows_with(cold_rows, "market_probabilities")),
            "model_warm": metric_block(warm_rows),
            "market_warm": metric_block(rows_with(warm_rows, "market_probabilities")),
        }
    return out


def run_market_phase() -> dict:
    if not FOOTBALL_DATA_DIR.exists() or not any(FOOTBALL_DATA_DIR.glob("*.csv")):
        return {
            "status": "WAITING_FOR_DATA",
            "message": (
                f"Drop football-data.co.uk CSVs into {FOOTBALL_DATA_DIR} "
                "(see FOOTBALL_DATA_FILES in this script for expected names)."
            ),
        }
    results = {}
    # big-5: use the cross-season manifest (validation season 2024 = 2024/25 CSVs)
    manifest_path = MANIFEST_DIR / "big5_cross_season_2023_to_2024.jsonl"
    if manifest_path.exists():
        rows = [json.loads(line) for line in manifest_path.open()]
        for competition in TOP_FIVE_COMPETITIONS:
            spec = FOOTBALL_DATA_FILES.get(competition)
            comp_rows = [r for r in rows if r["competition_id"] == competition]
            if not spec or not comp_rows:
                continue
            market_rows = load_football_data_rows(competition, spec, list(BIG5_SEASONS))
            if not market_rows:
                results[competition] = {"status": "CSV_MISSING"}
                continue
            joined, diagnostics = join_manifest_to_market(comp_rows, market_rows)
            evaluation = eval_market_league(joined)
            evaluation["join"] = diagnostics
            results[competition] = evaluation
    # in-season leagues
    for competition in IN_SEASON_NATIONAL_LEAGUES:
        manifest_path = MANIFEST_DIR / f"inseason_pooled_fit__{competition}.jsonl"
        spec = FOOTBALL_DATA_FILES.get(competition)
        if not manifest_path.exists() or spec is None:
            continue
        rows = [json.loads(line) for line in manifest_path.open()]
        market_rows = load_football_data_rows(competition, spec, list(IN_SEASON_SEASONS))
        if not market_rows:
            results[competition] = {"status": "CSV_MISSING"}
            continue
        joined, diagnostics = join_manifest_to_market(rows, market_rows)
        evaluation = eval_market_league(joined)
        evaluation["join"] = diagnostics
        results[competition] = evaluation

    report = {
        "schema_version": "w2.market_baseline_eval.market_phase.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "read_only": True,
        "provider_calls": 0,
        "devig_method": "proportional (1/odds normalized); overround reported",
        "results": results,
    }
    (OUT_DIR / "market_phase_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str)
    )
    _write_summary_md(report)
    return report


def _write_summary_md(report: dict) -> None:
    lines = [
        "# W2 模型 vs 市场基准对照(去 vig 收盘)",
        "",
        f"生成时间:{report['generated_at']}  ·  devig:proportional  ·  只读/零 provider calls",
        "",
        "| 联赛 | n(val joined) | champion | champion LL | champion gap "
        "| 原模型 LL | R4.1 LL | 市场 LL | 原 gap | R4.1 gap | Δgap "
        "| R4.1 gate | blend LL (w_mkt) | 先验 LL | join 率 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for comp, res in report["results"].items():
        if res.get("status") != "OK":
            lines.append(
                f"| {comp} | — | — | — | — | — | — | — | — | — | — "
                f"| {res.get('status')} | — | — | — |"
            )
            continue
        v = res["validation"]
        blend = res.get("blend", {})
        blend_text = (
            f"{blend.get('validation_blend', {}).get('log_loss', '—')}"
            f" (w={blend.get('w_market_fit_on_train', '—')})"
            if blend else "—"
        )
        lines.append(
            f"| {comp} | {v['fitted_calibrated']['n']} "
            f"| {res.get('divergence_champion_model_family', '—')} "
            f"| {_metric_text(v.get('divergence_champion'), 'log_loss')} "
            f"| {_signed_metric_text(res.get('gap_divergence_champion_minus_market_log_loss'))} "
            f"| {v['fitted_calibrated']['log_loss']} "
            f"| {_metric_text(v.get('r4_1_calibrated'), 'log_loss')} "
            f"| {v['market_devig']['log_loss']} "
            f"| {res['gap_model_minus_market_log_loss']:+.4f} "
            f"| {_signed_metric_text(res.get('gap_r4_1_minus_market_log_loss'))} "
            f"| {_signed_metric_text(res.get('r4_1_gap_delta_vs_fitted'))} "
            f"| {res.get('r4_1_league_gate', '—')} "
            f"| {blend_text} "
            f"| {v['baseline_prior']['log_loss']} "
            f"| {res['join']['join_rate']} |"
        )
    (OUT_DIR / "W2_MARKET_BASELINE_SUMMARY.md").write_text("\n".join(lines) + "\n")


def _metric_text(block: dict | None, key: str) -> str:
    if not block:
        return "—"
    value = block.get(key)
    return "—" if value is None else str(value)


def _signed_metric_text(value: float | None) -> str:
    return "—" if value is None else f"{value:+.4f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("model", "market", "all"), default="all")
    args = parser.parse_args()
    if args.phase in ("model", "all"):
        report = run_model_phase()
        print(json.dumps(_model_digest(report), indent=2, ensure_ascii=False))
    if args.phase in ("market", "all"):
        report = run_market_phase()
        if report.get("status") == "WAITING_FOR_DATA":
            print(report["message"])
        else:
            print((OUT_DIR / "W2_MARKET_BASELINE_SUMMARY.md").read_text())
    return 0


def _model_digest(report: dict) -> list[dict]:
    digest = []
    for item in report["results"]:
        if item.get("status") not in ("OK", "OK_SLICE"):
            digest.append(item)
            continue
        entry = {
            "protocol": item["protocol"],
            "competition": item["competition"],
            "val_fitted": item["validation"]["fitted_calibrated"],
            "val_divergence_champion": item["validation"].get("divergence_champion"),
            "val_prior": item["validation"].get("baseline_prior"),
        }
        digest.append(entry)
    return digest


if __name__ == "__main__":
    raise SystemExit(main())
