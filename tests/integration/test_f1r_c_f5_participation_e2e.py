"""F1R-C: F5 participates, end to end, from a real capture-built fact.

This drives the real worker write-side projection against an isolated
PostgreSQL 16, with a real `ForwardFactorRecorder`, a real
`RuntimeAhSettlementRepository` reader and the real ports. The AH settlement
fact is *built* from the committed real production-capture sample rather than
hand-written, so the quote capture, the settlement capture and both payload
hashes are the real ones.

Isolated PostgreSQL is required and the test skips without it, exactly like the
F1R-B end-to-end suite whose harness it reuses.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from w2.historical.runtime_ah_settlement import RuntimeAhSettlementRepository

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
#: The 1-1 quarter-line fixture: home does not cover, away does, so both sides of
#: F5 have a decisive row from a single fact.
SAMPLE_INDEX = 1


def _real_fact(*, home_w2: str, away_w2: str):  # type: ignore[no-untyped-def]
    from w2.markets.ah_settlement_fact import (
        TerminalSettlementEvidence,
        build_ah_settlement_fact,
    )

    item = json.loads(AH_SAMPLE.read_text(encoding="utf-8").splitlines()[SAMPLE_INDEX])
    fixture = item["fixture"]
    capture = item["settlement_capture"]
    fact = build_ah_settlement_fact(
        fixture_id=fixture["fixture_id"],
        provider_fixture_id=str(fixture["provider_fixture_id"]),
        competition_id=fixture["competition_id"],
        season=fixture["season"],
        kickoff=fixture["kickoff_utc"],
        market_observations=item["observations"] or [],
        settlement=TerminalSettlementEvidence(
            provider_fixture_id=str(fixture["provider_fixture_id"]),
            status=fixture["fixture_status"],
            home_goals=fixture["home_goals"],
            away_goals=fixture["away_goals"],
            endpoint_capture_id=capture["capture_id"],
            raw_payload_sha256=capture["raw_payload_sha256"],
            observed_at=capture["provider_captured_at"],
            capture_endpoint=capture["endpoint"],
            capture_status=capture["capture_status"],
        ),
        home_team_provider_id=fixture["home_team_provider_id"],
        away_team_provider_id=fixture["away_team_provider_id"],
        home_w2_team_id=home_w2,
        away_w2_team_id=away_w2,
    )
    assert fact.status == "READY", fact.refusal_code
    return fact


def _seed(engine, tmp_path: Path):  # type: ignore[no-untyped-def]
    """The F1R-B end-to-end setup, plus one runtime AH settlement fact."""
    f1rb._seed_ingested_fixture(engine, tmp_path)
    f1rb._canonicalise(engine)
    repository = RuntimeAhSettlementRepository(engine=engine)
    fact = _real_fact(home_w2=f1rb.HOME_W2, away_w2=f1rb.AWAY_W2)
    written = repository.append_facts([fact])
    assert written["appended"] == 1, written
    return repository, fact


@pytest.fixture
def e2e(monkeypatch, tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = f1rb._fresh_database(monkeypatch)
    repository, fact = _seed(engine, tmp_path)
    return engine, repository, fact


def test_the_repository_reader_serves_the_fact_to_both_teams(e2e) -> None:  # type: ignore[no-untyped-def]
    engine, repository, fact = e2e
    rows = repository.facts_for_teams(
        [f1rb.HOME_W2, f1rb.AWAY_W2], before=f1rb.NOW, limit_per_team=20
    )
    by_team = {row["team_id"]: row for row in rows}

    assert set(by_team) == {f1rb.HOME_W2, f1rb.AWAY_W2}
    for team_id, row in by_team.items():
        assert row["ah_fact_id"] == fact.fact_id, team_id
        assert row["ah_fact_hash"] == fact.fact_hash, team_id
        assert row["ah_source_capture_id"] == fact.settlement_capture_id, team_id
        assert row["ah_source_capture_sha256"] == fact.settlement_payload_sha256, team_id
        assert row["quote_identity_hash"] == fact.quote_identity_hash, team_id
        assert row["ah_policy"] == "canonical_bookmaker_mainline_majority_v1", team_id
        assert row["settlement_observed_at"] == fact.settlement_observed_at, team_id
        assert row["source"] == "canonical_historical_ah_fact", team_id
        assert row["source_group"] == "canonical_historical_ah_fact", team_id
        assert row["collection_status"] == "CANONICAL_AH_FACT", team_id
        assert row["ah_quote_capture_ids"] == tuple(fact.quote_capture_ids), team_id


def test_the_two_sides_get_opposite_settlements(e2e) -> None:  # type: ignore[no-untyped-def]
    """One fact, two team-perspective outcomes: the projection is per side."""
    engine, repository, fact = e2e
    rows = repository.facts_for_teams(
        [f1rb.HOME_W2, f1rb.AWAY_W2], before=f1rb.NOW, limit_per_team=20
    )
    by_team = {row["team_id"]: row for row in rows}

    assert by_team[f1rb.HOME_W2]["settlement_outcome"] == fact.home_settlement
    assert by_team[f1rb.AWAY_W2]["settlement_outcome"] == fact.away_settlement
    assert by_team[f1rb.HOME_W2]["settlement_outcome"] != (
        by_team[f1rb.AWAY_W2]["settlement_outcome"]
    )


def test_f5_participates_in_the_production_projection(e2e) -> None:  # type: ignore[no-untyped-def]
    """The whole point: F5 is recorded as a participation, not an absence."""
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    engine, _repository, fact = e2e
    recorder = ForwardFactorRecorder(engine, enabled=True)

    materialized = f1rb._run_projection(engine, recorder=recorder)

    assert materialized, "the projection materialized nothing"
    rows = f1rb._by_factor(f1rb._rows(engine))
    f5 = rows["F5_RECENT_AH_COVER"]

    assert f5["participated"] is True, f5["factor_inputs"].get("source_record_ids")
    assert f5["factor_status"] == "PARTICIPATED"
    assert f5["signed_score"] is not None
    assert float(f5["applied_weight"]) > 0.0


def _parts(value):  # type: ignore[no-untyped-def]
    """Read a recorded factor_inputs collection.

    The F1P contract stores `factor_inputs` values as flat strings, so a
    multi-valued field arrives as the `str()` of its list. Parse both shapes
    rather than assuming one.
    """
    if isinstance(value, str):
        text = value.strip().lstrip("[").rstrip("]")
        return {
            item.strip().strip("'\"")
            for item in text.split(",")
            if item.strip().strip("'\"")
        }
    return {str(item) for item in (value or [])}


def test_the_recorded_f5_provenance_is_the_real_capture_identity(e2e) -> None:  # type: ignore[no-untyped-def]
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    engine, _repository, fact = e2e
    f1rb._run_projection(engine, recorder=ForwardFactorRecorder(engine, enabled=True))
    f5 = f1rb._by_factor(f1rb._rows(engine))["F5_RECENT_AH_COVER"]
    inputs = f5["factor_inputs"]

    assert fact.fact_id in _parts(inputs["ah_fact_ids"])
    assert fact.fact_hash in _parts(inputs["ah_fact_hashes"])
    assert fact.settlement_capture_id in _parts(inputs["settlement_capture_ids"])
    assert fact.settlement_payload_sha256 in _parts(inputs["settlement_payload_sha256s"])
    assert set(fact.quote_capture_ids) <= _parts(inputs["quote_capture_ids"])
    assert set(fact.quote_payload_sha256s) <= _parts(inputs["quote_payload_sha256s"])
    assert inputs["canonical_ah_policy"] == "canonical_bookmaker_mainline_majority_v1"
    assert inputs["source_observed_time_semantics"] == (
        "PROVIDER_CAPTURE_OF_TERMINAL_RESULT"
    )
    assert fact.fact_id in _parts(inputs["source_record_ids"])


def test_the_recorded_source_observed_time_is_the_settlement_instant(e2e) -> None:  # type: ignore[no-untyped-def]
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    engine, _repository, fact = e2e
    f1rb._run_projection(engine, recorder=ForwardFactorRecorder(engine, enabled=True))
    f5 = f1rb._by_factor(f1rb._rows(engine))["F5_RECENT_AH_COVER"]

    observed = f1rb._utc(f5["factor_inputs"]["settlement_observed_at"])
    evidence = f1rb._utc(f5["evidence_time_utc"])
    evaluated = f1rb._utc(f5["evaluated_at_utc"])

    assert observed == fact.settlement_observed_at
    assert evidence == observed
    # The whole PIT chain, in one place.
    quote_at = fact.quote_captured_at
    assert quote_at < fact.kickoff_utc < observed < evaluated


def test_the_batch_is_complete_and_never_half_written(e2e) -> None:  # type: ignore[no-untyped-def]
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    engine, _repository, _fact = e2e
    f1rb._run_projection(engine, recorder=ForwardFactorRecorder(engine, enabled=True))
    rows = f1rb._rows(engine)

    assert len(rows) == 4
    assert {row["factor_id"] for row in rows} == {
        "F3_REST_FITNESS", "F5_RECENT_AH_COVER", "F6_H2H", "F9_TRUE_XG"
    }
    assert len({row["attempt_id"] for row in rows}) == 1
    for row in rows:
        assert f1rb._utc(row["evidence_time_utc"]) < f1rb._utc(row["evaluated_at_utc"])


def test_a_replay_adds_no_rows_and_keeps_the_f5_record(e2e) -> None:  # type: ignore[no-untyped-def]
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    engine, _repository, _fact = e2e
    f1rb._run_projection(engine, recorder=ForwardFactorRecorder(engine, enabled=True))
    before = f1rb._rows(engine)

    second = ForwardFactorRecorder(engine, enabled=True)
    f1rb._run_projection(engine, recorder=second)

    after = f1rb._rows(engine)
    assert after == before
    assert second.summary()["rows_appended"] == 0


def test_the_fact_table_is_never_written_by_the_recorder(e2e) -> None:  # type: ignore[no-untyped-def]
    """The recorder only reads the fact table; it never adds or rewrites facts."""
    from w2.quant_research.forward_factor_recording import ForwardFactorRecorder

    engine, repository, _fact = e2e
    before = repository.facts_for_teams(
        [f1rb.HOME_W2, f1rb.AWAY_W2], before=f1rb.NOW, limit_per_team=20
    )

    f1rb._run_projection(engine, recorder=ForwardFactorRecorder(engine, enabled=True))

    after = repository.facts_for_teams(
        [f1rb.HOME_W2, f1rb.AWAY_W2], before=f1rb.NOW, limit_per_team=20
    )
    assert after == before
