"""Read-time fault injection below append-only triggers on an actual v3 chain."""

from datetime import UTC, datetime, time, timedelta

import pytest
from apps.api.main import app
from apps.worker.celery_app import result_materialize
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session
from tests.integration.test_ah_ou_v11_postmatch_pg import _ft_capture

from w2.dashboard.date_window import FOOTBALL_DAY_TZ, football_day_for_kickoff
from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.infrastructure.persistence.ah_ou_postmatch_models import (
    AhOuV3SettlementModel,
    AhOuV3ValidationSampleModel,
)
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.candidate_notifications import enqueue_daily_settlement_in_session

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _day(future):
    return football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))


def _daily_at(day):
    return datetime.combine(day + timedelta(days=1), time(12), tzinfo=FOOTBALL_DAY_TZ).astimezone(
        UTC
    )


def _daily_probe(repo, day):
    with Session(repo.engine) as session:
        value = enqueue_daily_settlement_in_session(session, now=_daily_at(day))
        session.rollback()  # Keep the daily writer available for the tamper probe.
        return value


def _public_probes(repo, day):
    client = TestClient(app)
    daily = _daily_probe(repo, day)
    return (
        client.get("/v1/dashboard/intelligence-workspace/list", params={"date": day.isoformat()}),
        client.get("/v1/dashboard/intelligence-workspace/matches/1489404"),
        client.get("/v1/dashboard/intelligence-workspace/validation"),
        daily,
    )


def _update_below_trigger(repo, model, field, value):
    with Session(repo.engine) as session, session.begin():
        session.execute(text("SET LOCAL session_replication_role = replica"))
        row = session.scalar(select(model).where(model.market == "ASIAN_HANDICAP"))
        assert row is not None
        session.execute(
            update(model).where(model.decision_id == row.decision_id).values({field: value})
        )


@pytest.mark.parametrize(
    ("model", "field", "value", "reason"),
    [
        (AhOuV3SettlementModel, "net_units", "999", "V3_PUBLIC_SETTLEMENT_HASH_MISMATCH"),
        (AhOuV3SettlementModel, "outcome", "LOSS", "V3_PUBLIC_SETTLEMENT_HASH_MISMATCH"),
        (AhOuV3SettlementModel, "result_hash", "a" * 64, "V3_PUBLIC_SETTLEMENT_HASH_MISMATCH"),
        (AhOuV3SettlementModel, "terms_hash", "b" * 64, "V3_PUBLIC_SETTLEMENT_HASH_MISMATCH"),
        (
            AhOuV3ValidationSampleModel,
            "net_units",
            "999",
            "V3_PUBLIC_SAMPLE_FIELD_CONFLICT:net_units",
        ),
        (
            AhOuV3ValidationSampleModel,
            "selection",
            "AWAY",
            "V3_PUBLIC_SAMPLE_FIELD_CONFLICT:selection",
        ),
    ],
)
def test_all_public_consumers_reject_single_field_tamper(chain, model, field, value, reason):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    _ft_capture(repo, future)
    assert result_materialize.run(fixture_ids=["api_football:1489404"])["status"] == "PASS"
    day = _day(future)
    baseline = _public_probes(repo, day)
    assert all(response.status_code == 200 for response in baseline[:3])
    assert baseline[0].json()["performance_summary"]["total_profit_units"] == 1.15
    assert baseline[3] is not None
    print({"control": "FT_SETTLED", "net_units": 1.15, "field": field})

    with Session(repo.engine) as session, session.begin():
        session.execute(text("SET LOCAL session_replication_role = replica"))
        row = session.scalar(select(model).where(model.market == "ASIAN_HANDICAP"))
        assert row is not None
        session.execute(
            update(model)
            .where(model.decision_id == row.decision_id)
            .values({field: getattr(row, field)})
        )
    noop = _public_probes(repo, day)
    assert all(response.status_code == 200 for response in noop[:3])
    assert noop[0].json()["performance_summary"]["total_profit_units"] == 1.15

    _update_below_trigger(repo, model, field, value)
    blocked = TestClient(app, raise_server_exceptions=False).get(
        "/v1/dashboard/intelligence-workspace/list", params={"date": day.isoformat()}
    )
    assert blocked.status_code == 503
    assert reason in blocked.json()["message"]
    print({
        "attack": field,
        "http_status": blocked.status_code,
        "reason": blocked.json()["message"],
    })
    for endpoint in (
        lambda: TestClient(app).get(
            "/v1/dashboard/intelligence-workspace/list", params={"date": day.isoformat()}
        ),
        lambda: TestClient(app).get("/v1/dashboard/intelligence-workspace/matches/1489404"),
        lambda: TestClient(app).get("/v1/dashboard/intelligence-workspace/validation"),
        lambda: _daily_probe(repo, day),
    ):
        with pytest.raises(ValueError, match=reason):
            endpoint()


def test_rehashed_child_cannot_rebind_original_decision_and_sample(chain):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    _ft_capture(repo, future)
    assert result_materialize.run(fixture_ids=["api_football:1489404"])["status"] == "PASS"
    day = _day(future)
    assert _public_probes(repo, day)[0].json()["performance_summary"]["total_profit_units"] == 1.15
    with Session(repo.engine) as session, session.begin():
        session.execute(text("SET LOCAL session_replication_role = replica"))
        row = session.scalar(
            select(AhOuV3SettlementModel).where(AhOuV3SettlementModel.market == "ASIAN_HANDICAP")
        )
        assert row is not None
        fields = {
            name: getattr(row, name)
            for name in (
                "fixture_id",
                "market",
                "schema_version",
                "terms_hash",
                "result_id",
                "result_hash",
                "result_raw_sha256",
                "result_capture_id",
                "home_goals",
                "away_goals",
                "outcome",
                "net_units",
            )
        }
        fields["net_units"] = "999"
        forged_hash = canonical_sha256(
            {"decision_id": row.decision_id, **fields},
            domain=HashDomain.RECOMMENDATION_DECISION_V4,
        )
        session.execute(
            update(AhOuV3SettlementModel)
            .where(AhOuV3SettlementModel.decision_id == row.decision_id)
            .values(net_units="999", settlement_hash=forged_hash)
        )
    with pytest.raises(
        ValueError, match="V3_PUBLIC_SETTLEMENT_FIELD_CONFLICT:net_units"
    ) as blocked:
        _public_probes(repo, day)
    print({"attack": "rehash_net_units", "reason": str(blocked.value)})


def test_database_trigger_rejects_ordinary_settlement_update(chain):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    _ft_capture(repo, future)
    assert result_materialize.run(fixture_ids=["api_football:1489404"])["status"] == "PASS"
    with Session(repo.engine) as session:
        row = session.scalar(select(AhOuV3SettlementModel).where(
            AhOuV3SettlementModel.market == "ASIAN_HANDICAP"
        ))
        assert row is not None
        with pytest.raises(Exception, match="append_only|immutable"):
            session.execute(update(AhOuV3SettlementModel).where(
                AhOuV3SettlementModel.decision_id == row.decision_id
            ).values(net_units="999"))
            session.commit()
        session.rollback()
