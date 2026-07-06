from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
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


ApiFootballRequester = Callable[[str, dict[str, str]], tuple[int, dict[str, str], dict[str, Any]]]


def build_free_tier_2024_backtest_report(
    *,
    raw_dirs: Sequence[Path] = DEFAULT_RAW_DIRS,
    season: str = "2024",
    competitions: Sequence[str] = ANNUAL_COMPETITIONS,
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
            if stats_path.exists():
                skipped.append(stats_path.as_posix())
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


def _statistics_fixture_ids(raw_dirs: Sequence[Path]) -> set[str]:
    fixture_ids: set[str] = set()
    for path in _raw_files(raw_dirs, endpoint="statistics"):
        payload = _load_json(path)
        params = _params(payload)
        fixture_id = str(params.get("fixture") or "")
        if fixture_id:
            fixture_ids.add(fixture_id)
    return fixture_ids


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


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def report_sha256(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
