#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from w2.historical.builder import AsOfDatasetBuilder
from w2.historical.dataset import AsOfSample, LabelReference
from w2.historical.leakage import LeakageGuard
from w2.historical.quality import DataQualityChecker
from w2.historical.registry import (
    HistoricalSourceRegistry,
    HistoricalSourceStatus,
    registry_to_manifest,
)
from w2.historical.splitters import chronological_split

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "fixtures/stage5_demo"
REPORTS = ROOT / "reports"
W1_ROOT = Path.home() / ".openclaw" / "workspace" / "w1_world_cup_engine"


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_sample(
    *,
    fixture_id: str,
    competition: str,
    season: str,
    kickoff: datetime,
    phase_hours: int,
    home_goals: int,
    away_goals: int,
    source_id: str,
) -> AsOfSample:
    as_of = kickoff - timedelta(hours=phase_hours)
    phase = f"T-{phase_hours}h"
    return AsOfSample(
        fixture_id=fixture_id,
        competition=competition,
        season=season,
        kickoff_utc=kickoff,
        prediction_phase=phase,
        as_of_time=as_of,
        data_cutoff=as_of - timedelta(minutes=1),
        odds_snapshot={
            "snapshot_type": "first_seen",
            "provider_updated_at": (as_of - timedelta(minutes=3)).isoformat(),
            "bookmaker_count": 2,
            "one_x_two_reciprocal_sum": "1.08",
            "markets": ["ONE_X_TWO", "ASIAN_HANDICAP", "TOTALS"],
            "lines": ["-0.25", "2.5"],
            "first_seen_is_opening": False,
        },
        lineup_status={
            "provider_updated_at": (as_of - timedelta(minutes=10)).isoformat(),
            "home_status": "projected",
            "away_status": "projected",
        },
        injury_status={
            "provider_updated_at": (as_of - timedelta(minutes=12)).isoformat(),
            "known_absences": 1,
        },
        team_rating_features={
            "as_of_time": (as_of - timedelta(days=1)).isoformat(),
            "home_rating": "0.62",
            "away_rating": "0.55",
        },
        raw_payload_refs=(f"raw://stage5/{fixture_id}/{phase}",),
        feature_snapshot_version="stage5-demo-v1",
        label_reference=LabelReference(
            fixture_id=fixture_id,
            result_status="FINAL",
            home_goals=home_goals,
            away_goals=away_goals,
            confirmed_at=kickoff + timedelta(hours=3),
            raw_payload_refs=(f"raw://stage5/{fixture_id}/label",),
        ),
        provenance={
            "source_id": source_id,
            "provider_mapping_id": f"mapping-{fixture_id}",
            "synthetic": True,
        },
    )


def samples_for(dataset_id: str) -> list[AsOfSample]:
    if dataset_id == "international":
        fixtures = [
            (
                "fictional-int-2024-001",
                "Synthetic Nations Cup",
                "2024",
                utc("2024-03-01T18:00:00Z"),
                2,
                1,
            ),
            (
                "fictional-int-2025-001",
                "Synthetic Nations Cup",
                "2025",
                utc("2025-03-01T18:00:00Z"),
                0,
                0,
            ),
        ]
    else:
        fixtures = [
            (
                "fictional-club-2024-001",
                "Synthetic Club League",
                "2024",
                utc("2024-08-10T15:00:00Z"),
                3,
                2,
            ),
            (
                "fictional-club-2025-001",
                "Synthetic Club League",
                "2025",
                utc("2025-08-10T15:00:00Z"),
                1,
                2,
            ),
        ]
    samples: list[AsOfSample] = []
    for fixture_id, competition, season, kickoff, home_goals, away_goals in fixtures:
        samples.append(
            make_sample(
                fixture_id=fixture_id,
                competition=competition,
                season=season,
                kickoff=kickoff,
                phase_hours=72,
                home_goals=home_goals,
                away_goals=away_goals,
                source_id=f"{dataset_id}-synthetic-source",
            )
        )
        samples.append(
            make_sample(
                fixture_id=fixture_id,
                competition=competition,
                season=season,
                kickoff=kickoff,
                phase_hours=24,
                home_goals=home_goals,
                away_goals=away_goals,
                source_id=f"{dataset_id}-synthetic-source",
            )
        )
    return samples


