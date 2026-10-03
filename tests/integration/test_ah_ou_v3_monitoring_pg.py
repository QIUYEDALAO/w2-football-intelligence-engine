"""Actual producer and natural FT worker monitoring; no live Provider calls."""

from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal

import pytest
from apps.worker.celery_app import result_materialize
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from tests.integration.test_ah_ou_v9_system_pg import _build_chain
from tests.integration.test_ah_ou_v11_postmatch_pg import _ft_capture

from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.ah_ou_monitoring_models import AhOuV3MonitoringFactModel
from w2.infrastructure.persistence.ah_ou_postmatch_models import AhOuV3SettlementModel
from w2.prematch.analysis_calculator import ReadModelService

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def test_200_actual_frozen_fixtures_natural_worker_creates_separate_market_reports(chain):
    """Synthetic batch ingestion uses the live producer's persistence methods.

    No factor ORM inserts, fake FT or manual forward calls. The first fixture
    comes from the full checkpoint chain; 199 more use its captured upstream
    history and actual raw/capture/normalization/fixture producer methods.
    """

    from w2.domain.canonical_serialization import HashDomain
    from w2.infrastructure.persistence.ah_ou_monitoring_models import AhOuV3MonitoringReportModel
    from w2.ingestion.future_refresh import (
        FutureFixtureRefreshService,
        FutureRefreshConfig,
        sha256_payload,
    )
    from w2.ingestion.xg_backfill import XgHistoryBackfillService
    from w2.matchday.intake_v2 import normalize_matchday_odds_payload
    from w2.matchday.repository import MatchdayRuntimeRepository
    from w2.providers.api_football import LiveApiFootballResponse

    repo, original, _, xg = chain
    upstream = [deepcopy(original) for _ in range(199)]
    for index, item in enumerate(upstream):
        item["fixture"]["id"] = 1489405 + index
    producer = FutureFixtureRefreshService(
        client=object(),
        now=xg.now,
        config=FutureRefreshConfig(competition_id="allsvenskan", league_id="113", persistence="db"),
    )
    writer = MatchdayRuntimeRepository(engine=repo.engine)

    def ingest(endpoint, params, payload):
        response = LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            payload=payload,
            status_code=200,
            captured_at=xg.now,
            requested_at=xg.now,
            elapsed_ms=1,
            headers={},
        )
        raw = producer._raw_payload_record(endpoint=endpoint, params=params, payload=payload)
        digest = sha256_payload(raw, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
        assert producer._save_raw_payload_first(
            endpoint=endpoint, params=params, response=response, payload_hash=digest, payload=raw
        ) == (True, None)
        capture, error = producer._persist_matchday_endpoint_capture(
            endpoint=endpoint, params=params, attempt=1, response=response, payload=raw
        )
        assert capture and error is None
        return response, digest, capture

    fixtures_response, _, _ = ingest(
        "fixtures", {"league": "113", "season": "2026"}, {"response": upstream}
    )
    rows = producer._fixture_identities_from_response(
        fixtures_response=fixtures_response,
        fixtures=upstream,
        request_params={"league": "113", "season": "2026"},
    )
    writer.upsert_fixture_identities_with_business_changes(rows)
    with Session(repo.engine) as session:
        from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel

        quote = next(
            row.payload
            for row in session.scalars(
                select(RawPayloadModel).where(RawPayloadModel.endpoint == "odds")
            )
        )
    batch = []
    for item in upstream:
        odds_item = deepcopy(quote["response"][0])
        odds_item["fixture"]["id"] = item["fixture"]["id"]
        batch.append(odds_item)
    response, raw_hash, capture_id = ingest("odds", {"league": "113"}, {"response": batch})
    observations, rejected = normalize_matchday_odds_payload(
        response.payload,
        captured_at=xg.now,
        ingested_at=xg.now,
        raw_payload_sha256=raw_hash,
        source_revision="synthetic-200-forward",
        capture_id=capture_id,
        competition_id="allsvenskan",
    )
    assert not rejected and len(observations) == 199 * 4
    writer.insert_market_observations(observations)
    result = XgHistoryBackfillService(
        repository=repo, client=object(), now=xg.now, config=xg.config
    ).run_saved_raw()
    assert result.rolling_snapshot_rows == 400
    for item in [original, *upstream]:
        card = ReadModelService().public_analysis_card_bounded(
            str(item["fixture"]["id"]), use_frozen_canary=False
        )
        assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED", card
    # 199 FT per market must not trigger; the 200th is a natural worker event.
    for item in [original, *upstream[:-1]]:
        _ft_capture(repo, item)
    first = result_materialize.run()
    assert first["status"] == "PASS", first
    with Session(repo.engine) as session:
        assert session.scalar(select(AhOuV3MonitoringReportModel)) is None
        assert len(session.scalars(select(AhOuV3MonitoringFactModel)).all()) == 398
    _ft_capture(repo, upstream[-1])
    second = result_materialize.run()
    assert second["status"] == "PASS", second
    with Session(repo.engine) as session:
        reports = session.scalars(select(AhOuV3MonitoringReportModel)).all()
        assert len(reports) == 2
        assert {row.market for row in reports} == {"ASIAN_HANDICAP", "TOTALS"}
        assert all(row.eligible_settled_count == 200 for row in reports)
        assert all(row.payload["recommended"] == 200 for row in reports)
        # Independent constant-score and entry-price arithmetic.
        assert {row.market: Decimal(row.payload["net_units"]) for row in reports} == {
            "ASIAN_HANDICAP": Decimal("50.00"),
            "TOTALS": Decimal("180.00"),
        }
        frozen = {row.report_id: deepcopy(row.payload) for row in reports}
    assert result_materialize.run()["status"] == "PASS"
    with Session(repo.engine) as session:
        assert {
            row.report_id: row.payload
            for row in session.scalars(select(AhOuV3MonitoringReportModel))
        } == frozen
    # The four DB steps include explicit conflict submission under the same identity.
    with pytest.raises(DBAPIError, match="V3_MONITORING_IMMUTABLE"):
        with Session(repo.engine) as session, session.begin():
            session.execute(update(AhOuV3MonitoringReportModel).values(payload_hash="0" * 64))
    import os
    import subprocess

    downgrade = subprocess.run([".venv/bin/alembic", "downgrade", "0088_ahou_v3_outbox"],
                               env=os.environ.copy(), text=True, capture_output=True)
    assert downgrade.returncode != 0
    assert "V3_MONITORING_EVIDENCE_PREVENTS_SCHEMA_DOWNGRADE" in downgrade.stderr
    with Session(repo.engine) as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0091_ahou_decision_skip_reevaluate")
        assert {row.report_id: row.payload for row in session.scalars(
            select(AhOuV3MonitoringReportModel))} == frozen


def test_below_threshold_eligible_inputs_count_without_becoming_recommendations(
    tmp_path, monkeypatch
):
    with contextmanager(_build_chain)(
        tmp_path,
        monkeypatch,
        market_prices={
            "ASIAN_HANDICAP": ("1.90", "1.90"),
            "TOTALS": ("1.01", "50.00"),
        },
    ) as (repo, future, _, _):
        card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
        assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
        with Session(repo.engine) as session:
            decisions = session.scalars(select(AhOuDecisionLedgerModel)).all()
            assert len(decisions) == 2 and all(not row.selected for row in decisions)
            assert all(row.direction is None and row.frozen_terms is None for row in decisions)
            assert all(row.skip_reason is None for row in decisions)
        _ft_capture(repo, future)
        result = result_materialize.run(fixture_ids=["api_football:1489404"])
        assert result["status"] == "PASS", result
        assert result["result"]["validation_samples"]["v3"]["monitoring"] == {
            "created_facts": 2,
            "excluded_facts": 0,
            "created_reports": 0,
        }
        with Session(repo.engine) as session:
            facts = session.scalars(select(AhOuV3MonitoringFactModel)).all()
            assert len(facts) == 2 and all(row.payload["eligible"] for row in facts)
            assert all(row.payload["selected"] is False for row in facts)
            assert session.scalar(select(AhOuV3SettlementModel)) is None
            frozen = {row.decision_id: deepcopy(row.payload) for row in facts}
        for _ in range(2):
            retry = result_materialize.run(fixture_ids=["api_football:1489404"])
            assert retry["status"] == "PASS"
            assert retry["result"]["validation_samples"]["v3"]["monitoring"]["created_facts"] == 0
            with Session(repo.engine) as session:
                assert {
                    row.decision_id: row.payload
                    for row in session.scalars(select(AhOuV3MonitoringFactModel))
                } == frozen
        with pytest.raises(DBAPIError, match="V3_MONITORING_IMMUTABLE"):
            with Session(repo.engine) as session, session.begin():
                session.execute(update(AhOuV3MonitoringFactModel).values(payload_hash="0" * 64))
        # Same-path no-op control below the write trigger, then one-field attack.
        with Session(repo.engine) as session, session.begin():
            session.execute(text("SET LOCAL session_replication_role = replica"))
            row = session.scalar(select(AhOuV3MonitoringFactModel))
            session.execute(
                update(AhOuV3MonitoringFactModel)
                .where(AhOuV3MonitoringFactModel.decision_id == row.decision_id)
                .values(payload=row.payload)
            )
        assert result_materialize.run(fixture_ids=["api_football:1489404"])["status"] == "PASS"
        with Session(repo.engine) as session, session.begin():
            session.execute(text("SET LOCAL session_replication_role = replica"))
            row = session.scalar(select(AhOuV3MonitoringFactModel))
            changed = {**row.payload, "home_goals": 999}
            session.execute(
                update(AhOuV3MonitoringFactModel)
                .where(AhOuV3MonitoringFactModel.decision_id == row.decision_id)
                .values(payload=changed)
            )
        with pytest.raises(ValueError, match="V3_MONITORING_FACT_CONFLICT"):
            result_materialize.run(fixture_ids=["api_football:1489404"])
