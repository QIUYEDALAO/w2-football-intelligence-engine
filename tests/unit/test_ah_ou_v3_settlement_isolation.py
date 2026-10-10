"""结算逐 fixture 隔离：单场赛果溯源失败（V3_RESULT_*）不连坐其余场次。

直接锁定 `settle_ah_ou_v3_in_session` 的循环隔离语义：一个 decision 抛
`V3_RESULT_*` 时降级该场 blocked（曝光 reason），其余 decision 照常结算；
`DecisionContractViolation` / 字段冲突仍 fail-closed。用 monkeypatch 隔离
`_expected_postmatch_fields`，不需要重走完整 producer→决策→F9/F6 链。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.domain.decision_contract import DecisionContractViolation
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.ah_ou_monitoring_models import AhOuV3MonitoringFactModel
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
)
from w2.infrastructure.persistence.ah_ou_postmatch_models import (
    AhOuV3SettlementModel,
    AhOuV3ValidationSampleModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.tracking import ah_ou_v3_monitoring as monitoring
from w2.tracking import ah_ou_v3_postmatch as postmatch

DECISION_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
SETTLEMENT_FIELDS = {
    "fixture_id": "FIX1",
    "market": "TOTALS",
    "schema_version": postmatch.SETTLEMENT_SCHEMA,
    "terms_hash": "t" * 64,
    "result_id": "r1",
    "result_hash": "rh" * 32,
    "result_raw_sha256": "raw" * 21 + "0",
    "result_capture_id": "cap-1",
    "home_goals": 2,
    "away_goals": 2,
    "outcome": "WIN",
    "net_units": "0.83",
    "settlement_hash": "sh" * 32,
}
SAMPLE_FIELDS = {
    "fixture_id": "FIX1",
    "market": "TOTALS",
    "schema_version": postmatch.VALIDATION_SCHEMA,
    "selection": "OVER",
    "exact_line": "2.25",
    "decimal_odds": "1.83",
    "terms_hash": "t" * 64,
    "result_hash": "rh" * 32,
    "settlement_hash": "sh" * 32,
    "settlement": "WIN",
    "net_units": "0.83",
}


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _decision(session, *, fixture_id, decision_id):
    session.add(
        AhOuDecisionLedgerModel(
            decision_id=decision_id,
            fixture_id=fixture_id,
            market="TOTALS",
            decision_at=DECISION_AT,
            model_version="m1",
            calibration_version="c1",
            input_hash="i" * 64,
            full_distribution={"selection": {"selected": True, "edge": 0.1}},
            decision_contract="w2.ah_ou_decision.v3.1",
            frozen_terms={"schema_version": "w2.ah_ou_frozen_terms.v1"},
            terms_hash="t" * 64,
            quote_identity_hash="q" * 64,
            source_capture_sha256="s" * 64,
            capture_id="cap-1",
            source_id="src-1",
            home_team_id="H",
            away_team_id="A",
            selected=True,
            direction="OVER",
            score="0.1",
            skip_reason=None,
            created_at=CREATED_AT,
        )
    )
    session.add(
        ResultModel(
            id=f"r-{fixture_id}",
            fixture_id=f"api_football:{fixture_id}",
            home_goals=2,
            away_goals=2,
            result_status="FT",
            confirmed_at=CREATED_AT,
            source_payload_sha256="p" * 64,
            source_capture_id=None,
            result_hash=f"rh-{fixture_id}",
        )
    )


def test_blocked_fixture_does_not_block_others(monkeypatch):
    """一个 decision 赛果溯源失败 → blocked+reason；另一个 decision 照常结算落库。"""
    engine = _engine()
    with Session(engine) as session:
        _decision(session, fixture_id="GOOD", decision_id="d-good")
        _decision(session, fixture_id="BAD", decision_id="d-bad")
        session.commit()

    def fake_expected(session, decision, result):
        if decision.fixture_id == "BAD":
            raise ValueError("V3_RESULT_CAPTURE_MISSING")
        return dict(SETTLEMENT_FIELDS), dict(SAMPLE_FIELDS)

    monkeypatch.setattr(postmatch, "_expected_postmatch_fields", fake_expected)

    with Session(engine) as session:
        report = postmatch.settle_ah_ou_v3_in_session(session)
        session.commit()

    assert report["status"] == "BLOCKED"
    assert report["selected"] == 2
    assert report["created"] == 1
    assert report["blocked"] == 1
    assert report["settled"] == 1
    assert report["blocked_reasons"] == [
        {"decision_id": "d-bad", "reason": "V3_RESULT_CAPTURE_MISSING"}
    ]
    with Session(engine) as session:
        settled = list(session.scalars(select(AhOuV3SettlementModel)))
        samples = list(session.scalars(select(AhOuV3ValidationSampleModel)))
        assert len(settled) == len(samples) == 1
        assert settled[0].decision_id == "d-good"
        assert settled[0].outcome == "WIN"
        assert settled[0].net_units == "0.83"


def test_decision_contract_violation_still_fails_closed(monkeypatch):
    """决策字段篡改（DecisionContractViolation）仍整轮失败，不被隔离吞掉。"""
    engine = _engine()
    with Session(engine) as session:
        _decision(session, fixture_id="GOOD", decision_id="d-good")
        _decision(session, fixture_id="BAD", decision_id="d-bad")
        session.commit()

    def fake_expected(session, decision, result):
        raise DecisionContractViolation("V3_PUBLIC_TERMS_HASH_MISMATCH")

    monkeypatch.setattr(postmatch, "_expected_postmatch_fields", fake_expected)

    with Session(engine) as session:
        with pytest.raises(DecisionContractViolation, match="V3_PUBLIC_TERMS_HASH_MISMATCH"):
            postmatch.settle_ah_ou_v3_in_session(session)
    with Session(engine) as session:
        assert not list(session.scalars(select(AhOuV3SettlementModel)))
        assert not list(session.scalars(select(AhOuV3ValidationSampleModel)))


def test_idempotent_when_no_due_work(monkeypatch):
    """无 pending 时整轮 PASS、created=0，不产生重复写入。"""
    engine = _engine()
    with Session(engine) as session:
        _decision(session, fixture_id="GOOD", decision_id="d-good")
        session.commit()

    monkeypatch.setattr(
        postmatch,
        "_expected_postmatch_fields",
        lambda s, d, r: (dict(SETTLEMENT_FIELDS), dict(SAMPLE_FIELDS)),
    )
    with Session(engine) as session:
        first = postmatch.settle_ah_ou_v3_in_session(session)
        session.commit()
        assert first["created"] == 1 and first["status"] == "PASS"

    with Session(engine) as session:
        second = postmatch.settle_ah_ou_v3_in_session(session)
        session.commit()
        assert second["created"] == 0 and second["idempotent"] == 1
        assert second["status"] == "PASS"
    with Session(engine) as session:
        assert len(list(session.scalars(select(AhOuV3SettlementModel)))) == 1


def test_monitoring_dedupes_same_slot_decisions(monkeypatch):
    """同 (fixture, market, model, calibration) 双决策（旧 SKIP 重评估）→ 监控只写一条 fact。

    监控 fact 唯一约束是 (fixture_id, market, model_version, calibration_version)，
    但同一 slot 因 SKIP 重评估可能有多条 decision_id。append_monitoring_in_session
    必须去重，否则 INSERT 第二条撞 UniqueViolation 连坐整轮结算。
    """
    engine = _engine()
    with Session(engine) as session:
        # 同一 slot（同 fixture/market/model/calibration）两条 SKIP 决策。
        for decision_id, decision_at in (
            ("d-old", DECISION_AT),
            ("d-new", datetime(2026, 8, 2, 10, 0, tzinfo=UTC)),
        ):
            session.add(
                AhOuDecisionLedgerModel(
                    decision_id=decision_id,
                    fixture_id="FIX1",
                    market="TOTALS",
                    decision_at=decision_at,
                    model_version="m1",
                    calibration_version="c1",
                    input_hash="i" * 64,
                    full_distribution={"selection": {"selected": False, "edge": 0.1}},
                    decision_contract="w2.ah_ou_decision.v3.1",
                    frozen_terms=None,
                    terms_hash=None,
                    quote_identity_hash="q" * 64,
                    source_capture_sha256="s" * 64,
                    capture_id="cap-1",
                    source_id="src-1",
                    home_team_id="H",
                    away_team_id="A",
                    selected=False,
                    direction=None,
                    score="0.1",
                    skip_reason=None,
                    created_at=CREATED_AT,
                )
            )
        session.add(
            ResultModel(
                id="r-FIX1",
                fixture_id="api_football:FIX1",
                home_goals=2,
                away_goals=1,
                result_status="FT",
                confirmed_at=CREATED_AT,
                source_payload_sha256="p" * 64,
                source_capture_id=None,
                result_hash="rh-FIX1",
            )
        )
        session.commit()

    def fake_fact(session, decision, result):
        return {
            "schema_version": monitoring.FACT_SCHEMA,
            "decision_id": decision.decision_id,
            "fixture_id": decision.fixture_id,
            "market": decision.market,
            "model_version": decision.model_version,
            "calibration_version": decision.calibration_version,
            "selected": decision.selected,
            "eligible": True,
            "exclusion_reason": None,
            "result_hash": result.result_hash,
            "result_source": {"raw_sha256": "r", "capture_id": "c"},
            "home_goals": result.home_goals,
            "away_goals": result.away_goals,
            "competition": "c",
            "month": "2026-08",
        }

    monkeypatch.setattr(monitoring, "_fact", fake_fact)

    with Session(engine) as session:
        report = monitoring.append_monitoring_in_session(session)
        session.commit()
    # 去重后只写最新那条（decision_at 最大）的 fact，不撞 unique 约束。
    assert report["created_facts"] == 1, report
    with Session(engine) as session:
        facts = list(session.scalars(select(AhOuV3MonitoringFactModel)))
        assert len(facts) == 1
        assert facts[0].decision_id == "d-new"


# ─────────────────────────────────────────────────────────────────────────────
# 指令书 F（2026-10-10）：raw binding 时间子条件与 content-addressed 去重不兼容
#   + monitoring 对 V3_PUBLIC_QUOTE_* 逐决策隔离（quarantine）
# ─────────────────────────────────────────────────────────────────────────────


def _capture(capture_id, sha, provider_captured_at):
    return MatchdayEndpointCaptureModel(
        capture_id=capture_id,
        fixture_id="api_football:FIX1",
        competition_id="c1",
        checkpoint="T60_ODDS_LINEUPS",
        endpoint="odds",
        sanitized_params={},
        params_hash=capture_id + "-params",
        request_task_key="tk-" + capture_id,
        attempt=1,
        requested_at=provider_captured_at,
        provider_captured_at=provider_captured_at,
        status_code=200,
        elapsed_ms=10,
        response_count=1,
        quota_values={},
        raw_payload_sha256=sha,
        provider_event_time=None,
        capture_status="CAPTURED",
        error_code=None,
    )


def _raw(sha, captured_at):
    return RawPayloadModel(
        sha256=sha,
        endpoint="odds",
        captured_at=captured_at,
        storage_uri="memory://raw",
        payload={"response": []},
    )


def test_raw_time_binding_shared_payload_origin_is_accepted():
    """F 根因：raw_payload 内容寻址去重 ⇒ 后来的 capture 复用首发 raw 行（captured_at 停在首发）。

    生产实测形态：同一 sha 被恰好 2 个 capture 引用，首发时间与 raw.captured_at 秒级一致，
    决策绑定的第二个 capture 相差 ~3h（odds 内容未变）。此形态必须放行，否则每条都判
    V3_PUBLIC_QUOTE_RAW_BINDING_INVALID，monitoring 链整轮抛错 + 每 300s 复发。
    """
    engine = _engine()
    sha = "f" * 64
    first_at = datetime(2026, 10, 7, 18, 32, 28, tzinfo=UTC)
    second_at = datetime(2026, 10, 7, 21, 32, 26, tzinfo=UTC)
    with Session(engine) as session:
        session.add(_capture("cap-first", sha, first_at))
        session.add(_capture("cap-second", sha, second_at))
        session.add(_raw(sha, first_at + timedelta(microseconds=944_103)))
        session.commit()
        capture = session.get(MatchdayEndpointCaptureModel, "cap-second")
        raw = session.get(RawPayloadModel, sha)
        assert postmatch._raw_time_binding_invalid(session, capture, raw) is False


def test_raw_time_binding_single_capture_shift_is_refused():
    """反篡改防线不放松：raw 只被本 capture 引用且时间被平移 → 仍判违规。

    对应集成测试 test_v3_large_raw_capture_time_diff_is_refused 的构造（只平移 raw）。
    """
    engine = _engine()
    sha = "e" * 64
    at = datetime(2026, 10, 7, 18, 32, 28, tzinfo=UTC)
    with Session(engine) as session:
        session.add(_capture("cap-only", sha, at))
        session.add(_raw(sha, at + timedelta(minutes=5)))
        session.commit()
        capture = session.get(MatchdayEndpointCaptureModel, "cap-only")
        raw = session.get(RawPayloadModel, sha)
        assert postmatch._raw_time_binding_invalid(session, capture, raw) is True


def test_raw_time_binding_shared_payload_without_origin_is_refused():
    """共享 raw 但其时间**任何** capture 都解释不了（真篡改）→ 仍判违规。"""
    engine = _engine()
    sha = "d" * 64
    first_at = datetime(2026, 10, 7, 18, 32, 28, tzinfo=UTC)
    second_at = datetime(2026, 10, 7, 21, 32, 26, tzinfo=UTC)
    with Session(engine) as session:
        session.add(_capture("cap-first", sha, first_at))
        session.add(_capture("cap-second", sha, second_at))
        session.add(_raw(sha, second_at + timedelta(hours=5)))
        session.commit()
        capture = session.get(MatchdayEndpointCaptureModel, "cap-second")
        raw = session.get(RawPayloadModel, sha)
        assert postmatch._raw_time_binding_invalid(session, capture, raw) is True


def test_monitoring_quarantines_public_quote_violation(monkeypatch):
    """F 要求 2：V3_PUBLIC_QUOTE_* 逐决策隔离 —— 不抛错（不整轮回滚），其余场次照常落 fact。

    修复前语义：一条违规决策让 append_monitoring_in_session 抛错 → 外层事务回滚
    （settlement 一起丢）+ sweep 每 300s 产生一条 FAILURE + release 闸 f 项常红。
    """
    engine = _engine()
    with Session(engine) as session:
        for fixture_id, decision_id in (("FIXA", "d-a"), ("FIXB", "d-b")):
            session.add(
                AhOuDecisionLedgerModel(
                    decision_id=decision_id,
                    fixture_id=fixture_id,
                    market="TOTALS",
                    decision_at=DECISION_AT,
                    model_version="m1",
                    calibration_version="c1",
                    input_hash="i" * 64,
                    full_distribution={"selection": {"selected": False, "edge": 0.1}},
                    decision_contract="w2.ah_ou_decision.v3.1",
                    frozen_terms=None,
                    terms_hash=None,
                    quote_identity_hash="q" * 64,
                    source_capture_sha256="s" * 64,
                    capture_id="cap-" + fixture_id,
                    source_id="src-1",
                    home_team_id="H",
                    away_team_id="A",
                    selected=False,
                    direction=None,
                    score="0.1",
                    skip_reason=None,
                    created_at=CREATED_AT,
                )
            )
            session.add(
                ResultModel(
                    id="r-" + fixture_id,
                    fixture_id="api_football:" + fixture_id,
                    home_goals=2,
                    away_goals=1,
                    result_status="FT",
                    confirmed_at=CREATED_AT,
                    source_payload_sha256="p" * 64,
                    source_capture_id=None,
                    result_hash="rh-" + fixture_id,
                )
            )
        session.commit()

    def fake_fact(session, decision, result):
        if decision.fixture_id == "FIXA":
            raise DecisionContractViolation("V3_PUBLIC_QUOTE_RAW_BINDING_INVALID")
        return {
            "schema_version": monitoring.FACT_SCHEMA,
            "decision_id": decision.decision_id,
            "fixture_id": decision.fixture_id,
            "market": decision.market,
            "model_version": decision.model_version,
            "calibration_version": decision.calibration_version,
            "selected": decision.selected,
            "eligible": True,
            "exclusion_reason": None,
            "result_hash": result.result_hash,
            "result_source": {"raw_sha256": "r", "capture_id": "c"},
            "home_goals": result.home_goals,
            "away_goals": result.away_goals,
            "competition": "c",
            "month": "2026-08",
        }

    monkeypatch.setattr(monitoring, "_fact", fake_fact)

    with Session(engine) as session:
        report = monitoring.append_monitoring_in_session(session)
        session.commit()

    assert report["quarantined_facts"] == 1, report
    assert report["created_facts"] == 1, report
    with Session(engine) as session:
        facts = list(session.scalars(select(AhOuV3MonitoringFactModel)))
        assert [f.fixture_id for f in facts] == ["FIXB"]
