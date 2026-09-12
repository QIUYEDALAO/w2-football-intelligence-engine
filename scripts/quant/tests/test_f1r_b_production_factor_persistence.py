"""F1R-B successor: a real production evaluation persists its four AH factors.

F1R-B shipped the wiring and left it unconnected, so
`forward_ah_factor_observations` stayed at zero rows and F1R-B could only be
judged PARTIAL. These tests are about the connection being real.

They drive the accepted chain end to end on a database built here: the same
`canonical_team_match_history` and `matchday_endpoint_captures` tables, the real
F1R-B read ports, the real `build_production_batch`, the real append-only store,
and `FeatureContribution` objects produced by the production factor builders
rather than hand-written. Nothing is mocked into agreeing; when a check cannot
pass, the test asserts the refusal instead.

What is deliberately *not* tested here is whether the scoring is any good. The
recorder reads the scoring authority; it does not judge it.

Numbering follows this successor commit's own matrix.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from w2.competitions.registry import CoverageProfile
from w2.features.engine import FeatureSet
from w2.features.framework import FeatureContext, FeatureStatus
from w2.features.live_factors import TeamXgSnapshot, true_xg_factor
from w2.features.team_factors import (
    TeamMatchHistory,
    h2h_factor,
    recent_ah_cover_factor,
    rest_fitness_factor,
)

REPO = Path(__file__).resolve().parents[3]
QUANT = REPO / "scripts/quant"
RECORDING_MODULE = REPO / "src/w2/quant_research/forward_factor_recording.py"
MODULES_MODULE = REPO / "src/w2/quant_research/forward_factor_modules.py"


def _load(name: str, path: Path) -> Any:  # type: ignore[no-untyped-def]
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fixtures = _load("w2_f1r_b_fixtures", QUANT / "f1r_b_fixtures.py")
integration = _load(
    "w2_f1r_b_integration", QUANT / "f1r_b_production_recording_integration.py")
store_module = _load("w2_f1r_b_observation_store", QUANT / "f1r_b_observation_store.py")
recorder_module = _load("w2_f1r_a0_offline_factor_recorder",
                        QUANT / "f1r_a0_offline_factor_recorder.py")
ports = integration.ports
contract = integration.contract

FACTORS = contract.ALLOWED_FACTOR_IDS
COVERAGE = CoverageProfile(
    xg="READY", lineups_injuries="READY", squad_value="READY",
    bookmaker_depth="READY", h2h="READY", settled_ah="READY")

HOME_HISTORY_DAYS = (3, 10, 17)
AWAY_HISTORY_DAYS = (4, 11, 18)
MEETING_DAYS = (200, 400)
XG_HOME = {"days_ago": 1, "xg_for": 1.62, "xg_against": 1.05}
XG_AWAY = {"days_ago": 2, "xg_for": 1.11, "xg_against": 1.48}

REFUSALS = (
    recorder_module.BatchError, integration.capture.CaptureIdentityError,
    ports.SourcePortError, contract.ContractError)


# --- the production-shaped inputs -----------------------------------------
def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


#: The instant the recording's clock is pinned to: one second after the
#: production-shaped evaluation instant, so the default -- the instant the
#: factor evaluation was performed -- is strictly after the information cutoff
#: the way a real recording's would be, and two runs are byte-identical.
PINNED_NOW = fixtures.EVALUATED_AT + timedelta(seconds=1)


@pytest.fixture(autouse=True)
def _pinned_clock(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import w2.quant_research.forward_factor_recording as recording

    monkeypatch.setattr(recording, "_now", lambda: PINNED_NOW)


def _history_rows() -> list[dict[str, Any]]:
    """Exactly the shape `_canonical_match_history_dict` returns."""
    rows = [
        fixtures.history_row(
            team_w2_id=fixtures.HOME_TEAM, opponent_w2_id=f"w2-opp-{n}",
            days_ago=n, goals_for=2, goals_against=1)
        for n in HOME_HISTORY_DAYS
    ] + [
        fixtures.history_row(
            team_w2_id=fixtures.AWAY_TEAM, opponent_w2_id=f"w2-opp-{n}",
            days_ago=n, goals_for=1, goals_against=1)
        for n in AWAY_HISTORY_DAYS
    ] + [
        fixtures.history_row(
            team_w2_id=fixtures.HOME_TEAM, opponent_w2_id=fixtures.AWAY_TEAM,
            days_ago=n, goals_for=2, goals_against=0)
        for n in MEETING_DAYS
    ]
    return rows


def _meeting_rows() -> list[dict[str, Any]]:
    return [
        row for row in _history_rows()
        if row["team_w2_id"] == fixtures.HOME_TEAM
        and row["opponent_w2_id"] == fixtures.AWAY_TEAM
    ]


def _xg_rows() -> list[dict[str, Any]]:
    return [
        fixtures.xg_snapshot_row(team_id=fixtures.HOME_TEAM, **XG_HOME),
        fixtures.xg_snapshot_row(team_id=fixtures.AWAY_TEAM, **XG_AWAY),
    ]


def _context() -> FeatureContext:
    return FeatureContext(
        fixture_id=fixtures.FIXTURE_ID, competition_id=fixtures.COMPETITION,
        home_team_id=fixtures.HOME_TEAM, away_team_id=fixtures.AWAY_TEAM,
        kickoff_at=fixtures.KICKOFF, as_of=fixtures.AS_OF)


def _history(row: dict[str, Any], *, source_group: str,
             source: str = "canonical_team_match_history") -> TeamMatchHistory:
    """The projection `_canonical_history_rows_to_features` performs."""
    return TeamMatchHistory(
        team_id=row["team_w2_id"], opponent_id=row["opponent_w2_id"],
        kickoff_at=_utc(row["kickoff_utc"]), goals_for=row["goals_for"],
        goals_against=row["goals_against"],
        source=source, source_group=source_group,
        is_independent_signal=True, collection_status="READY",
        result_identity_hash=row["result_identity_hash"])


def _snapshot(row: dict[str, Any]) -> TeamXgSnapshot:
    return TeamXgSnapshot(
        team_id=row["team_id"], observed_at=_utc(row["as_of_time"]),
        xg_for=row["rolling_xg_for"], xg_against=row["rolling_xg_against"],
        goals_for=round(row["rolling_goals_for"]),
        goals_against=round(row["rolling_goals_against"]))


def _feature_set(*, history_source: str = "canonical_team_match_history") -> FeatureSet:
    """Built by the production builders from the rows the database holds.

    `history_source` is the source the projection stamps on the history rows.
    Production stamps `canonical_team_match_history` when it projects the
    canonical table and something else when it falls back to provider payloads;
    the builders copy that string onto the contribution, which is how the
    recorder can tell what the factor actually read.
    """
    context = _context()
    rows = _history_rows()
    home = [_history(row, source_group="team_fixture_history", source=history_source)
            for row in rows if row["team_w2_id"] == fixtures.HOME_TEAM]
    away = [_history(row, source_group="team_fixture_history", source=history_source)
            for row in rows if row["team_w2_id"] == fixtures.AWAY_TEAM]
    meetings = [_history(row, source_group="h2h", source=history_source)
                for row in _meeting_rows()]
    snapshots = _xg_rows()
    contributions = (
        rest_fitness_factor(context=context, home_history=home, away_history=away),
        # No canonical AH fact reaches this builder in production, and the
        # fixture does not manufacture one either.
        recent_ah_cover_factor(
            context=context, profile=COVERAGE, home_history=home, away_history=away),
        h2h_factor(context=context, profile=COVERAGE, meetings=meetings),
        true_xg_factor(
            context=context, profile=COVERAGE,
            home_xg=[_snapshot(snapshots[0])], away_xg=[_snapshot(snapshots[1])]),
    )
    return FeatureSet(
        fixture_id=fixtures.FIXTURE_ID, competition_id=fixtures.COMPETITION,
        as_of=fixtures.AS_OF, contributions=contributions, status=FeatureStatus.READY)


# --- the database the recorder reads --------------------------------------
TABLE_NAMES = (
    "canonical_team_match_history",
    "matchday_endpoint_captures",
    "forward_ah_factor_observations",
)


def _engine(tmp_path: Path) -> sa.Engine:
    import w2.infrastructure.persistence  # noqa: F401
    from w2.infrastructure.database import Base

    engine = sa.create_engine(f"sqlite+pysqlite:///{tmp_path / 'persistence.db'}")
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[name] for name in TABLE_NAMES])
    return engine


def _seed(engine: sa.Engine, *, capture_overrides: dict[str, str] | None = None) -> None:
    """Insert the history rows and the captures they point at."""
    from sqlalchemy.orm import Session

    from w2.infrastructure.persistence.factor_model_models import (
        CanonicalTeamMatchHistoryModel,
    )
    from w2.infrastructure.persistence.matchday_intake_models import (
        MatchdayEndpointCaptureModel,
    )

    overrides = capture_overrides or {}
    rows = _history_rows()
    with Session(engine) as session, session.begin():
        for position, row in enumerate(rows):
            session.add(CanonicalTeamMatchHistoryModel(
                history_id=row["history_id"], fixture_id=row["fixture_id"],
                provider=row["provider"], provider_fixture_id=row["provider_fixture_id"],
                competition_id=row["competition_id"], season=row["season"],
                kickoff_utc=_utc(row["kickoff_utc"]),
                fixture_status=row["fixture_status"], team_side=row["team_side"],
                team_provider_id=row["team_provider_id"],
                opponent_provider_id=row["opponent_provider_id"],
                team_w2_id=row["team_w2_id"], opponent_w2_id=row["opponent_w2_id"],
                goals_for=row["goals_for"], goals_against=row["goals_against"],
                result_identity_hash=row["result_identity_hash"],
                source_raw_hash=row["source_raw_hash"],
                endpoint_capture_id=row["endpoint_capture_id"],
                captured_at=_utc(row["captured_at"]),
                history_hash=row["history_hash"], payload={}))
            capture = fixtures.capture_row(row)
            if capture["capture_id"] in overrides:
                capture["capture_status"] = overrides[capture["capture_id"]]
            session.add(MatchdayEndpointCaptureModel(
                capture_id=capture["capture_id"], fixture_id=row["fixture_id"],
                competition_id=row["competition_id"], checkpoint=None,
                endpoint=capture["endpoint"], sanitized_params={},
                params_hash=f"{position:064d}",
                request_task_key="f1rb-persistence-test", attempt=1,
                requested_at=_utc(row["kickoff_utc"]),
                provider_captured_at=_utc(capture["provider_captured_at"]),
                status_code=200, elapsed_ms=1, response_count=1, quota_values={},
                raw_payload_sha256=capture["raw_payload_sha256"],
                provider_event_time=None,
                capture_status=capture["capture_status"], error_code=None))


def _recorder(engine: sa.Engine) -> Any:
    from w2.quant_research.forward_factor_modules import load_modules
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    return ForwardFactorRecorder(engine, enabled=True, modules=load_modules())


def _record(engine: sa.Engine, *, feature_set: Any = None,
            context: Any = None, evaluated_at: datetime | None = None) -> dict[str, Any]:
    recorder = _recorder(engine)
    outcome = recorder.record(
        fixture_id=fixtures.FIXTURE_ID,
        feature_set=feature_set if feature_set is not None else _feature_set(),
        context=context if context is not None else _context(),
        xg_snapshots=_xg_rows(),
        evaluated_at=evaluated_at,
    )
    return {"outcome": outcome, "summary": recorder.summary()}


def _stored(engine: sa.Engine) -> dict[str, dict[str, Any]]:
    return store_module.ForwardFactorObservationStore(engine).by_id()


def _by_factor(rows: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["factor_id"]: row for row in rows.values()}


def _row_counts(engine: sa.Engine) -> dict[str, int]:
    inspector = sa.inspect(engine)
    with engine.connect() as connection:
        return {
            # The names come from the inspector, never from a caller or a file.
            name: int(connection.execute(
                sa.text(f"select count(*) from {name}")).scalar_one())  # noqa: S608
            for name in inspector.get_table_names()
        }


def _authority() -> dict[str, Any]:
    return recorder_module.scoring_authority_view(_feature_set().contributions)


def _scored_ids(feature_set: Any) -> set[str]:
    """What `team_score` actually scored, by the authority's own verdict."""
    authority = recorder_module.scoring_authority_view(feature_set.contributions)
    return {str(factor_id) for factor_id in authority["scoring_factors"]}


