"""F1R-C: the runtime AH settlement fact writer runs on the natural path.

The final F1R-C implementation question is not "can a fact be built" -- the
offline constructor already proved that from a committed real capture sample.
It is "does anything build one without a human asking". This file drives the
writer the way production does: through the worker's result-materialisation
step, against an isolated PostgreSQL 16, with the real quote rows and the real
capture identity taken from the committed production-capture sample.

The claim each test makes is about the *writer*, not about the constructor:

* the natural path calls it, and the controlled recovery path is not the only
  caller;
* a terminal fixture with a complete chain gets a fact, and the fact is the one
  the offline constructor would have built from the same rows;
* a replay is an idempotent no-op, never a second fact;
* every refusal names its own missing link and stays visible in the report;
* no Provider call is made, or possible;
* a round whose results did not materialise writes no fact, and a writer that
  failed cannot let the task report a clean pass.

Isolated PostgreSQL is required and the test skips without it, exactly like the
F1R-B and F1R-C suites whose harness it reuses.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.historical.runtime_ah_settlement import RuntimeAhSettlementRepository
from w2.historical.runtime_ah_settlement_materializer import (
    REFUSAL_CAPTURE_FIXTURE_MISMATCH,
    REFUSAL_CAPTURE_IDENTITY_MISSING,
    REFUSAL_CAPTURE_OWNERSHIP_UNPROVEN,
    REFUSAL_FACT_REVISION_CONFLICT,
    REFUSAL_QUOTE_BUCKET_MISSING,
    REFUSAL_RESULT_PAYLOAD_HASH_MISMATCH,
    REFUSAL_TERMINAL_EVIDENCE_MISSING,
    STATUS_FAILED,
    STATUS_INCOMPLETE,
    STATUS_NO_DUE_WORK,
    STATUS_SKIPPED,
    empty_report,
    materialize_runtime_ah_settlement_facts,
    merge_runtime_ah_fact_reports,
    runtime_ah_fact_writer_status,
    writer_status_is_clean,
)
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
)
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.models import ResultModel

_HERE = Path(__file__).resolve().parent
REPO = _HERE.parents[1]


def _load(name: str, path: Path):  # type: ignore[no-untyped-def]
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


f1rb = _load("w2_f1rb_e2e", _HERE / "test_f1r_b_production_factor_recording_e2e.py")

AH_SAMPLE = REPO / "tests/fixtures/ah_settlement/real_production_capture_sample.jsonl"
#: The 1-1 quarter-line fixture: home does not cover, away does.
SAMPLE_INDEX = 1

#: The sample's own identities, kept exactly as captured so the natural writer
#: and the offline constructor read the same rows.
SAMPLE = json.loads(AH_SAMPLE.read_text(encoding="utf-8").splitlines()[SAMPLE_INDEX])
SAMPLE_FIXTURE = SAMPLE["fixture"]
SAMPLE_CAPTURE = SAMPLE["settlement_capture"]
FACT_FIXTURE_ID = str(SAMPLE_FIXTURE["fixture_id"])
FACT_PROVIDER_FIXTURE_ID = str(SAMPLE_FIXTURE["provider_fixture_id"])
QUOTE_CAPTURE_ID = str(SAMPLE["observations"][0]["capture_id"])


# --- seeding --------------------------------------------------------------
def _odds_capture_row() -> MatchdayEndpointCaptureModel:
    quote = SAMPLE["observations"][0]
    captured_at = _utc(quote["captured_at"])
    return MatchdayEndpointCaptureModel(
        capture_id=QUOTE_CAPTURE_ID,
        fixture_id=FACT_FIXTURE_ID,
        competition_id=str(SAMPLE_FIXTURE["competition_id"]),
        checkpoint="T24_OPEN_ODDS",
        endpoint="odds",
        sanitized_params={"fixture": FACT_PROVIDER_FIXTURE_ID},
        params_hash=_hex("odds-params"),
        request_task_key="f1r-c-natural-writer",
        attempt=1,
        requested_at=captured_at,
        provider_captured_at=captured_at,
        status_code=200,
        elapsed_ms=1,
        response_count=1,
        quota_values={},
        raw_payload_sha256=str(quote["raw_payload_sha256"]),
        provider_event_time=None,
        capture_status="CAPTURED",
        error_code=None,
    )


def _settlement_capture_row() -> MatchdayEndpointCaptureModel:
    """The terminal capture exactly as production stores it.

    A `fixtures`-endpoint capture is a *bulk* response: it names no fixture --
    every one of them in production has a null `fixture_id` -- so its payload is
    the only thing that says what it covered. That is the shape the ownership
    check has to handle, so it is the shape this harness builds.
    """
    kickoff = _utc(SAMPLE_FIXTURE["kickoff_utc"])
    return MatchdayEndpointCaptureModel(
        capture_id=str(SAMPLE_CAPTURE["capture_id"]),
        fixture_id=None,
        competition_id=str(SAMPLE_FIXTURE["competition_id"]),
        checkpoint="POSTMATCH_RESULT",
        endpoint=str(SAMPLE_CAPTURE["endpoint"]),
        sanitized_params={"fixture": FACT_PROVIDER_FIXTURE_ID},
        params_hash=_hex("settlement-params"),
        request_task_key="f1r-c-natural-writer",
        attempt=1,
        requested_at=kickoff,
        provider_captured_at=_utc(SAMPLE_CAPTURE["provider_captured_at"]),
        status_code=200,
        elapsed_ms=1,
        response_count=1,
        quota_values={},
        raw_payload_sha256=str(SAMPLE_CAPTURE["raw_payload_sha256"]),
        provider_event_time=None,
        capture_status=str(SAMPLE_CAPTURE["capture_status"]),
        error_code=None,
    )


def _settlement_payload_row(*, with_fixture: bool = True) -> RawPayloadModel:
    """The capture's stored payload -- the proof of which fixtures it covered."""
    fixture_item = {
        "fixture": {
            "id": int(FACT_PROVIDER_FIXTURE_ID),
            "date": SAMPLE_FIXTURE["kickoff_utc"],
            "status": {"short": str(SAMPLE_FIXTURE["fixture_status"])},
        },
        "goals": {
            "home": int(SAMPLE_FIXTURE["home_goals"]),
            "away": int(SAMPLE_FIXTURE["away_goals"]),
        },
        # What the result materialiser actually reads. A payload that is terminal
        # but carries no fulltime score is *invalid* evidence to it, not absent
        # evidence, and it blocks the round -- so the fixture here is the real
        # Provider shape, score included.
        "score": {
            "fulltime": {
                "home": int(SAMPLE_FIXTURE["home_goals"]),
                "away": int(SAMPLE_FIXTURE["away_goals"]),
            }
        },
    }
    other_item = {
        "fixture": {"id": 999999999, "status": {"short": "FT"}},
        "goals": {"home": 0, "away": 0},
    }
    return RawPayloadModel(
        sha256=str(SAMPLE_CAPTURE["raw_payload_sha256"]),
        endpoint="fixtures",
        captured_at=_utc(SAMPLE_CAPTURE["provider_captured_at"]),
        inserted_at=_utc(SAMPLE_CAPTURE["provider_captured_at"]),
        storage_uri="w2-test://fixtures",
        payload={"response": [fixture_item] if with_fixture else [other_item]},
    )


