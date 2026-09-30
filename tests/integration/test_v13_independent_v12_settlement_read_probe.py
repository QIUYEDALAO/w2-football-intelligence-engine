"""Independent V12 public read fault injection, using the real producer chain."""

from datetime import datetime

import pytest
from apps.api.main import app
from apps.worker.celery_app import result_materialize
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session
from tests.integration.test_ah_ou_v11_postmatch_pg import _ft_capture

from w2.dashboard.date_window import football_day_for_kickoff
from w2.infrastructure.persistence.ah_ou_postmatch_models import AhOuV3SettlementModel
from w2.prematch.analysis_calculator import ReadModelService

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def test_public_reader_detects_settlement_content_vs_frozen_hash(chain):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    _ft_capture(repo, future)
    assert result_materialize.run(fixture_ids=["api_football:1489404"])["status"] == "PASS"
    day = football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))
    url = "/v1/dashboard/intelligence-workspace/list"
    params = {"date": day.isoformat()}
    control = TestClient(app).get(url, params=params)
    assert control.status_code == 200
    assert control.json()["performance_summary"]["total_profit_units"] == 1.15

    # The implementation's decision tamper test uses this same PG-only fault
    # injection to exercise the read-time boundary beneath append-only triggers.
    with Session(repo.engine) as session, session.begin():
        session.execute(text("SET LOCAL session_replication_role = replica"))
        row = session.scalar(
            select(AhOuV3SettlementModel).where(AhOuV3SettlementModel.market == "ASIAN_HANDICAP")
        )
        assert row is not None
        session.execute(
            update(AhOuV3SettlementModel)
            .where(AhOuV3SettlementModel.decision_id == row.decision_id)
            .values(net_units=row.net_units)
        )
    noop = TestClient(app).get(url, params=params)
    assert noop.status_code == 200
    assert noop.json()["performance_summary"]["total_profit_units"] == 1.15

    with Session(repo.engine) as session, session.begin():
        session.execute(text("SET LOCAL session_replication_role = replica"))
        row = session.scalar(
            select(AhOuV3SettlementModel).where(AhOuV3SettlementModel.market == "ASIAN_HANDICAP")
        )
        assert row is not None
        session.execute(
            update(AhOuV3SettlementModel)
            .where(AhOuV3SettlementModel.decision_id == row.decision_id)
            .values(net_units="999")
        )
    with pytest.raises(ValueError, match="V3_PUBLIC_SETTLEMENT_HASH_MISMATCH"):
        TestClient(app).get(url, params=params)
