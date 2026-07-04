from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.audit_export import build_audit_export, write_audit_export
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.forward_ops_models import ForwardMarketSnapshotModel
from w2.infrastructure.persistence.models import RecommendationLockModel, SettlementModel


def test_audit_export_builds_five_tables_from_dashboard_payload() -> None:
    export = build_audit_export(_dashboard_payload())

    assert set(export.tables) == {
        "prematch_recommendations",
        "market_timeline_snapshots",
        "locked_recommendation_snapshots",
        "settlement_history",
        "calibration_report",
    }
    assert export.manifest["provider_calls"] == 0
    assert export.manifest["db_writes"] == 0
    assert export.manifest["status"] == "PASS"
    assert export.manifest["exported_at"] == "2026-07-01T01:00:00Z"
    assert export.tables["prematch_recommendations"][0]["fixture_id"] == "fixture-1"
    assert export.tables["prematch_recommendations"][0]["report_state"] == "LOCKED"
    assert export.tables["prematch_recommendations"][0]["decision_tier"] == "ANALYSIS_PICK"
    assert export.tables["prematch_recommendations"][0]["data_status"] == "READY"
    assert export.tables["prematch_recommendations"][0]["missing_fields"] == []
    assert export.tables["prematch_recommendations"][0]["stale_fields"] == ["odds"]
    assert export.tables["prematch_recommendations"][0]["provider_budget_status"] == "AVAILABLE"
    assert export.tables["prematch_recommendations"][0]["lock_eligible"] is True
    assert (
        export.tables["prematch_recommendations"][0]["decision_contract_reason_code"]
        == "EDGE_INSUFFICIENT"
    )
    assert "status" not in export.tables["prematch_recommendations"][0]
    assert export.tables["prematch_recommendations"][0]["market_ah_display"] == "主队 -0.5"
    assert [row["checkpoint"] for row in export.tables["market_timeline_snapshots"]] == [
        "open",
        "current",
    ]
    assert export.tables["market_timeline_snapshots"][0]["pattern"] == "STABLE"
    assert export.tables["market_timeline_snapshots"][0]["line"] == -0.5
    assert export.tables["market_timeline_snapshots"][0]["home_price"] == 1.91
    assert export.tables["market_timeline_snapshots"][0]["away_price"] == 1.95
    assert export.tables["market_timeline_snapshots"][0]["bookmaker_count"] == 4
    assert export.tables["market_timeline_snapshots"][1]["line"] == -0.75
    assert export.tables["market_timeline_snapshots"][1]["home_price"] == 2.02
    assert export.tables["market_timeline_snapshots"][1]["away_price"] == 1.84
    assert export.tables["market_timeline_snapshots"][1]["bookmaker_count"] == 5
    assert export.tables["locked_recommendation_snapshots"][0]["snapshot_payload_hash"] == "abc"
    assert export.tables["settlement_history"][0]["status"] == "PENDING"
    assert export.tables["settlement_history"][0]["lock_snapshot_status"] == "MISSING_LOCK_SNAPSHOT"
    assert export.tables["calibration_report"] == []


def test_audit_export_leaves_recommendation_fields_empty_for_non_formal() -> None:
    payload = _dashboard_payload()
    match = payload["all"][0]  # type: ignore[index]
    assert isinstance(match, dict)
    match.pop("locked_pre_match_recommendation")
    match["formal_recommendation"] = False
    match["recommendation"] = {"tier": "WATCH", "market": "ASIAN_HANDICAP"}
    match["pricing_shadow"] = {
        "market_ah": "-0.5",
        "fair_ah": "-0.6",
        "edge_ah": "0.1",
        "independent_signal_count": 5,
    }

    export = build_audit_export(payload)
    row = export.tables["prematch_recommendations"][0]

    assert row["report_state"] == "WATCH"
    assert row["recommendation_market"] is None
    assert row["recommendation_selection"] is None
    assert row["recommendation_line"] is None
    assert row["recommendation_odds"] is None
    assert row["raw_recommendation_json"] is None


def test_audit_export_keeps_recommendation_fields_for_formal_only() -> None:
    payload = _dashboard_payload()
    match = payload["all"][0]  # type: ignore[index]
    assert isinstance(match, dict)
    match.pop("locked_pre_match_recommendation")

    export = build_audit_export(payload)
    row = export.tables["prematch_recommendations"][0]

    assert row["report_state"] == "FORMAL"
    assert row["recommendation_market"] == "ASIAN_HANDICAP"
    assert row["recommendation_selection"] == "HOME_AH"
    assert row["recommendation_line"] == "-0.5"
    assert row["recommendation_odds"] == "1.91"
    assert row["ev_se"] == "0.21"