def build_registry(dataset_id: str) -> HistoricalSourceRegistry:
    return HistoricalSourceRegistry(
        source_id=f"{dataset_id}-synthetic-source",
        provider="synthetic_offline",
        national_or_club="national" if dataset_id == "international" else "club",
        competitions=("Synthetic Nations Cup",)
        if dataset_id == "international"
        else ("Synthetic Club League",),
        seasons=("2024", "2025"),
        date_range=(utc("2024-01-01T00:00:00Z"), utc("2025-12-31T00:00:00Z")),
        fixtures_coverage=HistoricalSourceStatus.AVAILABLE,
        results_coverage=HistoricalSourceStatus.AVAILABLE,
        one_x_two_coverage=HistoricalSourceStatus.AVAILABLE,
        asian_handicap_coverage=HistoricalSourceStatus.PARTIAL,
        totals_coverage=HistoricalSourceStatus.AVAILABLE,
        lineups_coverage=HistoricalSourceStatus.PARTIAL,
        injuries_coverage=HistoricalSourceStatus.PARTIAL,
        opening_capability=HistoricalSourceStatus.UNVERIFIED,
        first_seen_capability=HistoricalSourceStatus.AVAILABLE,
        closing_capability=HistoricalSourceStatus.PARTIAL,
        snapshot_frequency="demo fixed T-72h/T-24h",
        provider_ids=("fixture", "team", "bookmaker"),
        provenance="synthetic Stage 5A fixture; no real W1 data copied",
        licence_commercial_use_status=HistoricalSourceStatus.UNVERIFIED,
        acquisition_status=HistoricalSourceStatus.NOT_SELECTED,
        validation_status=HistoricalSourceStatus.AVAILABLE,
    )


def audit_w1_candidates() -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    roots = [
        W1_ROOT / "reports/legacy_baseline",
        W1_ROOT / "reports/legacy_classification",
        W1_ROOT / "reports/legacy_decisions",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".csv"}:
                candidates.append(
                    {
                        "relative_path": str(path.relative_to(W1_ROOT)),
                        "sha256": digest(path),
                        "size_bytes": path.stat().st_size,
                        "copy_status": "NOT_COPIED",
                    }
                )
    try:
        w1_head = subprocess.check_output(
            ["git", "-C", str(W1_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        w1_head = "UNAVAILABLE"
    return {
        "w1_head": w1_head,
        "audit_mode": "read_only_inventory_no_copy",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def build_negative_sample() -> dict[str, object]:
    leaked = make_sample(
        fixture_id="fictional-negative-001",
        competition="Synthetic Leakage Cup",
        season="2025",
        kickoff=utc("2025-09-01T18:00:00Z"),
        phase_hours=24,
        home_goals=4,
        away_goals=3,
        source_id="negative-synthetic-source",
    )
    payload = leaked.feature_payload()
    payload["odds_snapshot"]["snapshot_type"] = "closing"
    payload["odds_snapshot"]["provider_updated_at"] = utc("2025-09-01T19:00:00Z").isoformat()
    return payload


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    datasets_result: dict[str, object] = {}
    result: dict[str, object] = {
        "stage": "5A",
        "datasets": datasets_result,
        "negative_leakage_sample": build_negative_sample(),
    }
    for dataset_id in ("international", "club_league"):
        registry = build_registry(dataset_id)
        samples = samples_for(dataset_id)
        build = AsOfDatasetBuilder(OUTPUT).build(
            dataset_id=dataset_id, version="v1", samples=samples, incremental=False
        )
        quality = DataQualityChecker().check(dataset_id, "v1", samples)
        split = chronological_split(samples)
        leakage_findings = LeakageGuard().check(samples)
        registry_path = OUTPUT / dataset_id / "registry.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps(registry_to_manifest(registry), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        datasets_result[dataset_id] = {
            "manifest": build.manifest,
            "quality_status": quality.status,
            "leakage_findings": [finding.__dict__ for finding in leakage_findings],
            "split_counts": {
                "train": len(split.train),
                "validation": len(split.validation),
                "test": len(split.test),
            },
            "registry": registry_to_manifest(registry),
        }
    (REPORTS / "W2_STAGE5_SOURCE_COVERAGE_AUDIT.json").write_text(
        json.dumps(audit_w1_candidates(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "W2_STAGE5A_RESULT.md").write_text(
        "\n".join(
            [
                "# W2 Stage 5A Result",
                "",
                "STAGE_5A=COMPLETED",
                "STAGE_5=PROVISIONAL",
                "REAL_HISTORICAL_IMPORT_CHECKPOINT_REQUIRED",
                "GATE_2=CLOSED",
                "GATE_3=NOT_STARTED",
                "",
                "No network calls, W1 migration, real historical import, "
                "or model training were performed.",
                "Demo datasets are synthetic and use fictional teams only.",
                "PUSH_BLOCKED_NO_ORIGIN",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (REPORTS / "W2_STAGE5A_DEMO_DATASETS.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print("W2 Stage5 demo datasets built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
