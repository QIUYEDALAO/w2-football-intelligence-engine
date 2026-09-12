"""F1R-B end to end: a real evaluation writes four per-factor rows.

This is the acceptance test for the production wiring. It runs on PostgreSQL,
drives the real worker write-side entry (`_materialize_shadow_projection_events`,
the function `apps/worker/celery_app.py::future_fixture_refresh` calls), injects
the real `ForwardFactorRecorder`, and lets the real feature builders, the real
scoring authority and the real F1R-B source ports do the work. Nothing is
stubbed except the provider, which is the same fake the rest of this suite
already uses.

Then it reads `forward_ah_factor_observations` back, field by field.

Why PostgreSQL: the accepted store, the JSON column types and the partial unique
index all behave differently from SQLite, and the production database is
PostgreSQL. A wiring that only works on SQLite is not evidence.

Requires `W2_TEST_POSTGRES_URL`, like every other PostgreSQL test in this suite.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from apps.worker.celery_app import _materialize_shadow_projection_events
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import w2.infrastructure.persistence  # noqa: F401 - registers every table
from w2.competitions.seed import (
    apply_collection_policy_update,
    seed_competition_runtime_authority,
)
from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
    CanonicalTeamModel,
)
from w2.infrastructure.persistence.forward_factor_models import (
    ForwardAhFactorObservationModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
)
from w2.prematch.read_model_projection import ProjectionSourceEvent
from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

REPO = Path(__file__).resolve().parents[2]
HARNESS_PATH = REPO / "tests/integration/test_future_refresh_db_persistence.py"

FIXTURE_ID = "1489404"
#: The suite's fixed clock is moved to the wall clock for this file, so the
#: fixture under evaluation is an *upcoming* one. That is the shape production
#: evaluates, and it is what makes `evaluated_at_utc <= kickoff_at` a claim this
#: test can actually make. Applied to the harness below.
NOW = datetime.now(UTC).replace(second=0, microsecond=0)
HOME_W2 = "w2-team-e2e-home"
AWAY_W2 = "w2-team-e2e-away"
MEETING_KICKOFF = NOW - timedelta(days=200)
CAPTURE_LAG = timedelta(hours=3)
RECORDED_CAPTURE_PREFIX = "w2.consumed_source_set.v1:"

REQUIRED_FACTORS = (
    "F3_REST_FITNESS",
    "F5_RECENT_AH_COVER",
    "F6_H2H",
    "F9_TRUE_XG",
)
READBACK_FIELDS = (
    "factor_version",
    "source_capture_id",
    "source_capture_sha256",
    "evidence_time_utc",
    "evaluated_at_utc",
    "participated",
    "applied_weight",
    "factor_inputs",
    "factor_input_hash",
    "factor_verdict_hash",
    "observation_id",
)

_spec = importlib.util.spec_from_file_location("w2_future_refresh_harness", HARNESS_PATH)
assert _spec is not None and _spec.loader is not None
harness = importlib.util.module_from_spec(_spec)
sys.modules["w2_future_refresh_harness"] = harness
_spec.loader.exec_module(harness)
# The harness seeds the fixture, its checkpoint plan and its captures relative
# to its own clock. Move that clock to now so the fixture is upcoming.
harness.NOW = NOW


def _hex(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _postgres_url() -> str:
    url = (os.environ.get("W2_TEST_POSTGRES_URL") or "").strip()
    if not url:
        pytest.skip("W2_TEST_POSTGRES_URL is required for the F1R-B end-to-end test")
    return url


def _fresh_database(monkeypatch: Any) -> Engine:
    """An isolated database per test, so nothing survives a run."""
    admin_url = _postgres_url()
    name = f"w2_f1rb_{uuid.uuid4().hex[:12]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    test_url = admin_url.rsplit("/", 1)[0] + f"/{name}"
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    monkeypatch.setenv("W2_DATABASE_URL", test_url)
    monkeypatch.setenv("W2_FUTURE_REFRESH_PERSISTENCE", "db")
    get_settings.cache_clear()
    engine = create_engine(test_url)
    Base.metadata.create_all(engine)
    return engine


def _seed_ingested_fixture(engine: Engine, tmp_path: Path) -> None:
    """Run the real ingestion flow so the fixture has real captured data.

    The competition runtime authority is seeded here exactly the way the rest of
    this suite seeds it; the database stays the PostgreSQL one, so every reader
    the projection uses is the reader production uses.
    """
    seed_competition_runtime_authority(engine, environment="test", now=NOW)
    apply_collection_policy_update(engine, updated_by="f1r-b-e2e", now=NOW)
    audit = harness.run_direct_checkpoint(
        tmp_path,
        harness.FakeApiFootballClient(),
        harness.claimed_odds_checkpoint(with_identity=True),
    )
    assert audit.status in {"COMPLETED", "PASS"}, audit.result


def _canonicalise(engine: Engine) -> None:
    """Give the fixture canonical identities and canonical history.

    Production reaches `canonical_team_match_history` whenever a fixture's team
    identity is resolved, which is the branch the F1R-B source ports can serve.
    The ingestion flow above leaves `home_w2_team_id`/`away_w2_team_id` null, so
    the identity is resolved here the way the identity crosswalk would.
    """
    with Session(engine) as session, session.begin():
        for team_id, name in (
            (HOME_W2, "E2E Home"),
            (AWAY_W2, "E2E Away"),
            ("w2-opponent-a", "E2E Opponent A"),
            ("w2-opponent-b", "E2E Opponent B"),
        ):
            session.add(
                CanonicalTeamModel(
                    w2_team_id=team_id,
                    display_name=name,
                    country="SE",
                    active_status="ACTIVE",
                    created_at=NOW - timedelta(days=400),
                    identity_hash=_hex(f"team:{team_id}"),
                    payload={},
                )
            )
        session.execute(
            update(MatchdayFixtureIdentityModel)
            .where(MatchdayFixtureIdentityModel.fixture_id == f"api_football:{FIXTURE_ID}")
            .values(
                home_w2_team_id=HOME_W2,
                away_w2_team_id=AWAY_W2,
                team_identity_status="RESOLVED",
            )
        )
        plan = (
            ("9000003", HOME_W2, "w2-opponent-a", NOW - timedelta(days=3), 2, 1),
            ("9000010", HOME_W2, "w2-opponent-b", NOW - timedelta(days=10), 2, 1),
            ("9000004", AWAY_W2, "w2-opponent-a", NOW - timedelta(days=4), 1, 1),
            ("9000011", AWAY_W2, "w2-opponent-b", NOW - timedelta(days=11), 1, 1),
            # The meeting between the two sides, with the capture that carried
            # its result. F6 reads the capture's provider time, never the row
            # clock.
            ("9000200", HOME_W2, AWAY_W2, MEETING_KICKOFF, 2, 0),
        )
        for provider_fixture_id, _team_id, _opponent, kickoff, _gf, _ga in plan:
            _capture_row(session, provider_fixture_id=provider_fixture_id, kickoff=kickoff)
        # The capture rows carry the foreign key the history rows point at, so
        # they have to exist first.
        session.flush()
        for provider_fixture_id, team_id, opponent, kickoff, goals_for, goals_against in plan:
            _history_row(
                session,
                provider_fixture_id=provider_fixture_id,
                team_id=team_id,
                opponent=opponent,
                kickoff=kickoff,
                goals_for=goals_for,
                goals_against=goals_against,
            )


def _capture_id(*, provider_fixture_id: str) -> str:
    return _hex(f"capture:{provider_fixture_id}")[:64]


def _capture_row(session: Session, *, provider_fixture_id: str, kickoff: datetime) -> None:
    session.add(
        MatchdayEndpointCaptureModel(
            capture_id=_capture_id(provider_fixture_id=provider_fixture_id),
            fixture_id=f"api_football:{provider_fixture_id}",
            competition_id="allsvenskan",
            checkpoint="T168_OPEN_ODDS",
            endpoint="fixtures",
            sanitized_params={"fixture": provider_fixture_id},
            params_hash=_hex(f"params:{provider_fixture_id}"),
            request_task_key=f"f1r-b-e2e:{provider_fixture_id}",
            attempt=1,
            requested_at=kickoff,
            provider_captured_at=kickoff + CAPTURE_LAG,
            status_code=200,
            elapsed_ms=1,
            response_count=1,
            quota_values={},
            raw_payload_sha256=_hex(f"raw:{provider_fixture_id}"),
            provider_event_time=None,
            capture_status="CAPTURED",
            error_code=None,
        )
    )


def _history_row(
    session: Session,
    *,
    provider_fixture_id: str,
    team_id: str,
    opponent: str,
    kickoff: datetime,
    goals_for: int,
    goals_against: int,
) -> None:
    history_id = f"api_football:{provider_fixture_id}:{team_id}"
    session.add(
        CanonicalTeamMatchHistoryModel(
            history_id=history_id,
            fixture_id=f"api_football:{provider_fixture_id}",
            provider="api_football",
            provider_fixture_id=provider_fixture_id,
            competition_id="allsvenskan",
            season="2026",
            kickoff_utc=kickoff,
            fixture_status="FT",
            team_side="HOME" if team_id == HOME_W2 else "AWAY",
            team_provider_id=f"p-{team_id}",
            opponent_provider_id=f"p-{opponent}",
            team_w2_id=team_id,
            opponent_w2_id=opponent,
            goals_for=goals_for,
            goals_against=goals_against,
            result_identity_hash=_hex(f"result:{history_id}"),
            source_raw_hash=_hex(f"raw:{provider_fixture_id}"),
            endpoint_capture_id=_capture_id(provider_fixture_id=provider_fixture_id),
            captured_at=kickoff + timedelta(minutes=30),
            history_hash=_hex(f"history:{history_id}"),
            payload={},
        )
    )


def _run_projection(engine: Engine, *, recorder: ForwardFactorRecorder | None) -> list[str]:
    """The real worker write-side entry, with the real recorder injected."""
    event = ProjectionSourceEvent.create(
        fixture_id=FIXTURE_ID,
        event_type="ODDS_CHANGED",
        event_id=f"f1r-b-e2e:{FIXTURE_ID}",
        event_at=NOW,
        payload={"fixture_id": FIXTURE_ID, "source": "f1r-b-e2e"},
    )
    return _materialize_shadow_projection_events(
        [event], forward_factor_recorder=recorder
    )


def _rows(engine: Engine) -> list[dict[str, Any]]:
    with Session(engine) as session:
        models = list(
            session.scalars(
                select(ForwardAhFactorObservationModel).order_by(
                    ForwardAhFactorObservationModel.factor_id
                )
            )
        )
    rows: list[dict[str, Any]] = []
    for model in models:
        row = {
            name: getattr(model, name)
            for name in (
                "observation_id",
                "schema_version",
                "record_kind",
                "evaluation_id",
                "attempt_id",
                "fixture_id",
                "market",
                "factor_id",
                "factor_version",
                "factor_status",
                "participated",
                "applied_weight",
                "signed_score",
                "factor_inputs",
                "source_capture_id",
                "source_capture_sha256",
                "source_version",
                "factor_input_hash",
                "factor_verdict_hash",
                "supersedes_observation_id",
                "revision_reason",
                "evidence_time_utc",
                "evaluated_at_utc",
                "created_at_utc",
            )
        }
        rows.append(row)
    return rows


def _by_factor(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["factor_id"]): row for row in rows}


def _utc(value: Any) -> datetime:
    """A stored instant, whichever form the reader handed back.

    PostgreSQL returns aware datetimes for `DateTime(timezone=True)`; the row's
    own `factor_inputs` audit fields are ISO text because that is what the
    recorder wrote. Both are the same instant and both are compared as one.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    assert isinstance(value, str), value
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@pytest.fixture
def e2e(monkeypatch: Any, tmp_path: Path) -> Engine:
    engine = _fresh_database(monkeypatch)
    _seed_ingested_fixture(engine, tmp_path)
    _canonicalise(engine)
    return engine


