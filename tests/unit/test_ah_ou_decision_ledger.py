"""AH/OU v3 决策账本写入器单测（S3/S4 幂等 + 完整字段）。"""
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
    build_ah_ou_decision_id,
    build_ah_ou_input_hash,
    write_ah_ou_decision,
)

DECISION_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _features() -> dict:
    return {"f9_score": 0.1, "f6_n": 2, "f6_score": 0.2}


def _quote() -> dict:
    return {
        "capture_id": "cap-1",
        "line": "-0.5",
        "side_prices": {"home": 1.80, "away": 2.05},
    }


def _input_hash() -> str:
    return build_ah_ou_input_hash(
        features=_features(),
        home_snapshot={"snapshot_id": "s1"},
        away_snapshot={"snapshot_id": "s2"},
        meetings=[{"fixture_id": "f0", "goals_for": 1, "goals_against": 0}],
        quote=_quote(),
    )


def _write(session, *, input_hash: str | None = None, **overrides) -> AhOuDecisionLedgerModel:
    kwargs = dict(
        fixture_id="FIX1",
        market="ASIAN_HANDICAP",
        decision_at=DECISION_AT,
        model_version="m1",
        calibration_version="c1",
        input_hash=input_hash if input_hash is not None else _input_hash(),
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


def test_idempotent_write_is_noop(session) -> None:
    first = _write(session)
    session.commit()
    second = _write(session)
    assert first.decision_id == second.decision_id
    assert len(list(session.scalars(select(AhOuDecisionLedgerModel)))) == 1


def test_different_slot_produces_new_identity(session) -> None:
    first = _write(session)
    session.commit()
    second = _write(session, fixture_id="FIX2", input_hash="f" * 64)
    assert first.decision_id != second.decision_id
    assert len(list(session.scalars(select(AhOuDecisionLedgerModel)))) == 2


def test_slot_conflict_raises(session) -> None:
    _write(session)
    session.commit()
    with pytest.raises(ValueError, match="AH_OU_DECISION_SLOT_CONFLICT"):
        _write(session, input_hash="f" * 64)


def test_skip_reason_persisted(session) -> None:
    row = _write(session, selected=False, direction=None, score=0.0,
                 skip_reason="F9_SNAPSHOT_NOT_PIT_PROVEN")
    session.commit()
    assert row.skip_reason == "F9_SNAPSHOT_NOT_PIT_PROVEN"
    assert row.selected is False
    assert row.direction is None


def test_full_fields_covered(session) -> None:
    row = _write(session)
    session.commit()
    stored = session.get(AhOuDecisionLedgerModel, row.decision_id)
    assert stored.model_version == "m1"
    assert stored.calibration_version == "c1"
    assert stored.input_hash
    assert stored.full_distribution == {"HOME": 0.6, "AWAY": 0.4}
    assert stored.quote_identity_hash == "q1"
    assert stored.source_capture_sha256
    assert stored.capture_id == "cap-1"
    assert stored.source_id == "src-1"
    assert stored.home_team_id == "H"
    assert stored.away_team_id == "A"
    assert stored.direction == "HOME"


def test_decision_id_is_deterministic() -> None:
    kwargs = dict(
        fixture_id="FIX1", market="ASIAN_HANDICAP", decision_at=DECISION_AT,
        model_version="m1", calibration_version="c1", input_hash="a" * 64,
        quote_identity_hash="q", source_capture_sha256="b" * 64,
        direction="HOME", score="0.12", skip_reason=None, selected=True,
    )
    assert build_ah_ou_decision_id(**kwargs) == build_ah_ou_decision_id(**kwargs)
