"""V11 postmatch path: actual v3 producer, FT capture, both natural workers."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pytest
from apps.worker import celery_app as worker
from apps.worker.celery_app import forward_outcome_ledger, result_materialize
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from w2.api.repository import ReadModelService as ApiReadModelService
from w2.dashboard.date_window import FOOTBALL_DAY_TZ, football_day_for_kickoff
from w2.domain.canonical_serialization import HashDomain
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.ah_ou_postmatch_models import (
    AhOuV3SettlementModel,
    AhOuV3ValidationSampleModel,
)
from w2.infrastructure.persistence.dynamic_prematch_models import CandidateNotificationOutboxModel
from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerRunStateModel
from w2.ingestion.future_refresh import sha256_payload
from w2.matchday.intake_v2 import endpoint_capture_contract
from w2.matchday.repository import MatchdayRuntimeRepository
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.candidate_notifications import (
    _verify_current_outbox_in_session,
    enqueue_v3_daily_settlement_in_session,
)
from w2.tracking.outcome_ledger_repository import OutcomeLedgerRepository
from w2.tracking.outcome_ledger_runtime import OutcomeLedgerRuntimeRepository
from w2.tracking.outcome_result_refresh import run_outcome_result_refresh

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _ft_capture(repo, future, *, home=2, away=1, status="FT"):
    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    at = kickoff + timedelta(hours=2)
    ft = {
        **future,
        "fixture": {**future["fixture"], "status": {"short": status}},
        "goals": {"home": home, "away": away},
        "score": {"fulltime": {"home": home, "away": away}},
    }
    raw = {"response": [ft]}
    source_sha = sha256_payload(raw, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
    writer = MatchdayRuntimeRepository(engine=repo.engine)
    writer.save_raw_payload(sha256=source_sha, endpoint="fixtures", captured_at=at, payload=raw)
    capture = endpoint_capture_contract(
        endpoint="fixtures",
        params={"id": "1489404"},
        requested_at=at,
        provider_captured_at=at,
        status_code=200,
        elapsed_ms=1,
        payload=raw,
        fixture_id="api_football:1489404",
        competition_id="allsvenskan",
        checkpoint="POSTMATCH_RESULT",
    )
    assert capture["raw_payload_sha256"] == source_sha
    writer.insert_endpoint_capture(capture)
    return capture


def test_v3_selected_ft_capture_natural_result_worker_and_validation(chain):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    with Session(repo.engine) as session:
        decisions = list(session.scalars(select(AhOuDecisionLedgerModel)))
        assert len(decisions) == 2 and all(row.selected for row in decisions)
        assert all(row.decision_contract == "w2.ah_ou_decision.v3.1" for row in decisions)
        assert all(row.frozen_terms and row.terms_hash for row in decisions)
    pending_public = ApiReadModelService().dashboard_ah_ou_v3_validation()
    assert len(pending_public["rows"]) == 2
    assert all(row["state"] == "PENDING" for row in pending_public["rows"])
    assert all(
        item["hit_rate"] is None and item["hit_rate_denominator"] == 0
        for item in pending_public["by_market"].values()
    )
    from apps.api.main import app

    football_day = football_day_for_kickoff(
        datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    )
    client = TestClient(app)
    home_before = client.get(
        "/v1/dashboard/intelligence-workspace/list", params={"date": football_day.isoformat()}
    )
    assert home_before.status_code == 200, home_before.text
    assert {row["decision_id"] for row in home_before.json()["today_recommendations"]} == {
        row.decision_id for row in decisions
    }
    day_before = client.get("/v1/dashboard/day-view", params={"date": football_day.isoformat()})
    assert day_before.status_code == 200, day_before.text
    assert {row["decision_id"] for row in day_before.json()["recommendations"]} == {
        row.decision_id for row in decisions
    }
    detail_before = client.get("/v1/dashboard/intelligence-workspace/matches/1489404")
    assert detail_before.status_code == 200, detail_before.text
    assert {row["decision_id"] for row in detail_before.json()["ah_ou_v3_recommendations"]} == {
        row.decision_id for row in decisions
    }
    capture = _ft_capture(repo, future)
    # The natural result worker runs the shared settlement and sample writer.
    result = result_materialize.run(fixture_ids=["api_football:1489404"])
    assert result["status"] == "PASS", result
    with Session(repo.engine) as session:
        confirmed = session.scalar(
            select(ResultModel).where(ResultModel.fixture_id == "api_football:1489404")
        )
        assert confirmed and confirmed.source_capture_id == capture["capture_id"]
        settled = list(session.scalars(select(AhOuV3SettlementModel)))
        samples = list(session.scalars(select(AhOuV3ValidationSampleModel)))
        assert len(settled) == len(samples) == 2
        assert {row.decision_id for row in settled} == {row.decision_id for row in decisions}
        assert {row.decision_id for row in samples} == {row.decision_id for row in decisions}
        assert all(row.result_raw_sha256 == capture["raw_payload_sha256"] for row in settled)
        frozen = {
            row.decision_id: (
                row.terms_hash,
                row.result_hash,
                row.result_capture_id,
                row.outcome,
                row.net_units,
                row.settlement_hash,
            )
            for row in settled
        }
    # Initial commit plus three natural same-content retries: four DB steps.
    for _ in range(3):
        repeat = result_materialize.run(fixture_ids=["api_football:1489404"])
        assert repeat["status"] == "PASS"
        assert repeat["result"]["validation_samples"]["v3"]["idempotent"] == 2
        with Session(repo.engine) as session:
            assert {
                row.decision_id: (
                    row.terms_hash,
                    row.result_hash,
                    row.result_capture_id,
                    row.outcome,
                    row.net_units,
                    row.settlement_hash,
                )
                for row in session.scalars(select(AhOuV3SettlementModel))
            } == frozen
    # The second natural result worker consumes the same versioned writer.
    dispatch = OutcomeLedgerRuntimeRepository(repo.engine).prepare_dispatch(
        now=datetime.now(UTC), task_id="forward-outcome-ledger"
    )
    assert dispatch.status == "QUEUED", dispatch
    forward = forward_outcome_ledger.run(window="next7")
    assert forward["status"] not in {"BLOCKED", "ACTIVE_OR_RESERVED"}, forward
    assert forward["result"]["validation_samples"]["v3"]["idempotent"] == 2
    public = ApiReadModelService().dashboard_ah_ou_v3_validation()
    assert public["registered_cohorts"] == 1
    assert public["completed_decisions"] == public["selected"] == 2
    assert {row["decision_id"] for row in public["rows"]} == {row.decision_id for row in decisions}
    assert all(row["state"] == "SETTLED" and row["validation_sample_id"] for row in public["rows"])
    assert all(
        item["pending"] == 0 and item["settled"] == 1 for item in public["by_market"].values()
    )
    http = TestClient(app).get("/v1/dashboard/intelligence-workspace/validation")
    assert http.status_code == 200, http.text
    displayed = http.json()["ah_ou_v3"]
    assert {row["decision_id"] for row in displayed["rows"]} == {
        row.decision_id for row in decisions
    }
    assert displayed["by_market"] == public["by_market"]
    home_after = client.get(
        "/v1/dashboard/intelligence-workspace/list", params={"date": football_day.isoformat()}
    )
    assert home_after.status_code == 200, home_after.text
    assert home_after.json()["performance_summary"]["total_profit_units"] == pytest.approx(
        sum(float(row["net_units"]) for row in public["rows"] if row["state"] == "SETTLED")
    )
    assert http.json()["cumulative_profit_units"] == pytest.approx(
        home_after.json()["performance_summary"]["total_profit_units"]
    )
    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    football_day = football_day_for_kickoff(kickoff)
    daily_at = datetime.combine(
        football_day + timedelta(days=1), time(12), tzinfo=FOOTBALL_DAY_TZ
    ).astimezone(UTC)
    with Session(repo.engine) as session, session.begin():
        event_id = enqueue_v3_daily_settlement_in_session(session, now=daily_at)
        assert event_id
    with Session(repo.engine) as session:
        daily = session.get(CandidateNotificationOutboxModel, event_id)
        assert daily and daily.payload["selected"] == 2
        assert {item["decision_id"] for item in daily.payload["items"]} == {
            row.decision_id for row in decisions
        }
        _verify_current_outbox_in_session(session, daily)
        changed = CandidateNotificationOutboxModel(
            notification_event_id=daily.notification_event_id,
            event_type=daily.event_type,
            created_at=daily.created_at,
            current_state=daily.current_state,
            payload={**daily.payload, "net_units": "999"},
        )
        with pytest.raises(ValueError, match="V3_DAILY_CONTENT_CONFLICT"):
            _verify_current_outbox_in_session(session, changed)
    with pytest.raises(DBAPIError, match="AH_OU_POSTMATCH_FROZEN_CONTENT_CONFLICT"):
        with Session(repo.engine) as session, session.begin():
            session.execute(update(AhOuV3SettlementModel).values(net_units="999"))
    for field, replacement in (("selected_line", "-0.25"), ("entry_odds", "9.99")):
        with pytest.raises(DBAPIError, match="AH_OU_POSTMATCH_FROZEN_CONTENT_CONFLICT"):
            with Session(repo.engine) as session, session.begin():
                ah = session.scalar(
                    select(AhOuDecisionLedgerModel).where(
                        AhOuDecisionLedgerModel.market == "ASIAN_HANDICAP"
                    )
                )
                terms = {**ah.frozen_terms, field: replacement}
                session.execute(
                    update(AhOuDecisionLedgerModel)
                    .where(AhOuDecisionLedgerModel.decision_id == ah.decision_id)
                    .values(frozen_terms=terms)
                )


@pytest.mark.parametrize(
    "corruption, reason",
    [
        ("wrong_fixture", "V3_RESULT_FIXTURE_BINDING_INVALID"),
        ("failed_capture", "V3_RESULT_CAPTURE_INVALID"),
        ("wrong_raw_binding", "V3_RESULT_CAPTURE_INVALID"),
    ],
)
def test_v3_result_source_corruption_blocks_natural_worker(chain, corruption, reason):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    capture = _ft_capture(repo, future)
    materialized = run_outcome_result_refresh(
        repository=OutcomeLedgerRepository(repo.engine),
        fixture_ids=["api_football:1489404"],
        dry_run=False,
        write_db=True,
    )
    assert materialized["status"] == "PASS"
    with Session(repo.engine) as session, session.begin():
        if corruption == "wrong_fixture":
            session.execute(
                update(MatchdayEndpointCaptureModel)
                .where(MatchdayEndpointCaptureModel.capture_id == capture["capture_id"])
                .values(fixture_id="api_football:other")
            )
        elif corruption == "failed_capture":
            session.execute(
                update(MatchdayEndpointCaptureModel)
                .where(MatchdayEndpointCaptureModel.capture_id == capture["capture_id"])
                .values(capture_status="FAILED")
            )
        else:
            session.execute(
                update(MatchdayEndpointCaptureModel)
                .where(MatchdayEndpointCaptureModel.capture_id == capture["capture_id"])
                .values(raw_payload_sha256="0" * 64)
            )
    with pytest.raises(ValueError, match=reason):
        result_materialize.run(fixture_ids=["api_football:1489404"])
    with Session(repo.engine) as session:
        assert not list(session.scalars(select(AhOuV3SettlementModel)))
        assert not list(session.scalars(select(AhOuV3ValidationSampleModel)))


@pytest.mark.parametrize("terminal_status", ["AET", "PEN"])
def test_v3_extra_time_or_penalties_void_in_natural_worker(chain, terminal_status):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    _ft_capture(repo, future, status=terminal_status)
    result = result_materialize.run(fixture_ids=["api_football:1489404"])
    assert result["status"] == "PASS", result
    with Session(repo.engine) as session:
        rows = list(session.scalars(select(AhOuV3SettlementModel)))
        assert len(rows) == 2 and all(
            row.outcome == "VOID" and row.net_units == "0" for row in rows
        )
    public = ApiReadModelService().dashboard_ah_ou_v3_validation()
    assert all(row["state"] == "VOID" for row in public["rows"])
    assert all(
        item["settled"] == 0 and item["hit_rate_denominator"] == 0
        for item in public["by_market"].values()
    )


def test_v3_validation_failure_cannot_mark_natural_workers_success(chain, monkeypatch):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    _ft_capture(repo, future)

    def fail_validation(*args, **kwargs):
        raise RuntimeError("V3_VALIDATION_WRITE_FAILED")

    monkeypatch.setattr(worker, "_settle_v3_postmatch", fail_validation)
    with pytest.raises(RuntimeError, match="V3_VALIDATION_WRITE_FAILED"):
        result_materialize.run(fixture_ids=["api_football:1489404"])
    dispatch = OutcomeLedgerRuntimeRepository(repo.engine).prepare_dispatch(
        now=datetime.now(UTC), task_id="forward-outcome-ledger"
    )
    assert dispatch.status == "QUEUED"
    with pytest.raises(RuntimeError, match="V3_VALIDATION_WRITE_FAILED"):
        forward_outcome_ledger.run(window="next7")
    with Session(repo.engine) as session:
        state = session.get(OutcomeLedgerRunStateModel, "forward_outcome_ledger")
        assert state and state.status == "FAILED"
        assert not list(session.scalars(select(AhOuV3SettlementModel)))
        assert not list(session.scalars(select(AhOuV3ValidationSampleModel)))
