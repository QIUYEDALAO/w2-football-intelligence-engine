"""R4 逐字段幂等：同 decision_id 任一冻结业务字段改值 → 明确冲突（非静默 return）。"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
    AhOuDecisionLedgerModel,
)
from w2.strategy.ah_ou_decision_ledger import (
    build_ah_ou_input_hash,
    write_ah_ou_decision,
)

DECISION_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


def _write(session, **overrides) -> AhOuDecisionLedgerModel:
    input_hash = build_ah_ou_input_hash(
        features={"f9_score": 0.1},
        home_snapshot={"snapshot_id": "s1"},
        away_snapshot={"snapshot_id": "s2"},
        meetings=[{"fixture_id": "f0", "goals_for": 1, "goals_against": 0}],
        quote={"capture_id": "cap-1", "line": "-0.5", "side_prices": {"home": 1.8, "away": 2.05}},
    )
    kwargs = dict(
        fixture_id="FIX1",
        market="ASIAN_HANDICAP",
        decision_at=DECISION_AT,
        model_version="m1",
        calibration_version="c1",
        input_hash=input_hash,
        full_distribution={"HOME": 0.6, "AWAY": 0.4},
        quote_identity_hash="q1",
        source_capture_sha256="s1" * 32,
        capture_id="cap-1",
        source_id="src-1",
        home_team_id="H",
        away_team_id="A",
        selected=True,
        direction="HOME",
        score=0.12,
        skip_reason=None,
        created_at=CREATED_AT,
    )
    kwargs.update(overrides)
    return write_ah_ou_decision(session, **kwargs)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_identical_rerun_is_noop() -> None:
    engine = _engine()
    with Session(engine) as session:
        first = _write(session)
        first_id = first.decision_id
        session.commit()
    with Session(engine) as session:
        second = _write(session)  # 同对象重提（DB 回读重提）
        second_id = second.decision_id
        session.commit()
    assert first_id == second_id
    with Session(engine) as session:
        assert len(list(session.scalars(select(AhOuDecisionLedgerModel)))) == 1


# 不在 decision_id 里的字段：改值 → 同 decision_id → FIELD_CONFLICT
@pytest.mark.parametrize(
    "field,new_value",
    [
        ("full_distribution", {"HOME": 0.7, "AWAY": 0.3}),
        ("capture_id", "cap-2"),
        ("source_id", "src-2"),
        ("home_team_id", "H2"),
        ("away_team_id", "A2"),
    ],
)
def test_non_identity_field_change_is_field_conflict(field, new_value) -> None:
    engine = _engine()
    with Session(engine) as session:
        _write(session)
        session.commit()
    with Session(engine) as session:
        with pytest.raises(ValueError, match="AH_OU_DECISION_FIELD_CONFLICT"):
            _write(session, **{field: new_value})


# 在 decision_id 里的字段：改值 → 新 decision_id → 同 slot → SLOT_CONFLICT
@pytest.mark.parametrize(
    "field,new_value",
    [
        ("score", 0.99),
        ("model_version", "m2"),
        ("skip_reason", "LATE"),
        ("direction", "AWAY"),
    ],
)
def test_identity_field_change_is_slot_conflict(field, new_value) -> None:
    engine = _engine()
    with Session(engine) as session:
        _write(session)
        session.commit()
    with Session(engine) as session:
        with pytest.raises(ValueError, match="AH_OU_DECISION_SLOT_CONFLICT"):
            _write(session, **{field: new_value})