# --- 1: one evaluation, four rows ----------------------------------------
def test_one_production_evaluation_writes_four_factor_rows(e2e: Engine) -> None:
    recorder = ForwardFactorRecorder(e2e, enabled=True)

    materialized = _run_projection(e2e, recorder=recorder)

    assert materialized == [FIXTURE_ID]
    # The projection evaluates the card twice for one event -- once for the
    # artifact and once for the read-time reference -- so the recorder is called
    # twice for the same evaluated attempt. The first call writes the four rows;
    # the second is the once-per-attempt no-op. Without that rule the second
    # call would have written a second row set, because its evaluation instant
    # is later than the first's.
    assert recorder.summary()["status_counts"] == {
        "RECORDED": 1,
        "IDEMPOTENT_NO_OP": 1,
    }
    assert recorder.summary()["rows_appended"] == 4
    rows = _rows(e2e)
    assert sorted(str(row["factor_id"]) for row in rows) == sorted(REQUIRED_FACTORS)
    assert {str(row["fixture_id"]) for row in rows} == {FIXTURE_ID}
    assert {str(row["market"]) for row in rows} == {"ASIAN_HANDICAP"}
    assert len({str(row["attempt_id"]) for row in rows}) == 1


def test_every_field_the_order_names_is_readable(e2e: Engine) -> None:
    _run_projection(e2e, recorder=ForwardFactorRecorder(e2e, enabled=True))

    rows = _by_factor(_rows(e2e))
    assert sorted(rows) == sorted(REQUIRED_FACTORS)
    for factor_id, row in rows.items():
        for name in READBACK_FIELDS:
            value = row[name]
            assert value is not None and value != "", f"{factor_id}.{name}"
        assert len(str(row["source_capture_sha256"])) == 64
        assert len(str(row["factor_input_hash"])) == 64
        assert len(str(row["factor_verdict_hash"])) == 64
        assert len(str(row["observation_id"])) == 64
        # The capture identity of the source set each factor consumed, not a
        # placeholder: prefix plus the digest of that set.
        capture_id = str(row["source_capture_id"])
        assert capture_id.startswith(RECORDED_CAPTURE_PREFIX), capture_id
        assert len(capture_id) == len(RECORDED_CAPTURE_PREFIX) + 64
        assert isinstance(row["factor_inputs"], dict)


