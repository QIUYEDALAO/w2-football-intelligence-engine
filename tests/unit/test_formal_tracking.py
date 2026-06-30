from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from w2.tracking.formal_results import (
    MIN_BUCKET_SAMPLES_FOR_RATE,
    build_tracking_report,
    capture_formal_snapshots,
    endpoint_summary,
    settle_formal_snapshots,
    settle_snapshot,
    snapshot_from_card,
)

NOW = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)


def formal_card(
    *,
    fixture_id: str = "1562345",
    kickoff: str = "2026-06-30T01:00:00Z",
    line: str = "0.5",
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "kickoff_utc": kickoff,
        "status": "UPCOMING",
        "competition_name": "世界杯",
        "home_team_name": "Netherlands",
        "away_team_name": "Morocco",
        "formal_recommendation": True,
        "candidate": False,
        "recommendation": {
            "tier": "FORMAL",
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY_AH",
            "selection_label_cn": "Morocco 受让",
            "line": line,
            "odds": "2.27",
            "risk_adjusted_ev": "13.5pct",
            "reverse_factor_value": True,
            "generated_at": "2026-06-29T10:00:00Z",
        },
        "pricing_shadow": {
            "model_version": "S1_SHADOW",
            "calibration_version": "UNVALIDATED",
            "simulation_model_version": "FORMAL_SIMULATION",
            "simulation_calibration_version": "UNVALIDATED",
            "fair_ah": 0.0,
            "market_ah": 0.5,
            "edge_ah": 0.5,
            "coverage": 0.8,
            "asof_market_snapshot_id": "lock-1",
            "devig_method": "POWER",
            "beats_market": False,
        },
        "market_movement": {
            "pattern": "STABLE",
            "as_of_latest": "2026-06-29T10:00:00Z",
        },
        "market_divergence": {
            "open_divergence": 0.5,
            "lock_divergence": 0.5,
        },
    }


def finished_card(
    *,
    home_goals: int = 1,
    away_goals: int = 1,
    line: str = "0.5",
) -> dict[str, object]:
    card = formal_card(line=line)
    card["status"] = "FINISHED"
    card["result"] = {
        "status": "FINISHED",
        "home_goals": home_goals,
        "away_goals": away_goals,
        "settled_at": "2026-06-30T03:00:00Z",
    }
    return card


def test_capture_formal_snapshot_is_prematch_and_immutable(tmp_path) -> None:
    result = capture_formal_snapshots(
        [formal_card()],
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        now=NOW,
        release_sha="sha",
    )

    assert result["written"] == 1
    assert result["not_a_formal_gate"] is True
    assert result["posthoc_only"] is True
    assert list((tmp_path / "formal_recommendation_snapshots").glob("*.json"))


def test_capture_formal_snapshot_preserves_scoreline_and_simulation_evidence(tmp_path) -> None:
    card = formal_card()
    card["scoreline_reference"] = {
        "source": "formal_simulation",
        "top_scorelines": [{"scoreline": "1-1", "probability_label": "12%"}],
    }
    card["pricing_shadow"] = {
        **card["pricing_shadow"],  # type: ignore[index]
        "simulation": {
            "status": "READY",
            "simulations": 10000,
            "model_version": "FORMAL_SIMULATION",
            "calibration_version": "UNVALIDATED",
        },
    }

    capture_formal_snapshots(
        [card],
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        now=NOW,
    )

    [snapshot_path] = list((tmp_path / "formal_recommendation_snapshots").glob("*.json"))
    snapshot = snapshot_path.read_text(encoding="utf-8")
    assert '"scoreline_reference"' in snapshot
    assert '"simulations": 10000' in snapshot


def test_capture_blocks_post_kickoff_snapshot(tmp_path) -> None:
    result = capture_formal_snapshots(
        [formal_card(kickoff="2026-06-29T11:00:00Z")],
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        now=NOW,
    )

    assert result["written"] == 0
    assert result["blockers"]["NOT_PREMATCH"] == 1


def test_duplicate_fixture_market_selection_line_is_not_overwritten(tmp_path) -> None:
    first = capture_formal_snapshots(
        [formal_card(line="0")],
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        now=NOW,
    )
    second = capture_formal_snapshots(
        [formal_card(line="0")],
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        now=NOW,
    )

    assert first["written"] == 1
    assert second["written"] == 0
    assert second["already_captured"] == 1


def test_settlement_push_counts_as_sample_but_not_win(tmp_path) -> None:
    capture_formal_snapshots(
        [formal_card(line="0")],
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        now=NOW,
    )
    result = settle_formal_snapshots(
        [finished_card(home_goals=1, away_goals=1, line="0")],
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        now=NOW,
    )

    assert result["written"] == 1
    report = build_tracking_report(runtime_root=tmp_path)
    assert report["sample_count"] == 1
    assert report["win_count"] == 0
    assert report["win_rate"] is None
    assert report["roi"] is None


def test_void_settlement_is_excluded_from_sample() -> None:
    snapshot, blocker = snapshot_from_card(formal_card(), now=NOW)
    assert blocker is None
    assert snapshot is not None

    settlement = settle_snapshot(
        snapshot,
        {"status": "POSTPONED", "home_goals": None, "away_goals": None},
        now=NOW,
    )

    assert settlement["settlement_outcome"] == "VOID"
    assert settlement["sample_included"] is False
    assert settlement["win_included"] is False


def test_report_hides_rates_until_minimum_sample_size(tmp_path) -> None:
    capture_formal_snapshots(
        [formal_card(fixture_id=f"f{i}") for i in range(MIN_BUCKET_SAMPLES_FOR_RATE - 1)],
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        now=NOW,
    )
    settle_formal_snapshots(
        [finished_card() | {"fixture_id": f"f{i}"} for i in range(MIN_BUCKET_SAMPLES_FOR_RATE - 1)],
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        now=NOW,
    )
    report = build_tracking_report(runtime_root=tmp_path)

    assert report["status"] == "OBSERVING"
    assert report["sample_count"] == MIN_BUCKET_SAMPLES_FOR_RATE - 1
    assert report["win_rate"] is None
    assert report["roi"] is None
    assert "观察中" in report["label"]


def test_endpoint_summary_is_posthoc_not_formal_gate(tmp_path) -> None:
    summary = endpoint_summary(runtime_root=tmp_path)

    assert summary["not_a_formal_gate"] is True
    assert summary["posthoc_only"] is True
    assert summary["sample_count"] == 0
    assert summary["win_rate"] is None


def test_endpoint_summary_skips_unreadable_artifact_dirs(tmp_path, monkeypatch) -> None:
    def raise_permission_error(self: Path, pattern: str):
        raise PermissionError("unreadable")

    monkeypatch.setattr(Path, "glob", raise_permission_error)

    summary = endpoint_summary(runtime_root=tmp_path)

    assert summary["not_a_formal_gate"] is True
    assert summary["posthoc_only"] is True
    assert summary["sample_count"] == 0
    assert summary["label"] == "观察中 · 0/30"
