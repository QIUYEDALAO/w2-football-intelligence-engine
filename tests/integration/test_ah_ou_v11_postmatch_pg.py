"""V11 postmatch path: actual v3 producer, FT capture, both natural workers."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from apps.worker import celery_app as worker
from apps.worker.celery_app import (
    ah_ou_v3_settlement_sweep,
    forward_outcome_ledger,
    result_materialize,
)
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from w2.api.repository import ReadModelService as ApiReadModelService
from w2.dashboard.date_window import FOOTBALL_DAY_TZ, football_day_for_kickoff
from w2.domain.canonical_serialization import HashDomain
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.ah_ou_monitoring_models import AhOuV3MonitoringFactModel
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


def _ft_capture(repo, future, *, home=2, away=1, status="FT", fill_fixture_id=True):
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
        params={"id": str(future["fixture"]["id"])},
        requested_at=at,
        provider_captured_at=at,
        status_code=200,
        elapsed_ms=1,
        payload=raw,
        fixture_id=("api_football:" + str(future["fixture"]["id"])) if fill_fixture_id else None,
        competition_id="allsvenskan",
        checkpoint="POSTMATCH_RESULT",
    )
    assert capture["raw_payload_sha256"] == source_sha
    writer.insert_endpoint_capture(capture)
    return capture


def test_v3_selected_ft_capture_natural_result_worker_and_validation(chain):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
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
        facts = list(session.scalars(select(AhOuV3MonitoringFactModel)))
        assert len(facts) == 2
        assert all(row.payload["eligible"] and row.payload["selected"] for row in facts)
        assert {row.payload["decision_id"] for row in facts} == {
            row.decision_id for row in decisions}
        assert {row.market for row in facts} == {"ASIAN_HANDICAP", "TOTALS"}
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
    assert forward["result"]["validation_samples"]["v3"]["monitoring"]["created_facts"] == 0
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


def _shift_raw_capture_times(repo, delta, endpoint=None):
    """odds/fixtures raw 入库时间平移 delta，模拟本地微秒时钟 vs 秒级 provider 时点。

    statistics raw 有永久保留保护；h2h raw 属于已修的 F6 交锋时间防线，均不改。
    """
    from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel

    with Session(repo.engine) as session, session.begin():
        for raw in session.scalars(select(RawPayloadModel)):
            if raw.endpoint not in ("odds", "fixtures"):
                continue
            if endpoint is not None and raw.endpoint != endpoint:
                continue
            raw.captured_at = raw.captured_at + delta


def test_v3_subsecond_raw_capture_time_diff_is_accepted(chain):
    """亚秒差异（raw 微秒 vs provider 秒级）→ 决策/结算校验放行。"""
    from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel

    repo, future, _, _ = chain
    _shift_raw_capture_times(repo, timedelta(microseconds=370_000))

    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"

    capture = _ft_capture(repo, future)
    with Session(repo.engine) as session, session.begin():
        raw = session.get(RawPayloadModel, capture["raw_payload_sha256"])
        raw.captured_at = raw.captured_at + timedelta(microseconds=370_000)

    result = result_materialize.run(fixture_ids=["api_football:1489404"])
    assert result["status"] == "PASS", result
    with Session(repo.engine) as session:
        assert len(list(session.scalars(select(AhOuV3SettlementModel)))) == 2
        assert len(list(session.scalars(select(AhOuV3ValidationSampleModel)))) == 2


def test_v3_large_raw_capture_time_diff_is_refused(chain):
    """大差异（odds raw.captured_at 差 5min）→ 决策落账本被 249 行拒（防线不失效）。"""
    repo, future, _, _ = chain
    # 只改 odds raw（决策报价 raw binding），fixtures raw 保持一致，精确触发 249 行。
    _shift_raw_capture_times(repo, timedelta(minutes=5), endpoint="odds")

    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "NOT_RECORDED"
    assert "V3_PUBLIC_QUOTE_RAW_BINDING_INVALID" in card["ah_ou_result"]["recording"]["error"]


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
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
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
    # 逐 fixture 隔离：单场赛果溯源损坏不再整轮抛错，而是该场降级 blocked
    # （settlement 零落库），其余场次照常结算。此处单场损坏，故 blocked=2、
    # 零 settlement，且对外 status=BLOCKED（不静默，但不连坐）。
    result = result_materialize.run(fixture_ids=["api_football:1489404"])
    assert result["status"] == "BLOCKED", result
    v3 = result["result"]["validation_samples"]["v3"]
    assert v3["blocked"] == 2, v3
    assert v3["created"] == 0, v3
    assert {row["reason"] for row in v3["blocked_reasons"]} == {reason}, v3
    with Session(repo.engine) as session:
        assert not list(session.scalars(select(AhOuV3SettlementModel)))
        assert not list(session.scalars(select(AhOuV3ValidationSampleModel)))


def test_v3_bulk_capture_empty_fixture_id_binds_via_sanitized_params(chain):
    """fixtures 批量采集 capture.fixture_id 空 → 绑定校验用 sanitized_params.id 通过。"""
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    capture = _ft_capture(repo, future, fill_fixture_id=False)
    assert capture["fixture_id"] is None  # 批量采集：capture 层无单一 fixture_id
    materialized = run_outcome_result_refresh(
        repository=OutcomeLedgerRepository(repo.engine),
        fixture_ids=["api_football:1489404"],
        dry_run=False,
        write_db=True,
    )
    assert materialized["status"] == "PASS"
    result = result_materialize.run(fixture_ids=["api_football:1489404"])
    assert result["status"] == "PASS", result
    with Session(repo.engine) as session:
        settled = list(session.scalars(select(AhOuV3SettlementModel)))
        samples = list(session.scalars(select(AhOuV3ValidationSampleModel)))
        assert len(settled) == len(samples) == 2
        assert all(row.result_raw_sha256 == capture["raw_payload_sha256"] for row in settled)
    public = ApiReadModelService().dashboard_ah_ou_v3_validation()
    assert all(row["state"] == "SETTLED" for row in public["rows"])


def test_v3_tampered_sanitized_params_id_rejected(chain):
    """篡改 sanitized_params.id → 仍拒绝（防线不失效）。"""
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    capture = _ft_capture(repo, future, fill_fixture_id=False)
    materialized = run_outcome_result_refresh(
        repository=OutcomeLedgerRepository(repo.engine),
        fixture_ids=["api_football:1489404"],
        dry_run=False,
        write_db=True,
    )
    assert materialized["status"] == "PASS"
    with Session(repo.engine) as session, session.begin():
        session.execute(
            update(MatchdayEndpointCaptureModel)
            .where(MatchdayEndpointCaptureModel.capture_id == capture["capture_id"])
            .values(sanitized_params={"id": "999999"})
        )
    # 逐 fixture 隔离：绑定失败该场 blocked（不抛错、不连坐），settlement 零落库。
    result = result_materialize.run(fixture_ids=["api_football:1489404"])
    assert result["status"] == "BLOCKED", result
    v3 = result["result"]["validation_samples"]["v3"]
    assert v3["blocked"] == 2, v3
    assert {row["reason"] for row in v3["blocked_reasons"]} == {
        "V3_RESULT_FIXTURE_BINDING_INVALID"
    }, v3
    with Session(repo.engine) as session:
        assert not list(session.scalars(select(AhOuV3SettlementModel)))
        assert not list(session.scalars(select(AhOuV3ValidationSampleModel)))


def test_v3_validation_snapshot_isolates_postmatch_failure(chain):
    """止血：单个场次赛后校验失败不抛 503，降级 BLOCKED，其余场次正常返回。"""
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    capture = _ft_capture(repo, future, fill_fixture_id=False)
    materialized = run_outcome_result_refresh(
        repository=OutcomeLedgerRepository(repo.engine),
        fixture_ids=["api_football:1489404"],
        dry_run=False,
        write_db=True,
    )
    assert materialized["status"] == "PASS"
    # 篡改 sanitized_params.id → 赛后绑定校验失败（写路径会拒绝）。
    with Session(repo.engine) as session, session.begin():
        session.execute(
            update(MatchdayEndpointCaptureModel)
            .where(MatchdayEndpointCaptureModel.capture_id == capture["capture_id"])
            .values(sanitized_params={"id": "999999"})
        )
    # 读路径不抛异常：该场降级 BLOCKED，而不是整个 snapshot 抛 503。
    public = ApiReadModelService().dashboard_ah_ou_v3_validation()
    assert public["rows"]
    assert all(row["state"] == "BLOCKED" for row in public["rows"])
    # 公开推荐读路径走同一 snapshot，同样不抛（返回列表）。
    public_list = ApiReadModelService().dashboard_ah_ou_v3_public()
    assert isinstance(public_list, list)


@pytest.mark.parametrize("terminal_status", ["AET", "PEN"])
def test_v3_extra_time_or_penalties_void_in_natural_worker(chain, terminal_status):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
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
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
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


def _expected_settlement(market: str, home: int, away: int, terms: dict) -> dict:
    """独立结算 oracle：不 import 生产结算 writer，只复用领域结算权威 + 手算净单位。

    五态支付（计划书 §五）：WIN=odds-1、HALF_WIN=(odds-1)/2、PUSH/VOID=0、
    HALF_LOSS=-0.5、LOSS=-1。2:2 平局按盘口结算据此核对。
    """
    if market == "ASIAN_HANDICAP":
        outcome = settle_asian_handicap(
            home, away, terms["selection"], Decimal(str(terms["selected_line"]))
        ).value
    elif market == "TOTALS":
        outcome = settle_total_goals(
            home + away, terms["selection"], Decimal(str(terms["selected_line"]))
        ).value
    else:  # pragma: no cover - defensive
        raise AssertionError(f"unexpected market {market}")
    odds = Decimal(str(terms["entry_odds"]))
    if outcome == "WIN":
        net = str(odds - 1)
    elif outcome == "HALF_WIN":
        net = str((odds - 1) / 2)
    elif outcome in {"PUSH", "VOID"}:
        net = "0"
    elif outcome == "HALF_LOSS":
        net = "-0.5"
    elif outcome == "LOSS":
        net = "-1"
    else:  # pragma: no cover - defensive
        raise AssertionError(f"unexpected outcome {outcome}")
    return {"outcome": outcome, "net_units": net}


def test_v3_settlement_sweep_recovers_unsettled_selected(chain):
    """周期重扫：result 已落库但 settlement 未落 → 下轮重扫补结算；已结算幂等跳过。"""
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    # 2:2 平局，对齐生产 1569956（TOTALS OVER 按盘口结算）。
    capture = _ft_capture(repo, future, home=2, away=2)
    # 仅物化赛果（result 落库），不触发结算 → 构造「selected + result 已落 + 未结算」。
    materialized = run_outcome_result_refresh(
        repository=OutcomeLedgerRepository(repo.engine),
        fixture_ids=["api_football:1489404"],
        dry_run=False,
        write_db=True,
    )
    assert materialized["status"] == "PASS"
    with Session(repo.engine) as session:
        decisions = {
            row.market: row for row in session.scalars(select(AhOuDecisionLedgerModel))
        }
        assert len(decisions) == 2 and all(row.selected for row in decisions.values())
        assert session.scalar(
            select(ResultModel).where(ResultModel.fixture_id == "api_football:1489404")
        )
        assert not list(session.scalars(select(AhOuV3SettlementModel)))
        assert not list(session.scalars(select(AhOuV3ValidationSampleModel)))
        outbox_before = len(list(session.scalars(select(CandidateNotificationOutboxModel))))
    # 下轮重扫 → 补结算 + 验证样本。
    sweep = ah_ou_v3_settlement_sweep.run()
    assert sweep["status"] == "PASS", sweep
    assert sweep["v3"]["created"] == 2, sweep["v3"]
    with Session(repo.engine) as session:
        settled = {
            row.market: row for row in session.scalars(select(AhOuV3SettlementModel))
        }
        samples = {
            row.market: row for row in session.scalars(select(AhOuV3ValidationSampleModel))
        }
        assert set(settled) == {"ASIAN_HANDICAP", "TOTALS"}
        assert set(samples) == {"ASIAN_HANDICAP", "TOTALS"}
        for market, decision in decisions.items():
            expected = _expected_settlement(market, 2, 2, decision.frozen_terms)
            assert settled[market].outcome == expected["outcome"], (market, settled[market].outcome)
            assert settled[market].net_units == expected["net_units"], (
                market, settled[market].net_units,
            )
            assert settled[market].result_raw_sha256 == capture["raw_payload_sha256"]
        frozen = {
            row.decision_id: (row.settlement_hash, row.outcome, row.net_units)
            for row in settled.values()
        }
        # 重扫不重复生成通知 outbox。
        assert len(list(session.scalars(select(CandidateNotificationOutboxModel)))) == outbox_before
    # 再次重扫 → 幂等：不新增、不覆盖已结算。
    sweep2 = ah_ou_v3_settlement_sweep.run()
    assert sweep2["status"] == "PASS", sweep2
    assert sweep2["v3"]["created"] == 0 and sweep2["v3"]["idempotent"] == 2, sweep2["v3"]
    with Session(repo.engine) as session:
        assert len(list(session.scalars(select(AhOuV3SettlementModel)))) == 2
        assert len(list(session.scalars(select(AhOuV3ValidationSampleModel)))) == 2
        assert {
            row.decision_id: (row.settlement_hash, row.outcome, row.net_units)
            for row in session.scalars(select(AhOuV3SettlementModel))
        } == frozen
    public = ApiReadModelService().dashboard_ah_ou_v3_validation()
    assert all(row["state"] == "SETTLED" for row in public["rows"])


def test_v3_settlement_sweep_retries_after_failure(chain):
    """结算失败不再静默：绑定失败重扫拒绝并暴露；恢复绑定后下次重扫补结算。"""
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    capture = _ft_capture(repo, future, fill_fixture_id=False)
    materialized = run_outcome_result_refresh(
        repository=OutcomeLedgerRepository(repo.engine),
        fixture_ids=["api_football:1489404"],
        dry_run=False,
        write_db=True,
    )
    assert materialized["status"] == "PASS"
    # 篡改 sanitized_params.id → fixture 绑定失败（复现 b5d875d3 前 1569956 的失败）。
    with Session(repo.engine) as session, session.begin():
        session.execute(
            update(MatchdayEndpointCaptureModel)
            .where(MatchdayEndpointCaptureModel.capture_id == capture["capture_id"])
            .values(sanitized_params={"id": "999999"})
        )
    # 逐 fixture 隔离：绑定失败该场 blocked（不抛错、不静默、不连坐），
    # settlement 零落库，blocked_reasons 曝光具体 reason。
    sweep_blocked = ah_ou_v3_settlement_sweep.run()
    assert sweep_blocked["status"] == "BLOCKED", sweep_blocked
    assert sweep_blocked["v3"]["blocked"] == 2, sweep_blocked["v3"]
    assert {row["reason"] for row in sweep_blocked["v3"]["blocked_reasons"]} == {
        "V3_RESULT_FIXTURE_BINDING_INVALID"
    }, sweep_blocked["v3"]
    with Session(repo.engine) as session:
        assert not list(session.scalars(select(AhOuV3SettlementModel)))
        assert not list(session.scalars(select(AhOuV3ValidationSampleModel)))
    # 恢复绑定（等价 b5d875d3 修复后）→ 下次重扫补结算。
    with Session(repo.engine) as session, session.begin():
        session.execute(
            update(MatchdayEndpointCaptureModel)
            .where(MatchdayEndpointCaptureModel.capture_id == capture["capture_id"])
            .values(sanitized_params={"id": str(future["fixture"]["id"])})
        )
    sweep = ah_ou_v3_settlement_sweep.run()
    assert sweep["status"] == "PASS", sweep
    assert sweep["v3"]["created"] == 2, sweep["v3"]
    with Session(repo.engine) as session:
        assert len(list(session.scalars(select(AhOuV3SettlementModel)))) == 2
        assert len(list(session.scalars(select(AhOuV3ValidationSampleModel)))) == 2
    public = ApiReadModelService().dashboard_ah_ou_v3_validation()
    assert all(row["state"] == "SETTLED" for row in public["rows"])


def test_n2_selected_short_circuit_no_conflict(chain):
    """N2：已 selected fixture 再次评估 → 短路返回原决策，零 COHORT_SLOT_CONFLICT。"""
    repo, future, _, _ = chain
    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    first = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    assert first["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    with Session(repo.engine) as session:
        before = {
            row.market: row.decision_id for row in session.scalars(select(AhOuDecisionLedgerModel))
        }
    assert len(before) == 2 and all(before.values())
    # 第二次评估（决策点已到）：评估入口先读回已 selected 冻结决策短路返回，
    # 不再走到 upsert_cohort 撞 AH_OU_COHORT_SLOT_CONFLICT。
    second = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    recording = second["ah_ou_result"]["recording"]
    assert recording["status"] == "COMMITTED", recording
    assert recording["reason"] == "ALREADY_SELECTED_SHORT_CIRCUIT", recording
    assert recording["receipt"]["short_circuit"] is True, recording
    markets = {m["market"]: m for m in second["markets"] if m["market"] in before}
    for market, decision_id in before.items():
        assert markets[market]["decision_hash"] == decision_id, markets[market]
        assert markets[market]["selected"] is True
    # 账本零新增：决策 id 不变，幂等/结算不受影响。
    with Session(repo.engine) as session:
        after = {
            row.market: row.decision_id for row in session.scalars(select(AhOuDecisionLedgerModel))
        }
    assert after == before