def test_the_readback_revalidates_against_the_frozen_contract(e2e: Engine) -> None:
    from w2.quant_research.forward_factor_modules import load_modules

    modules = load_modules()
    contract = modules.contract
    _run_projection(e2e, recorder=ForwardFactorRecorder(e2e, enabled=True))

    # Read back through the accepted store, which is how any reader gets the
    # rows -- with the canonical text form the identity was computed over.
    stored = modules.store.ForwardFactorObservationStore(e2e).by_id()
    assert len(stored) == 4
    for row in stored.values():
        sealed = contract.validate(
            contract.ForwardFactorObservation(
                **{
                    key: row[key]
                    for key in contract.ForwardFactorObservation.__dataclass_fields__
                }
            )
        )
        # The stored identity is the identity the contract recomputes from the
        # stored fields -- so a readback cannot disagree with the record.
        assert sealed.observation_id == row["observation_id"]
        assert sealed.factor_input_hash == row["factor_input_hash"]
        assert sealed.factor_verdict_hash == row["factor_verdict_hash"]


def test_point_in_time_ordering_holds_on_every_row(e2e: Engine) -> None:
    _run_projection(e2e, recorder=ForwardFactorRecorder(e2e, enabled=True))

    kickoff = None
    with Session(e2e) as session:
        identity = session.get(MatchdayFixtureIdentityModel, f"api_football:{FIXTURE_ID}")
        assert identity is not None
        kickoff = _utc(identity.kickoff_utc)
    assert kickoff is not None
    cutoff = None
    for row in _rows(e2e):
        evidence = _utc(row["evidence_time_utc"])
        evaluated = _utc(row["evaluated_at_utc"])
        created = _utc(row["created_at_utc"])
        # Strictly earlier: the contract refuses an equal instant, which is why
        # the recording carries the cutoff and the evaluation instant apart.
        assert evidence < evaluated, row["factor_id"]
        # The fixture is upcoming, so the evaluation happened before kickoff --
        # the production shape this test reproduces.
        assert evaluated <= kickoff, row["factor_id"]
        assert created >= evaluated, row["factor_id"]
        # The cutoff the batch read from is the evaluation's own information
        # cutoff, and it is at or before kickoff by construction.
        assert _utc(row["factor_inputs"]["information_cutoff"]) <= kickoff
        cutoff = _utc(row["factor_inputs"]["information_cutoff"])
    assert cutoff is not None