def _observation_row(quote: dict[str, Any]) -> MatchdayMarketObservationModel:
    captured_at = _utc(quote["captured_at"])
    return MatchdayMarketObservationModel(
        observation_id=str(quote["observation_id"]),
        fixture_id=str(quote["fixture_id"]),
        provider_fixture_id=FACT_PROVIDER_FIXTURE_ID,
        competition_id=str(SAMPLE_FIXTURE["competition_id"]),
        provider=str(quote["provider"]),
        bookmaker_id=str(quote["bookmaker_id"]),
        bookmaker_name=str(quote["bookmaker_name"]),
        capture_id=str(quote["capture_id"]),
        provider_bet_id=str(quote.get("provider_bet_id") or quote["bookmaker_id"]),
        raw_market_label=str(quote["raw_market_label"]),
        canonical_market=str(quote["canonical_market"]),
        canonical_selection=str(quote["selection"]),
        provider_selection=str(quote["selection"]),
        line=str(quote["line"]),
        decimal_odds=str(quote["decimal_odds"]),
        suspended=bool(quote["suspended"]),
        live=bool(quote["live"]),
        provider_updated_at=str(quote["captured_at"]),
        captured_at=captured_at,
        ingested_at=captured_at,
        raw_payload_sha256=str(quote["raw_payload_sha256"]),
        source_revision=str(quote["source_revision"]),
    )


def _world_cup_free_season() -> str:
    return str(SAMPLE_FIXTURE["season"])


def _seed_fact_chain(engine: Engine) -> None:
    """A terminal fixture whose whole chain is already persisted.

    Every row is the production row: the quote bucket, both capture identities
    and the payload digests come from the committed capture sample, not from a
    hand-written fixture. The two w2 team ids are the ones the evaluated fixture
    carries, because a fact is only useful if F5 can read it as a participation.
    """
    with Session(engine) as session, session.begin():
        session.add(_odds_capture_row())
        session.add(_settlement_capture_row())
        session.flush()
        session.add(_settlement_payload_row())
        session.add_all([_observation_row(quote) for quote in SAMPLE["observations"]])
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id=FACT_FIXTURE_ID,
                provider="api_football",
                provider_fixture_id=FACT_PROVIDER_FIXTURE_ID,
                competition_id=str(SAMPLE_FIXTURE["competition_id"]),
                provider_league_id="253",
                season=_world_cup_free_season(),
                kickoff_utc=_utc(SAMPLE_FIXTURE["kickoff_utc"]),
                fixture_status=str(SAMPLE_FIXTURE["fixture_status"]),
                home_provider_team_id=str(SAMPLE_FIXTURE["home_team_provider_id"]),
                away_provider_team_id=str(SAMPLE_FIXTURE["away_team_provider_id"]),
                home_w2_team_id=f1rb.HOME_W2,
                away_w2_team_id=f1rb.AWAY_W2,
                team_identity_status="PROVIDER_PRIMARY_READY",
                raw_payload_sha256=str(SAMPLE_CAPTURE["raw_payload_sha256"]),
                endpoint_capture_id=str(SAMPLE_CAPTURE["capture_id"]),
                captured_at=_utc(SAMPLE_CAPTURE["provider_captured_at"]),
                identity_hash=_hex("fact-identity"),
                # The terminal payload itself: this is what the result
                # materialiser reads to confirm a fixture, so the natural
                # trigger can be driven end to end without a provider. The score
                # it reads is the fulltime one, in the Provider's own shape.
                payload={
                    "fixture": {
                        "id": int(FACT_PROVIDER_FIXTURE_ID),
                        "date": SAMPLE_FIXTURE["kickoff_utc"],
                        "status": {"short": str(SAMPLE_FIXTURE["fixture_status"])},
                    },
                    "teams": {
                        "home": {"id": int(SAMPLE_FIXTURE["home_team_provider_id"])},
                        "away": {"id": int(SAMPLE_FIXTURE["away_team_provider_id"])},
                    },
                    "goals": {
                        "home": int(SAMPLE_FIXTURE["home_goals"]),
                        "away": int(SAMPLE_FIXTURE["away_goals"]),
                    },
                    "score": {
                        "fulltime": {
                            "home": int(SAMPLE_FIXTURE["home_goals"]),
                            "away": int(SAMPLE_FIXTURE["away_goals"]),
                        }
                    },
                },
            )
        )
        session.add(
            ResultModel(
                fixture_id=FACT_FIXTURE_ID,
                home_goals=int(SAMPLE_FIXTURE["home_goals"]),
                away_goals=int(SAMPLE_FIXTURE["away_goals"]),
                result_status=str(SAMPLE_FIXTURE["fixture_status"]),
                confirmed_at=_utc(SAMPLE_CAPTURE["provider_captured_at"]),
                source_payload_sha256=str(SAMPLE_CAPTURE["raw_payload_sha256"]),
                source_capture_id=str(SAMPLE_CAPTURE["capture_id"]),
                result_hash=_hex("fact-result"),
            )
        )