def test_audit_export_exposes_ev_uncertainty_blocker() -> None:
    payload = _dashboard_payload()
    match = payload["all"][0]  # type: ignore[index]
    assert isinstance(match, dict)
    match.pop("locked_pre_match_recommendation")
    match["formal_recommendation"] = False
    match["recommendation"] = None
    pricing_shadow = match["pricing_shadow"]
    assert isinstance(pricing_shadow, dict)
    pricing_shadow["formal_blockers"] = ["EV_WITHIN_UNCERTAINTY_BAND"]

    export = build_audit_export(payload)
    row = export.tables["prematch_recommendations"][0]

    assert row["formal_blockers"] == ["EV_WITHIN_UNCERTAINTY_BAND"]


def test_audit_export_preserves_zero_market_timeline_line() -> None:
    payload = _dashboard_payload()
    match = payload["all"][0]  # type: ignore[index]
    assert isinstance(match, dict)
    timeline = match["market_timeline"]
    assert isinstance(timeline, dict)
    timeline["open"] = {"line": 0, "home_price": 1.91, "away_price": 1.91, "bookmaker_count": 2}

    export = build_audit_export(payload)

    assert export.tables["market_timeline_snapshots"][0]["line"] == 0


def test_audit_export_requires_payload_as_of_for_deterministic_manifest() -> None:
    payload = _dashboard_payload()
    payload.pop("generated_at")

    with pytest.raises(ValueError, match="dashboard payload missing generated_at/as_of"):
        build_audit_export(payload)


def test_audit_export_appends_existing_model_rows_read_only() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            ForwardMarketSnapshotModel(
                fixture_id="fixture-db",
                phase="lock",
                captured_at=datetime(2026, 7, 1, 1, 0, tzinfo=UTC),
                market_comparable=True,
                payload={
                    "as_of": "2026-07-01T01:00:00Z",
                    "pattern": "JUMP_LINE",
                    "home_line": 0.25,
                    "home_price": 1.88,
                    "away_price": 2.02,
                    "bookmaker_count": 3,
                },
            )
        )
        session.add(
            RecommendationLockModel(
                recommendation_id="rec-db",
                status="LOCKED",
                locked_at=datetime(2026, 7, 1, 1, 0, tzinfo=UTC),
                reason="test",
                fixture_id="fixture-db",
                as_of=datetime(2026, 7, 1, 1, 0, tzinfo=UTC),
                tier="FORMAL",
                pick_side="HOME_AH",
                pick_line=Decimal("-0.5"),
                snapshot_payload_hash="h" * 64,
                release_sha="sha",
                reproducible=True,
                legacy_marker_only=False,
                data_profile="real-db",
            )
        )
        session.add(
            SettlementModel(
                recommendation_id="rec-db",
                lock_id=None,
                result_id="result-db",
                outcome="WIN",
                settled_at=datetime(2026, 7, 1, 3, 0, tzinfo=UTC),
            )
        )
        session.flush()

        export = build_audit_export(_dashboard_payload(), session=session)

    assert any(
        row["source"] == "forward_market_snapshot_model"
        and row["line"] == 0.25
        and row["home_price"] == 1.88
        and row["away_price"] == 2.02
        and row["bookmaker_count"] == 3
        for row in export.tables["market_timeline_snapshots"]
    )
    assert any(
        row["source"] == "recommendation_lock_model"
        for row in export.tables["locked_recommendation_snapshots"]
    )
    assert any(row["source"] == "settlement_model" for row in export.tables["settlement_history"])
    assert "calibration_report" in export.manifest["table_counts"]


def test_audit_export_writes_manifest_csv_and_json(tmp_path) -> None:
    export = build_audit_export(_dashboard_payload())

    written = write_audit_export(export, tmp_path, output_format="both")

    names = {path.name for path in written}
    assert "manifest.json" in names
    assert "prematch_recommendations.csv" in names
    assert "prematch_recommendations.json" in names
    assert "calibration_report.csv" in names
    assert "calibration_report.json" in names
    assert (tmp_path / "prematch_recommendations.csv").read_text(encoding="utf-8")
    assert '"provider_calls": 0' in (tmp_path / "manifest.json").read_text(encoding="utf-8")