def test_the_weights_are_the_scoring_authoritys_and_the_scores_the_builders(
    e2e: Engine,
) -> None:
    """The batch's weights are what `team_score` summed, not what a builder claimed.

    The claim is enforced rather than asserted: the accepted recorder refuses a
    batch whose applied weights do not sum to `weight_sum_used`, and refuses a
    participated factor whose applied weight is not the authority's. A recorded
    batch is therefore a proof that those two agreed -- and the row keeps the
    builder's own declaration beside the applied value for audit.
    """
    recorder = ForwardFactorRecorder(e2e, enabled=True)
    _run_projection(e2e, recorder=recorder)

    assert recorder.summary()["refusal_codes"] == {}
    rows = _by_factor(_rows(e2e))
    applied = 0.0
    declared = 0.0
    for factor_id, row in rows.items():
        if row["participated"]:
            assert row["signed_score"] is not None, factor_id
            assert row["factor_inputs"]["weight_entered_weight_sum_used"] == "true"
            assert row["factor_inputs"]["scoring_authority_share"] is not None
            applied += float(row["applied_weight"])
            declared += float(row["factor_inputs"]["declared_weight"])
        else:
            assert float(row["applied_weight"]) == 0.0, factor_id
            assert row["signed_score"] is None, factor_id
            assert row["factor_inputs"]["weight_entered_weight_sum_used"] == "false"
            assert row["factor_inputs"]["scoring_authority_share"] is None
    assert applied == pytest.approx(declared)