@pytest.fixture
def natural(monkeypatch: Any, tmp_path: Path) -> Engine:
    """The F1R-B end-to-end world, plus a terminal fixture chain to write from."""
    engine = f1rb._fresh_database(monkeypatch)
    f1rb._seed_ingested_fixture(engine, tmp_path)
    f1rb._canonicalise(engine)
    _seed_fact_chain(engine)
    return engine


def _offline_fact():  # type: ignore[no-untyped-def]
    """The fact the offline constructor builds from the committed sample.

    This is the authority on what a fact *is* for these rows. The natural writer
    is held against it rather than against a hand-written expectation.
    """
    from w2.markets.ah_settlement_fact import (
        TerminalSettlementEvidence,
        build_ah_settlement_fact,
    )

    fact = build_ah_settlement_fact(
        fixture_id=FACT_FIXTURE_ID,
        provider_fixture_id=FACT_PROVIDER_FIXTURE_ID,
        competition_id=str(SAMPLE_FIXTURE["competition_id"]),
        season=_world_cup_free_season(),
        kickoff=SAMPLE_FIXTURE["kickoff_utc"],
        market_observations=SAMPLE["observations"],
        settlement=TerminalSettlementEvidence(
            provider_fixture_id=FACT_PROVIDER_FIXTURE_ID,
            status=str(SAMPLE_FIXTURE["fixture_status"]),
            home_goals=int(SAMPLE_FIXTURE["home_goals"]),
            away_goals=int(SAMPLE_FIXTURE["away_goals"]),
            endpoint_capture_id=str(SAMPLE_CAPTURE["capture_id"]),
            raw_payload_sha256=str(SAMPLE_CAPTURE["raw_payload_sha256"]),
            observed_at=_utc(SAMPLE_CAPTURE["provider_captured_at"]),
            capture_endpoint=str(SAMPLE_CAPTURE["endpoint"]),
            capture_status=str(SAMPLE_CAPTURE["capture_status"]),
        ),
        home_team_provider_id=str(SAMPLE_FIXTURE["home_team_provider_id"]),
        away_team_provider_id=str(SAMPLE_FIXTURE["away_team_provider_id"]),
        home_w2_team_id=f1rb.HOME_W2,
        away_w2_team_id=f1rb.AWAY_W2,
    )
    assert fact.status == "READY", fact.refusal_code
    return fact


# --- 1: the natural writer writes the fact the constructor would -----------
def test_the_natural_writer_appends_the_terminal_fixtures_fact(
    natural: Engine,
) -> None:
    expected = _offline_fact()

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert report["status"] == "COMPLETE", report
    assert report["appended"] == 1
    assert report["idempotent_no_ops"] == 0
    assert report["refused_fixture_count"] == 0
    assert report["refusal_codes"] == {}
    assert report["provider_calls"] == 0
    assert report["db_writes"] == 1
    detail = report["fixtures"][0]
    assert detail["fixture_id"] == FACT_FIXTURE_ID
    assert detail["status"] == "APPENDED"
    assert detail["evidence_source"] == "results"
    assert detail["identity_source"] == "matchday_fixture_identities"
    assert detail["line"] == _line_text(expected.line)
    assert detail["terminal_status"] == "FT"
    assert detail["fact_id"] == expected.fact_id
    assert detail["fact_hash"] == expected.fact_hash
    assert detail["settlement_capture_id"] == SAMPLE_CAPTURE["capture_id"]
    assert detail["settlement_payload_sha256"] == SAMPLE_CAPTURE["raw_payload_sha256"]

    rows = RuntimeAhSettlementRepository(engine=natural).facts_for_teams(
        [f1rb.HOME_W2, f1rb.AWAY_W2], before=f1rb.NOW, limit_per_team=20
    )
    assert len(rows) == 2
    for row in rows:
        assert row["ah_fact_id"] == detail["fact_id"]
        assert row["ah_fact_hash"] == detail["fact_hash"]
        assert row["ah_source_capture_id"] == SAMPLE_CAPTURE["capture_id"]
        assert row["ah_source_capture_sha256"] == SAMPLE_CAPTURE["raw_payload_sha256"]
        assert row["ah_policy"] == "canonical_bookmaker_mainline_majority_v1"
        assert row["source"] == "canonical_historical_ah_fact"
        assert row["collection_status"] == "CANONICAL_AH_FACT"


def test_the_natural_writer_builds_the_same_fact_as_the_offline_constructor(
    natural: Engine,
) -> None:
    """Same rows, same fact: the writer adds no second interpretation.

    The offline constructor is the authority on what a fact *is*. If the natural
    writer could mint a different identity from the same persisted rows, the
    table would hold two truths about one fixture.
    """
    expected = _offline_fact()

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )
    detail = report["fixtures"][0]

    assert detail["fact_id"] == expected.fact_id
    assert detail["fact_hash"] == expected.fact_hash
    assert detail["quote_identity_hash"] == expected.quote_identity_hash
    assert detail["settlement_observed_at"] == expected.settlement_observed_at.isoformat()
    assert detail["quote_captured_at"] == expected.quote_captured_at.isoformat()
    # The whole point-in-time chain, in one place.
    assert expected.quote_captured_at < expected.kickoff_utc < expected.settlement_observed_at


