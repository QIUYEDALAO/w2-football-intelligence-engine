from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from apps.api.main import app
from fastapi.testclient import TestClient
from scripts.project_stage10c_matchday_read_model import checkpoint_payloads

from w2.api import repository
from w2.matchday.cards import DailyMatchdayCycle, ResearchCardBuilder
from w2.matchday.integrity import SnapshotHashVerifier
from w2.matchday.settlement import MatchdaySettlementService
from w2.matchday.temporal import TemporalStatus, classify_temporal_status


def write_json(path: Path, payload: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, sort_keys=True).encode()
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def build_snapshot(root: Path, *, captured_at: str = "2026-06-22T16:30:00Z") -> Path:
    snapshot = root / "20260622T163000_000000Z"
    normalized = {
        "rows": [
            {
                "fixture_id": "1489399",
                "bookmaker_id": "1",
                "bookmaker_name": "Pinnacle",
                "market_type": "ONE_X_TWO",
                "canonical_selection": "HOME",
                "normalized_line": None,
                "odds_value": "1.80",
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "1489399",
                "bookmaker_id": "2",
                "bookmaker_name": "SBO",
                "market_type": "ASIAN_HANDICAP",
                "canonical_selection": "AWAY",
                "normalized_line": "+0.75",
                "odds_value": "2.52",
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "1489399",
                "bookmaker_id": "3",
                "bookmaker_name": "Betfair",
                "market_type": "TOTALS",
                "canonical_selection": "UNDER",
                "normalized_line": "2.5",
                "odds_value": "1.95",
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "1489399",
                "bookmaker_id": "4",
                "bookmaker_name": "Bet365",
                "market_type": "BTTS",
                "canonical_selection": "YES",
                "normalized_line": None,
                "odds_value": "2.20",
                "suspended": False,
                "live": False,
            },
        ]
    }
    model = {
        "probabilities": {"HOME": 0.52, "DRAW": 0.25, "AWAY": 0.23, "YES": 0.49},
        "score_matrix_probability_sum": 1.0,
        "value_rows": [
            {
                "market": "ONE_X_TWO",
                "selection": "HOME",
                "line": None,
                "bookmaker_name": "Pinnacle",
                "executable_odds": "1.80",
                "model_probability": 0.52,
                "settlement_probabilities": {"HOME": 0.52},
            },
            {
                "market": "ASIAN_HANDICAP",
                "selection": "AWAY",
                "line": "+0.75",
                "bookmaker_name": "SBO",
                "executable_odds": "2.52",
                "model_probability": 0.47,
                "settlement_probabilities": {
                    "win": 0.47,
                    "half_loss": 0.25,
                    "loss": 0.28,
                },
            },
            {
                "market": "TOTALS",
                "selection": "UNDER",
                "line": "2.5",
                "bookmaker_name": "Betfair",
                "executable_odds": "1.95",
                "model_probability": 0.53,
                "settlement_probabilities": {"UNDER": 0.53},
            },
            {
                "market": "BTTS",
                "selection": "YES",
                "line": None,
                "bookmaker_name": "Bet365",
                "executable_odds": "2.20",
                "model_probability": 0.49,
                "settlement_probabilities": {"YES": 0.49},
            },
        ],
    }
    decision = {"state": "WATCH", "formal_recommendation": False, "candidate": False}
    quality = {
        "status": "READY",
        "fixture_identity": "PASS",
        "frozen_artifact_hash": "PASS",
        "feature_leakage": "PASS",
    }
    fixture = {
        "payload": {
            "response": [
                {
                    "fixture": {
                        "id": 1489399,
                        "date": "2026-06-22T17:00:00Z",
                        "status": {"short": "NS"},
                        "venue": {"name": "Synthetic"},
                    },
                    "league": {"id": 1, "name": "World Cup", "round": "Group J"},
                    "teams": {
                        "home": {"id": 1, "name": "Home"},
                        "away": {"id": 2, "name": "Away"},
                    },
                }
            ]
        }
    }
    normalized_sha = write_json(snapshot / "normalized_odds.json", normalized)
    model_sha = write_json(snapshot / "model_output.json", model)
    decision_sha = write_json(snapshot / "decision.json", decision)
    write_json(snapshot / "data_quality.json", quality)
    write_json(snapshot / "raw" / "01_fixture_detail.json", fixture)
    write_json(
        snapshot / "manifest.json",
        {
            "fixture_id": "1489399",
            "phase": "T-30m",
            "captured_at_utc": captured_at,
            "kickoff_utc": "2026-06-22T17:00:00Z",
            "append_only": True,
            "hash_scheme_version": "SHA256_FILE_BYTES_V1",
            "normalized_data_sha256": normalized_sha,
            "model_artifact_sha256": model_sha,
            "decision_sha256": decision_sha,
        },
    )
    return snapshot


