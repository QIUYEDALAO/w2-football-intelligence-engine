"""Independent pre-FT frozen decision read-defense, same PG no-op first."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from apps.api.main import app
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from w2.dashboard.date_window import football_day_for_kickoff
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.prematch.analysis_calculator import ReadModelService

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def mutate(repo, decision_id, field, value):
    with Session(repo.engine) as session, session.begin():
        session.execute(text("SET LOCAL session_replication_role = replica"))
        session.execute(
            update(AhOuDecisionLedgerModel)
            .where(AhOuDecisionLedgerModel.decision_id == decision_id)
            .values(**{field: value})
        )


def read(day):
    response = TestClient(app, raise_server_exceptions=False).get(
        "/v1/dashboard/intelligence-workspace/list", params={"date": day.isoformat()}
    )
    body = response.json()
    return response.status_code, body


@pytest.mark.parametrize(
    "field",
    [
        "score",
        "decision_at",
        "skip_reason",
        "home_team_id",
        "source_id",
        "model_version",
        "calibration_version",
        "input_hash",
        "quote_identity_hash",
        "capture_id",
    ],
)
def test_pending_homepage_rejects_frozen_decision_field_conflicts(chain, field):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    day = football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))
    with Session(repo.engine) as session:
        ah = session.scalar(
            select(AhOuDecisionLedgerModel).where(
                AhOuDecisionLedgerModel.market == "ASIAN_HANDICAP"
            )
        )
        decision_id, original = ah.decision_id, getattr(ah, field)
        assert ah.selected and ah.decision_contract == "w2.ah_ou_decision.v3.1"
    mutate(repo, decision_id, field, original)
    code, payload = read(day)
    assert code == 200, payload
    assert len(payload["today_recommendations"]) == 2
    print(
        json.dumps(
            {
                "scenario": f"pending_public_{field}_noop",
                "db": repo.engine.url.database,
                "http": code,
                "rows": payload["today_recommendations"],
            },
            default=str,
        )
    )
    bad = {
        "score": Decimal("999"),
        "decision_at": (
            original + timedelta(seconds=1) if field == "decision_at" else datetime.now(UTC)
        ),
        "skip_reason": "F6_H2H_CAPTURED_AFTER_DECISION",
        "home_team_id": "W2_OTHER",
        "source_id": "other",
        "model_version": "other",
        "calibration_version": "other",
        "input_hash": "f" * 64,
        "quote_identity_hash": "f" * 64,
        "capture_id": "other",
    }[field]
    assert original != bad
    mutate(repo, decision_id, field, bad)
    code, payload = read(day)
    print(
        json.dumps(
            {
                "scenario": f"pending_public_{field}_attack",
                "db": repo.engine.url.database,
                "decision_id": decision_id,
                "old": original,
                "new": bad,
                "http": code,
                "body": payload
                if code != 200
                else {
                    "today_recommendations": payload["today_recommendations"],
                    "performance_summary": payload["performance_summary"],
                },
            },
            default=str,
        )
    )
    assert code == 503, payload
    expected = {
        "score": "V3_PUBLIC_DECISION_ID_MISMATCH",
        "decision_at": "V3_PUBLIC_FIXTURE_TEAM_BINDING_INVALID",
        "home_team_id": "V3_PUBLIC_FIXTURE_TEAM_BINDING_INVALID",
        "skip_reason": "V3_SELECTED_DECISION_STATE_INVALID",
        "source_id": "V3_PUBLIC_SOURCE_ID_MISMATCH",
    }.get(field, "V3_PUBLIC_FROZEN_TERMS_BINDING_INVALID")
    assert expected in payload["message"]


def test_pending_public_rejects_feature_distribution_change_under_original_input_hash(chain):
    from copy import deepcopy

    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["ah"]["selected"]
    day = football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))
    with Session(repo.engine) as session:
        ah = session.scalar(
            select(AhOuDecisionLedgerModel).where(
                AhOuDecisionLedgerModel.market == "ASIAN_HANDICAP"
            )
        )
        identity, original = ah.decision_id, deepcopy(ah.full_distribution)
    mutate(repo, identity, "full_distribution", original)
    code, payload = read(day)
    assert code == 200 and len(payload["today_recommendations"]) == 2
    changed = deepcopy(original)
    changed["features"]["f9_home_xgf"] += 0.1
    mutate(repo, identity, "full_distribution", changed)
    code, payload = read(day)
    assert code == 503, payload
    assert "V3_PUBLIC_INPUT_CONTENT_HASH_MISMATCH" in payload["message"]
    print({"control_http": 200, "attack_http": code, "reason": payload["message"]})