def test_a_bare_provider_fixture_id_resolves_the_same_fixture(
    natural: Engine,
) -> None:
    """The writer accepts either identity, and both name one fact."""
    by_canonical = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )
    by_provider = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_PROVIDER_FIXTURE_ID]
    )

    assert by_provider["appended"] == 0
    assert by_provider["idempotent_no_ops"] == 1
    assert (
        by_provider["fixtures"][0]["fact_id"] == by_canonical["fixtures"][0]["fact_id"]
    )


def test_an_unknown_fixture_is_refused_and_visible(natural: Engine) -> None:
    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=["api_football:not-a-real-fixture"]
    )

    assert report["appended"] == 0
    assert report["refusal_codes"] == {"AH_SETTLEMENT_FIXTURE_IDENTITY_UNRESOLVED": 1}
    assert report["fixtures"][0]["status"] == "REFUSED"


# --- 2: replay ------------------------------------------------------------
def test_a_replay_of_the_natural_writer_is_an_idempotent_no_op(
    natural: Engine,
) -> None:
    first = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )
    assert first["appended"] == 1

    second = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert second["appended"] == 0
    assert second["idempotent_no_ops"] == 1
    assert second["fixtures"][0]["status"] == "IDEMPOTENT_NO_OP"
    assert second["fixtures"][0]["fact_id"] == first["fixtures"][0]["fact_id"]
    assert _fact_count(natural) == 1


# --- 3: every refusal names its own missing link -------------------------
def test_a_non_terminal_fixture_is_refused_and_visible(natural: Engine) -> None:
    """With no terminal evidence, the refusal says the evidence is missing."""
    with Session(natural) as session, session.begin():
        session.execute(
            update(ResultModel)
            .where(ResultModel.fixture_id == FACT_FIXTURE_ID)
            .values(source_capture_id=None)
        )
        session.add(
            _history_row(fixture_status="NS", kickoff=SAMPLE_FIXTURE["kickoff_utc"])
        )

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert report["appended"] == 0
    # The constructor owns this refusal: the history row says NS, so no fact
    # may claim a settlement.
    assert report["refusal_codes"] == {"AH_SETTLEMENT_NOT_TERMINAL": 1}
    assert report["fixtures"][0]["status"] == "REFUSED"


def test_a_terminal_fixture_without_a_quote_bucket_is_refused_and_visible(
    natural: Engine,
) -> None:
    with Session(natural) as session, session.begin():
        session.execute(
            update(MatchdayMarketObservationModel).values(captured_at=_future())
        )

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert report["appended"] == 0
    assert report["refusal_codes"] == {REFUSAL_QUOTE_BUCKET_MISSING: 1}
    assert report["fixtures"][0]["status"] == "REFUSED"
    assert report["fixtures"][0]["refusal_code"] == REFUSAL_QUOTE_BUCKET_MISSING
    assert _fact_count(natural) == 0


def test_a_terminal_result_without_a_capture_identity_is_refused_and_visible(
    natural: Engine,
) -> None:
    with Session(natural) as session, session.begin():
        session.execute(
            update(ResultModel)
            .where(ResultModel.fixture_id == FACT_FIXTURE_ID)
            .values(source_capture_id=None)
        )
        session.add(
            _history_row(
                fixture_status="FT",
                kickoff=SAMPLE_FIXTURE["kickoff_utc"],
                endpoint_capture_id=None,
            )
        )

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert report["appended"] == 0
    assert report["refusal_codes"] == {REFUSAL_CAPTURE_IDENTITY_MISSING: 1}
    assert report["fixtures"][0]["status"] == "REFUSED"
    assert _fact_count(natural) == 0


def test_a_fixture_with_no_terminal_evidence_at_all_is_refused(
    natural: Engine,
) -> None:
    with Session(natural) as session, session.begin():
        session.execute(
            sa_delete(ResultModel).where(ResultModel.fixture_id == FACT_FIXTURE_ID)
        )

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert report["appended"] == 0
    assert report["refusal_codes"] == {REFUSAL_TERMINAL_EVIDENCE_MISSING: 1}
    assert _fact_count(natural) == 0


def test_a_fact_with_no_w2_team_mapping_is_not_written(natural: Engine) -> None:
    """A fact F5 could never consume is a row that costs without paying."""
    with Session(natural) as session, session.begin():
        session.execute(
            update(MatchdayFixtureIdentityModel)
            .where(MatchdayFixtureIdentityModel.fixture_id == FACT_FIXTURE_ID)
            .values(home_w2_team_id=None, away_w2_team_id=None)
        )

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert report["appended"] == 0
    assert report["refusal_codes"] == {"AH_SETTLEMENT_TEAM_MAPPING_MISSING": 1}
    assert _fact_count(natural) == 0


# --- 3b: a broken evidence chain is fail-closed, and it is not a quiet pass --
def _assert_integrity_refusal(engine: Engine, report: dict[str, Any], code: str) -> None:
    """Every integrity refusal: no fact, a named refusal, and no clean pass.

    The last part is the point. "No pre-kickoff quote bucket" is a statement
    about Tuesday; "the result cites a capture it did not read from" is a defect.
    Only the second kind may degrade the run, and it must.
    """
    assert report["appended"] == 0, report
    assert report["idempotent_no_ops"] == 0, report
    assert report["refusal_codes"] == {code: 1}, report
    assert report["fixtures"][0]["status"] == "REFUSED"
    assert report["fixtures"][0]["refusal_code"] == code
    assert _fact_count(engine) == 0
    assert report["status"] == STATUS_INCOMPLETE, report
    assert runtime_ah_fact_writer_status(report) == "PARTIAL"
    assert not writer_status_is_clean(report)