# --- 2: replay ------------------------------------------------------------
def test_replaying_the_same_worker_evaluation_adds_no_rows(e2e: Engine) -> None:
    first = ForwardFactorRecorder(e2e, enabled=True)
    _run_projection(e2e, recorder=first)
    before = _rows(e2e)
    assert len(before) == 4

    # A replay runs later, so its recording clock is later. That must not be
    # able to make the same evaluated attempt look like a new one.
    time.sleep(0.01)
    second = ForwardFactorRecorder(e2e, enabled=True)
    _run_projection(e2e, recorder=second)

    assert second.summary()["status_counts"] == {"IDEMPOTENT_NO_OP": 2}
    assert second.summary()["rows_appended"] == 0
    after = _rows(e2e)
    assert after == before
    # Same attempt, same instants, same identities: the clock moved and nothing
    # else did.
    assert {row["attempt_id"] for row in after} == {row["attempt_id"] for row in before}
    assert {row["evaluation_id"] for row in after} == {
        row["evaluation_id"] for row in before
    }
    assert {row["observation_id"] for row in after} == {
        row["observation_id"] for row in before
    }
    assert {row["evaluated_at_utc"] for row in after} == {
        row["evaluated_at_utc"] for row in before
    }


def test_a_conflicting_row_set_is_refused(e2e: Engine) -> None:
    """Re-appending the same record with different business fields is a refusal.

    Append-only means a stored row is never rewritten. The store proves it by
    refusing the batch when an observation id is presented again carrying
    different business fields, and the stored row is left exactly as it was.
    """
    from w2.quant_research.forward_factor_modules import load_modules

    modules = load_modules()
    contract = modules.contract
    _run_projection(e2e, recorder=ForwardFactorRecorder(e2e, enabled=True))
    before = _rows(e2e)
    # Read back through the accepted store, so the record is rebuilt from the
    # stored text form the identity was computed over.
    f3 = modules.store.ForwardFactorObservationStore(e2e).by_id()
    f3_row = next(
        row for row in f3.values() if row["factor_id"] == "F3_REST_FITNESS"
    )

    rebuilt = contract.ForwardFactorObservation(
        **{
            key: f3_row[key]
            for key in contract.ForwardFactorObservation.__dataclass_fields__
        }
    )
    tampered = replace(rebuilt, applied_weight="0.99")

    with pytest.raises(contract.ContractError) as excinfo:
        modules.store.ForwardFactorObservationStore(e2e).append_batch([tampered])

    # The identity no longer recomputes from the tampered fields, so the refusal
    # is the identity check -- and nothing was written or rewritten.
    assert excinfo.value.code in {
        "IDENTITY_MISMATCH",
        "OBSERVATION_ID_BUSINESS_CONFLICT",
        "BATCH_FACTOR_SET_INVALID",
    }, excinfo.value.code
    assert _rows(e2e) == before


# --- 3: F5 stays fail-closed ---------------------------------------------
def test_f5_is_recorded_as_an_absence_with_zero_weight(e2e: Engine) -> None:
    _run_projection(e2e, recorder=ForwardFactorRecorder(e2e, enabled=True))

    f5 = _by_factor(_rows(e2e))["F5_RECENT_AH_COVER"]
    assert f5["participated"] is False
    assert float(f5["applied_weight"]) == 0.0
    assert f5["signed_score"] is None
    assert f5["factor_status"] in {"INSUFFICIENT_DATA", "SOURCE_UNAVAILABLE"}
    assert f5["factor_inputs"]["evidence_time_semantics"] == "SOURCE_QUERIED_AT_AS_OF"
    # Its evidence is the lookup cutoff -- an honest statement of when we looked
    # -- and never the kickoff or a quote capture time.
    identity_kickoff = None
    with Session(e2e) as session:
        identity = session.get(MatchdayFixtureIdentityModel, f"api_football:{FIXTURE_ID}")
        assert identity is not None
        identity_kickoff = _utc(identity.kickoff_utc)
    assert _utc(f5["evidence_time_utc"]) != identity_kickoff
    assert _utc(f5["evidence_time_utc"]) == _utc(f5["factor_inputs"]["information_cutoff"])
    assert f5["factor_inputs"]["source_observed_time_semantics"] == "SOURCE_QUERIED_AT_AS_OF"
    # F5's own port refuses to serve a source time at all; that refusal is the
    # recorded reason, in the port's own words.
    assert "F5_AH_FACT_SOURCE_TIME_UNPROVABLE" in f5["factor_inputs"]["source_record_ids"]


# --- 4: failure visibility ------------------------------------------------
def test_the_task_result_reports_recording_and_not_only_pass(e2e: Engine) -> None:
    from apps.worker.celery_app import _project_and_record_factors, _task_status

    event = ProjectionSourceEvent.create(
        fixture_id=FIXTURE_ID,
        event_type="ODDS_CHANGED",
        event_id=f"f1r-b-report:{FIXTURE_ID}",
        event_at=NOW,
        payload={"fixture_id": FIXTURE_ID, "source": "f1r-b-e2e"},
    )

    materialized, report = _project_and_record_factors([event])

    assert materialized == [FIXTURE_ID]
    assert report["schema_version"] == "w2.forward_factor_production_recording.v1"
    assert report["enabled"] is True
    assert report["recording_status"] == "COMPLETE"
    assert report["recording_incomplete"] is False
    assert report["evaluations"] == 2
    assert report["rows_appended"] == 4
    assert report["status_counts"] == {"RECORDED": 1, "IDEMPOTENT_NO_OP": 1}
    assert report["refusal_codes"] == {}
    assert "note" not in report
    assert _task_status(report) == "PASS"


