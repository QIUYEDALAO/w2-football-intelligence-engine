from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import ResultModel
from w2.tracking.formal_results import (
    MIN_BUCKET_SAMPLES_FOR_RATE,
    build_tracking_report,
    capture_formal_snapshots,
    endpoint_summary,
    settle_formal_snapshots,
    settle_snapshot,
    snapshot_from_card,
)
from w2.tracking.outcome_ledger_repository import ImportRecord, OutcomeLedgerRepository

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
            "decision_tier": "RECOMMEND",
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
    repository = _repository(tmp_path)
    result = capture_formal_snapshots(
        [formal_card()],
        repository=repository,
        dry_run=False,
        write_db=True,
        now=NOW,
        release_sha="sha",
    )

    assert result["written"] == 1
    assert result["not_a_formal_gate"] is True
    assert result["posthoc_only"] is True
    assert len(repository.records({"formal_snapshot"})) == 1


def test_capture_formal_snapshot_preserves_scoreline_and_simulation_evidence(tmp_path) -> None:
    repository = _repository(tmp_path)
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
    card["simulation"] = card["pricing_shadow"]["simulation"]  # type: ignore[index]

    capture_formal_snapshots(
        [card],
        repository=repository,
        dry_run=False,
        write_db=True,
        now=NOW,
    )

    snapshot = repository.records({"formal_snapshot"})[0]
    assert snapshot["scoreline_reference"] is not None
    assert snapshot["simulation_evidence"]["simulations"] == 10000


def test_capture_blocks_post_kickoff_snapshot(tmp_path) -> None:
    repository = _repository(tmp_path)
    result = capture_formal_snapshots(
        [formal_card(kickoff="2026-06-29T11:00:00Z")],
        repository=repository,
        dry_run=False,
        write_db=True,
        now=NOW,
    )

    assert result["written"] == 0
    assert result["blockers"]["NOT_PREMATCH"] == 1


def test_duplicate_fixture_market_selection_line_is_not_overwritten(tmp_path) -> None:
    repository = _repository(tmp_path)
    first = capture_formal_snapshots(
        [formal_card(line="0")],
        repository=repository,
        dry_run=False,
        write_db=True,
        now=NOW,
    )
    second = capture_formal_snapshots(
        [formal_card(line="0")],
        repository=repository,
        dry_run=False,
        write_db=True,
        now=NOW,
    )

    assert first["written"] == 1
    assert second["written"] == 0
    assert second["already_captured"] == 1


def test_settlement_push_counts_as_sample_but_not_win(tmp_path) -> None:
    repository = _repository(tmp_path)
    capture_formal_snapshots(
        [formal_card(line="0")],
        repository=repository,
        dry_run=False,
        write_db=True,
        now=NOW,
    )
    _seed_results(repository, [finished_card(home_goals=1, away_goals=1, line="0")])
    result = settle_formal_snapshots(
        repository=repository,
        dry_run=False,
        write_db=True,
        now=NOW,
    )

    assert result["written"] == 1
    report = build_tracking_report(repository=repository)
    assert report["sample_count"] == 1
    assert report["win_count"] == 0
    assert report["win_rate"] is None
    assert report["roi"] is None


def test_formal_report_uses_result_model_instead_of_embedded_legacy_score(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    capture_formal_snapshots(
        [formal_card(line="0")],
        repository=repository,
        dry_run=False,
        write_db=True,
        now=NOW,
    )
    snapshot = repository.records({"formal_snapshot"})[0]
    _seed_results(repository, [finished_card(home_goals=1, away_goals=1, line="0")])
    legacy = settle_snapshot(
        snapshot,
        {"status": "FT", "home_goals": 2, "away_goals": 0},
        now=NOW,
    )
    repository._append_imports(
        [
            ImportRecord(
                payload=legacy,
                record_type="formal_settlement",
                source_artifact="legacy.json",
                source_line_number=1,
            )
        ],
        dry_run=False,
        write_db=True,
    )

    report = build_tracking_report(repository=repository)

    assert report["sample_count"] == 1
    assert report["win_count"] == 0


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
    repository = _repository(tmp_path)
    capture_formal_snapshots(
        [formal_card(fixture_id=f"f{i}") for i in range(MIN_BUCKET_SAMPLES_FOR_RATE - 1)],
        repository=repository,
        dry_run=False,
        write_db=True,
        now=NOW,
    )
    cards = [
        finished_card() | {"fixture_id": f"f{i}"}
        for i in range(MIN_BUCKET_SAMPLES_FOR_RATE - 1)
    ]
    _seed_results(repository, cards)
    settle_formal_snapshots(
        repository=repository,
        dry_run=False,
        write_db=True,
        now=NOW,
    )
    report = build_tracking_report(repository=repository)

    assert report["status"] == "OBSERVING"
    assert report["sample_count"] == MIN_BUCKET_SAMPLES_FOR_RATE - 1
    assert report["win_rate"] is None
    assert report["roi"] is None
    assert "观察中" in report["label"]


def test_endpoint_summary_is_posthoc_not_formal_gate(tmp_path) -> None:
    summary = endpoint_summary(repository=_repository(tmp_path))

    assert summary["not_a_formal_gate"] is True
    assert summary["posthoc_only"] is True
    assert summary["sample_count"] == 0
    assert summary["win_rate"] is None


def test_endpoint_summary_skips_unreadable_artifact_dirs(tmp_path, monkeypatch) -> None:
    def raise_permission_error(self: Path, pattern: str):
        raise PermissionError("unreadable")

    monkeypatch.setattr(Path, "glob", raise_permission_error)

    summary = endpoint_summary(repository=_repository(tmp_path))

    assert summary["not_a_formal_gate"] is True
    assert summary["posthoc_only"] is True
    assert summary["sample_count"] == 0
    assert summary["label"] == "观察中 · 0/30"


def _repository(root: Path) -> OutcomeLedgerRepository:
    engine = create_engine(f"sqlite+pysqlite:///{root / 'formal.db'}")
    Base.metadata.create_all(engine)
    return OutcomeLedgerRepository(engine)


def _seed_results(
    repository: OutcomeLedgerRepository,
    cards: list[dict[str, object]],
) -> None:
    with Session(repository.engine) as session:
        for card in cards:
            result = card["result"]
            assert isinstance(result, dict)
            fixture_id = str(card["fixture_id"])
            home = int(result["home_goals"])
            away = int(result["away_goals"])
            identity = f"{fixture_id}:{home}:{away}"
            session.add(
                ResultModel(
                    fixture_id=fixture_id,
                    home_goals=home,
                    away_goals=away,
                    result_status="FT",
                    confirmed_at=NOW,
                    source_payload_sha256=sha256(identity.encode()).hexdigest(),
                    source_capture_id=None,
                    result_hash=sha256(f"result:{identity}".encode()).hexdigest(),
                )
            )
        session.commit()