def _feature_set_with_ah_cover() -> FeatureSet:
    """A feature set where the canonical AH fact reached F5, so it scored.

    This is the shape production would have if a writer emitted the canonical
    AH settlement fact -- the three markers `_canonical_ah_rows` requires. No
    such writer exists, which is why F5 is normally an absence; the test exists
    so that the branch which fires if one ever appears is documented rather
    than discovered.
    """
    context = _context()
    rows = _history_rows()

    def ah_row(row: dict[str, Any]) -> TeamMatchHistory:
        return TeamMatchHistory(
            team_id=row["team_w2_id"], opponent_id=row["opponent_w2_id"],
            kickoff_at=_utc(row["kickoff_utc"]), goals_for=row["goals_for"],
            goals_against=row["goals_against"],
            source="canonical_historical_ah_fact",
            source_group="canonical_historical_ah_fact",
            is_independent_signal=True, collection_status="CANONICAL_AH_FACT",
            ah_fact_id=f"ah-fact:{row['history_id']}",
            ah_fact_hash=row["result_identity_hash"],
            settlement_outcome="WIN",
        )

    home = [ah_row(row) for row in rows if row["team_w2_id"] == fixtures.HOME_TEAM]
    away = [ah_row(row) for row in rows if row["team_w2_id"] == fixtures.AWAY_TEAM]
    snapshots = _xg_rows()
    contributions = (
        rest_fitness_factor(context=context, home_history=home, away_history=away),
        recent_ah_cover_factor(
            context=context, profile=COVERAGE, home_history=home, away_history=away),
        h2h_factor(context=context, profile=COVERAGE, meetings=[]),
        true_xg_factor(
            context=context, profile=COVERAGE,
            home_xg=[_snapshot(snapshots[0])], away_xg=[_snapshot(snapshots[1])]),
    )
    return FeatureSet(
        fixture_id=fixtures.FIXTURE_ID, competition_id=fixtures.COMPETITION,
        as_of=fixtures.AS_OF, contributions=contributions, status=FeatureStatus.READY)