def test_a_refused_recording_does_not_report_a_clean_pass(e2e: Engine) -> None:
    """A card that is still returned must not hide a recording that failed.

    The h2h capture is marked failed, which is a real production refusal: the
    F6 source cannot prove an observed time, so the whole batch is refused and
    no factor row may be written. The evaluation card is still returned -- that
    is the deliberate decision -- so the task result is the only place the
    failure can appear, and it has to appear there.
    """
    from apps.worker.celery_app import _project_and_record_factors, _task_status

    with Session(e2e) as session, session.begin():
        session.execute(
            update(MatchdayEndpointCaptureModel)
            .where(MatchdayEndpointCaptureModel.capture_id == _capture_id(
                provider_fixture_id="9000200"))
            .values(capture_status="FAILED")
        )
    event = ProjectionSourceEvent.create(
        fixture_id=FIXTURE_ID,
        event_type="ODDS_CHANGED",
        event_id=f"f1r-b-refused:{FIXTURE_ID}",
        event_at=NOW,
        payload={"fixture_id": FIXTURE_ID, "source": "f1r-b-e2e"},
    )

    materialized, report = _project_and_record_factors([event])

    assert materialized == [FIXTURE_ID], "the evaluation card was not returned"
    assert _rows(e2e) == [], "a refused batch wrote rows"
    assert report["recording_status"] == "INCOMPLETE"
    assert report["recording_incomplete"] is True
    assert report["rows_appended"] == 0
    assert report["status_counts"] == {"REFUSED": 2}
    assert list(report["refusal_codes"]) == ["F6_ENDPOINT_CAPTURE_NOT_SUCCESSFUL"]
    assert _task_status(report) == "PASS_WITH_RECORDING_INCOMPLETE"


def test_a_missing_module_set_is_refused_and_not_reported_as_recorded(
    e2e: Engine, monkeypatch: Any
) -> None:
    """The one thing worse than writing no rows is claiming that you did."""
    from apps.worker.celery_app import _project_and_record_factors, _task_status

    import w2.quant_research.forward_factor_modules as modules
    import w2.quant_research.forward_factor_recording as recording

    def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        raise modules.ForwardFactorModulesNotFound(
            "FORWARD_FACTOR_MODULES_NOT_FOUND:package=/:checkout=/"
        )

    # The recorder resolves the modules through its own module global, so that
    # is the name a missing module set has to be injected through.
    monkeypatch.setattr(recording, "load_modules", unavailable)
    event = ProjectionSourceEvent.create(
        fixture_id=FIXTURE_ID,
        event_type="ODDS_CHANGED",
        event_id=f"f1r-b-missing:{FIXTURE_ID}",
        event_at=NOW,
        payload={"fixture_id": FIXTURE_ID, "source": "f1r-b-e2e"},
    )

    materialized, report = _project_and_record_factors([event])

    # The evaluation still happens -- a recording failure must not become an
    # outage -- but the factor table stays empty and the result says so.
    assert materialized == [FIXTURE_ID]
    assert _rows(e2e) == []
    assert report["recording_status"] == "INCOMPLETE"
    assert report["rows_appended"] == 0
    assert report["refusal_codes"] == {"ForwardFactorModulesNotFound": 2}
    assert _task_status(report) == "PASS_WITH_RECORDING_INCOMPLETE"


def test_a_recorder_that_cannot_be_built_is_reported_as_unavailable(
    e2e: Engine, monkeypatch: Any
) -> None:
    from apps.worker.celery_app import _project_and_record_factors, _task_status

    import w2.quant_research.forward_factor_recording as recording

    def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("DATABASE_UNAVAILABLE")

    monkeypatch.setattr(recording, "build_recorder", explode)
    event = ProjectionSourceEvent.create(
        fixture_id=FIXTURE_ID,
        event_type="ODDS_CHANGED",
        event_id=f"f1r-b-nobuild:{FIXTURE_ID}",
        event_at=NOW,
        payload={"fixture_id": FIXTURE_ID, "source": "f1r-b-e2e"},
    )

    materialized, report = _project_and_record_factors([event])

    assert materialized == [FIXTURE_ID]
    assert _rows(e2e) == []
    assert report["recording_status"] == "UNAVAILABLE"
    assert report["enabled"] is True
    assert report["rows_appended"] == 0
    assert report["note"] == "RECORDER_UNAVAILABLE"
    assert _task_status(report) == "PASS_WITH_RECORDING_INCOMPLETE"