def test_a_result_whose_payload_hash_disagrees_with_its_capture_is_refused(
    natural: Engine,
) -> None:
    """The result and the capture must be the same payload, byte for byte."""
    with Session(natural) as session, session.begin():
        session.execute(
            update(ResultModel)
            .where(ResultModel.fixture_id == FACT_FIXTURE_ID)
            .values(source_payload_sha256=_hex("a-different-payload"))
        )

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    _assert_integrity_refusal(natural, report, REFUSAL_RESULT_PAYLOAD_HASH_MISMATCH)


def test_a_capture_that_names_another_fixture_is_refused(natural: Engine) -> None:
    """A capture that does name a fixture must name *this* one."""
    with Session(natural) as session, session.begin():
        session.execute(
            update(MatchdayEndpointCaptureModel)
            .where(
                MatchdayEndpointCaptureModel.capture_id
                == str(SAMPLE_CAPTURE["capture_id"])
            )
            .values(fixture_id="api_football:999999999")
        )

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    _assert_integrity_refusal(natural, report, REFUSAL_CAPTURE_FIXTURE_MISMATCH)


def test_a_capture_with_no_fixture_attribution_at_all_is_refused(
    natural: Engine,
) -> None:
    """No fixture named and no payload to prove it: nothing owns this evidence.

    This is the production shape with the payload missing -- a bulk capture whose
    stored payload has gone. Ownership is then unprovable, and unprovable means
    no fact.
    """
    with Session(natural) as session, session.begin():
        session.execute(
            sa_delete(RawPayloadModel).where(
                RawPayloadModel.sha256 == str(SAMPLE_CAPTURE["raw_payload_sha256"])
            )
        )

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    _assert_integrity_refusal(natural, report, REFUSAL_CAPTURE_OWNERSHIP_UNPROVEN)


def test_a_capture_whose_payload_omits_the_fixture_is_refused(
    natural: Engine,
) -> None:
    """A payload that exists but does not carry this fixture proves nothing."""
    with Session(natural) as session, session.begin():
        session.execute(
            update(RawPayloadModel)
            .where(RawPayloadModel.sha256 == str(SAMPLE_CAPTURE["raw_payload_sha256"]))
            .values(payload={"response": [{"fixture": {"id": 999999999}}]})
        )

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    _assert_integrity_refusal(natural, report, REFUSAL_CAPTURE_OWNERSHIP_UNPROVEN)


# --- 3c: one fixture, one fact -------------------------------------------
def _alternative_settlement_capture() -> tuple[str, str]:
    return _hex("alternative-settlement-capture")[:64], _hex("alternative-payload")


def _seed_alternative_terminal_evidence(engine: Engine) -> str:
    """A second, legitimate terminal capture for the same fixture.

    Nothing about it is invalid -- successful `fixtures` capture, after kickoff,
    payload proves the fixture. It is simply *different* evidence for a match
    that already has a fact, which is exactly the case that must not be counted
    twice.
    """
    capture_id, payload_sha = _alternative_settlement_capture()
    with Session(engine) as session, session.begin():
        session.add(
            MatchdayEndpointCaptureModel(
                capture_id=capture_id,
                fixture_id=None,
                competition_id=str(SAMPLE_FIXTURE["competition_id"]),
                checkpoint="POSTMATCH_RESULT",
                endpoint="fixtures",
                sanitized_params={"fixture": FACT_PROVIDER_FIXTURE_ID},
                params_hash=_hex("alternative-settlement-params"),
                request_task_key="f1r-c-natural-writer",
                attempt=1,
                requested_at=_utc(SAMPLE_FIXTURE["kickoff_utc"]),
                provider_captured_at=_utc(SAMPLE_CAPTURE["provider_captured_at"]),
                status_code=200,
                elapsed_ms=1,
                response_count=1,
                quota_values={},
                raw_payload_sha256=payload_sha,
                provider_event_time=None,
                capture_status="CAPTURED",
                error_code=None,
            )
        )
        session.add(
            RawPayloadModel(
                sha256=payload_sha,
                endpoint="fixtures",
                captured_at=_utc(SAMPLE_CAPTURE["provider_captured_at"]),
                inserted_at=_utc(SAMPLE_CAPTURE["provider_captured_at"]),
                storage_uri="w2-test://fixtures",
                payload={
                    "response": [
                        {"fixture": {"id": int(FACT_PROVIDER_FIXTURE_ID)}},
                    ]
                },
            )
        )
        session.execute(
            update(ResultModel)
            .where(ResultModel.fixture_id == FACT_FIXTURE_ID)
            .values(
                source_capture_id=capture_id,
                source_payload_sha256=payload_sha,
            )
        )
    return capture_id


def test_the_same_evidence_replays_as_an_idempotent_no_op(natural: Engine) -> None:
    first = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )
    assert first["appended"] == 1
    assert first["status"] == "COMPLETE"

    replay = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert replay["appended"] == 0
    assert replay["idempotent_no_ops"] == 1
    assert replay["refusal_codes"] == {}
    assert writer_status_is_clean(replay)
    assert _fact_count(natural) == 1