def test_temporal_postmatch_recomputation() -> None:
    status = classify_temporal_status(
        source_captured_at=datetime(2026, 6, 22, 16, 30, tzinfo=UTC),
        kickoff_utc=datetime(2026, 6, 22, 17, tzinfo=UTC),
        valuation_generated_at=datetime(2026, 6, 22, 18, tzinfo=UTC),
        source_phase="T-30m",
    )
    assert status == TemporalStatus.POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH


def test_hash_verifier_file_bytes_and_quarantine(tmp_path: Path) -> None:
    snapshot = build_snapshot(tmp_path / "snapshots")
    assert SnapshotHashVerifier().verify_snapshot(snapshot)["integrity_status"] == "PASS"
    manifest = json.loads((snapshot / "manifest.json").read_text())
    manifest["hash_scheme_version"] = "SHA256_FILE_BYTES_V1"
    manifest["decision_sha256"] = "bad"
    write_json(snapshot / "manifest.json", manifest)
    assert SnapshotHashVerifier().verify_snapshot(snapshot)["integrity_status"] == "QUARANTINED"


def test_card_builder_all_markets_and_gate_cap(tmp_path: Path) -> None:
    snapshot = build_snapshot(tmp_path / "snapshots")
    card = ResearchCardBuilder().build_from_snapshot(
        snapshot,
        valuation_generated_at=datetime(2026, 6, 22, 18, tzinfo=UTC),
    )
    markets = {row["market"] for row in card.market_ranking}
    assert {"ONE_X_TWO", "ASIAN_HANDICAP", "TOTALS", "BTTS"} <= markets
    assert card.card["published_grade"] in {"C", "D", "X"}
    assert card.card["formal_recommendation"] is False
    assert card.temporal["temporal_status"] == "POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH"


def test_daily_cycle_reports_and_api(tmp_path: Path, monkeypatch) -> None:
    snapshot_root = tmp_path / "snapshots"
    reports = tmp_path / "reports"
    build_snapshot(snapshot_root)
    cycle = DailyMatchdayCycle(
        snapshot_root=snapshot_root,
        schedule_path=Path("config/policies/matchday_schedule.v1.json"),
        reports_dir=reports,
        now=datetime(2026, 6, 22, 18, tzinfo=UTC),
    )
    result = cycle.run(target_date=datetime(2026, 6, 22, tzinfo=UTC).date())
    assert result["actual_fixture_count"] == 1
    monkeypatch.setattr(repository, "REPORTS", reports)
    client = TestClient(app)
    matchday = client.get("/v1/matchday/2026-06-22").json()
    assert matchday["total"] == 1
    fixture_id = matchday["items"][0]["fixture_id"]
    assert client.get(f"/v1/fixtures/{fixture_id}/research-card").status_code == 200
    assert client.get(f"/v1/fixtures/{fixture_id}/market-ranking").json()["items"]
    assert client.get(f"/v1/fixtures/{fixture_id}/integrity").status_code == 200


