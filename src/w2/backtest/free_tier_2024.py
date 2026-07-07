from __future__ import annotations

import hashlib
import json
import math
import time
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from w2.competitions.league_whitelist_scope import (
    IN_SEASON_NATIONAL_LEAGUES,
    NATIONAL_LEAGUES_OFFSEASON,
    TOP_FIVE_COMPETITIONS,
)
from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryEntry
from w2.domain.time import require_utc
from w2.models.evaluation import EvaluationRow, metrics, reliability
from w2.models.independent import (
    AsOfFeatureBuilder,
    MatchRecord,
    ModelFamily,
    artifact_hash,
    predict_from_features,
    prediction_from_lambdas,
)
from w2.providers.quota import parse_api_football_quota

FREE_TIER_2024_BACKTEST_VERSION = "w2.free_tier_2024_backtest.v1"
ANNUAL_COMPETITIONS = (
    *TOP_FIVE_COMPETITIONS,
    *IN_SEASON_NATIONAL_LEAGUES,
    *NATIONAL_LEAGUES_OFFSEASON,
)
DEFAULT_RAW_DIRS = (Path("runtime/w2_free_tier_2024/raw"), Path("runtime/stage5b/raw"))
MIN_READY_SAMPLE = 200
MIN_OBSERVING_SAMPLE = 30
MIN_LAMBDA_FIT_SAMPLE = 200
DEFAULT_UNDERSTAT_CACHE_DIR = Path("runtime/w2_understat_xg")
UNDERSTAT_XG_SOURCE = "understat_xg_local"
UNDERSTAT_LEAGUE_CODES = {
    "premier_league": "EPL",
    "la_liga": "La_liga",
    "bundesliga": "Bundesliga",
    "serie_a": "Serie_A",
    "ligue_1": "Ligue_1",
}
UNDERSTAT_TEAM_ALIASES = {
    "Newcastle United": "Newcastle",
    "Wolverhampton Wanderers": "Wolves",
}
MODEL_ITERATION_COMPETITIONS = tuple(UNDERSTAT_LEAGUE_CODES)


@dataclass(frozen=True, kw_only=True)
class HistoricalFixture:
    fixture_id: str
    competition_id: str
    league_id: str
    season: str
    kickoff_utc: datetime
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    neutral_site: bool
    raw_source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kickoff_utc", require_utc(self.kickoff_utc, "kickoff_utc"))

    @property
    def actual(self) -> str:
        if self.home_goals > self.away_goals:
            return "HOME"
        if self.home_goals == self.away_goals:
            return "DRAW"
        return "AWAY"


@dataclass(frozen=True, kw_only=True)
class ProviderFetchResult:
    provider_calls: int
    written_files: tuple[str, ...]
    skipped_existing: tuple[str, ...]
    stopped_reason: str | None
    ledger: tuple[dict[str, Any], ...]


@dataclass(frozen=True, kw_only=True)
class UnderstatFetchResult:
    provider_calls: int
    understat_requests: int
    cache_path: str
    skipped_existing: bool
    fixture_count: int


@dataclass
class RollingXgState:
    xg_for_total: float = 0.0
    xg_against_total: float = 0.0
    matches: int = 0

    @property
    def xg_for(self) -> float:
        return self.xg_for_total / self.matches if self.matches else 0.0

    @property
    def xg_against(self) -> float:
        return self.xg_against_total / self.matches if self.matches else 0.0


@dataclass(frozen=True, kw_only=True)
class OfflineModelSample:
    fixture: HistoricalFixture
    proxy_features: dict[str, Any]
    true_features: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class OfflineLambdaModel:
    coefficients: tuple[float, ...]
    feature_names: tuple[str, ...]
    l2: float
    iterations: int
    learning_rate: float


ApiFootballRequester = Callable[[str, dict[str, str]], tuple[int, dict[str, str], dict[str, Any]]]
UnderstatRequester = Callable[[str, str], dict[str, Any]]