def test_a_different_terminal_capture_for_one_fixture_is_refused_not_counted(
    natural: Engine,
) -> None:
    """The match must not be counted twice because the evidence was re-observed.

    The fact identity binds the settlement capture, so a second capture for the
    same fixture is a *new* row to the store -- both would be kept and F5 would
    read the match twice. The revision rule refuses it here, where the fixture is
    still known, and says which fact already holds the fixture.
    """
    first = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )
    assert first["appended"] == 1
    original_fact_id = first["fixtures"][0]["fact_id"]

    _seed_alternative_terminal_evidence(natural)

    second = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert second["appended"] == 0, second
    assert second["idempotent_no_ops"] == 0, second
    assert second["refusal_codes"] == {REFUSAL_FACT_REVISION_CONFLICT: 1}, second
    assert second["fixtures"][0]["status"] == "REFUSED"
    assert original_fact_id in str(second["fixtures"][0]["refusal_detail"])
    assert second["status"] == STATUS_INCOMPLETE
    assert runtime_ah_fact_writer_status(second) == "PARTIAL"
    assert _fact_count(natural) == 1

    from apps.worker.celery_app import _task_status

    from w2.quant_research.forward_factor_recording import empty_report as rec_report

    recording = rec_report(enabled=True, note="")
    recording["recording_status"] = "COMPLETE"
    assert _task_status(recording, ah_fact_report=second) == (
        "PASS_WITH_AH_FACT_INCOMPLETE"
    )


# --- 4: no Provider call is made, or possible ----------------------------
def test_the_natural_writer_makes_no_provider_call(
    natural: Engine, monkeypatch: Any
) -> None:
    """Every Provider entry point is armed to explode; the writer must not fire.

    Asserting `provider_calls == 0` only reads the writer's own counter. Arming
    the client instead makes the claim falsifiable: a single call anywhere under
    the writer raises and the test fails.
    """
    import w2.providers.api_football as provider

    def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the AH fact writer called the Provider")

    for name in ("ApiFootballClient",):
        monkeypatch.setattr(provider, name, explode)

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert report["status"] == "COMPLETE", report
    assert report["appended"] == 1
    assert report["provider_calls"] == 0


def test_the_writer_module_has_no_provider_path() -> None:
    """The writer cannot call the Provider, structurally: it imports no client."""
    source = (
        REPO / "src/w2/historical/runtime_ah_settlement_materializer.py"
    ).read_text(encoding="utf-8")
    body = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert "w2.providers" not in body
    assert "ApiFootballClient" not in body
    assert "requests" not in body


# --- 5: the natural path is a caller, and not the only one ---------------
def test_the_result_materialisation_path_calls_the_writer(natural: Engine) -> None:
    """`_materialize_outcome_results` writes the fact, from the results it wrote.

    This is the production trigger: the result materialisation succeeds, and the
    fixtures it confirmed are the ones the writer is handed.
    """
    from apps.worker.celery_app import _materialize_outcome_results

    with Session(natural) as session, session.begin():
        session.execute(
            update(MatchdayFixtureIdentityModel)
            .where(MatchdayFixtureIdentityModel.fixture_id == FACT_FIXTURE_ID)
            .values(fixture_status="FT")
        )

    result = _materialize_outcome_results((FACT_FIXTURE_ID,), f1rb.NOW)

    report = result["runtime_ah_settlement_facts"]
    assert isinstance(report, dict)
    assert report["status"] == "COMPLETE", (report, result.get("result_materialization"))
    assert report["appended"] == 1, report
    assert report["fixtures"][0]["fixture_id"] == FACT_FIXTURE_ID
    assert _fact_count(natural) == 1


def test_the_refresh_task_carries_the_fact_report_it_wrote(
    natural: Engine, monkeypatch: Any
) -> None:
    """The task that caused the write states it, instead of hiding it."""
    from apps.worker import celery_app as worker

    class Audit:
        task_id = "f1r-c-natural-task"
        key = "checkpoint-refresh:f1r-c-e2e"
        status = "COMPLETED"
        result: dict[str, Any] = {}

    def fake_run_future_refresh_task(**kwargs: Any) -> Audit:
        kwargs["materialize_results"]((FACT_FIXTURE_ID,), f1rb.NOW)
        return Audit()

    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(worker, "run_future_refresh_task", fake_run_future_refresh_task)

    result = worker.future_fixture_refresh.run(competition_id="allsvenskan")

    report = result["runtime_ah_settlement_facts"]
    assert report["status"] == "COMPLETE", report
    assert report["appended"] == 1, report
    assert report["provider_calls"] == 0
    # The result and the database are one claim, not two.
    assert _fact_count(natural) == report["appended"] == 1
    assert result["status"] == "PASS"


def test_the_recovery_path_is_not_the_only_writer() -> None:
    """Two callers, one implementation: the shared writer, called from the tree.

    The defect this closes is that the fact had exactly one caller -- the manual
    recovery service -- so nothing on the natural path could ever write one.
    """
    tree = REPO / "src"
    app_tree = REPO / "apps"
    callers: list[str] = []
    for path in sorted(
        [*tree.rglob("*.py"), *app_tree.rglob("*.py")]
    ):
        text = path.read_text(encoding="utf-8")
        if "materialize_runtime_ah_settlement_facts(" in text and path.name != (
            "runtime_ah_settlement_materializer.py"
        ):
            callers.append(str(path.relative_to(REPO)))

    assert "apps/worker/celery_app.py" in callers, callers
    assert "src/w2/factor_model/remediation.py" in callers, callers
    assert len(callers) >= 2, callers

    # And the recovery service no longer holds a private copy of the fact.
    remediation = (REPO / "src/w2/factor_model/remediation.py").read_text(
        encoding="utf-8"
    )
    assert "build_ah_settlement_fact" not in remediation
    assert "TerminalSettlementEvidence" not in remediation