# --- 1: a production evaluation writes four per-factor rows ----------------
def test_01_an_evaluation_writes_one_row_per_factor(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)

    result = _record(engine)

    assert result["outcome"]["status"] == "RECORDED", result["outcome"]
    assert result["outcome"]["batch_size"] == 4
    assert result["outcome"]["appended"] == 4
    assert sorted(row["factor_id"] for row in _stored(engine).values()) == sorted(FACTORS)


def test_01_every_row_is_re_readable_with_its_own_provenance(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)

    from w2.domain.factor_versions import factor_computation_version

    rows = _by_factor(_stored(engine))
    assert sorted(rows) == sorted(FACTORS)
    for factor_id, row in rows.items():
        assert row["factor_version"] == factor_computation_version(factor_id)
        assert row["source_capture_id"].startswith(
            integration.capture.PRODUCTION_SET_PREFIX)
        assert len(row["source_capture_sha256"]) == 64
        assert row["factor_input_hash"] and row["factor_verdict_hash"]
        assert row["observation_id"]
        assert _utc(row["evaluated_at_utc"]) > fixtures.AS_OF
        assert row["factor_status"] in contract.ALLOWED_FACTOR_STATUSES
        # The re-read rows must be exactly what the contract validates, not
        # merely what the store happened to keep.
        assert contract.validate(contract.ForwardFactorObservation(**{
            key: row[key] for key in contract.ForwardFactorObservation.__dataclass_fields__
        })).observation_id == row["observation_id"]


def test_01_the_four_evidence_semantics_survive_the_round_trip(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)

    rows = _by_factor(_stored(engine))
    # What the evidence time *is* -- the accepted recorder's rule per factor.
    assert {
        factor_id: row["factor_inputs"]["evidence_time_semantics"]
        for factor_id, row in rows.items()
    } == {
        "F3_REST_FITNESS": recorder_module.FIXTURE_EVENT_TIME,
        "F5_RECENT_AH_COVER": integration.ABSENCE_LOOKUP,
        "F6_H2H": recorder_module.RESULT_DERIVED,
        "F9_TRUE_XG": recorder_module.SOURCE_SNAPSHOT_OBSERVED_AT,
    }
    # Where the evidence time *came from* -- the F1R-B port's own semantics,
    # which is the finer claim and is kept beside the rule rather than instead
    # of it.
    assert {
        factor_id: row["factor_inputs"]["source_observed_time_semantics"]
        for factor_id, row in rows.items()
    } == {
        "F3_REST_FITNESS": ports.FIXTURE_EVENT_TIME,
        "F5_RECENT_AH_COVER": integration.ABSENCE_LOOKUP,
        "F6_H2H": ports.PROVIDER_CAPTURE_OF_FINISHED_FIXTURE,
        "F9_TRUE_XG": ports.ROLLING_SNAPSHOT_COMPONENT_AVAILABILITY,
    }


def test_01_the_rows_satisfy_point_in_time_ordering(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)

    kickoff = fixtures.KICKOFF
    for row in _stored(engine).values():
        evaluated = _utc(row["evaluated_at_utc"])
        evidence = _utc(row["evidence_time_utc"])
        created = _utc(row["created_at_utc"])
        # The information cutoff is the instant the evaluation looked, and the
        # evaluation was performed strictly after it -- equal is refused by the
        # contract, so a row that exists proves the strict order.
        assert evaluated > fixtures.AS_OF, row["factor_id"]
        assert evaluated <= kickoff, row["factor_id"]
        # Nothing may claim to have observed a fact at or after evaluation.
        assert evidence < evaluated, row["factor_id"]
        # The write instant is the one field that is allowed to be later.
        assert created >= evaluated, row["factor_id"]


def test_01_the_two_instants_and_their_semantics_are_on_every_row(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)

    for row in _stored(engine).values():
        inputs = row["factor_inputs"]
        # The cutoff the batch read from, restated per row with the field that
        # produced it, and the instant the factor evaluation ran.
        assert inputs["information_cutoff"] == fixtures.AS_OF.isoformat()
        assert inputs["information_cutoff_semantics"] == "FEATURE_CONTEXT_AS_OF"
        assert _utc(inputs["evaluation_performed_at"]) == _utc(row["evaluated_at_utc"])
        assert inputs["evaluation_performed_at_semantics"] == (
            "FACTOR_EVALUATION_PERFORMED_AT")


