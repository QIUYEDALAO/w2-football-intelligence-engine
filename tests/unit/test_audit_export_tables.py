from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.audit_export import build_audit_export, write_audit_export
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.forward_ops_models import ForwardMarketSnapshotModel
from w2.infrastructure.persistence.models import RecommendationLockModel, SettlementModel


def test_audit_export_builds_four_tables_from_dashboard_payload() -> None:
    export = build_audit_export(_dashboard_payload())

    assert set(export.tables) == {
        "prematch_recommendations",
        "market_timeline_snapshots",
        "locked_recommendation_snapshots",
        "settlement_history",
    }
    assert export.manifest["provider_calls"] == 0
    assert export.manifest["db_writes"] == 0
    assert export.tables["prematch_recommendations"][0]["fixture_id"] == "fixture-1"
    assert export.tables["prematch_recommendations"][0]["market_ah_display"] == "主队 -0.5"
    assert export.tables["market_timeline_snapshots"][0]["pattern"] == "STABLE"
    assert export.tables["locked_recommendation_snapshots"][0]["snapshot_payload_hash"] == "abc"
    assert export.tables["settlement_history"][0]["status"] == "PENDING"


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
                payload={"as_of": "2026-07-01T01:00:00Z", "pattern": "JUMP_LINE"},
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
        for row in export.tables["market_timeline_snapshots"]
    )
    assert any(
        row["source"] == "recommendation_lock_model"
        for row in export.tables["locked_recommendation_snapshots"]
    )
    assert any(row["source"] == "settlement_model" for row in export.tables["settlement_history"])


def test_audit_export_writes_manifest_csv_and_json(tmp_path) -> None:
    export = build_audit_export(_dashboard_payload())

    written = write_audit_export(export, tmp_path, output_format="both")

    names = {path.name for path in written}
    assert "manifest.json" in names
    assert "prematch_recommendations.csv" in names
    assert "prematch_recommendations.json" in names
    assert (tmp_path / "prematch_recommendations.csv").read_text(encoding="utf-8")
    assert '"provider_calls": 0' in (tmp_path / "manifest.json").read_text(encoding="utf-8")


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
                "recommendation": {
                    "tier": "FORMAL",
                    "market": "ASIAN_HANDICAP",
                    "selection": "HOME_AH",
                    "line": "-0.5",
                    "odds": "1.91",
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
                    "open": {"line": -0.5},
                    "current": {"line": -0.5},
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