# --- 6: failure visibility -----------------------------------------------
def test_a_blocked_result_materialisation_writes_no_fact(natural: Engine) -> None:
    from apps.worker.celery_app import _materialize_ah_facts_after_results

    report = _materialize_ah_facts_after_results(
        [FACT_FIXTURE_ID], result_status="BLOCKED"
    )

    assert report["status"] == STATUS_SKIPPED
    assert report["appended"] == 0
    assert report["requested_fixture_count"] == 0
    assert _fact_count(natural) == 0
    assert not writer_status_is_clean(report)


def test_a_writer_that_failed_does_not_let_the_task_report_a_clean_pass(
    natural: Engine, monkeypatch: Any
) -> None:
    """A failed fact write is visible in the result, not swallowed."""
    from apps.worker.celery_app import _task_status

    from w2.historical import runtime_ah_settlement as settlement_store

    def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("RUNTIME_AH_SETTLEMENT_FACT_CONFLICT")

    monkeypatch.setattr(
        settlement_store.RuntimeAhSettlementRepository, "append_facts", explode
    )

    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    assert report["status"] == STATUS_FAILED
    assert "RUNTIME_AH_SETTLEMENT_FACT_CONFLICT" in report["error"]
    assert report["appended"] == 0
    assert _fact_count(natural) == 0
    assert runtime_ah_fact_writer_status(report) == "FAIL"

    from w2.quant_research.forward_factor_recording import empty_report

    recording = empty_report(enabled=True, note="")
    recording["recording_status"] = "COMPLETE"
    assert _task_status(recording) == "PASS"
    assert _task_status(recording, ah_fact_report=report) == (
        "PASS_WITH_AH_FACT_INCOMPLETE"
    )


def test_a_refusal_alone_does_not_degrade_the_writer_verdict(
    natural: Engine,
) -> None:
    """A refusal is a statement about the data, and it stays visible.

    Refusing a fixture whose odds were never captured is the writer working
    correctly. Treating it as a writer failure would make every round that
    contains one unprovable fixture look broken.
    """
    report = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=["api_football:unknown-fixture"]
    )

    assert report["refused_fixture_count"] == 1
    assert report["refusal_codes"]
    assert writer_status_is_clean(report)
    assert runtime_ah_fact_writer_status(report) == "PASS"


def test_no_due_work_is_a_verdict_and_not_a_failure(natural: Engine) -> None:
    report = materialize_runtime_ah_settlement_facts(engine=natural, fixture_ids=[])

    assert report["status"] == STATUS_NO_DUE_WORK
    assert report["requested_fixture_count"] == 0
    assert writer_status_is_clean(report)
    assert merge_runtime_ah_fact_reports([])["status"] == STATUS_NO_DUE_WORK


def test_merging_reports_takes_the_worst_writer_verdict(natural: Engine) -> None:
    complete = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )
    failed = empty_report(STATUS_FAILED, error="BOOM")

    merged = merge_runtime_ah_fact_reports([complete, failed])

    assert merged["status"] == STATUS_FAILED
    assert merged["error"] == "BOOM"
    # The branch that did work keeps its counts; the verdict is the worst one.
    assert merged["appended"] == 1
    assert merged["db_writes"] == 1
    assert runtime_ah_fact_writer_status(merged) == "FAIL"


# --- 7: F5 reads the fact the natural writer wrote -----------------------
def test_f5_participates_from_a_fact_the_natural_writer_wrote(
    natural: Engine,
) -> None:
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    written = materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )
    assert written["appended"] == 1

    f1rb._run_projection(natural, recorder=ForwardFactorRecorder(natural, enabled=True))
    rows = _rows_by_factor(natural)

    f5 = rows["F5_RECENT_AH_COVER"]
    assert f5["participated"] is True, f5["factor_inputs"].get("source_record_ids")
    assert f5["factor_status"] == "PARTICIPATED"
    assert f5["signed_score"] is not None
    assert float(f5["applied_weight"]) > 0.0
    assert written["fixtures"][0]["fact_id"] in _parts(
        f5["factor_inputs"]["ah_fact_ids"]
    )


def test_f5_stays_an_absence_when_the_writer_wrote_nothing(
    natural: Engine,
) -> None:
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    assert _fact_count(natural) == 0

    f1rb._run_projection(natural, recorder=ForwardFactorRecorder(natural, enabled=True))
    f5 = _rows_by_factor(natural)["F5_RECENT_AH_COVER"]

    assert f5["participated"] is False
    assert float(f5["applied_weight"]) == 0.0
    assert f5["signed_score"] is None


# --- 8: the other three factors and the batch are untouched -------------
def test_the_fact_write_leaves_the_other_factors_verdicts_unchanged(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """F3/F6/F9 read the same sources whether or not an AH fact exists.

    Two isolated worlds, one difference: the second one has a runtime AH
    settlement fact before the projection runs. Every field of the other three
    factors' rows is compared, so "unaffected" is measured rather than asserted
    from the writer's own claim.
    """
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    other_factors = ("F3_REST_FITNESS", "F6_H2H", "F9_TRUE_XG")

    without = f1rb._fresh_database(monkeypatch)
    f1rb._seed_ingested_fixture(without, tmp_path / "without")
    f1rb._canonicalise(without)
    f1rb._run_projection(
        without, recorder=ForwardFactorRecorder(without, enabled=True)
    )
    baseline = {
        factor_id: _verdict(_rows_by_factor(without)[factor_id])
        for factor_id in other_factors
    }
    assert _fact_count(without) == 0

    with_fact = f1rb._fresh_database(monkeypatch)
    f1rb._seed_ingested_fixture(with_fact, tmp_path / "with")
    f1rb._canonicalise(with_fact)
    _seed_fact_chain(with_fact)
    written = materialize_runtime_ah_settlement_facts(
        engine=with_fact, fixture_ids=[FACT_FIXTURE_ID]
    )
    assert written["appended"] == 1
    f1rb._run_projection(
        with_fact, recorder=ForwardFactorRecorder(with_fact, enabled=True)
    )
    after = {
        factor_id: _verdict(_rows_by_factor(with_fact)[factor_id])
        for factor_id in other_factors
    }

    assert after == baseline
    # And the batch is still one attempt of exactly four rows in both worlds.
    assert _attempt_sizes(with_fact) == {4}
    assert _attempt_sizes(without) == {4}


def test_the_fact_write_leaves_the_four_factor_batch_intact(
    natural: Engine,
) -> None:
    """Writing facts must not change the shape of the recorded batch."""
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )
    recorder = ForwardFactorRecorder(natural, enabled=True)
    f1rb._run_projection(natural, recorder=recorder)

    rows = f1rb._rows(natural)
    assert len(rows) == 4
    assert {str(row["factor_id"]) for row in rows} == {
        "F3_REST_FITNESS",
        "F5_RECENT_AH_COVER",
        "F6_H2H",
        "F9_TRUE_XG",
    }
    assert _attempt_sizes(natural) == {4}
    assert recorder.summary()["rows_appended"] == 4
    assert recorder.summary()["refusal_codes"] == {}