# --- 2: replay is an idempotent no-op --------------------------------------
def test_02_replaying_the_same_evaluation_adds_no_rows(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    first = _record(engine)
    before = _stored(engine)

    # A replay happens later, so it carries a later instant. The accepted store
    # keys idempotency on the observation id, which carries the evaluation
    # instant, so on its own it would treat this as new and append a second row
    # set for the same evaluated attempt.
    second = _record(engine, evaluated_at=PINNED_NOW + timedelta(minutes=1))

    assert first["outcome"]["appended"] == 4
    assert second["outcome"]["status"] == "IDEMPOTENT_NO_OP", second["outcome"]
    assert second["outcome"]["appended"] == 0
    assert second["outcome"]["idempotent_no_ops"] == 4
    assert _stored(engine) == before


def test_02_the_once_only_rule_does_not_depend_on_the_instant(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)
    before = _stored(engine)

    same = _record(engine)
    later = _record(engine, evaluated_at=PINNED_NOW + timedelta(hours=1))

    # Both are no-ops for the same reason: the attempt is already recorded. The
    # rule cannot be a comparison of instants -- that is exactly what a replay
    # moves -- so it is a statement about the attempt.
    assert same["outcome"]["status"] == "IDEMPOTENT_NO_OP", same["outcome"]
    assert later["outcome"]["status"] == "IDEMPOTENT_NO_OP", later["outcome"]
    assert _stored(engine) == before


def test_02_a_replay_leaves_the_attempts_first_instant_untouched(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)
    before = _stored(engine)

    _record(engine, evaluated_at=PINNED_NOW + timedelta(minutes=1))

    after = _stored(engine)
    assert after == before
    # Not a rewrite of the first recording: the instants the first recording
    # wrote are the ones that stay, and nothing was superseded or revised.
    assert {row["evaluated_at_utc"] for row in after.values()} == {
        row["evaluated_at_utc"] for row in before.values()}
    assert all(row["supersedes_observation_id"] is None for row in after.values())
    assert all(row["revision_reason"] is None for row in after.values())


def test_02_a_later_cutoff_is_a_new_attempt_and_appends_a_new_set(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)
    before = _stored(engine)

    later = _context()
    later = replace(later, as_of=later.as_of + timedelta(minutes=1))
    _record(engine, context=later)

    after = _stored(engine)
    assert len(after) == 2 * len(before)
    # Append-only: the earlier rows are untouched, not superseded in place.
    assert {key: value for key, value in after.items() if key in before} == before


def test_02_a_supplied_evaluation_instant_is_the_one_recorded(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)

    supplied = fixtures.EVALUATED_AT
    result = _record(engine, evaluated_at=supplied)

    assert result["outcome"]["status"] == "RECORDED", result["outcome"]
    for row in _stored(engine).values():
        assert _utc(row["evaluated_at_utc"]) == supplied
        assert _utc(row["factor_inputs"]["evaluation_performed_at"]) == supplied


@pytest.mark.parametrize("offset", [timedelta(0), -timedelta(minutes=1)])
def test_02_an_instant_at_or_before_the_cutoff_is_refused(tmp_path, offset) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    before = _row_counts(engine)

    result = _record(engine, evaluated_at=fixtures.AS_OF + offset)

    assert result["outcome"]["status"] == "REFUSED", result["outcome"]
    assert result["outcome"]["code"] == (
        "EVALUATION_INSTANT_NOT_AFTER_INFORMATION_CUTOFF")
    # Fail closed: the contract will not carry a batch whose evidence instant is
    # not strictly before its evaluation instant, so nothing is built and
    # nothing is written -- not a half batch, not a shifted row.
    assert _row_counts(engine) == before
    assert _stored(engine) == {}


def test_02_the_replay_key_is_the_evaluations_own_identity(tmp_path) -> None:
    from w2.quant_research.forward_factor_recording import evaluation_identity

    first = evaluation_identity(fixture_id=fixtures.FIXTURE_ID, context=_context())
    again = evaluation_identity(fixture_id=fixtures.FIXTURE_ID, context=_context())
    assert first == again
    later = _context()
    other = evaluation_identity(
        fixture_id=fixtures.FIXTURE_ID,
        context=replace(later, as_of=later.as_of + timedelta(minutes=5)))
    assert other != first


# --- 3: F5 stays fail-closed ----------------------------------------------
def test_03_f5_is_an_absence_with_zero_weight(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)

    f5 = _by_factor(_stored(engine))["F5_RECENT_AH_COVER"]
    assert f5["participated"] is False
    assert Decimal(f5["applied_weight"]) == Decimal(0)
    assert f5["signed_score"] is None
    assert f5["factor_status"] in {
        contract.INSUFFICIENT_DATA, contract.SOURCE_UNAVAILABLE}
    assert f5["factor_inputs"]["weight_entered_weight_sum_used"] == "false"


def test_03_f5s_recorded_query_identity_carries_the_ports_refusal(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)

    f5 = _by_factor(_stored(engine))["F5_RECENT_AH_COVER"]
    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.ah_fact_records([])
    assert excinfo.value.code == "F5_AH_FACT_SOURCE_TIME_UNPROVABLE"
    # The recorded reason is the port's own code, not a string this codebase
    # made up and not the kickoff.
    assert excinfo.value.code in f5["factor_inputs"]["source_record_ids"]
    assert excinfo.value.code in f5["source_capture_id"] or excinfo.value.code in (
        f5["factor_inputs"]["source_record_ids"])


def test_03_a_participating_f5_refuses_the_batch(tmp_path) -> None:
    """The one case the wiring cannot record, pinned rather than assumed.

    F5 has no provable production source-observed time, so it is only ever
    recorded as a non-participating absence with `applied_weight = 0`. If the
    scoring authority actually scored F5, that record would understate the
    weight it applied and the batch's weights would no longer sum to what
    `team_score` used -- so the batch refuses, whole, and says which factor
    caused it. This is the fail-closed branch F1R-B's own port describes.
    """
    engine = _engine(tmp_path)
    _seed(engine)
    before = _row_counts(engine)
    feature_set = _feature_set_with_ah_cover()

    result = _record(engine, feature_set=feature_set)

    assert "F5_RECENT_AH_COVER" in _scored_ids(feature_set)
    assert result["outcome"]["status"] == "REFUSED", result["outcome"]
    assert result["outcome"]["code"] == "PARTICIPATED_FACTOR_BOUND_TO_ABSENCE_LOOKUP"
    assert "F5_RECENT_AH_COVER" in result["outcome"]["detail"]
    assert _row_counts(engine) == before
    assert _stored(engine) == {}


def test_03_a_participating_factor_read_from_a_non_canonical_source_is_recorded_as_an_absence(
    tmp_path,
) -> None:
    """Rows the ports cannot serve are an absence, not an attribution.

    The F1R-B read ports serve `canonical_team_match_history` and nothing else.
    When a factor's own declaration says it read something else, binding it to
    canonical rows would record a capture identity the factor never consumed.
    It is recorded as an absence instead -- and if it was scored, that absence
    cannot carry a participated weight, so the batch refuses.
    """
    engine = _engine(tmp_path)
    _seed(engine)
    before = _row_counts(engine)
    feature_set = _feature_set(history_source="api_football_fixtures")

    result = _record(engine, feature_set=feature_set)

    assert "F3_REST_FITNESS" in _scored_ids(feature_set)
    assert result["outcome"]["status"] == "REFUSED", result["outcome"]
    assert result["outcome"]["code"] == "PARTICIPATED_FACTOR_BOUND_TO_ABSENCE_LOOKUP"
    assert "F3_REST_FITNESS" in result["outcome"]["detail"]
    assert _row_counts(engine) == before
    assert _stored(engine) == {}


def test_03_no_factor_uses_the_kickoff_as_its_evidence_time(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)

    for row in _stored(engine).values():
        assert _utc(row["evidence_time_utc"]) != fixtures.KICKOFF, row["factor_id"]


def test_03_f5_cannot_be_handed_a_source_time_at_all(tmp_path) -> None:
    """The refusal is structural: there is no argument that would satisfy it."""
    with pytest.raises(ports.SourcePortError) as excinfo:
        ports.ah_fact_records([{"kickoff_at": fixtures.KICKOFF.isoformat()}])
    assert excinfo.value.code == "F5_AH_FACT_SOURCE_TIME_UNPROVABLE"


# --- 4: tampering is refused ----------------------------------------------
def test_04_a_capture_that_did_not_succeed_refuses_the_whole_batch(tmp_path) -> None:
    engine = _engine(tmp_path)
    meetings = _meeting_rows()
    failed = {row["endpoint_capture_id"]: "FAILED" for row in meetings}
    _seed(engine, capture_overrides=failed)

    result = _record(engine)

    assert result["outcome"]["status"] == "REFUSED", result["outcome"]
    assert result["outcome"]["code"] == "F6_ENDPOINT_CAPTURE_NOT_SUCCESSFUL"
    assert _stored(engine) == {}


def test_04_a_missing_capture_refuses_the_whole_batch(tmp_path) -> None:
    from sqlalchemy.orm import Session

    from w2.infrastructure.persistence.matchday_intake_models import (
        MatchdayEndpointCaptureModel,
    )

    engine = _engine(tmp_path)
    _seed(engine)
    with Session(engine) as session, session.begin():
        for row in _meeting_rows():
            session.execute(sa.delete(MatchdayEndpointCaptureModel).where(
                MatchdayEndpointCaptureModel.capture_id == row["endpoint_capture_id"]))

    result = _record(engine)

    assert result["outcome"]["status"] == "REFUSED", result["outcome"]
    assert result["outcome"]["code"] == "F6_ENDPOINT_CAPTURE_NOT_RESOLVED"
    assert _stored(engine) == {}


def test_04_a_source_time_before_the_kickoff_refuses(tmp_path) -> None:
    from sqlalchemy.orm import Session

    from w2.infrastructure.persistence.matchday_intake_models import (
        MatchdayEndpointCaptureModel,
    )

    engine = _engine(tmp_path)
    _seed(engine)
    with Session(engine) as session, session.begin():
        for row in _meeting_rows():
            # A capture claiming to show a finished fixture before it kicked off.
            session.execute(
                sa.update(MatchdayEndpointCaptureModel)
                .where(MatchdayEndpointCaptureModel.capture_id == row["endpoint_capture_id"])
                .values(provider_captured_at=_utc(row["kickoff_utc"])))

    result = _record(engine)

    assert result["outcome"]["status"] == "REFUSED", result["outcome"]
    assert result["outcome"]["code"] == "F6_SOURCE_TIME_NOT_AFTER_KICKOFF"
    assert _stored(engine) == {}


def test_04_a_factor_version_that_is_not_the_builders_refuses(tmp_path, monkeypatch) -> None:
    import w2.quant_research.forward_factor_recording as recording

    engine = _engine(tmp_path)
    _seed(engine)

    real = recording.factor_computation_version

    def impostor(factor_id: str) -> str:
        return "v1" if factor_id == "F6_H2H" else real(factor_id)

    monkeypatch.setattr(recording, "factor_computation_version", impostor)
    result = _record(engine)

    assert result["outcome"]["status"] == "REFUSED", result["outcome"]
    assert result["outcome"]["code"] == "FACTOR_VERSION_DISAGREES_WITH_BUILDER_AUTHORITY"
    assert _stored(engine) == {}


def test_04_a_tampered_applied_weight_is_refused_by_the_store(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    result = _record(engine)
    assert result["outcome"]["status"] == "RECORDED"
    stored_before = _stored(engine)

    batch = integration.build_production_batch(
        feature_set=_feature_set(), context=_context(),
        evaluation_id=result["outcome"]["evaluation_id"],
        attempt_id=result["outcome"]["attempt_id"],
        evaluated_at_utc=fixtures.EVALUATED_AT.isoformat(),
        created_at_utc=fixtures.CREATED_AT.isoformat(),
        bindings=_recorder(engine)._bindings(  # noqa: SLF001 - the tamper is the point
            feature_set=_feature_set(), context=_context(),
            history_rows=_history_rows(), xg_snapshots=_xg_rows()))
    tampered = [
        replace(record, applied_weight=Decimal("0.99"))
        if record.factor_id == "F5_RECENT_AH_COVER" else record
        for record in batch
    ]

    with pytest.raises(REFUSALS) as excinfo:
        store_module.ForwardFactorObservationStore(engine).append_batch(tampered)

    assert excinfo.value.code == "NON_PARTICIPATING_FACTOR_CARRIES_APPLIED_WEIGHT"
    assert _stored(engine) == stored_before


def test_04_a_tampered_verdict_hash_is_refused(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    stored_before = _stored(engine)

    recorder = _recorder(engine)
    batch = integration.build_production_batch(
        feature_set=_feature_set(), context=_context(),
        evaluation_id="dqe-" + "1" * 64, attempt_id="att-" + "2" * 60,
        evaluated_at_utc=fixtures.EVALUATED_AT.isoformat(),
        created_at_utc=fixtures.CREATED_AT.isoformat(),
        bindings=recorder._bindings(  # noqa: SLF001 - the tamper is the point
            feature_set=_feature_set(), context=_context(),
            history_rows=_history_rows(), xg_snapshots=_xg_rows()))
    tampered = [
        replace(record, factor_verdict_hash="0" * 64)
        if record.factor_id == "F3_REST_FITNESS" else record
        for record in batch
    ]

    with pytest.raises(REFUSALS) as excinfo:
        store_module.ForwardFactorObservationStore(engine).append_batch(tampered)

    assert excinfo.value.code == "IDENTITY_MISMATCH"
    assert _stored(engine) == stored_before


def test_04_a_tampered_source_capture_leaves_zero_rows(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    before = _row_counts(engine)

    result = _record(engine, feature_set=_feature_set())

    # A clean run writes rows; the tampered runs above wrote none. This test is
    # the positive control for those zero-row assertions.
    assert result["outcome"]["status"] == "RECORDED"
    after = _row_counts(engine)
    assert after["forward_ah_factor_observations"] == 4
    for name in TABLE_NAMES[:-1]:
        assert after[name] == before[name], name


def test_04_a_refusal_leaves_no_half_batch(tmp_path) -> None:
    engine = _engine(tmp_path)
    failed = {row["endpoint_capture_id"]: "FAILED" for row in _meeting_rows()}
    _seed(engine, capture_overrides=failed)
    before = _row_counts(engine)

    result = _record(engine)

    assert result["outcome"]["status"] == "REFUSED"
    assert _row_counts(engine) == before
    assert result["summary"]["rows_appended"] == 0


# --- 5: the recorder reports rather than swallows -------------------------
def test_05_a_refusal_is_reported_with_its_code(tmp_path) -> None:
    engine = _engine(tmp_path)
    failed = {row["endpoint_capture_id"]: "FAILED" for row in _meeting_rows()}
    _seed(engine, capture_overrides=failed)

    result = _record(engine)

    assert result["summary"]["status_counts"] == {"REFUSED": 1}
    assert result["summary"]["refusal_codes"] == {
        "F6_ENDPOINT_CAPTURE_NOT_SUCCESSFUL": 1}
    assert result["summary"]["rows_appended"] == 0


def test_05_the_switch_can_stop_recording_without_a_redeploy(tmp_path, monkeypatch) -> None:
    import w2.quant_research.forward_factor_recording as recording
    from w2.quant_research.forward_factor_modules import load_modules

    engine = _engine(tmp_path)
    _seed(engine)
    monkeypatch.setenv(recording.RECORDING_FLAG, "off")

    # The switch is read where a recorder is constructed, so the recorder is
    # built the way the composition root builds one rather than with `enabled`
    # forced.
    recorder = recording.ForwardFactorRecorder(engine, modules=load_modules())
    outcome = recorder.record(
        fixture_id=fixtures.FIXTURE_ID, feature_set=_feature_set(),
        context=_context(), xg_snapshots=_xg_rows())

    assert outcome["status"] == "DISABLED", outcome
    assert _stored(engine) == {}


def test_05_the_switch_is_on_by_default() -> None:
    import w2.quant_research.forward_factor_recording as recording

    assert recording.recording_enabled() is True
    assert recording.RECORDING_FLAG == "W2_FORWARD_FACTOR_RECORDING"


# --- 6: scoring, admission and Provider behaviour are unchanged -----------
def test_06_the_recorded_weights_are_the_scoring_authoritys(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)

    authority = _authority()
    scored = authority["scoring_factors"]
    rows = _by_factor(_stored(engine))
    for factor_id, row in rows.items():
        if factor_id in scored:
            assert row["participated"] is True
            assert Decimal(row["applied_weight"]) == Decimal(str(scored[factor_id]["weight"]))
        else:
            assert row["participated"] is False
            assert Decimal(row["applied_weight"]) == Decimal(0)
    assert sum(Decimal(row["applied_weight"]) for row in rows.values()) == Decimal(
        str(authority["weight_sum_used"]))


def test_06_the_recorded_score_is_the_builders_score(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _record(engine)

    contributions = {item.feature_id: item for item in _feature_set().contributions}
    for row in _stored(engine).values():
        contribution = contributions[row["factor_id"]]
        if row["participated"]:
            assert Decimal(str(row["signed_score"])) == Decimal(str(contribution.score))
        else:
            assert row["signed_score"] is None


def test_06_recording_does_not_change_the_evaluation(tmp_path) -> None:
    """The recorder reads the evaluation. It cannot rewrite it."""
    engine = _engine(tmp_path)
    _seed(engine)

    feature_set = _feature_set()
    contributions_before = tuple(feature_set.contributions)
    authority_before = recorder_module.scoring_authority_view(feature_set.contributions)

    _record(engine, feature_set=feature_set)

    assert tuple(feature_set.contributions) == contributions_before
    assert recorder_module.scoring_authority_view(
        feature_set.contributions) == authority_before
    assert [item.feature_id for item in feature_set.contributions] == [
        "F3_REST_FITNESS", "F5_RECENT_AH_COVER", "F6_H2H", "F9_TRUE_XG"]


def test_06_the_recorder_writes_only_the_factor_table(tmp_path) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    before = _row_counts(engine)

    _record(engine)

    after = _row_counts(engine)
    changed = {name for name in after if after[name] != before[name]}
    assert changed == {"forward_ah_factor_observations"}
    assert after["canonical_team_match_history"] == before["canonical_team_match_history"]
    assert after["matchday_endpoint_captures"] == before["matchday_endpoint_captures"]


@pytest.mark.parametrize("module_path", [RECORDING_MODULE, MODULES_MODULE])
def test_06_no_provider_network_or_capture_activation(module_path) -> None:
    text = module_path.read_text(encoding="utf-8")
    for banned in ("requests", "httpx", "urllib.request", "socket", "paramiko",
                   "api-football", "ssh "):
        assert banned not in text, f"{module_path.name}: {banned}"
    assert "PRODUCTION_CAPTURE_ENABLED = True" not in text
    assert "send_task" not in text


def test_06_the_live_capture_port_stays_disabled() -> None:
    assert ports.PRODUCTION_CAPTURE_ENABLED is False


# --- 7: the wiring stays inside its boundary ------------------------------
def test_07_the_production_import_graph_never_imports_the_modules() -> None:
    """Nothing imports F1R-B statically; exactly one module names it at all.

    F1R-B asserted that `src/` never mentioned the wiring, because the wiring
    did not exist yet. It exists now, so the invariant becomes the one that
    still matters: the modules are reached by file path, from one module, and
    are never pulled into anyone else's import graph.
    """
    allowed = {"src/w2/quant_research/forward_factor_modules.py"}
    hits = sorted(
        path.relative_to(REPO).as_posix()
        for path in (REPO / "src").rglob("*.py")
        if "f1r_b_" in path.read_text(encoding="utf-8"))
    assert hits == sorted(allowed), hits
    text = MODULES_MODULE.read_text(encoding="utf-8")
    assert "import f1r_b_" not in text
    assert "from f1r_b_" not in text
    assert "from w2.quant_research._f1r_b" not in text
    assert "spec_from_file_location" in text


def test_07_the_recorder_is_reached_by_injection_only() -> None:
    """Read-only callers hold no recorder and therefore write nothing."""
    from w2.prematch.analysis_calculator import ReadModelService

    assert ReadModelService()._forward_factor_recorder is None  # noqa: SLF001
    source = (REPO / "apps/worker/celery_app.py").read_text(encoding="utf-8")
    # Exactly two hand-overs, both in the write-side composition root: the
    # projection passes the recorder on, and the service that reaches the
    # scored evaluation receives it.
    assert source.count("forward_factor_recorder=recorder") == 2, source.count(
        "forward_factor_recorder=recorder")
    assert "public_analysis_card_bounded" in source
    # The read-only paths must not be handed one.
    for read_only in ("src/w2/api/routers.py", "src/w2/api/repository.py"):
        text = (REPO / read_only).read_text(encoding="utf-8")
        assert "forward_factor_recorder" not in text, read_only


def test_07_the_recorder_is_called_at_the_scored_evaluation() -> None:
    """The call sits where the final contributions and the score already exist."""
    text = (REPO / "src/w2/prematch/analysis_calculator.py").read_text(encoding="utf-8")
    build = text.index("card = build_multi_market_analysis(")
    record = text.index("self._record_forward_factor_observations(")
    return_payload = text.index("return payload", record)
    assert build < record < return_payload
    for name in ("build_production_batch", "independent_team_scores_from_contributions",
                 "factor_computation_version"):
        assert name not in text, name


def test_07_no_protected_path_mentions_the_wiring() -> None:
    """The wiring reaches no Scheduler, Dashboard, V4 or strategy module.

    Asserted against the files rather than against a git diff: a diff is a
    property of one working tree, and this has to keep holding afterwards.
    """
    import w2.quant_research.forward_factor_recording as recording

    for root in ("src/w2/scheduler", "src/w2/dashboard", "src/w2/strategy"):
        for path in (REPO / root).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for banned in ("forward_factor_recorder", "quant_research",
                           "forward_ah_factor_observation"):
                assert banned not in text, f"{path.relative_to(REPO)}: {banned}"
    # V4 is reached through its own module, which the recorder never names.
    v4 = (REPO / "src/w2/domain/recommendation_decision_v4.py").read_text(encoding="utf-8")
    assert "quant_research" not in v4
    assert recording.RECORDED_MARKET == contract.AH_MARKET


def test_07_the_wiring_did_not_touch_a_forbidden_path() -> None:
    """A working-tree guard over the trees this task may not touch.

    Listed as forbidden rather than exhaustive on purpose: a whitelist would
    have to be rewritten by every later, separately authorised task.
    """
    import subprocess

    changed = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"], cwd=REPO,
        capture_output=True, text=True, check=True).stdout.splitlines()
    paths = [line[3:].strip() for line in changed if line.strip()]
    forbidden_prefixes = (
        "src/w2/scheduler/", "src/w2/dashboard/", "src/w2/strategy/",
        "src/w2/api/", "src/w2/replay/", "migrations/", "config/",
        "docs/review_packages/", "scripts/quant/f1r_",
    )
    for path in paths:
        for prefix in forbidden_prefixes:
            assert not path.startswith(prefix), path
        assert path != "src/w2/prematch/read_model_projection.py", path
        assert path != "src/w2/domain/recommendation_decision_v4.py", path
        assert path != "scripts/quant/f1p_forward_factor_contract.py", path


#: The six modules exactly as F1R-B delivered them. The successor commit reuses
#: this code, so it must not have edited it; recording the delivery digests is
#: the same discipline `factor_versions.builder_source_sha256` uses for the
#: factor builders.
F1R_B_MODULE_SHA256 = {
    "f1p_forward_factor_contract.py":
        "b43adcbb42c3642c1fad4f29a5b1568c1077c175450fd2cc4544160ebc1bb329",
    "f1r_a0_offline_factor_recorder.py":
        "3a057699f933f5f0d1a80debafbc4569f056a40743749d1afaacee743287f360",
    "f1r_b_source_capture.py":
        "f2451a14da5d442b6fc09fcf79e2ce2141aec6a0b5a19707ba3277a7f95ffea1",
    "f1r_b_production_ports.py":
        "e4f84a5010ae81121dc02e42838b8f38868b8c09a6843ad6e7296faced304df2",
    "f1r_b_production_recording_integration.py":
        "b383652b7d71adc64d3253a13deda5590e79a0421a6231e5030e65078478c02c",
    "f1r_b_observation_store.py":
        "4ab1ae874942eabfc2e721ec5c1cc3beefc27dcf541f61ed5314caef2cfb8499",
}


def test_07_the_accepted_store_is_still_reached_and_still_no_ops(tmp_path) -> None:
    """The once-only rule sits in front of an intact accepted store, not over it.

    Reaching `append_batch` directly with the same batch twice must still be the
    accepted idempotent no-op; the recorder's attempt check short-circuits
    earlier but does not replace or weaken the store's own identity check.
    """
    engine = _engine(tmp_path)
    _seed(engine)
    batch = integration.build_production_batch(
        feature_set=_feature_set(), context=_context(),
        evaluation_id="dqe-" + "1" * 64, attempt_id="att-" + "2" * 60,
        evaluated_at_utc=fixtures.EVALUATED_AT.isoformat(),
        created_at_utc=fixtures.CREATED_AT.isoformat(),
        bindings=_recorder(engine)._bindings(  # noqa: SLF001 - the point is the store
            feature_set=_feature_set(), context=_context(),
            history_rows=_history_rows(), xg_snapshots=_xg_rows()))
    store = store_module.ForwardFactorObservationStore(engine)

    first = store.append_batch(batch)
    second = store.append_batch(batch)

    assert first["appended"] == 4
    assert second["appended"] == 0
    assert second["idempotent_no_ops"] == 4
    assert len(_stored(engine)) == 4


def test_07_the_frozen_f1r_b_modules_are_byte_identical() -> None:
    import hashlib

    for name, expected in F1R_B_MODULE_SHA256.items():
        actual = hashlib.sha256((QUANT / name).read_bytes()).hexdigest()
        assert actual == expected, f"{name} was modified"
    # The wheel carries a copy of the same bytes, never a second version of them.
    installed = (REPO / "src/w2/quant_research/_f1r_b")
    if installed.is_dir():
        for name, expected in F1R_B_MODULE_SHA256.items():
            assert hashlib.sha256((installed / name).read_bytes()).hexdigest() == expected


# --- 8: the released image can reach the modules --------------------------
def test_08_the_wheel_carries_the_modules_and_resolves_them_outside_a_checkout(
    tmp_path, monkeypatch,
) -> None:
    """The SC21 failure mode, tested rather than assumed.

    The image installs non-editable and carries no `scripts/`, so a path
    guessed from the checkout is not a fallback -- it is the bug. The modules
    must be in the package and load with the working directory elsewhere.
    """
    import subprocess

    from w2.quant_research.forward_factor_modules import (
        PACKAGE_MODULE_DIRNAME,
        REQUIRED_FILENAMES,
        load_modules,
        module_dir,
    )

    directory = module_dir()
    assert {path.name for path in directory.iterdir()} >= set(REQUIRED_FILENAMES)
    # Either the wheel's in-package copy or the source checkout, never a path
    # guessed from the module's own location.
    assert directory.name in {PACKAGE_MODULE_DIRNAME, "quant"}, directory

    module = load_modules()
    assert module.directory == directory
    assert module.integration.INTEGRATION_ID == "w2.f1r_b_production_recording_integration.v1"

    elsewhere = subprocess.run(
        [sys.executable, "-c",
         "from w2.quant_research.forward_factor_modules import load_modules;"
         "print(load_modules().integration.INTEGRATION_ID)"],
        cwd=tmp_path, capture_output=True, text=True, check=False,
        env={**__import__("os").environ, "PYTHONPATH": ""})
    assert elsewhere.returncode == 0, elsewhere.stderr
    assert "w2.f1r_b_production_recording_integration.v1" in elsewhere.stdout


def test_08_a_missing_module_directory_fails_closed(monkeypatch) -> None:
    import w2.quant_research.forward_factor_modules as modules

    monkeypatch.setattr(
        modules, "package_module_dir", lambda: Path("/nonexistent/_f1r_b"))
    monkeypatch.setattr(
        modules, "checkout_module_dir", lambda: Path("/nonexistent/scripts/quant"))
    with pytest.raises(modules.ForwardFactorModulesNotFound) as excinfo:
        modules.load_modules()
    assert str(excinfo.value).startswith("FORWARD_FACTOR_MODULES_NOT_FOUND")
    assert "/nonexistent/_f1r_b" in str(excinfo.value)
    assert "/nonexistent/scripts/quant" in str(excinfo.value)


def test_08_the_dockerfile_ships_and_then_removes_the_build_input() -> None:
    text = (REPO / "Dockerfile.python").read_text(encoding="utf-8")
    for name in (
        "f1p_forward_factor_contract.py",
        "f1r_a0_offline_factor_recorder.py",
        "f1r_b_source_capture.py",
        "f1r_b_production_ports.py",
        "f1r_b_production_recording_integration.py",
        "f1r_b_observation_store.py",
    ):
        assert name in text, name
    assert "w2/quant_research/_f1r_b/f1r_b_observation_store.py" in text
    assert "rm -f /app/scripts/quant/" in text
    assert "test ! -e /app/scripts/quant" in text
    # The two allowlisted runtime scripts are not collateral damage.
    assert "test -f /app/scripts/run_w2_free_mode_model_validation_canary.py" in text
    assert "test -f /app/scripts/repair_w2_xg_retention_lineage.py" in text


def test_08_the_wheel_force_include_lists_all_six_modules() -> None:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    block = text.split("[tool.hatch.build.targets.wheel.force-include]")[1]
    for name in (
        "f1p_forward_factor_contract.py",
        "f1r_a0_offline_factor_recorder.py",
        "f1r_b_source_capture.py",
        "f1r_b_production_ports.py",
        "f1r_b_production_recording_integration.py",
        "f1r_b_observation_store.py",
    ):
        assert f'"scripts/quant/{name}" = "w2/quant_research/_f1r_b/{name}"' in block, name
