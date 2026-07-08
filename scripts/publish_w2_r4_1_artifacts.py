#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from w2.backtest.free_tier_2024 import (  # noqa: E402
    MIN_LAMBDA_FIT_SAMPLE,
    _fit_temperature,
    load_fixture_statistics,
    load_historical_fixtures,
    load_understat_fixture_dataset,
)
from w2.competitions.league_whitelist_scope import IN_SEASON_NATIONAL_LEAGUES  # noqa: E402
from w2.competitions.registry import CompetitionRegistry  # noqa: E402
from w2.models.r4_1_artifacts import build_r4_1_artifact_payload  # noqa: E402
from w2.models.r4_1_features import (  # noqa: E402
    fit_r4_1_lambda_model,
    r4_1_offline_model_samples,
    r4_1_predictions,
    rho_from_r4_1,
)

OUT_DIR = REPO_ROOT / "runtime" / "model_artifacts" / "r4_1"
MODEL_REPORT = REPO_ROOT / "runtime" / "market_baseline_eval" / "model_phase_report.json"
PRO_DAY1_RAW = REPO_ROOT / "runtime" / "w2_pro_day1_provider_data" / "raw"
PRO_DAY1_DIRS = tuple(
    PRO_DAY1_RAW / sub for sub in ("", "fixtures", "statistics", "odds", "lineups")
)
UNDERSTAT_DIRS = (REPO_ROOT / "runtime" / "w2_understat_model_iter1" / "understat",)

TARGET_COMPETITIONS = ("bundesliga", "chinese_super_league", "allsvenskan")
INSEASON_ARTIFACT_COMPETITIONS = ("chinese_super_league", "allsvenskan")
BIG5_COMPETITIONS = ("premier_league", "la_liga", "bundesliga", "serie_a", "ligue_1")
INSEASON_SEASONS = ("2024", "2025")
BIG5_SEASONS = ("2023", "2024")
MIN_HISTORY = 5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = publish_artifacts(args.out_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for item in report["artifacts"]:
            print(
                f"{item['competition_id']} {item['artifact_path']} "
                f"{item['artifact_hash']} {item['protocol_identity_check']}"
            )
    return 0 if report["status"] == "PASS" else 1


def publish_artifacts(out_dir: Path) -> dict[str, Any]:
    if "brasileirao_serie_a" in TARGET_COMPETITIONS:
        raise SystemExit("brasileirao_serie_a must not be published for R4.1")
    eval_report = _load_model_report()
    out_dir.mkdir(parents=True, exist_ok=True)

    big5_fixtures, big5_stats = load_understat_fixture_dataset(
        raw_dirs=list(UNDERSTAT_DIRS),
        seasons=BIG5_SEASONS,
        competitions=BIG5_COMPETITIONS,
    )
    big5_samples = r4_1_offline_model_samples(
        fixtures=big5_fixtures,
        statistics_by_fixture=big5_stats,
        min_history=MIN_HISTORY,
    )
    big5_identity = _protocol_identity_check(
        name="big5_cross_season_2023_to_2024",
        samples=[sample for sample in big5_samples if sample.fixture.season == "2023"],
        expected=_expected_r4_1(
            eval_report,
            competition="big5_pooled",
            protocol="big5_cross_season_2023_to_2024",
        ),
    )
    big5_full = _fit_protocol(big5_samples)

    registry_entries = CompetitionRegistry().entries()
    stats = load_fixture_statistics(list(PRO_DAY1_DIRS))
    inseason_fixtures = []
    for season in INSEASON_SEASONS:
        inseason_fixtures.extend(
            load_historical_fixtures(
                raw_dirs=list(PRO_DAY1_DIRS),
                entries=registry_entries,
                season=season,
                competitions=list(IN_SEASON_NATIONAL_LEAGUES),
            )
        )
    inseason_samples = r4_1_offline_model_samples(
        fixtures=inseason_fixtures,
        statistics_by_fixture=stats,
        min_history=MIN_HISTORY,
    )
    inseason_identity = _protocol_identity_check(
        name="inseason_pooled_cross_season",
        samples=[sample for sample in inseason_samples if sample.fixture.season == "2024"],
        expected=_expected_r4_1(
            eval_report,
            competition="inseason_pooled",
            protocol="inseason_pooled_cross_season",
        ),
    )
    inseason_full = _fit_protocol(inseason_samples)

    artifacts = []
    for competition_id in TARGET_COMPETITIONS:
        fit = big5_full if competition_id == "bundesliga" else inseason_full
        identity = big5_identity if competition_id == "bundesliga" else inseason_identity
        payload = build_r4_1_artifact_payload(
            competition_id=competition_id,
            coefficients=fit["model"].coefficients,
            feature_names=fit["model"].feature_names,
            temperature=fit["temperature"],
            rho=rho_from_r4_1(fit["model"]),
            train_cutoff_utc=fit["train_cutoff_utc"],
            fit_sample_count=fit["fit_sample_count"],
            protocol_identity_check=identity["status"],
            artifact_version="v1",
        )
        path = out_dir / f"{competition_id}.v1.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifacts.append(
            {
                "competition_id": competition_id,
                "artifact_path": path.as_posix(),
                "artifact_hash": payload["artifact_hash"],
                "fit_sample_count": payload["fit_sample_count"],
                "train_cutoff_utc": payload["train_cutoff_utc"],
                "protocol_identity_check": identity["status"],
            }
        )
    return {
        "status": "PASS",
        "provider_calls": 0,
        "target_competitions": list(TARGET_COMPETITIONS),
        "disabled_competitions": ["brasileirao_serie_a"],
        "protocol_identity": [big5_identity, inseason_identity],
        "artifacts": artifacts,
    }


