"""结算逐 fixture 隔离：单场赛果溯源失败（V3_RESULT_*）不连坐其余场次。

直接锁定 `settle_ah_ou_v3_in_session` 的循环隔离语义：一个 decision 抛
`V3_RESULT_*` 时降级该场 blocked（曝光 reason），其余 decision 照常结算；
`DecisionContractViolation` / 字段冲突仍 fail-closed。用 monkeypatch 隔离
`_expected_postmatch_fields`，不需要重走完整 producer→决策→F9/F6 链。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.domain.decision_contract import DecisionContractViolation
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.ah_ou_postmatch_models import (
    AhOuV3SettlementModel,
    AhOuV3ValidationSampleModel,
)
from w2.infrastructure.persistence.models import ResultModel
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
