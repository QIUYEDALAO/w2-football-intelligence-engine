"""V11 0/2 probe repaired for the v3.1 capture and versioned sample contract.

The original probe inserted FT raw without a capture and read the legacy v2
validation table. This preserves its selected AH/OU -> FT -> natural worker
attack while providing a valid FT capture and asserting the v3 table.
"""

from datetime import UTC, datetime, timedelta

from apps.worker.celery_app import result_materialize
from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import HashDomain
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.ah_ou_postmatch_models import AhOuV3ValidationSampleModel
from w2.infrastructure.persistence.models import ResultModel
from w2.ingestion.future_refresh import sha256_payload
from w2.matchday.intake_v2 import endpoint_capture_contract
from w2.matchday.repository import MatchdayRuntimeRepository
from w2.prematch.analysis_calculator import ReadModelService

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def test_v3_selected_matches_enter_postmatch_validation(chain):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    with Session(repo.engine) as session:
        selected = list(
            session.scalars(
                select(AhOuDecisionLedgerModel).where(AhOuDecisionLedgerModel.selected.is_(True))
            )
        )
        print(
            "all_ledger_rows",
            [
                (r.market, r.selected, r.skip_reason)
                for r in session.scalars(select(AhOuDecisionLedgerModel))
            ],
        )
        print(
            "public_markets",
            [(m.get("market"), m.get("selected"), m.get("reason")) for m in card["markets"]],
        )
    assert {r.market for r in selected} == {"ASIAN_HANDICAP", "TOTALS"}

    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    ft = {
        **future,
        "fixture": {**future["fixture"], "status": {"short": "FT"}},
        "goals": {"home": 2, "away": 1},
        "score": {"fulltime": {"home": 2, "away": 1}},
    }
    raw = {"response": [ft]}
    sha = sha256_payload(raw, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
    repo.save_raw_payload(
        sha256=sha,
        endpoint="fixtures",
        captured_at=kickoff + timedelta(hours=2),
        payload=raw,
    )
    capture = endpoint_capture_contract(
        endpoint="fixtures",
        params={"id": "1489404"},
        requested_at=kickoff + timedelta(hours=2),
        provider_captured_at=kickoff + timedelta(hours=2),
        status_code=200,
        elapsed_ms=1,
        payload=raw,
        fixture_id="api_football:1489404",
        competition_id="allsvenskan",
        checkpoint="POSTMATCH_RESULT",
    )
    assert capture["raw_payload_sha256"] == sha
    MatchdayRuntimeRepository(engine=repo.engine).insert_endpoint_capture(capture)
    materialized = result_materialize.run(fixture_ids=["api_football:1489404"])
    print("result_materialized", materialized)
    with Session(repo.engine) as session:
        result = session.scalar(
            select(ResultModel).where(ResultModel.fixture_id == "api_football:1489404")
        )
        print("result_readback", result.result_status if result else None)
        assert result is not None and result.result_status == "FT"
    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(AhOuV3ValidationSampleModel).where(
                    AhOuV3ValidationSampleModel.fixture_id == "1489404"
                )
            )
        )
    print(
        "v3_selected",
        len(selected),
        "validation_rows",
        len(rows),
        "writer_report",
        materialized["result"]["validation_samples"]["v3"],
    )
    assert len(rows) == 2, "V3_SELECTED_NOT_POSTMATCH_VALIDATED"
    assert {row.market for row in rows} == {"ASIAN_HANDICAP", "TOTALS"}
