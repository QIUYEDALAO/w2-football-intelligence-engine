from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from w2.historical.adapters import CsvAdapter, JsonAdapter, ParquetAdapter
from w2.historical.builder import AsOfDatasetBuilder
from w2.historical.dataset import AsOfSample, LabelReference
from w2.historical.leakage import LeakageGuard, assert_no_random_time_split
from w2.historical.quality import DataQualityChecker
from w2.historical.registry import (
    HistoricalSourceRegistry,
    HistoricalSourceStatus,
    registry_to_manifest,
)
from w2.historical.splitters import (
    chronological_split,
    expanding_split,
    rolling_split,
    walk_forward_split,
)

NOW = datetime(2025, 1, 1, 12, tzinfo=UTC)


def sample(fixture_id: str = "fixture-a", hours: int = 24) -> AsOfSample:
    kickoff = NOW + timedelta(days=1)
    as_of = kickoff - timedelta(hours=hours)
    return AsOfSample(
        fixture_id=fixture_id,
        competition="Synthetic League",
        season="2025",
        kickoff_utc=kickoff,
        prediction_phase=f"T-{hours}h",
        as_of_time=as_of,
        data_cutoff=as_of - timedelta(minutes=1),
        odds_snapshot={
            "snapshot_type": "first_seen",
            "provider_updated_at": (as_of - timedelta(minutes=2)).isoformat(),
            "bookmaker_count": 1,
            "one_x_two_reciprocal_sum": "1.05",
            "lines": ["-0.25", "2.5"],
            "first_seen_is_opening": False,
        },
        lineup_status={"provider_updated_at": (as_of - timedelta(minutes=3)).isoformat()},
        injury_status={"provider_updated_at": (as_of - timedelta(minutes=4)).isoformat()},
        team_rating_features={"as_of_time": (as_of - timedelta(days=1)).isoformat()},
        raw_payload_refs=("raw://fixture-a",),
        feature_snapshot_version="v1",
        label_reference=LabelReference(
            fixture_id=fixture_id,
            result_status="FINAL",
            home_goals=1,
            away_goals=0,
            confirmed_at=kickoff + timedelta(hours=2),
            raw_payload_refs=("raw://label-a",),
        ),
        provenance={"source_id": "synthetic-source", "provider_mapping_id": "mapping-a"},
    )


def leaked_closing_sample() -> AsOfSample:
    kickoff = NOW + timedelta(days=1)
    as_of = kickoff - timedelta(hours=24)
    return AsOfSample(
        fixture_id="leaked",
        competition="Synthetic League",
        season="2025",
        kickoff_utc=kickoff,
        prediction_phase="T-24h",
        as_of_time=as_of,
        data_cutoff=as_of - timedelta(minutes=1),
        odds_snapshot={
            "snapshot_type": "closing",
            "provider_updated_at": (as_of + timedelta(hours=1)).isoformat(),
            "bookmaker_count": 1,
            "one_x_two_reciprocal_sum": "1.05",
            "lines": ["2.5"],
            "first_seen_is_opening": False,
        },
        lineup_status={"provider_updated_at": (as_of - timedelta(minutes=3)).isoformat()},
        injury_status={"provider_updated_at": (as_of - timedelta(minutes=4)).isoformat()},
        team_rating_features={"as_of_time": (as_of - timedelta(days=1)).isoformat()},
        raw_payload_refs=("raw://leaked",),
        feature_snapshot_version="v1",
        label_reference=LabelReference(
            fixture_id="leaked",
            result_status="FINAL",
            home_goals=2,
            away_goals=1,
            confirmed_at=kickoff + timedelta(hours=2),
            raw_payload_refs=("raw://label-leaked",),
        ),
        provenance={"source_id": "synthetic-source", "provider_mapping_id": "mapping-leaked"},
    )