def test_the_switch_off_is_reported_as_a_decision_not_a_failure(
    e2e: Engine, monkeypatch: Any
) -> None:
    from apps.worker.celery_app import _project_and_record_factors, _task_status

    monkeypatch.setenv("W2_FORWARD_FACTOR_RECORDING", "off")
    event = ProjectionSourceEvent.create(
        fixture_id=FIXTURE_ID,
        event_type="ODDS_CHANGED",
        event_id=f"f1r-b-disabled:{FIXTURE_ID}",
        event_at=NOW,
        payload={"fixture_id": FIXTURE_ID, "source": "f1r-b-e2e"},
    )

    materialized, report = _project_and_record_factors([event])

    assert materialized == [FIXTURE_ID]
    assert _rows(e2e) == []
    assert report["enabled"] is False
    assert report["recording_status"] == "DISABLED"
    assert report["rows_appended"] == 0
    assert report["note"] == "DISABLED"
    # Switching the recording off is an explicit decision, so the evaluation is
    # still a clean pass -- the report is where the decision is accounted for.
    assert _task_status(report) == "PASS"


def test_the_recording_only_adds_rows_to_the_factor_table(e2e: Engine) -> None:
    """The recording reads its sources and writes one table, and nothing else.

    The projection writes its own artifacts, so the claim is made about the
    tables the recording touches: the sources it reads must come out unchanged,
    and the factor table must gain exactly the four rows.
    """
    read_only_sources = (
        "canonical_team_match_history",
        "matchday_endpoint_captures",
        "matchday_fixture_identities",
        "matchday_market_observations",
    )
    before = _table_counts(e2e)
    assert before["forward_ah_factor_observations"] == 0

    _run_projection(e2e, recorder=ForwardFactorRecorder(e2e, enabled=True))

    after = _table_counts(e2e)
    assert after["forward_ah_factor_observations"] == 4
    for name in read_only_sources:
        assert after[name] == before[name], name


# --- 5: the refresh task result carries what the run actually recorded -----
def _projection_event(*, tag: str) -> ProjectionSourceEvent:
    return ProjectionSourceEvent.create(
        fixture_id=FIXTURE_ID,
        event_type="ODDS_CHANGED",
        event_id=f"f1r-b-refresh:{tag}",
        event_at=NOW,
        payload={"fixture_id": FIXTURE_ID, "source": "f1r-b-refresh"},
    )


def _run_refresh_task(
    monkeypatch: Any, *, tag: str
) -> tuple[dict[str, Any], list[list[str]]]:
    """Run the real celery task, stubbing only the provider-facing entrypoint.

    `run_future_refresh_task` is the one collaborator that would call the
    provider, so it is replaced by a stub that invokes whatever the task passed
    as `materialize_public_artifacts`. That is the point of the test: the
    materializer under test is the task's own, running the real recorder against
    the real database with the real feature builders.
    """
    from apps.worker import celery_app as worker

    materialized: list[list[str]] = []

    class Audit:
        task_id = "f1r-b-refresh-task"
        key = "checkpoint-refresh:f1r-b-e2e"
        status = "COMPLETED"
        result: dict[str, Any] = {}

    def fake_run_future_refresh_task(**kwargs: Any) -> Audit:
        materializer = kwargs["materialize_public_artifacts"]
        materialized.append(materializer([_projection_event(tag=tag)]))
        return Audit()

    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(worker, "run_future_refresh_task", fake_run_future_refresh_task)
    return worker.future_fixture_refresh.run(competition_id="allsvenskan"), materialized


def test_the_refresh_task_result_carries_the_recording_it_wrote(
    e2e: Engine, monkeypatch: Any
) -> None:
    """A task that wrote rows must not report that it wrote none.

    The callback contract is `list[str]`, so the report the write-side projector
    produced was built and dropped: the task that wrote four factor rows still
    reported `rows_appended=0`. This drives the real task and holds its own
    report against the table.
    """
    result, materialized = _run_refresh_task(monkeypatch, tag="carries")

    rows = _rows(e2e)
    report = result["forward_factor_recording"]
    assert materialized == [[FIXTURE_ID]]
    assert len(rows) == 4
    # The result and the database are one claim, not two.
    assert report["rows_appended"] == len(rows) == 4
    # One dynamic evaluation reaches the recorder twice -- once for the artifact
    # and once for the read-time reference -- so one pass records and the second
    # is the in-run replay.
    assert report["evaluations"] == 2
    assert report["status_counts"] == {"RECORDED": 1, "IDEMPOTENT_NO_OP": 1}
    assert report["rows_idempotent_no_ops"] == 4
    assert report["enabled"] is True
    assert report["refusal_codes"] == {}
    assert report["recording_status"] == "COMPLETE"
    assert report["recording_incomplete"] is False
    assert result["status"] == "PASS"
    # The refresh audit's own verdict is still reported, under its own name.
    assert result["audit_status"] == "COMPLETED"