def _fit_protocol(samples: list[Any]) -> dict[str, Any]:
    if len(samples) < MIN_LAMBDA_FIT_SAMPLE:
        raise SystemExit(f"insufficient R4.1 fit samples: {len(samples)}")
    model = fit_r4_1_lambda_model(samples, min_sample=MIN_LAMBDA_FIT_SAMPLE)
    raw = r4_1_predictions(samples, model)
    temperature = _fit_temperature(raw)
    return {
        "model": model,
        "temperature": temperature,
        "fit_sample_count": len(samples),
        "train_cutoff_utc": max(sample.fixture.kickoff_utc for sample in samples).astimezone(UTC),
    }


def _protocol_identity_check(
    *,
    name: str,
    samples: list[Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    fit = _fit_protocol(samples)
    model = fit["model"]
    actual_coefficients = [round(float(value), 6) for value in model.coefficients]
    expected_coefficients = [round(float(value), 6) for value in expected["coefficients"]]
    actual_temperature = round(float(fit["temperature"]), 6)
    expected_temperature = round(float(expected["temperature"]), 6)
    actual_rho = round(float(rho_from_r4_1(model)), 6)
    expected_rho = round(float(expected["policy"]["dixon_coles_rho"]), 6)
    mismatches = []
    if actual_coefficients != expected_coefficients:
        mismatches.append("coefficients")
    if actual_temperature != expected_temperature:
        mismatches.append("temperature")
    if actual_rho != expected_rho:
        mismatches.append("rho")
    if mismatches:
        raise SystemExit(
            f"R4.1 protocol identity mismatch for {name}: {','.join(mismatches)}"
        )
    return {
        "name": name,
        "status": "PASS",
        "fit_sample_count": fit["fit_sample_count"],
        "temperature": actual_temperature,
        "rho": actual_rho,
    }


def _expected_r4_1(
    report: dict[str, Any],
    *,
    competition: str,
    protocol: str,
) -> dict[str, Any]:
    for item in report["results"]:
        if item.get("competition") == competition and item.get("protocol") == protocol:
            r4_1 = item.get("r4_1")
            if isinstance(r4_1, dict):
                return r4_1
    raise SystemExit(f"missing expected R4.1 eval record: {competition}/{protocol}")


def _load_model_report() -> dict[str, Any]:
    if not MODEL_REPORT.exists():
        raise SystemExit(f"missing eval report: {MODEL_REPORT}")
    payload = json.loads(MODEL_REPORT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"invalid eval report payload: {MODEL_REPORT}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