def test_the_fact_write_touches_no_source_table(natural: Engine) -> None:
    """The writer adds facts and moves nothing it read."""
    read_only_sources = (
        "matchday_endpoint_captures",
        "matchday_fixture_identities",
        "matchday_market_observations",
        "canonical_team_match_history",
        "results",
    )
    before = f1rb._table_counts(natural)

    materialize_runtime_ah_settlement_facts(
        engine=natural, fixture_ids=[FACT_FIXTURE_ID]
    )

    after = f1rb._table_counts(natural)
    assert after["runtime_ah_settlement_facts"] == before["runtime_ah_settlement_facts"] + 1
    for name in read_only_sources:
        assert after[name] == before[name], name


# --- helpers -------------------------------------------------------------
def _hex(seed: str) -> str:
    import hashlib

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _line_text(value: Any) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f")


def _parts(value: Any) -> set[str]:
    """Read a recorded `factor_inputs` collection, in either stored shape."""
    if isinstance(value, str):
        text = value.strip().lstrip("[").rstrip("]")
        return {
            item.strip().strip("'\"")
            for item in text.split(",")
            if item.strip().strip("'\"")
        }
    return {str(item) for item in (value or [])}


def _utc(value: Any) -> datetime:
    return f1rb._utc(value)


def _future() -> datetime:
    return f1rb.NOW + timedelta(days=1)


def _history_row(
    *,
    fixture_status: str,
    kickoff: Any,
    endpoint_capture_id: str | None | object = ...,
) -> CanonicalTeamMatchHistoryModel:
    """A home-side history row for the sample fixture."""
    ids = f1rb._hex(f"natural-history:{fixture_status}:{kickoff}")
    return CanonicalTeamMatchHistoryModel(
        history_id=f"api_football:{FACT_PROVIDER_FIXTURE_ID}:home",
        fixture_id=FACT_FIXTURE_ID,
        provider="api_football",
        provider_fixture_id=FACT_PROVIDER_FIXTURE_ID,
        competition_id=str(SAMPLE_FIXTURE["competition_id"]),
        season=_world_cup_free_season(),
        kickoff_utc=_utc(kickoff),
        fixture_status=fixture_status,
        team_side="HOME",
        team_provider_id=str(SAMPLE_FIXTURE["home_team_provider_id"]),
        opponent_provider_id=str(SAMPLE_FIXTURE["away_team_provider_id"]),
        team_w2_id=f1rb.HOME_W2,
        opponent_w2_id=f1rb.AWAY_W2,
        goals_for=int(SAMPLE_FIXTURE["home_goals"]),
        goals_against=int(SAMPLE_FIXTURE["away_goals"]),
        result_identity_hash=ids,
        source_raw_hash=ids,
        endpoint_capture_id=(
            str(SAMPLE_CAPTURE["capture_id"])
            if endpoint_capture_id is ...
            else endpoint_capture_id
        ),
        captured_at=_utc(SAMPLE_CAPTURE["provider_captured_at"]),
        history_hash=ids,
        payload={},
    )


def _fact_count(engine: Engine) -> int:
    from w2.infrastructure.persistence.models import RuntimeAhSettlementFactModel

    with Session(engine) as session:
        return len(
            list(session.scalars(select(RuntimeAhSettlementFactModel.fact_id)))
        )


def _rows_by_factor(engine: Engine) -> dict[str, dict[str, Any]]:
    return f1rb._by_factor(f1rb._rows(engine))


def _verdict(row: dict[str, Any]) -> tuple[str, ...]:
    """The source-derived verdict of a recorded factor row, as text.

    Comparing this rather than one flag is what makes "unaffected" a
    measurement: a changed weight, score, evidence time, capture identity or
    consumed source set would all show up here.

    The evaluation instant is deliberately excluded. The recorder binds it to a
    real clock seam, so two runs of the same world legitimately differ there --
    and `factor_input_hash`/`factor_verdict_hash` are computed over it for the
    same reason. Including them would compare the clock, not the factors.
    """
    return tuple(
        str(row[name])
        for name in (
            "factor_id",
            "factor_version",
            "factor_status",
            "participated",
            "applied_weight",
            "signed_score",
            "evidence_time_utc",
            "source_capture_id",
            "source_capture_sha256",
            "source_version",
        )
    )


def _attempt_sizes(engine: Engine) -> set[int]:
    from collections import Counter

    return set(Counter(str(row["attempt_id"]) for row in f1rb._rows(engine)).values())