def test_the_refresh_task_result_keeps_every_field_it_had_before(
    e2e: Engine, monkeypatch: Any
) -> None:
    """The recording verdict is added; nothing that was already there moved."""
    result, _ = _run_refresh_task(monkeypatch, tag="shape")

    assert set(result) == {
        "task_id",
        "task_key",
        "status",
        "audit_status",
        "requested_interval_seconds",
        "effective_interval_seconds",
        "provider_refresh_min_interval_seconds",
        "checkpoint_fixture_ids",
        "refresh_checkpoints",
        "discovery_date",
        "result",
        "opportunity_write",
        "t30_capture",
        "forward_factor_recording",
        "candidate",
        "formal_recommendation",
    }
    assert result["task_id"] == "f1r-b-refresh-task"
    assert result["task_key"] == "checkpoint-refresh:f1r-b-e2e"
    assert result["result"] == {}
    assert result["checkpoint_fixture_ids"] == []
    assert result["refresh_checkpoints"] == []
    assert result["discovery_date"] is None
    assert result["candidate"] is False
    assert result["formal_recommendation"] is False
    # The opportunity branch keeps its own report, and both branches appear in
    # the merged one the task result carries.
    assert result["opportunity_write"]["forward_factor_recording"]["rows_appended"] == 0
    assert result["t30_capture"]["provider_calls"] == 0


def test_the_refresh_task_does_not_report_a_clean_pass_when_recording_fails(
    e2e: Engine, monkeypatch: Any
) -> None:
    """A missing module set is invisible unless the task result says so."""
    import w2.quant_research.forward_factor_modules as modules
    import w2.quant_research.forward_factor_recording as recording

    def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        raise modules.ForwardFactorModulesNotFound(
            "FORWARD_FACTOR_MODULES_NOT_FOUND:package=/:checkout=/"
        )

    monkeypatch.setattr(recording, "load_modules", unavailable)

    result, materialized = _run_refresh_task(monkeypatch, tag="unavailable")

    report = result["forward_factor_recording"]
    # The evaluation still ran -- a recording failure is not an outage -- but the
    # table stayed empty and the task result says the recording did not finish.
    assert materialized == [[FIXTURE_ID]]
    assert _rows(e2e) == []
    assert report["rows_appended"] == 0
    assert report["recording_status"] == "INCOMPLETE"
    assert report["recording_incomplete"] is True
    assert report["refusal_codes"]
    assert result["status"] == "PASS_WITH_RECORDING_INCOMPLETE"
    assert result["audit_status"] == "COMPLETED"


def test_the_refresh_task_reports_a_refused_batch_as_incomplete(
    e2e: Engine, monkeypatch: Any
) -> None:
    """A whole-batch refusal reaches the task result and writes nothing."""
    with Session(e2e) as session, session.begin():
        session.execute(
            update(MatchdayEndpointCaptureModel)
            .where(
                MatchdayEndpointCaptureModel.capture_id
                == _capture_id(provider_fixture_id="9000200")
            )
            .values(capture_status="FAILED")
        )

    result, _ = _run_refresh_task(monkeypatch, tag="refused")

    report = result["forward_factor_recording"]
    assert _rows(e2e) == []
    assert report["rows_appended"] == 0
    assert "F6_ENDPOINT_CAPTURE_NOT_SUCCESSFUL" in report["refusal_codes"]
    assert report["recording_status"] == "INCOMPLETE"
    assert result["status"] == "PASS_WITH_RECORDING_INCOMPLETE"


def test_the_read_only_projection_path_writes_no_factor_rows(e2e: Engine) -> None:
    """The read path shares the database and must not move the factor table.

    The API router and the dashboard build their cards through the read model
    without a recorder. This is that composition: the projection still runs and
    still returns the fixture, and no factor row appears.
    """
    materialized = _materialize_shadow_projection_events(
        [_projection_event(tag="read-only")], forward_factor_recorder=None
    )

    assert materialized == [FIXTURE_ID]
    assert _rows(e2e) == []


def _table_counts(engine: Engine) -> dict[str, int]:
    names = sorted(Base.metadata.tables)
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for name in names:
            counts[name] = int(
                connection.execute(
                    text(f'select count(*) from "{name}"')  # noqa: S608 - names from metadata
                ).scalar_one()
            )
    return counts