def build_free_tier_2024_backtest_report(
    *,
    raw_dirs: Sequence[Path] = DEFAULT_RAW_DIRS,
    season: str = "2024",
    competitions: Sequence[str] = ANNUAL_COMPETITIONS,
    true_xg_source: str = "api_football_statistics",
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = (generated_at or datetime.now(UTC)).astimezone(UTC)
    registry = CompetitionRegistry()
    entries = registry.entries()
    fixtures = load_historical_fixtures(
        raw_dirs=raw_dirs,
        entries=entries,
        season=season,
        competitions=competitions,
    )
    predictions = build_walk_forward_predictions(fixtures)
    rows = [
        EvaluationRow(
            fixture_id=item["fixture_id"],
            actual=item["actual"],
            probabilities=item["probabilities"],
            competition=item["competition_id"],
            season=item["season"],
            neutral_site=bool(item["neutral_site"]),
        )
        for item in predictions
    ]
    by_competition = {
        competition_id: _slice_report(
            [row for row in rows if row.competition == competition_id],
            predictions=[item for item in predictions if item["competition_id"] == competition_id],
        )
        for competition_id in competitions
    }
    covered_competitions = sorted(
        {row.competition for row in rows},
        key=lambda item: competitions.index(item) if item in competitions else 999,
    )
    missing_competitions = [item for item in competitions if item not in covered_competitions]
    input_coverage = _input_coverage(
        raw_dirs=raw_dirs,
        entries=entries,
        season=season,
        competitions=competitions,
    )
    true_xg_statistics = (
        load_understat_xg_statistics(
            raw_dirs=raw_dirs,
            fixtures=fixtures,
            league_code="EPL",
            season=season,
        )
        if true_xg_source == UNDERSTAT_XG_SOURCE
        else load_fixture_statistics(raw_dirs)
    )
    true_xg_comparison = build_true_xg_delta_report(
        fixtures=fixtures,
        statistics_by_fixture=true_xg_statistics,
        competition_id="premier_league",
        xg_source=true_xg_source,
    )
    overall = _slice_report(rows, predictions=predictions)
    calibration_status = _calibration_status(
        rows=rows,
        missing_competitions=missing_competitions,
        input_coverage=input_coverage,
    )
    return {
        "schema_version": FREE_TIER_2024_BACKTEST_VERSION,
        "generated_at": generated.isoformat().replace("+00:00", "Z"),
        "read_only": True,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "enabled_true": False,
        "staging_deploy": False,
        "production_deploy": False,
        "canonical_season_changed": False,
        "value_pick_enabled": False,
        "season": season,
        "scope": {
            "annual_competitions": list(competitions),
            "covered_competitions": covered_competitions,
            "missing_competitions": missing_competitions,
            "world_cup_excluded_reason": "2024 is not a World Cup tournament season",
        },
        "model": {
            "model_family": ModelFamily.INDEPENDENT_POISSON.value,
            "model_version": "stage7.v1",
            "leakage_guard": "features are built before each fixture result updates team state",
            "forbidden_inputs": ["odds", "market_line", "closing_price", "result_as_feature"],
        },
        "input_coverage": input_coverage,
        "overall": overall,
        "by_competition": by_competition,
        "true_xg_comparison": true_xg_comparison,
        "calibration_status": calibration_status,
        "s2_calibration_validation": _s2_summary(rows),
        "outcome_tracked_samples": _outcome_tracked_samples(predictions),
    }


def load_historical_fixtures(
    *,
    raw_dirs: Sequence[Path],
    entries: dict[str, CompetitionRegistryEntry],
    season: str,
    competitions: Sequence[str],
) -> list[HistoricalFixture]:
    by_league = {
        entries[competition_id].provider_mapping.get("api_football_league_id", ""): competition_id
        for competition_id in competitions
        if competition_id in entries
    }
    fixtures: dict[str, HistoricalFixture] = {}
    for path in _raw_files(raw_dirs, endpoint="fixtures"):
        payload = _load_json(path)
        params = _params(payload)
        league_id = str(params.get("league") or "")
        raw_season = str(params.get("season") or "")
        if league_id not in by_league or raw_season != season:
            continue
        competition_id = by_league[league_id]
        for row in _response_rows(payload):
            fixture = _fixture_from_row(
                row,
                competition_id=competition_id,
                league_id=league_id,
                season=season,
                raw_source=path.as_posix(),
            )
            if fixture is not None:
                fixtures.setdefault(fixture.fixture_id, fixture)
    return sorted(fixtures.values(), key=lambda item: (item.kickoff_utc, item.fixture_id))


def build_walk_forward_predictions(fixtures: Sequence[HistoricalFixture]) -> list[dict[str, Any]]:
    builders: dict[str, AsOfFeatureBuilder] = {}
    predictions: list[dict[str, Any]] = []
    for fixture in sorted(fixtures, key=lambda item: (item.competition_id, item.kickoff_utc)):
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
        features = builder.features(match)
        prediction = predict_from_features(
            fixture.fixture_id,
            ModelFamily.INDEPENDENT_POISSON,
            features,
            fixture.kickoff_utc,
        )
        fair_total_goals = prediction.expected_home_goals + prediction.expected_away_goals
        row = {
            "fixture_id": fixture.fixture_id,
            "competition_id": fixture.competition_id,
            "season": fixture.season,
            "kickoff_utc": fixture.kickoff_utc.isoformat().replace("+00:00", "Z"),
            "home_team": fixture.home_team,
            "away_team": fixture.away_team,
            "actual": fixture.actual,
            "actual_score": {"home": fixture.home_goals, "away": fixture.away_goals},
            "probabilities": {
                key: round(value, 6) for key, value in prediction.one_x_two.items()
            },
            "fair_line": {
                "expected_home_goals": round(prediction.expected_home_goals, 6),
                "expected_away_goals": round(prediction.expected_away_goals, 6),
                "fair_total_goals": round(fair_total_goals, 6),
            },
            "neutral_site": fixture.neutral_site,
            "data_cutoff": prediction.data_cutoff.isoformat().replace("+00:00", "Z"),
            "feature_policy": prediction.provenance.get("feature_policy"),
            "odds_free": prediction.provenance.get("odds_free") is True,
            "home_sample_size": float(features["home_sample_size"]),
            "away_sample_size": float(features["away_sample_size"]),
            "rolling_home_xg_proxy": float(features["rolling_home_xg"]),
            "rolling_away_xg_proxy": float(features["rolling_away_xg"]),
        }
        row["prediction_hash"] = artifact_hash(
            {
                "fixture_id": row["fixture_id"],
                "probabilities": row["probabilities"],
                "fair_line": row["fair_line"],
                "data_cutoff": row["data_cutoff"],
            }
        )
        predictions.append(row)
        builder.update(match)
    return predictions


def build_true_xg_delta_report(
    *,
    fixtures: Sequence[HistoricalFixture],
    statistics_by_fixture: dict[str, dict[str, float]],
    competition_id: str = "premier_league",
    xg_source: str = "api_football_statistics",
    min_history: int = 5,
) -> dict[str, Any]:
    scoped = [
        fixture
        for fixture in sorted(fixtures, key=lambda item: (item.kickoff_utc, item.fixture_id))
        if fixture.competition_id == competition_id
    ]
    proxy_builder = AsOfFeatureBuilder()
    xg_states: dict[str, RollingXgState] = {}
    proxy_predictions: list[dict[str, Any]] = []
    true_predictions: list[dict[str, Any]] = []
    for fixture in scoped:
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
        proxy_features = proxy_builder.features(match)
        home_xg_state = xg_states.get(fixture.home_team, RollingXgState())
        away_xg_state = xg_states.get(fixture.away_team, RollingXgState())
        current_xg = statistics_by_fixture.get(fixture.fixture_id)
        eligible = (
            current_xg is not None
            and home_xg_state.matches >= min_history
            and away_xg_state.matches >= min_history
        )
        if eligible:
            true_features = dict(proxy_features)
            true_features.update(
                {
                    "home_attack_strength": home_xg_state.xg_for,
                    "away_attack_strength": away_xg_state.xg_for,
                    "home_defence_strength": home_xg_state.xg_against,
                    "away_defence_strength": away_xg_state.xg_against,
                    "rolling_home_xg": home_xg_state.xg_for,
                    "rolling_away_xg": away_xg_state.xg_for,
                }
            )
            proxy_prediction = predict_from_features(
                fixture.fixture_id,
                ModelFamily.INDEPENDENT_POISSON,
                proxy_features,
                fixture.kickoff_utc,
            )
            true_prediction = predict_from_features(
                fixture.fixture_id,
                ModelFamily.INDEPENDENT_POISSON,
                true_features,
                fixture.kickoff_utc,
            )
            common = {
                "fixture_id": fixture.fixture_id,
                "competition_id": fixture.competition_id,
                "season": fixture.season,
                "actual": fixture.actual,
                "neutral_site": fixture.neutral_site,
                "prior_home_xg_for": round(home_xg_state.xg_for, 6),
                "prior_away_xg_for": round(away_xg_state.xg_for, 6),
                "home_xg_history_matches": home_xg_state.matches,
                "away_xg_history_matches": away_xg_state.matches,
                "target_fixture_xg_excluded_from_features": True,
            }
            proxy_predictions.append(
                {
                    **common,
                    "probabilities": {
                        key: round(value, 6)
                        for key, value in proxy_prediction.one_x_two.items()
                    },
                }
            )
            true_predictions.append(
                {
                    **common,
                    "probabilities": {
                        key: round(value, 6)
                        for key, value in true_prediction.one_x_two.items()
                    },
                }
            )
        proxy_builder.update(match)
        if current_xg is not None:
            _update_xg_state(
                xg_states,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                home_xg=current_xg.get(fixture.home_team),
                away_xg=current_xg.get(fixture.away_team),
            )
    proxy_rows = _evaluation_rows(proxy_predictions)
    true_rows = _evaluation_rows(true_predictions)
    proxy_metrics = metrics(proxy_rows) if proxy_rows else None
    true_metrics = metrics(true_rows) if true_rows else None
    delta = _metric_delta(true_metrics, proxy_metrics)
    return {
        "competition_id": competition_id,
        "xg_source": xg_source,
        "min_history_matches": min_history,
        "statistics_fixtures_available": len(statistics_by_fixture),
        "sample_count": len(true_rows),
        "proxy_metrics": proxy_metrics,
        "true_xg_metrics": true_metrics,
        "delta_real_xg_minus_proxy": delta,
        "interpretation": _true_xg_interpretation(len(true_rows), delta),
        "leakage_guard": (
            "target fixture statistics are loaded only after prediction and are "
            "used only to update future rolling xG state"
        ),
        "sample_rows": true_predictions[:10],
    }


def build_understat_model_iteration_report(
    *,
    raw_dirs: Sequence[Path] = DEFAULT_RAW_DIRS,
    season: str = "2024",
    competitions: Sequence[str] = MODEL_ITERATION_COMPETITIONS,
    min_history: int = 5,
    train_fraction: float = 0.7,
) -> dict[str, Any]:
    registry = CompetitionRegistry()
    fixtures = load_historical_fixtures(
        raw_dirs=raw_dirs,
        entries=registry.entries(),
        season=season,
        competitions=competitions,
    )
    statistics = load_understat_xg_statistics_for_competitions(
        raw_dirs=raw_dirs,
        fixtures=fixtures,
        season=season,
    )
    samples = _offline_model_samples(
        fixtures=fixtures,
        statistics_by_fixture=statistics,
        min_history=min_history,
    )
    split_index = max(MIN_LAMBDA_FIT_SAMPLE, int(len(samples) * train_fraction))
    if split_index >= len(samples):
        split_index = max(0, len(samples) - MIN_OBSERVING_SAMPLE)
    train_samples = samples[:split_index]
    validation_samples = samples[split_index:]

    fitted_model = _fit_offline_lambda_model(train_samples)
    train_predictions = _model_iteration_predictions(train_samples, fitted_model)
    validation_predictions = _model_iteration_predictions(validation_samples, fitted_model)
    temperature = _fit_temperature(train_predictions["fitted_raw"])
    calibrated_train = _temperature_scaled_predictions(
        train_predictions["fitted_raw"], temperature=temperature
    )
    calibrated_validation = _temperature_scaled_predictions(
        validation_predictions["fitted_raw"], temperature=temperature
    )
    train_predictions["fitted_calibrated"] = calibrated_train
    validation_predictions["fitted_calibrated"] = calibrated_validation

    return {
        "schema_version": "w2.understat_model_iteration_1.v1",
        "season": season,
        "xg_source": UNDERSTAT_XG_SOURCE,
        "competitions": list(competitions),
        "fixtures_loaded": len(fixtures),
        "understat_xg_fixtures_available": len(statistics),
        "eligible_sample_count": len(samples),
        "min_history_matches": min_history,
        "split_policy": {
            "type": "chronological_prefix_train_suffix_validation",
            "train_fraction": train_fraction,
            "train_sample_count": len(train_samples),
            "validation_sample_count": len(validation_samples),
            "leakage_guard": (
                "features and coefficients are fitted only from fixtures before "
                "the validation boundary"
            ),
        },
        "model": {
            "status": "OFFLINE_MODEL_DEVELOPMENT_ONLY",
            "online_lambda_fit_enabled": False,
            "canonical_season_changed": False,
            "feature_names": list(fitted_model.feature_names),
            "coefficients": [round(value, 6) for value in fitted_model.coefficients],
            "l2": fitted_model.l2,
            "iterations": fitted_model.iterations,
            "learning_rate": fitted_model.learning_rate,
            "temperature": temperature,
        },
        "baselines": {
            "uniform": "constant 1/3 1X2 probabilities",
            "elo_only": "existing TIME_DECAY_ELO model family",
            "baseline_prior": "existing INDEPENDENT_POISSON prior with Understat rolling xG",
        },
        "train": _model_iteration_section(train_predictions),
        "validation": _model_iteration_section(validation_predictions),
        "validation_delta_vs_baseline_prior": _model_delta(
            validation_predictions["fitted_calibrated"],
            validation_predictions["baseline_prior"],
        ),
        "interpretation": _model_iteration_interpretation(validation_predictions),
        "safety": {
            "api_football_provider_calls": 0,
            "db_reads": 0,
            "db_writes": 0,
            "enabled_true": False,
            "staging_deploy": False,
            "production_deploy": False,
            "online_model_path_changed": False,
        },
    }


def build_understat_model_robustness_report(
    *,
    raw_dirs: Sequence[Path],
    seasons: Sequence[str] = ("2023", "2024"),
    competitions: Sequence[str] = MODEL_ITERATION_COMPETITIONS,
    min_history: int = 5,
) -> dict[str, Any]:
    fixtures, statistics = load_understat_fixture_dataset(
        raw_dirs=raw_dirs,
        seasons=seasons,
        competitions=competitions,
    )
    samples = _offline_model_samples(
        fixtures=fixtures,
        statistics_by_fixture=statistics,
        min_history=min_history,
    )
    single_split = _offline_iteration_eval(
        samples[: max(MIN_LAMBDA_FIT_SAMPLE, int(len(samples) * 0.7))],
        samples[max(MIN_LAMBDA_FIT_SAMPLE, int(len(samples) * 0.7)) :],
    )
    cross_season = _cross_season_robustness(samples=samples, seasons=seasons)
    rolling = _rolling_origin_robustness(samples)
    return {
        "schema_version": "w2.understat_model_iteration_1_robustness.v1",
        "xg_source": UNDERSTAT_XG_SOURCE,
        "seasons": list(seasons),
        "competitions": list(competitions),
        "fixtures_loaded": len(fixtures),
        "understat_xg_fixtures_available": len(statistics),
        "eligible_sample_count": len(samples),
        "train_validation_gap": _train_validation_gap(single_split),
        "cross_season": cross_season,
        "rolling_origin": rolling,
        "interpretation": _robustness_interpretation(
            single_split=single_split,
            cross_season=cross_season,
            rolling=rolling,
        ),
        "safety": {
            "api_football_provider_calls": 0,
            "db_reads": 0,
            "db_writes": 0,
            "enabled_true": False,
            "staging_deploy": False,
            "production_deploy": False,
            "online_model_path_changed": False,
        },
    }


def collect_understat_xg_dataset(
    *,
    out_dir: Path,
    league_code: str = "EPL",
    season: str = "2024",
    requester: UnderstatRequester,
    generated_at: datetime | None = None,
) -> UnderstatFetchResult:
    cache_dir = out_dir / "understat"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _understat_cache_path(cache_dir, league_code=league_code, season=season)
    if cache_path.exists():
        payload = _load_json(cache_path)
        return UnderstatFetchResult(
            provider_calls=0,
            understat_requests=0,
            cache_path=cache_path.as_posix(),
            skipped_existing=True,
            fixture_count=len(_understat_dates(payload)),
        )
    generated = (generated_at or datetime.now(UTC)).astimezone(UTC)
    data = requester(league_code, season)
    cache_payload = {
        "source": UNDERSTAT_XG_SOURCE,
        "endpoint": "understat_league_data",
        "league_code": league_code,
        "season": season,
        "captured_at": generated.isoformat().replace("+00:00", "Z"),
        "payload": data,
    }
    cache_path.write_text(
        json.dumps(cache_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return UnderstatFetchResult(
        provider_calls=0,
        understat_requests=1,
        cache_path=cache_path.as_posix(),
        skipped_existing=False,
        fixture_count=len(_understat_dates(cache_payload)),
    )


def collect_provider_dataset(
    *,
    out_dir: Path,
    season: str = "2024",
    competitions: Sequence[str] = ANNUAL_COMPETITIONS,
    reuse_raw_dirs: Sequence[Path] = DEFAULT_RAW_DIRS,
    daily_hard_cap: int = 80,
    max_statistics_calls: int = 0,
    request_interval_seconds: float = 10.0,
    requester: ApiFootballRequester | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    generated_at: datetime | None = None,
) -> ProviderFetchResult:
    if daily_hard_cap < 0 or max_statistics_calls < 0:
        raise ValueError("provider call caps must be non-negative")
    registry = CompetitionRegistry()
    entries = registry.entries()
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    generated = (generated_at or datetime.now(UTC)).astimezone(UTC)
    provider_calls = 0
    written: list[str] = []
    skipped: list[str] = []
    ledger: list[dict[str, Any]] = []
    stopped_reason: str | None = None

    def remaining() -> int:
        return daily_hard_cap - provider_calls

    for competition_id in competitions:
        if competition_id not in entries:
            continue
        entry = entries[competition_id]
        league_id = entry.provider_mapping.get("api_football_league_id", "")
        fixture_path = raw_dir / f"fixtures_{competition_id}_{league_id}_{season}.json"
        existing_fixture = _existing_fixture_cache(
            raw_dirs=(raw_dir, *reuse_raw_dirs),
            league_id=league_id,
            season=season,
        )
        if existing_fixture is not None:
            skipped.append(existing_fixture.as_posix())
            continue
        if remaining() <= 0:
            stopped_reason = "GLOBAL_PROVIDER_HARD_CAP_REACHED"
            break
        status_code, headers, payload = _perform_provider_request(
            "fixtures",
            {"league": league_id, "season": season, "status": "FT"},
            requester=requester,
        )
        provider_calls += 1
        captured_at = datetime.now(UTC)
        quota = parse_api_football_quota(headers=headers, payload=payload, observed_at=captured_at)
        _write_raw(
            fixture_path,
            endpoint="fixtures",
            params={"league": league_id, "season": season, "status": "FT"},
            payload=payload,
            captured_at=generated,
        )
        written.append(fixture_path.as_posix())
        ledger.append(
            _ledger_record(
                competition_id=competition_id,
                endpoint="fixtures",
                status_code=status_code,
                response_count=len(_response_rows({"payload": payload})),
                provider_call_index=provider_calls,
                quota_remaining=quota.daily_remaining,
                captured_at=captured_at,
            )
        )
        stopped_reason = _stop_reason(
            status_code=status_code,
            quota_remaining=quota.daily_remaining,
        )
        if stopped_reason:
            break
        if request_interval_seconds > 0:
            sleeper(request_interval_seconds)

    if stopped_reason is None and max_statistics_calls:
        fixtures = load_historical_fixtures(
            raw_dirs=(raw_dir, *reuse_raw_dirs),
            entries=entries,
            season=season,
            competitions=competitions,
        )
        for fixture in _round_robin_by_competition(fixtures):
            if provider_calls >= daily_hard_cap:
                stopped_reason = "GLOBAL_PROVIDER_HARD_CAP_REACHED"
                break
            statistics_calls = sum(1 for item in ledger if item["endpoint"] == "statistics")
            if statistics_calls >= max_statistics_calls:
                break
            stats_path = raw_dir / f"statistics_{fixture.competition_id}_{fixture.fixture_id}.json"
            existing_stats = _existing_statistics_cache(
                raw_dirs=(raw_dir, *reuse_raw_dirs),
                fixture_id=fixture.fixture_id,
            )
            if existing_stats is not None:
                skipped.append(existing_stats.as_posix())
                continue
            status_code, headers, payload = _perform_provider_request(
                "statistics",
                {"fixture": fixture.fixture_id},
                requester=requester,
            )
            provider_calls += 1
            captured_at = datetime.now(UTC)
            quota = parse_api_football_quota(
                headers=headers,
                payload=payload,
                observed_at=captured_at,
            )
            _write_raw(
                stats_path,
                endpoint="statistics",
                params={"fixture": fixture.fixture_id},
                payload=payload,
                captured_at=generated,
            )
            written.append(stats_path.as_posix())
            ledger.append(
                _ledger_record(
                    competition_id=fixture.competition_id,
                    endpoint="statistics",
                    status_code=status_code,
                    response_count=len(_response_rows({"payload": payload})),
                    provider_call_index=provider_calls,
                    quota_remaining=quota.daily_remaining,
                    captured_at=captured_at,
                )
            )
            stopped_reason = _stop_reason(
                status_code=status_code,
                quota_remaining=quota.daily_remaining,
            )
            if stopped_reason:
                break
            if request_interval_seconds > 0:
                sleeper(request_interval_seconds)

    ledger_path = out_dir / "provider_ledger.json"
    ledger_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return ProviderFetchResult(
        provider_calls=provider_calls,
        written_files=tuple(written),
        skipped_existing=tuple(skipped),
        stopped_reason=stopped_reason,
        ledger=tuple(ledger),
    )


def _slice_report(
    rows: list[EvaluationRow],
    *,
    predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    if not rows:
        return {
            "sample_count": 0,
            "metrics": None,
            "reliability_curve": [],
            "ecc": None,
            "baseline": None,
            "calibration_status": "NO_SETTLED_SAMPLE",
        }
    metric_values = metrics(rows)
    curve = reliability(rows)
    ecc = round(
        sum(item["weight"] * abs(item["accuracy"] - item["confidence"]) for item in curve),
        6,
    )
    return {
        "sample_count": len(rows),
        "metrics": {**metric_values, "ecc": ecc},
        "reliability_curve": [
            {
                "bin": int(item["bin"]),
                "count": int(item["count"]),
                "confidence": round(item["confidence"], 6),
                "accuracy": round(item["accuracy"], 6),
                "weight": round(item["weight"], 6),
            }
            for item in curve
        ],
        "baseline": _baseline_report(rows),
        "calibration_status": _sample_status(len(rows)),
        "prediction_hash_sample": [item["prediction_hash"] for item in predictions[:5]],
    }


def _baseline_report(rows: list[EvaluationRow]) -> dict[str, Any]:
    uniform = [
        EvaluationRow(
            fixture_id=row.fixture_id,
            actual=row.actual,
            probabilities={"HOME": 1 / 3, "DRAW": 1 / 3, "AWAY": 1 / 3},
            competition=row.competition,
            season=row.season,
            neutral_site=row.neutral_site,
        )
        for row in rows
    ]
    return {"uniform": metrics(uniform)}


def _calibration_status(
    *,
    rows: list[EvaluationRow],
    missing_competitions: list[str],
    input_coverage: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if missing_competitions:
        blockers.append("MISSING_2024_FIXTURE_RAW")
    if input_coverage["statistics"]["covered_fixtures"] < input_coverage["fixtures"]["covered"]:
        warnings.append("XG_STATISTICS_PARTIAL_OR_MISSING")
    if input_coverage["squad_value"]["covered_competitions"] == 0:
        warnings.append("SQUAD_VALUE_MISSING")
    if len(rows) < MIN_OBSERVING_SAMPLE:
        blockers.append("INSUFFICIENT_SETTLED_SAMPLE")
    status = "BLOCKED" if blockers else _sample_status(len(rows))
    return {
        "status": status,
        "settled_sample": len(rows),
        "minimum_observing_sample": MIN_OBSERVING_SAMPLE,
        "minimum_ready_sample": MIN_READY_SAMPLE,
        "blockers": blockers,
        "warnings": warnings,
        "online_calibration_changed": False,
    }


def _sample_status(sample_count: int) -> str:
    if sample_count >= MIN_READY_SAMPLE:
        return "READY_FOR_REVIEW"
    if sample_count >= MIN_OBSERVING_SAMPLE:
        return "OBSERVING"
    return "INSUFFICIENT_SAMPLE"


def _input_coverage(
    *,
    raw_dirs: Sequence[Path],
    entries: dict[str, CompetitionRegistryEntry],
    season: str,
    competitions: Sequence[str],
) -> dict[str, Any]:
    fixtures = load_historical_fixtures(
        raw_dirs=raw_dirs,
        entries=entries,
        season=season,
        competitions=competitions,
    )
    fixture_ids = {item.fixture_id for item in fixtures}
    stats_ids = _statistics_fixture_ids(raw_dirs)
    fixtures_by_competition: dict[str, int] = {competition: 0 for competition in competitions}
    for item in fixtures:
        fixtures_by_competition[item.competition_id] += 1
    return {
        "fixtures": {
            "covered": len(fixtures),
            "by_competition": fixtures_by_competition,
        },
        "statistics": {
            "covered_fixtures": len(fixture_ids & stats_ids),
            "coverage_ratio": round(len(fixture_ids & stats_ids) / len(fixture_ids), 6)
            if fixture_ids
            else 0.0,
        },
        "squad_value": {
            "covered_competitions": 0,
            "status": "MISSING_SOURCE",
        },
    }


def load_fixture_statistics(raw_dirs: Sequence[Path]) -> dict[str, dict[str, float]]:
    statistics: dict[str, dict[str, float]] = {}
    for path in _raw_files(raw_dirs, endpoint="statistics"):
        payload = _load_json(path)
        fixture_id = str(_params(payload).get("fixture") or "")
        if not fixture_id:
            continue
        values = _fixture_xg_values(payload)
        if values:
            statistics[fixture_id] = values
    return statistics


def load_understat_xg_statistics(
    *,
    raw_dirs: Sequence[Path],
    fixtures: Sequence[HistoricalFixture],
    league_code: str = "EPL",
    season: str = "2024",
) -> dict[str, dict[str, float]]:
    understat_rows: dict[tuple[str, str, str], dict[str, float]] = {}
    understat_rows_by_date: dict[tuple[str, str, str], list[dict[str, float]]] = {}
    understat_candidates_by_date: dict[
        str, list[tuple[str, str, float, float]]
    ] = {}
    for payload in _understat_payloads(raw_dirs, league_code=league_code, season=season):
        for row in _understat_dates(payload):
            parsed = _understat_match_xg(row)
            if parsed is None:
                continue
            key, home_team, away_team, home_xg, away_xg = parsed
            values = {home_team: home_xg, away_team: away_xg}
            understat_rows[key] = values
            date_key = (key[0][:10], home_team, away_team)
            understat_rows_by_date.setdefault(date_key, []).append(values)
            understat_candidates_by_date.setdefault(key[0][:10], []).append(
                (home_team, away_team, home_xg, away_xg)
            )

    output: dict[str, dict[str, float]] = {}
    for fixture in fixtures:
        key = (
            fixture.kickoff_utc.strftime("%Y-%m-%dT%H:%M"),
            fixture.home_team,
            fixture.away_team,
        )
        matched_values = understat_rows.get(key)
        if matched_values is None:
            date_key = (
                fixture.kickoff_utc.strftime("%Y-%m-%d"),
                fixture.home_team,
                fixture.away_team,
            )
            date_matches = understat_rows_by_date.get(date_key, [])
            matched_values = date_matches[0] if len(date_matches) == 1 else None
        if matched_values is None:
            matched_values = _unique_understat_name_match(
                understat_candidates_by_date.get(fixture.kickoff_utc.strftime("%Y-%m-%d"), []),
                home_team=fixture.home_team,
                away_team=fixture.away_team,
            )
        if matched_values is not None:
            output[fixture.fixture_id] = matched_values
    return output


def load_understat_xg_statistics_for_competitions(
    *,
    raw_dirs: Sequence[Path],
    fixtures: Sequence[HistoricalFixture],
    season: str = "2024",
    league_codes: dict[str, str] | None = None,
) -> dict[str, dict[str, float]]:
    codes = league_codes or UNDERSTAT_LEAGUE_CODES
    output: dict[str, dict[str, float]] = {}
    for competition_id, league_code in codes.items():
        scoped = [fixture for fixture in fixtures if fixture.competition_id == competition_id]
        output.update(
            load_understat_xg_statistics(
                raw_dirs=raw_dirs,
                fixtures=scoped,
                league_code=league_code,
                season=season,
            )
        )
    return output


def load_understat_fixture_dataset(
    *,
    raw_dirs: Sequence[Path],
    seasons: Sequence[str],
    competitions: Sequence[str],
    league_codes: dict[str, str] | None = None,
) -> tuple[list[HistoricalFixture], dict[str, dict[str, float]]]:
    codes = league_codes or UNDERSTAT_LEAGUE_CODES
    fixtures: dict[str, HistoricalFixture] = {}
    statistics: dict[str, dict[str, float]] = {}
    for competition_id in competitions:
        league_code = codes.get(competition_id)
        if league_code is None:
            continue
        for season in seasons:
            for payload in _understat_payloads(raw_dirs, league_code=league_code, season=season):
                for row in _understat_dates(payload):
                    parsed = _understat_fixture_from_row(
                        row,
                        competition_id=competition_id,
                        league_code=league_code,
                        season=season,
                    )
                    if parsed is None:
                        continue
                    fixture, xg_values = parsed
                    fixtures.setdefault(fixture.fixture_id, fixture)
                    statistics[fixture.fixture_id] = xg_values
    ordered = sorted(
        fixtures.values(),
        key=lambda item: (item.kickoff_utc, item.competition_id, item.fixture_id),
    )
    return ordered, statistics


def _understat_fixture_from_row(
    row: dict[str, Any],
    *,
    competition_id: str,
    league_code: str,
    season: str,
) -> tuple[HistoricalFixture, dict[str, float]] | None:
    parsed = _understat_match_xg(row)
    if parsed is None:
        return None
    key, home_team, away_team, home_xg, away_xg = parsed
    goals = _dict(row.get("goals"))
    home_goals = _int(goals.get("h"))
    away_goals = _int(goals.get("a"))
    match_id = str(row.get("id") or "")
    kickoff = _parse_datetime(key[0] + "+00:00")
    if home_goals is None or away_goals is None or not match_id or kickoff is None:
        return None
    fixture_id = f"understat:{league_code}:{season}:{match_id}"
    fixture = HistoricalFixture(
        fixture_id=fixture_id,
        competition_id=competition_id,
        league_id=league_code,
        season=season,
        kickoff_utc=kickoff,
        home_team=home_team,
        away_team=away_team,
        home_goals=home_goals,
        away_goals=away_goals,
        neutral_site=False,
        raw_source=UNDERSTAT_XG_SOURCE,
    )
    return fixture, {home_team: home_xg, away_team: away_xg}


def _unique_understat_name_match(
    candidates: Sequence[tuple[str, str, float, float]],
    *,
    home_team: str,
    away_team: str,
) -> dict[str, float] | None:
    scored: list[tuple[float, float, float, float]] = []
    for candidate_home, candidate_away, home_xg, away_xg in candidates:
        home_score = _name_similarity(home_team, candidate_home)
        away_score = _name_similarity(away_team, candidate_away)
        score = (home_score + away_score) / 2
        if home_score >= 0.62 and away_score >= 0.62:
            scored.append((score, home_score, home_xg, away_xg))
    scored.sort(reverse=True)
    if not scored:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.08:
        return None
    _, _, home_xg, away_xg = scored[0]
    return {home_team: home_xg, away_team: away_xg}


def _name_similarity(left: str, right: str) -> float:
    norm_left = _normalized_team_name(left)
    norm_right = _normalized_team_name(right)
    if not norm_left or not norm_right:
        return 0.0
    if norm_left == norm_right:
        return 1.0
    if norm_left in norm_right or norm_right in norm_left:
        return 0.9
    return SequenceMatcher(None, norm_left, norm_right).ratio()


def _normalized_team_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    name_parts = []
    stopwords = {
        "1",
        "05",
        "1899",
        "ac",
        "as",
        "cf",
        "club",
        "fc",
        "fsv",
        "rc",
        "sc",
        "ss",
        "stadium",
        "sv",
        "team",
        "vfb",
        "vfl",
    }
    for part in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split():
        if part not in stopwords:
            name_parts.append(part)
    return " ".join(name_parts)


def _offline_model_samples(
    *,
    fixtures: Sequence[HistoricalFixture],
    statistics_by_fixture: dict[str, dict[str, float]],
    min_history: int,
) -> list[OfflineModelSample]:
    builders: dict[str, AsOfFeatureBuilder] = {}
    xg_states: dict[tuple[str, str], RollingXgState] = {}
    samples: list[OfflineModelSample] = []
    for fixture in sorted(
        fixtures,
        key=lambda item: (item.kickoff_utc, item.competition_id, item.fixture_id),
    ):
        builder = builders.setdefault(fixture.competition_id, AsOfFeatureBuilder())
        match = _match_record(fixture)
        proxy_features = builder.features(match)
        home_key = (fixture.competition_id, fixture.home_team)
        away_key = (fixture.competition_id, fixture.away_team)
        home_xg_state = xg_states.get(home_key, RollingXgState())
        away_xg_state = xg_states.get(away_key, RollingXgState())
        current_xg = statistics_by_fixture.get(fixture.fixture_id)
        if (
            current_xg is not None
            and home_xg_state.matches >= min_history
            and away_xg_state.matches >= min_history
        ):
            true_features = dict(proxy_features)
            true_features.update(
                {
                    "home_attack_strength": home_xg_state.xg_for,
                    "away_attack_strength": away_xg_state.xg_for,
                    "home_defence_strength": home_xg_state.xg_against,
                    "away_defence_strength": away_xg_state.xg_against,
                    "rolling_home_xg": home_xg_state.xg_for,
                    "rolling_away_xg": away_xg_state.xg_for,
                }
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
            _update_competition_xg_state(
                xg_states,
                competition_id=fixture.competition_id,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                home_xg=current_xg.get(fixture.home_team),
                away_xg=current_xg.get(fixture.away_team),
            )
    return samples


def _match_record(fixture: HistoricalFixture) -> MatchRecord:
    return MatchRecord(
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


def _update_competition_xg_state(
    states: dict[tuple[str, str], RollingXgState],
    *,
    competition_id: str,
    home_team: str,
    away_team: str,
    home_xg: float | None,
    away_xg: float | None,
) -> None:
    if home_xg is None or away_xg is None:
        return
    home = states.setdefault((competition_id, home_team), RollingXgState())
    away = states.setdefault((competition_id, away_team), RollingXgState())
    home.xg_for_total += home_xg
    home.xg_against_total += away_xg
    home.matches += 1
    away.xg_for_total += away_xg
    away.xg_against_total += home_xg
    away.matches += 1


def _fit_offline_lambda_model(samples: Sequence[OfflineModelSample]) -> OfflineLambdaModel:
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
            l2=0.002,
            iterations=0,
            learning_rate=0.0,
        )
    feature_names = ("intercept", "home_field", "attack_xg_for", "opponent_xg_against", "elo_gap")
    beta = [math.log(1.25), 0.08, 0.08, 0.08, 0.05]
    learning_rate = 0.025
    l2 = 0.002
    rows: list[tuple[list[float], float]] = []
    for sample in samples:
        rows.extend(_goal_fit_rows(sample))
    for _ in range(1200):
        gradient = [0.0 for _ in beta]
        for features, goals in rows:
            log_mu = _clamp(
                sum(coef * value for coef, value in zip(beta, features, strict=True)),
                -3.0,
                2.0,
            )
            mu = math.exp(log_mu)
            error = mu - goals
            for index, value in enumerate(features):
                gradient[index] += error * value
        for index in range(len(beta)):
            penalty = 0.0 if index == 0 else l2 * beta[index]
            beta[index] -= learning_rate * (gradient[index] / len(rows) + penalty)
    return OfflineLambdaModel(
        coefficients=tuple(beta),
        feature_names=feature_names,
        l2=l2,
        iterations=1200,
        learning_rate=learning_rate,
    )


def _goal_fit_rows(sample: OfflineModelSample) -> list[tuple[list[float], float]]:
    fixture = sample.fixture
    features = sample.true_features
    elo_gap = float(features["elo_diff"]) / 400.0
    home_row = [
        1.0,
        float(features["home_field"]),
        float(features["home_attack_strength"]),
        float(features["away_defence_strength"]),
        elo_gap,
    ]
    away_row = [
        1.0,
        0.0,
        float(features["away_attack_strength"]),
        float(features["home_defence_strength"]),
        -elo_gap,
    ]
    return [(home_row, float(fixture.home_goals)), (away_row, float(fixture.away_goals))]


def _model_iteration_predictions(
    samples: Sequence[OfflineModelSample],
    model: OfflineLambdaModel,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {
        "uniform": [],
        "elo_only": [],
        "baseline_prior": [],
        "fitted_raw": [],
    }
    for sample in samples:
        fixture = sample.fixture
        match = _match_record(fixture)
        output["uniform"].append(
            _prediction_row(
                fixture=fixture,
                probabilities={"HOME": 1 / 3, "DRAW": 1 / 3, "AWAY": 1 / 3},
            )
        )
        elo_prediction = predict_from_features(
            fixture.fixture_id,
            ModelFamily.TIME_DECAY_ELO,
            sample.proxy_features,
            fixture.kickoff_utc,
        )
        output["elo_only"].append(
            _prediction_row(fixture=fixture, probabilities=elo_prediction.one_x_two)
        )
        baseline_prediction = predict_from_features(
            fixture.fixture_id,
            ModelFamily.INDEPENDENT_POISSON,
            sample.true_features,
            fixture.kickoff_utc,
        )
        output["baseline_prior"].append(
            _prediction_row(fixture=fixture, probabilities=baseline_prediction.one_x_two)
        )
        home_mu, away_mu = _offline_lambdas(sample, model)
        fitted_prediction = prediction_from_lambdas(
            fixture_id=fixture.fixture_id,
            model_name="OFFLINE_UNDERSTAT_FITTED_POISSON",
            data_cutoff=match.kickoff_utc,
            home_mu=home_mu,
            away_mu=away_mu,
            provenance={"feature_policy": "OFFLINE_UNDERSTAT_MODEL_ITERATION_1", "odds_free": True},
        )
        output["fitted_raw"].append(
            _prediction_row(fixture=fixture, probabilities=fitted_prediction.one_x_two)
        )
    return output


def _offline_iteration_eval(
    train_samples: Sequence[OfflineModelSample],
    validation_samples: Sequence[OfflineModelSample],
) -> dict[str, Any]:
    fitted_model = _fit_offline_lambda_model(train_samples)
    train_predictions = _model_iteration_predictions(train_samples, fitted_model)
    validation_predictions = _model_iteration_predictions(validation_samples, fitted_model)
    temperature = _fit_temperature(train_predictions["fitted_raw"])
    train_predictions["fitted_calibrated"] = _temperature_scaled_predictions(
        train_predictions["fitted_raw"], temperature=temperature
    )
    validation_predictions["fitted_calibrated"] = _temperature_scaled_predictions(
        validation_predictions["fitted_raw"], temperature=temperature
    )
    return {
        "train_sample_count": len(train_samples),
        "validation_sample_count": len(validation_samples),
        "temperature": temperature,
        "model": {
            "coefficients": [round(value, 6) for value in fitted_model.coefficients],
            "feature_names": list(fitted_model.feature_names),
            "l2": fitted_model.l2,
        },
        "train": _model_iteration_section(train_predictions),
        "validation": _model_iteration_section(validation_predictions),
        "validation_delta_vs_baseline_prior": _model_delta(
            validation_predictions["fitted_calibrated"],
            validation_predictions["baseline_prior"],
        ),
        "interpretation": _model_iteration_interpretation(validation_predictions),
    }


def _offline_lambdas(
    sample: OfflineModelSample,
    model: OfflineLambdaModel,
) -> tuple[float, float]:
    rows = _goal_fit_rows(sample)
    lambdas = []
    for features, _ in rows:
        log_mu = _clamp(
            sum(coef * value for coef, value in zip(model.coefficients, features, strict=True)),
            -3.0,
            2.0,
        )
        lambdas.append(_clamp(math.exp(log_mu), 0.05, 4.25))
    return lambdas[0], lambdas[1]


def _train_validation_gap(eval_report: dict[str, Any]) -> dict[str, Any]:
    train_metrics = eval_report["train"]["fitted_calibrated"]["metrics"]
    validation_metrics = eval_report["validation"]["fitted_calibrated"]["metrics"]
    gap = {
        key: round(validation_metrics[key] - train_metrics[key], 6)
        for key in ("log_loss", "brier", "rps", "ece")
    }
    overfit_flag = gap["log_loss"] > 0.04
    return {
        "train": eval_report["train"],
        "validation": eval_report["validation"],
        "gap_validation_minus_train": gap,
        "overfit_flag": overfit_flag,
        "temperature": eval_report["temperature"],
    }


def _cross_season_robustness(
    *,
    samples: Sequence[OfflineModelSample],
    seasons: Sequence[str],
) -> list[dict[str, Any]]:
    if len(seasons) < 2:
        return []
    output = []
    for train_season, validation_season in (
        (seasons[0], seasons[1]),
        (seasons[1], seasons[0]),
    ):
        train_samples = [item for item in samples if item.fixture.season == train_season]
        validation_samples = [item for item in samples if item.fixture.season == validation_season]
        eval_report = _offline_iteration_eval(train_samples, validation_samples)
        output.append(
            {
                "train_season": train_season,
                "validation_season": validation_season,
                "train_sample_count": len(train_samples),
                "validation_sample_count": len(validation_samples),
                "validation": eval_report["validation"],
                "validation_delta_vs_baseline_prior": eval_report[
                    "validation_delta_vs_baseline_prior"
                ],
                "interpretation": eval_report["interpretation"],
            }
        )
    return output


def _rolling_origin_robustness(samples: Sequence[OfflineModelSample]) -> dict[str, Any]:
    folds = []
    total = len(samples)
    fold_specs = ((0.45, 0.15), (0.55, 0.15), (0.65, 0.15), (0.75, 0.15))
    for index, (train_fraction, validation_fraction) in enumerate(fold_specs, start=1):
        train_end = max(MIN_LAMBDA_FIT_SAMPLE, int(total * train_fraction))
        validation_end = min(total, train_end + int(total * validation_fraction))
        if validation_end - train_end < MIN_OBSERVING_SAMPLE:
            continue
        eval_report = _offline_iteration_eval(
            samples[:train_end],
            samples[train_end:validation_end],
        )
        validation = eval_report["validation"]["fitted_calibrated"]["metrics"]
        baseline = eval_report["validation"]["baseline_prior"]["metrics"]
        elo = eval_report["validation"]["elo_only"]["metrics"]
        folds.append(
            {
                "fold": index,
                "train_sample_count": train_end,
                "validation_sample_count": validation_end - train_end,
                "temperature": eval_report["temperature"],
                "fitted_calibrated": validation,
                "baseline_prior": baseline,
                "elo_only": elo,
                "delta_vs_baseline_prior": eval_report["validation_delta_vs_baseline_prior"],
                "interpretation": eval_report["interpretation"]["status"],
            }
        )
    return {
        "folds": folds,
        "summary": _fold_summary(folds),
    }


def _fold_summary(folds: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not folds:
        return {}
    values = [fold["fitted_calibrated"]["log_loss"] for fold in folds]
    deltas = [fold["delta_vs_baseline_prior"]["log_loss"] for fold in folds]
    return {
        "fold_count": len(folds),
        "mean_log_loss": round(sum(values) / len(values), 6),
        "stddev_log_loss": _stddev(values),
        "mean_delta_log_loss_vs_baseline_prior": round(sum(deltas) / len(deltas), 6),
        "wins_vs_baseline_prior": sum(1 for value in deltas if value < 0),
    }


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return round(math.sqrt(variance), 6)


def _robustness_interpretation(
    *,
    single_split: dict[str, Any],
    cross_season: Sequence[dict[str, Any]],
    rolling: dict[str, Any],
) -> dict[str, Any]:
    gap = _train_validation_gap(single_split)["gap_validation_minus_train"]
    cross_wins = [
        item["validation_delta_vs_baseline_prior"]["log_loss"] < 0
        for item in cross_season
        if item["validation_delta_vs_baseline_prior"] is not None
    ]
    fold_summary = rolling.get("summary", {})
    stable_folds = (
        bool(fold_summary)
        and fold_summary["wins_vs_baseline_prior"] == fold_summary["fold_count"]
        and fold_summary["stddev_log_loss"] <= 0.04
    )
    cross_stable = bool(cross_wins) and all(cross_wins)
    gap_ok = gap["log_loss"] <= 0.04
    if gap_ok and cross_stable and stable_folds:
        status = "ROBUST_IMPROVEMENT"
        conclusion = "The fitted model improvement is stable across gap, cross-season, and folds."
    elif gap_ok and stable_folds:
        status = "PROMISING_BUT_CROSS_SEASON_MIXED"
        conclusion = "The fitted model is stable in folds but cross-season evidence is mixed."
    else:
        status = "NOT_ROBUST_ENOUGH"
        conclusion = "The fitted model improvement may be fold- or season-dependent."
    return {
        "status": status,
        "conclusion": conclusion,
        "train_validation_gap_ok": gap_ok,
        "cross_season_stable": cross_stable,
        "rolling_origin_stable": stable_folds,
    }


def _prediction_row(
    *,
    fixture: HistoricalFixture,
    probabilities: dict[str, float],
) -> dict[str, Any]:
    return {
        "fixture_id": fixture.fixture_id,
        "competition_id": fixture.competition_id,
        "season": fixture.season,
        "actual": fixture.actual,
        "neutral_site": fixture.neutral_site,
        "probabilities": {key: round(float(value), 8) for key, value in probabilities.items()},
    }


def _fit_temperature(predictions: Sequence[dict[str, Any]]) -> float:
    if not predictions:
        return 1.0
    candidates = [round(0.6 + index * 0.02, 2) for index in range(61)]
    best_temperature = 1.0
    best_loss = float("inf")
    for temperature in candidates:
        rows = _evaluation_rows(
            _temperature_scaled_predictions(predictions, temperature=temperature)
        )
        loss = sum(-math.log(max(row.probabilities[row.actual], 1e-12)) for row in rows) / len(rows)
        if loss < best_loss:
            best_loss = loss
            best_temperature = temperature
    return best_temperature


def _temperature_scaled_predictions(
    predictions: Sequence[dict[str, Any]],
    *,
    temperature: float,
) -> list[dict[str, Any]]:
    scaled = []
    for item in predictions:
        probabilities = dict(item["probabilities"])
        adjusted = {
            key: max(float(value), 1e-12) ** (1.0 / temperature)
            for key, value in probabilities.items()
        }
        total = sum(adjusted.values())
        scaled.append(
            {
                **item,
                "probabilities": {
                    key: round(value / total, 8)
                    for key, value in adjusted.items()
                },
            }
        )
    return scaled


def _model_iteration_section(predictions: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    section: dict[str, Any] = {}
    for name, rows in predictions.items():
        section[name] = {
            "sample_count": len(rows),
            "metrics": metrics(_evaluation_rows(rows)) if rows else None,
        }
    return section


def _model_delta(
    candidate: Sequence[dict[str, Any]],
    baseline: Sequence[dict[str, Any]],
) -> dict[str, float] | None:
    candidate_metrics = metrics(_evaluation_rows(candidate)) if candidate else None
    baseline_metrics = metrics(_evaluation_rows(baseline)) if baseline else None
    return _metric_delta(candidate_metrics, baseline_metrics)


def _model_iteration_interpretation(predictions: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    fitted = metrics(_evaluation_rows(predictions["fitted_calibrated"]))
    baseline = metrics(_evaluation_rows(predictions["baseline_prior"]))
    elo = metrics(_evaluation_rows(predictions["elo_only"]))
    log_loss_delta = fitted["log_loss"] - baseline["log_loss"]
    ece_delta = fitted["ece"] - baseline["ece"]
    beats_baseline = (
        fitted["log_loss"] < baseline["log_loss"]
        and fitted["brier"] < baseline["brier"]
    )
    beats_reference = fitted["log_loss"] < elo["log_loss"]
    if beats_baseline and beats_reference and log_loss_delta <= -0.01 and ece_delta <= 0:
        status = "MODEL_ITERATION_PROMISING"
        conclusion = (
            "Offline fitted lambdas plus temperature scaling beat prior and simple reference."
        )
    elif beats_baseline:
        status = "SMALL_GAIN_NEEDS_MORE_MODEL_WORK"
        conclusion = "Offline fit improves some metrics but not enough for acceptance."
    else:
        status = "MODEL_ITERATION_NOT_ACCEPTED"
        conclusion = "Offline fit does not beat the current prior on validation."
    return {
        "status": status,
        "conclusion": conclusion,
        "beats_baseline_prior": beats_baseline,
        "beats_simple_reference": beats_reference,
        "log_loss_delta_vs_baseline_prior": round(log_loss_delta, 6),
        "ece_delta_vs_baseline_prior": round(ece_delta, 6),
    }


def _statistics_fixture_ids(raw_dirs: Sequence[Path]) -> set[str]:
    fixture_ids: set[str] = set()
    for path in _raw_files(raw_dirs, endpoint="statistics"):
        payload = _load_json(path)
        params = _params(payload)
        fixture_id = str(params.get("fixture") or "")
        if fixture_id:
            fixture_ids.add(fixture_id)
    return fixture_ids


def _understat_payloads(
    raw_dirs: Sequence[Path],
    *,
    league_code: str,
    season: str,
) -> Iterable[dict[str, Any]]:
    for raw_dir in raw_dirs:
        if not raw_dir.exists():
            continue
        for path in sorted(raw_dir.glob(f"understat_{league_code.lower()}_{season}.json")):
            payload = _load_json(path)
            if (
                str(payload.get("source") or "") == UNDERSTAT_XG_SOURCE
                and str(payload.get("league_code") or "") == league_code
                and str(payload.get("season") or "") == season
            ):
                yield payload


def _understat_cache_path(cache_dir: Path, *, league_code: str, season: str) -> Path:
    return cache_dir / f"understat_{league_code.lower()}_{season}.json"


def _understat_dates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = _dict(payload.get("payload"))
    rows = data.get("dates")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _understat_match_xg(
    row: dict[str, Any],
) -> tuple[tuple[str, str, str], str, str, float, float] | None:
    if row.get("isResult") is not True:
        return None
    kickoff = _parse_datetime(str(row.get("datetime") or "").replace(" ", "T") + "+00:00")
    if kickoff is None:
        return None
    home = _understat_team_name(_dict(row.get("h")).get("title"))
    away = _understat_team_name(_dict(row.get("a")).get("title"))
    xg = _dict(row.get("xG"))
    home_xg = _float(xg.get("h"))
    away_xg = _float(xg.get("a"))
    if not home or not away or home_xg is None or away_xg is None:
        return None
    key = (kickoff.strftime("%Y-%m-%dT%H:%M"), home, away)
    return key, home, away, home_xg, away_xg


def _understat_team_name(value: Any) -> str:
    name = str(value or "")
    return UNDERSTAT_TEAM_ALIASES.get(name, name)


def _fixture_xg_values(payload: dict[str, Any]) -> dict[str, float]:
    output: dict[str, float] = {}
    for row in _response_rows(payload):
        team = _dict(row.get("team"))
        team_name = str(team.get("name") or "")
        if not team_name:
            continue
        for item in row.get("statistics") or []:
            if not isinstance(item, dict):
                continue
            stat_type = str(item.get("type") or "").lower().replace(" ", "_")
            if stat_type not in {"expected_goals", "xg"}:
                continue
            value = _float(item.get("value"))
            if value is not None:
                output[team_name] = value
    return output


def _update_xg_state(
    states: dict[str, RollingXgState],
    *,
    home_team: str,
    away_team: str,
    home_xg: float | None,
    away_xg: float | None,
) -> None:
    if home_xg is None or away_xg is None:
        return
    home = states.setdefault(home_team, RollingXgState())
    away = states.setdefault(away_team, RollingXgState())
    home.xg_for_total += home_xg
    home.xg_against_total += away_xg
    home.matches += 1
    away.xg_for_total += away_xg
    away.xg_against_total += home_xg
    away.matches += 1


def _evaluation_rows(predictions: Sequence[dict[str, Any]]) -> list[EvaluationRow]:
    return [
        EvaluationRow(
            fixture_id=str(item["fixture_id"]),
            actual=str(item["actual"]),
            probabilities=dict(item["probabilities"]),
            competition=str(item["competition_id"]),
            season=str(item["season"]),
            neutral_site=bool(item["neutral_site"]),
        )
        for item in predictions
    ]


def _metric_delta(
    true_metrics: dict[str, float] | None,
    proxy_metrics: dict[str, float] | None,
) -> dict[str, float] | None:
    if true_metrics is None or proxy_metrics is None:
        return None
    return {
        key: round(true_metrics[key] - proxy_metrics[key], 6)
        for key in ("brier", "log_loss", "rps", "ece")
    }


def _true_xg_interpretation(
    sample_count: int,
    delta: dict[str, float] | None,
) -> dict[str, Any]:
    if sample_count < MIN_OBSERVING_SAMPLE or delta is None:
        return {
            "status": "INSUFFICIENT_TRUE_XG_SAMPLE",
            "conclusion": "Need more target-competition statistics before judging architecture.",
        }
    log_loss_delta = delta["log_loss"]
    if log_loss_delta <= -0.03:
        return {
            "status": "ARCHITECTURE_PROMISING",
            "conclusion": "True rolling xG materially improves log-loss versus proxy features.",
        }
    if abs(log_loss_delta) <= 0.005:
        return {
            "status": "MODEL_WEAK_REWORK_BEFORE_PAID_SCALE",
            "conclusion": "True rolling xG barely moves log-loss; improve model before paid scale.",
        }
    return {
        "status": "MIXED_OR_SMALL_TRUE_XG_GAIN",
        "conclusion": "True rolling xG moves metrics but not enough for an architecture decision.",
    }


def _round_robin_by_competition(
    fixtures: Sequence[HistoricalFixture],
) -> list[HistoricalFixture]:
    grouped: dict[str, list[HistoricalFixture]] = {}
    for fixture in sorted(fixtures, key=lambda item: (item.competition_id, item.kickoff_utc)):
        grouped.setdefault(fixture.competition_id, []).append(fixture)
    ordered: list[HistoricalFixture] = []
    index = 0
    while True:
        added = False
        for competition_id in sorted(grouped):
            rows = grouped[competition_id]
            if index < len(rows):
                ordered.append(rows[index])
                added = True
        if not added:
            return ordered
        index += 1


def _s2_summary(rows: list[EvaluationRow]) -> dict[str, Any]:
    return {
        "reused": "w2.models.evaluation + S2 sample gates",
        "settled_sample": len(rows),
        "minimum_walk_forward_sample": 200,
        "status": "READY_FOR_OFFLINE_COMPARISON" if len(rows) >= 200 else "BLOCKED",
        "blockers": [] if len(rows) >= 200 else ["INSUFFICIENT_S2_WALK_FORWARD_SAMPLE"],
    }


def _outcome_tracked_samples(
    predictions: list[dict[str, Any]],
    limit: int = 20,
) -> list[dict[str, Any]]:
    samples = []
    for item in predictions[:limit]:
        actual_probability = item["probabilities"][item["actual"]]
        samples.append(
            {
                "fixture_id": item["fixture_id"],
                "competition_id": item["competition_id"],
                "outcome_tracked": True,
                "prediction_hash": item["prediction_hash"],
                "actual": item["actual"],
                "actual_score": item["actual_score"],
                "actual_probability": actual_probability,
                "log_loss": round(-math.log(max(actual_probability, 1e-12)), 6),
            }
        )
    return samples


def _raw_files(raw_dirs: Sequence[Path], *, endpoint: str) -> Iterable[Path]:
    for raw_dir in raw_dirs:
        if not raw_dir.exists():
            continue
        yield from sorted(raw_dir.glob(f"*{endpoint}*.json"))


def _existing_fixture_cache(
    *,
    raw_dirs: Sequence[Path],
    league_id: str,
    season: str,
) -> Path | None:
    for path in _raw_files(raw_dirs, endpoint="fixtures"):
        payload = _load_json(path)
        params = _params(payload)
        if (
            str(params.get("league") or "") == league_id
            and str(params.get("season") or "") == season
        ):
            return path
    return None


def _existing_statistics_cache(
    *,
    raw_dirs: Sequence[Path],
    fixture_id: str,
) -> Path | None:
    for path in _raw_files(raw_dirs, endpoint="statistics"):
        payload = _load_json(path)
        if str(_params(payload).get("fixture") or "") == fixture_id:
            return path
    return None


def _fixture_from_row(
    row: dict[str, Any],
    *,
    competition_id: str,
    league_id: str,
    season: str,
    raw_source: str,
) -> HistoricalFixture | None:
    fixture = _dict(row.get("fixture"))
    status = _dict(fixture.get("status"))
    if str(status.get("short") or "") != "FT":
        return None
    goals = _dict(row.get("goals"))
    home_goals = _int(goals.get("home"))
    away_goals = _int(goals.get("away"))
    if home_goals is None or away_goals is None:
        return None
    teams = _dict(row.get("teams"))
    home = _dict(teams.get("home"))
    away = _dict(teams.get("away"))
    kickoff = _parse_datetime(fixture.get("date"))
    fixture_id = str(fixture.get("id") or "")
    home_team = str(home.get("name") or "")
    away_team = str(away.get("name") or "")
    if not fixture_id or not home_team or not away_team or kickoff is None:
        return None
    venue = _dict(fixture.get("venue"))
    neutral_site = not bool(venue.get("id"))
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id=competition_id,
        league_id=league_id,
        season=season,
        kickoff_utc=kickoff,
        home_team=home_team,
        away_team=away_team,
        home_goals=home_goals,
        away_goals=away_goals,
        neutral_site=neutral_site,
        raw_source=raw_source,
    )


def _perform_provider_request(
    endpoint: str,
    params: dict[str, str],
    *,
    requester: ApiFootballRequester | None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    if requester is not None:
        return requester(endpoint, params)
    raise RuntimeError("PROVIDER_REQUESTER_REQUIRED")


def _stop_reason(*, status_code: int, quota_remaining: int | None) -> str | None:
    if status_code == 429:
        return "PROVIDER_HTTP_429"
    if status_code >= 400:
        return f"PROVIDER_HTTP_{status_code}"
    if quota_remaining is not None and quota_remaining <= 0:
        return "DAILY_QUOTA_EXHAUSTED"
    if quota_remaining is not None and quota_remaining <= 10:
        return "QUOTA_WARNING"
    return None


def _write_raw(
    path: Path,
    *,
    endpoint: str,
    params: dict[str, str],
    payload: dict[str, Any],
    captured_at: datetime,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "endpoint": endpoint,
        "params": params,
        "captured_at": captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "payload": payload,
    }
    path.write_text(
        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ledger_record(
    *,
    competition_id: str,
    endpoint: str,
    status_code: int,
    response_count: int,
    provider_call_index: int,
    quota_remaining: int | None,
    captured_at: datetime,
) -> dict[str, Any]:
    return {
        "competition_id": competition_id,
        "endpoint": endpoint,
        "status_code": status_code,
        "response_count": response_count,
        "provider_call_index": provider_call_index,
        "quota_remaining": quota_remaining,
        "captured_at": captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _params(payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params")
    if isinstance(params, dict):
        return params
    inner = _dict(payload.get("payload"))
    params = inner.get("parameters")
    return params if isinstance(params, dict) else {}


def _response_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    inner = _dict(payload.get("payload")) or payload
    response = inner.get("response")
    if not isinstance(response, list):
        return []
    return [item for item in response if isinstance(item, dict)]


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(float(value), minimum), maximum)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def report_sha256(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
