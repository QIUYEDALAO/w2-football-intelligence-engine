"""A current recommendation pause preserves real ingestion and FT settlement."""

from datetime import UTC, datetime

from apps.worker.celery_app import result_materialize
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.integration.test_ah_ou_v11_postmatch_pg import _ft_capture

from w2.api.repository import ReadModelService as ApiReadModelService
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.ah_ou_postmatch_models import AhOuV3SettlementModel
from w2.infrastructure.persistence.dynamic_prematch_models import CandidateNotificationOutboxModel
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.candidate_notifications import deliver_pending_notifications

pytest_plugins = [
    "tests.integration.test_ah_ou_v9_system_pg",
    "tests.integration.test_ah_ou_prelaunch_fence_pg",
]


def test_pause_preserves_ft_and_pending_messages_without_reopening_current_output(
    chain, monkeypatch
):
    repo, future, _, _ = chain
    assert (
        ReadModelService().public_analysis_card_bounded(
            "1489404",
            use_frozen_canary=False,
            evaluation_time=datetime.fromisoformat(future["fixture"]["date"]),
        )["ah_ou_result"]["recording"]["status"]
        == "COMMITTED"
    )
    public = ApiReadModelService().dashboard_ah_ou_v3_public()
    assert len(public) == 2
    monkeypatch.setenv("W2_CURRENT_RECOMMENDATIONS_PAUSED", "true")
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://bark.example.test")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "test-key")
    sent = []
    assert ApiReadModelService().dashboard_ah_ou_v3_public() == []
    paused = deliver_pending_notifications(
        now=datetime.now(UTC), engine=repo.engine, sender=sent.append
    )
    assert paused["status"] == "PAUSED" and paused["held"] == 2 and not sent
    _ft_capture(repo, future)
    result = result_materialize.run(fixture_ids=["api_football:1489404"])
    assert result["status"] == "PASS", result
    with Session(repo.engine) as session:
        assert session.scalar(select(func.count()).select_from(AhOuV3SettlementModel)) == 2
        assert session.scalar(select(func.count()).select_from(AhOuDecisionLedgerModel)) == 2
        assert all(
            row.delivery_status == "PENDING"
            for row in session.scalars(select(CandidateNotificationOutboxModel))
        )
    monkeypatch.setenv("W2_CURRENT_RECOMMENDATIONS_PAUSED", "false")
    resumed = ApiReadModelService().dashboard_ah_ou_v3_public()
    assert {row["decision_id"] for row in resumed} == {row["decision_id"] for row in public}
    assert sum(float(row["net_units"]) for row in resumed) == 1.15
    delivered = deliver_pending_notifications(
        now=datetime.now(UTC), engine=repo.engine, sender=sent.append
    )
    assert delivered["delivered"] == len(sent) == 2


def test_partial_0076_schema_keeps_trusted_ft_without_false_v3_pass(migrated_database, monkeypatch):
    import os
    import subprocess
    from datetime import timedelta
    from types import SimpleNamespace

    from sqlalchemy import inspect, text

    from w2.domain.canonical_serialization import HashDomain
    from w2.infrastructure.persistence.models import ResultModel
    from w2.ingestion.future_refresh import sha256_payload
    from w2.matchday.intake_v2 import MatchdayCompetitionPolicy, fixture_discovery_from_payloads
    from w2.matchday.repository import MatchdayRuntimeRepository

    engine = migrated_database
    subprocess.run(
        [".venv/bin/alembic", "downgrade", "0076_forward_review_evidence"],
        check=True,
        env=os.environ.copy(),
        capture_output=True,
    )
    assert not inspect(engine).has_table("ah_ou_decision_ledger")
    monkeypatch.setenv("W2_CURRENT_RECOMMENDATIONS_PAUSED", "true")
    at = datetime.now(UTC) - timedelta(hours=6)
    future = {
        "fixture": {
            "id": 1489404,
            "date": (at + timedelta(hours=3)).isoformat(),
            "status": {"short": "NS"},
        },
        "league": {"id": 113, "season": 2026},
        "teams": {"home": {"id": 10, "name": "H"}, "away": {"id": 20, "name": "A"}},
    }
    raw = {"response": [future]}
    sha = sha256_payload(raw, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
    writer = MatchdayRuntimeRepository(engine=engine)
    assert writer.save_raw_payload(sha256=sha, endpoint="fixtures", captured_at=at, payload=raw)
    policy = MatchdayCompetitionPolicy(
        competition_id="allsvenskan",
        enabled=True,
        provider="api_football",
        provider_league_id="113",
        season="2026",
        discovery_horizon_hours=168,
        fixture_status_allowlist=("NS",),
        checkpoints=(),
        endpoint_matrix={},
        odds_max_age_seconds=1800,
        lineup_requirement="OPTIONAL",
        request_caps={},
        provider_allowlist=("fixtures",),
        feature_enrichment_policy={},
    )
    discovered = fixture_discovery_from_payloads(
        [future],
        policies={"allsvenskan": policy},
        captured_at=at,
        source_payload_sha256=sha,
    )["candidate_fixtures"]
    for row in discovered:
        row.update(fixture_status="NS", raw_payload_sha256=sha, payload=future)
    assert writer.insert_fixture_identities(discovered) == 1
    captured = _ft_capture(SimpleNamespace(engine=engine), future)
    result = result_materialize.run(fixture_ids=["api_football:1489404"])
    assert result["status"] == "BLOCKED", result
    assert result["result"]["validation_samples"]["v3"]["reason"] == (
        "V3_POSTMATCH_SCHEMA_UNAVAILABLE"
    )
    with Session(engine) as session:
        confirmed = session.scalar(select(ResultModel))
        assert confirmed.home_goals == 2 and confirmed.away_goals == 1
        assert confirmed.source_capture_id == captured["capture_id"]
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0076_forward_review_evidence"
        )
    print(
        {
            "schema": "0076",
            "trusted_ft_persisted": True,
            "current_recommendations": "PAUSED",
            "v3_settlement": result["status"],
        }
    )