def test_source_registry_statuses_and_manifest() -> None:
    registry = HistoricalSourceRegistry(
        source_id="synthetic-source",
        provider="synthetic",
        national_or_club="club",
        competitions=("Synthetic League",),
        seasons=("2024", "2025"),
        date_range=(NOW, NOW + timedelta(days=365)),
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
        snapshot_frequency="daily",
        provider_ids=("fixture", "team"),
        provenance="unit test",
        licence_commercial_use_status=HistoricalSourceStatus.UNVERIFIED,
        acquisition_status=HistoricalSourceStatus.NOT_SELECTED,
        validation_status=HistoricalSourceStatus.AVAILABLE,
    )
    manifest = registry_to_manifest(registry)
    assert manifest["coverage"]["1X2"] == "AVAILABLE"  # type: ignore[index]


def test_asof_sample_rejects_naive_time_and_label_leakage() -> None:
    with pytest.raises(ValueError):
        LabelReference(
            fixture_id="fixture-a",
            result_status="FINAL",
            home_goals=1,
            away_goals=0,
            confirmed_at=datetime(2025, 1, 1, 1),
            raw_payload_refs=("raw://label",),
        )
    with pytest.raises(ValueError):
        AsOfSample(
            fixture_id="fixture-a",
            competition="Synthetic League",
            season="2025",
            kickoff_utc=NOW + timedelta(days=1),
            prediction_phase="T-24h",
            as_of_time=NOW,
            data_cutoff=NOW - timedelta(minutes=1),
            odds_snapshot={"home_goals": 1},
            lineup_status={},
            injury_status={},
            team_rating_features={},
            raw_payload_refs=("raw://x",),
            feature_snapshot_version="v1",
            label_reference=sample().label_reference,
            provenance={"provider_mapping_id": "mapping-a"},
        )


def test_adapters_and_deterministic_builder(tmp_path: Path) -> None:
    rows = [{"b": "2", "a": "1"}]
    csv_path = tmp_path / "rows.csv"
    json_path = tmp_path / "rows.jsonl"
    parquet_path = tmp_path / "rows.parquet"
    CsvAdapter().write(csv_path, rows)
    JsonAdapter().write(json_path, rows)
    ParquetAdapter().write(parquet_path, rows)
    assert CsvAdapter().read(csv_path) == [{"a": "1", "b": "2"}]
    assert JsonAdapter().read(json_path) == rows
    assert ParquetAdapter().read(parquet_path) == rows
    built = AsOfDatasetBuilder(tmp_path).build(
        dataset_id="demo",
        version="v1",
        samples=[sample("a", 72), sample("a", 24)],
        incremental=False,
    )
    rebuilt = AsOfDatasetBuilder(tmp_path).build(
        dataset_id="demo",
        version="v1",
        samples=[sample("a", 72), sample("a", 24)],
        incremental=True,
    )
    assert built.manifest["sample_order"] == rebuilt.manifest["sample_order"]
    assert built.artifacts[0].sha256 == rebuilt.artifacts[0].sha256


def test_duplicate_detection(tmp_path: Path) -> None:
    builder = AsOfDatasetBuilder(tmp_path)
    with pytest.raises(ValueError):
        builder.build(dataset_id="demo", version="v1", samples=[sample("a", 24), sample("a", 24)])


def test_leakage_rules_and_splitters() -> None:
    clean = [sample("a", 72), sample("a", 24), sample("b", 72), sample("b", 24)]
    assert LeakageGuard().check(clean) == []
    findings = LeakageGuard().check([leaked_closing_sample()])
    assert {finding.rule for finding in findings} >= {
        "closing_odds_used_before_closing",
        "future_odds",
    }
    split = chronological_split(clean)
    assert split.train and split.validation and split.test
    assert rolling_split(clean, train_size=2, test_size=1)
    assert expanding_split(clean, min_train_size=2, test_size=1)
    assert walk_forward_split(clean, initial_train_size=2, step_size=1)
    with pytest.raises(ValueError):
        assert_no_random_time_split("random")


def test_quality_checker_passes_and_reports_issues() -> None:
    run = DataQualityChecker().check("demo", "v1", [sample("a", 24), sample("b", 24)])
    assert run.status == "PASS"
    broken_payload = sample("broken", 24).feature_payload()
    broken_payload["odds_snapshot"]["first_seen_is_opening"] = True
    assert json.dumps(broken_payload)