def test_stage10c_report_projection_feeds_matchday_api(monkeypatch) -> None:
    item = {
        "fixture": {
            "away_team_id": "775",
            "away_team_name": "Austria",
            "competition_id": "1",
            "competition_name": "World Cup",
            "data_health": "READY",
            "fixture_id": "1489399",
            "home_team_id": "26",
            "home_team_name": "Argentina",
            "kickoff_utc": "2026-06-22T17:00:00+00:00",
            "last_captured": "2026-06-22T16:30:04+00:00",
            "published_grade": "C",
            "stage": "Group J",
            "status": "NS",
            "venue": "AT&T Stadium",
        },
        "card": {
            "action": "WATCH",
            "candidate": False,
            "fixture_id": "1489399",
            "formal_recommendation": False,
            "gate4_status": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "published_grade": "C",
            "primary_market_direction": {
                "market": "ASIAN_HANDICAP",
                "selection": "AUSTRIA",
                "line": "+0.75",
                "executable_decimal_odds": "2.52",
                "model_fair_odds": "1.84",
                "risk_adjusted_ev": "0.29",
            },
            "temporal_status": "POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH",
        },
        "integrity": {"integrity_status": "PASS"},
        "market_probabilities": {"ARGENTINA_WIN": 0.62},
        "model_probabilities": {"ARGENTINA_WIN": 0.55},
        "expected_goals": {"home": 1.5, "away": 0.9},
        "market_ranking": [
            {
                "market": "ASIAN_HANDICAP",
                "selection": "AUSTRIA",
                "line": "+0.75",
                "valid_bookmaker_count": 7,
            }
        ],
        "temporal": {
            "source_snapshot_id": "20260622T163004_391908Z",
            "source_captured_at": "2026-06-22T16:30:04+00:00",
            "source_phase": "T-30m",
            "kickoff_utc": "2026-06-22T17:00:00+00:00",
            "valuation_generated_at": "2026-06-22T18:00:00+00:00",
            "projector_generated_at": "2026-06-22T18:00:00+00:00",
            "temporal_status": "POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH",
        },
    }
    payloads = checkpoint_payloads({"items": [item]})

    class Repo(repository.ReadModelRepository):
        def dashboard_checkpoint_payload(self, key: str):  # type: ignore[no-untyped-def]
            return payloads.get(key)

        def dashboard_checkpoints(self, prefix: str = "dashboard:"):  # type: ignore[no-untyped-def]
            return [
                {"checkpoint_key": key, "payload": value, "source_hash": "x", "created_at": None}
                for key, value in payloads.items()
                if key.startswith(prefix)
            ]

    service = repository.ReadModelService(Repo())
    matchday = service.matchday(target_date="2026-06-22")
    assert matchday["total"] == 1
    assert matchday["items"][0]["home_team_name"] == "Argentina"
    assert matchday["items"][0]["away_team_name"] == "Austria"
    assert service.research_card("1489399")["formal_recommendation"] is False
    assert service.market_ranking("1489399")[0]["market"] == "ASIAN_HANDICAP"
    assert service.integrity("1489399")["integrity_status"] == "PASS"
    fixture = service.fixture("1489399", "UTC")
    assert fixture is not None
    assert fixture["temporal_status"] == "POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH"


def test_settlement_service_uses_90_minute_result() -> None:
    service = MatchdaySettlementService()
    ah = service.settle_direction(
        fixture_id="f1",
        home_goals_90=1,
        away_goals_90=0,
        market="ASIAN_HANDICAP",
        selection="AWAY",
        line="+0.75",
    )
    assert ah.outcome == "HALF_LOSS"
    btts = service.settle_direction(
        fixture_id="f1",
        home_goals_90=1,
        away_goals_90=0,
        market="BTTS",
        selection="NO",
        line=None,
    )
    assert btts.outcome == "WIN"