def test_audit_export_writes_fixed_headers_for_empty_tables(tmp_path) -> None:
    export = build_audit_export({"generated_at": "2026-07-01T01:00:00Z", "all": []})

    write_audit_export(export, tmp_path, output_format="csv")

    with (tmp_path / "locked_recommendation_snapshots.csv").open(encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[:4] == ["source", "lock_id", "recommendation_id", "fixture_id"]

    with (tmp_path / "market_timeline_snapshots.csv").open(encoding="utf-8") as handle:
        timeline_header = next(csv.reader(handle))
    assert "line" in timeline_header
    assert "home_price" in timeline_header
    assert "away_price" in timeline_header
    assert "bookmaker_count" in timeline_header

    with (tmp_path / "calibration_report.csv").open(encoding="utf-8") as handle:
        calibration_header = next(csv.reader(handle))
    assert calibration_header[:4] == ["schema_version", "generated_at", "as_of", "release_sha"]
    assert "actual_cover_probability" in calibration_header
    assert "win_rate" not in calibration_header
    assert "ROI" not in calibration_header


def _dashboard_payload() -> dict[str, object]:
    return {
        "generated_at": "2026-07-01T01:00:00Z",
        "selected_football_day": "2026-07-01",
        "data_profile": "real-db",
        "web_git_sha": "web-sha",
        "api_git_sha": "api-sha",
        "all": [
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": "2026-07-01T04:00:00Z",
                "home_team_name": "Home",
                "away_team_name": "Away",
                "competition_name": "World Cup",
                "status": "UPCOMING",
                "formal_recommendation": True,
                "decision_tier": "ANALYSIS_PICK",
                "data_status": "READY",
                "missing_fields": [],
                "stale_fields": ["odds"],
                "lifecycle_status": "DRAFT",
                "outcome_tracked": True,
                "lock_eligible": True,
                "reason_code": "EDGE_INSUFFICIENT",
                "action": "盯价格变动",
                "next_eval_at": "2026-07-01T03:30:00Z",
                "provider_budget_status": "AVAILABLE",
                "recommendation": {
                    "tier": "FORMAL",
                    "market": "ASIAN_HANDICAP",
                    "selection": "HOME_AH",
                    "line": "-0.5",
                    "odds": "1.91",
                    "expected_value": "0.041",
                    "ev_se": "0.21",
                },
                "current_odds": {
                    "ah": {
                        "display_line_cn": "主队 -0.5",
                        "home_display_line_cn": "主队 -0.5",
                        "away_display_line_cn": "客队 +0.5",
                    }
                },
                "pricing_shadow": {
                    "fair_ah": "-0.75",
                    "market_ah": "-0.5",
                    "edge_ah": "0.25",
                    "formal_blockers": [],
                    "independent_signal_count": 5,
                    "missing_independent_sources": [],
                    "model_version": "model",
                    "calibration_version": "calibration",
                },
                "data_refresh": {"as_of": "2026-07-01T01:00:00Z"},
                "market_timeline": {
                    "status": "READY",
                    "as_of": "2026-07-01T01:00:00Z",
                    "pattern": "STABLE",
                    "verified": False,
                    "direction_allowed": False,
                    "open": {
                        "line": -0.5,
                        "home_price": 1.91,
                        "away_price": 1.95,
                        "bookmaker_count": 4,
                    },
                    "current": {
                        "home_line": -0.75,
                        "home_price": 2.02,
                        "away_price": 1.84,
                        "bookmaker_count": 5,
                    },
                    "checkpoints_seen": ["opening", "lock"],
                },
                "locked_pre_match_recommendation": {
                    "fixture_id": "fixture-1",
                    "captured_at": "2026-07-01T01:00:00Z",
                    "as_of": "2026-07-01T01:00:00Z",
                    "status": "LOCKED",
                    "reproducible": True,
                    "snapshot_payload_hash": "abc",
                    "recommendation": {
                        "market": "ASIAN_HANDICAP",
                        "selection": "HOME_AH",
                        "line": "-0.5",
                        "odds": "1.91",
                    },
                    "settlement": {"status": "PENDING", "result": None, "pnl": None},
                },
            }
        ],
    }
