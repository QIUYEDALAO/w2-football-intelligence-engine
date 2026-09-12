"""F1R-C: the runtime AH settlement fact, replayed from real Provider captures.

The positive cases in this file are **real**: the rows in
``tests/fixtures/ah_settlement/real_production_capture_sample.jsonl`` were
extracted read-only from the production database and carry the real odds quotes,
the real capture identities and the real terminal scores. Nothing here is
synthesised to make a case pass.
"""

from __future__ import annotations

import json
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from w2.markets import ah_settlement_fact as module
from w2.markets.ah_settlement_fact import (
    SETTLEMENT_OBSERVED_AT_SEMANTICS,
    TerminalSettlementEvidence,
    build_ah_settlement_fact,
)

SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "ah_settlement"
    / "real_production_capture_sample.jsonl"
)


def _sample() -> list[dict[str, Any]]:
    return [json.loads(line) for line in SAMPLE.read_text().splitlines() if line.strip()]


def _evidence(item: dict[str, Any]) -> TerminalSettlementEvidence:
    fixture = item["fixture"]
    capture = item["settlement_capture"]
    return TerminalSettlementEvidence(
        provider_fixture_id=str(fixture["provider_fixture_id"]),
        status=fixture["fixture_status"],
        home_goals=fixture["home_goals"],
        away_goals=fixture["away_goals"],
        endpoint_capture_id=capture["capture_id"],
        raw_payload_sha256=capture["raw_payload_sha256"],
        observed_at=capture["provider_captured_at"],
        capture_endpoint=capture["endpoint"],
        capture_status=capture["capture_status"],
    )


def _build(item: dict[str, Any], **overrides: Any) -> module.AhSettlementFact:
    fixture = item["fixture"]
    kwargs: dict[str, Any] = {
        "fixture_id": fixture["fixture_id"],
        "provider_fixture_id": str(fixture["provider_fixture_id"]),
        "competition_id": fixture["competition_id"],
        "season": fixture["season"],
        "kickoff": fixture["kickoff_utc"],
        "market_observations": item["observations"] or [],
        "settlement": _evidence(item),
        "home_team_provider_id": fixture["home_team_provider_id"],
        "away_team_provider_id": fixture["away_team_provider_id"],
    }
    kwargs.update(overrides)
    return build_ah_settlement_fact(**kwargs)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


# --- 1: the real captures build real facts ---------------------------------
def test_every_real_sample_fixture_builds_a_fact() -> None:
    for item in _sample():
        fact = _build(item)
        assert fact.status == "READY", (item["fixture"]["provider_fixture_id"], fact.refusal_code)


def test_the_fact_carries_every_required_identity_field() -> None:
    for item in _sample():
        fact = _build(item)
        assert fact.fact_id and fact.fact_hash
        assert fact.canonical_key and len(fact.canonical_key) == 64
        assert fact.quote_identity_hash and len(fact.quote_identity_hash) == 64
        assert fact.result_identity_hash and len(fact.result_identity_hash) == 64
        assert fact.quote_capture_ids, fact.fact_id
        assert fact.quote_payload_sha256s, fact.fact_id
        assert all(len(value) == 64 for value in fact.quote_payload_sha256s)
        assert fact.settlement_capture_id
        assert fact.settlement_payload_sha256
        assert fact.line is not None
        assert fact.home_settlement in {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"}
        assert fact.away_settlement in {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"}
        assert fact.home_settlement != fact.away_settlement or fact.home_settlement == "PUSH"


def test_the_source_observed_time_is_the_capture_instant_not_the_kickoff() -> None:
    for item in _sample():
        fact = _build(item)
        kickoff = _utc(item["fixture"]["kickoff_utc"])
        capture_at = _utc(item["settlement_capture"]["provider_captured_at"])
        assert fact.settlement_observed_at == capture_at
        assert fact.source_observed_at == capture_at
        assert fact.settlement_observed_at != kickoff
        assert fact.settlement_observed_at_semantics == SETTLEMENT_OBSERVED_AT_SEMANTICS
        # The quote was observed before the result, and the result after kickoff.
        assert fact.quote_captured_at is not None
        assert fact.quote_captured_at < kickoff < fact.settlement_observed_at


def test_the_settlement_outcomes_match_the_real_final_score() -> None:
    expected = {
        "1490377": ("WIN", "LOSS", "-0.5"),  # 2-1, home gives a half goal
        "1490376": ("HALF_LOSS", "HALF_WIN", "-0.25"),  # 1-1 on a quarter line
        "1490136": ("LOSS", "WIN", "0.25"),  # 0-2, home receives a quarter goal
    }
    seen: set[str] = set()
    for item in _sample():
        provider_fixture_id = str(item["fixture"]["provider_fixture_id"])
        if provider_fixture_id not in expected:
            continue
        home, away, line = expected[provider_fixture_id]
        fact = _build(item)
        assert str(fact.line) == line, provider_fixture_id
        assert fact.home_settlement == home, provider_fixture_id
        assert fact.away_settlement == away, provider_fixture_id
        seen.add(provider_fixture_id)
    assert seen == set(expected)


def test_the_quote_identity_is_recomputable_from_the_stored_rows() -> None:
    for item in _sample():
        fact = _build(item)
        observations = item["observations"] or []
        captures = {str(row["capture_id"]) for row in observations}
        payloads = {str(row["raw_payload_sha256"]) for row in observations}
        assert set(fact.quote_capture_ids) <= captures, fact.fact_id
        assert set(fact.quote_payload_sha256s) <= payloads, fact.fact_id
        # The selected bookmakers are the ones the policy voted with.
        voted = {str(row["bookmaker_id"]) for row in observations}
        assert set(fact.selected_bookmakers) <= voted


# --- 2: determinism and idempotency ---------------------------------------
def test_the_same_capture_builds_the_same_fact() -> None:
    for item in _sample():
        first = _build(item)
        second = _build(item)
        assert first.fact_id == second.fact_id
        assert first.fact_hash == second.fact_hash
        assert first.canonical_key == second.canonical_key


def test_a_reordered_observation_set_builds_the_same_fact() -> None:
    """The fact is a function of the evidence, not of row order."""
    for item in _sample():
        reversed_item = {**item, "observations": list(reversed(item["observations"] or []))}
        assert _build(item).fact_hash == _build(reversed_item).fact_hash


def test_a_different_final_score_changes_the_fact() -> None:
    for item in _sample():
        base = _build(item)
        changed = _build(
            item,
            settlement=replace(
                _evidence(item),
                home_goals=_evidence(item).home_goals + 3,
            ),
        )
        assert changed.status == "READY"
        assert changed.fact_hash != base.fact_hash


# --- 3: every refusal path ------------------------------------------------
def test_a_non_terminal_status_is_refused() -> None:
    for status in ("1H", "2H", "NS", "LIVE", "PST", ""):
        item = _sample()[0]
        fact = _build(item, settlement=replace(_evidence(item), status=status))
        assert fact.status == "REFUSED"
        assert fact.refusal_code == module.REFUSAL_NOT_TERMINAL
        assert fact.fact_hash is None


def test_a_settlement_observed_at_or_before_kickoff_is_refused() -> None:
    item = _sample()[0]
    kickoff = _utc(item["fixture"]["kickoff_utc"])
    for observed in (kickoff, kickoff - timedelta(minutes=1)):
        fact = _build(item, settlement=replace(_evidence(item), observed_at=observed))
        assert fact.status == "REFUSED"
        assert fact.refusal_code == module.REFUSAL_SETTLEMENT_NOT_AFTER_KICKOFF


def test_the_kickoff_cannot_stand_in_for_the_observation_time() -> None:
    """Impersonating the source time with the kickoff is refused, not coerced."""
    item = _sample()[0]
    fact = _build(
        item, settlement=replace(_evidence(item), observed_at=item["fixture"]["kickoff_utc"])
    )
    assert fact.status == "REFUSED"
    assert fact.refusal_code == module.REFUSAL_SETTLEMENT_NOT_AFTER_KICKOFF


def test_a_non_fixtures_capture_is_refused() -> None:
    item = _sample()[0]
    fact = _build(item, settlement=replace(_evidence(item), capture_endpoint="odds"))
    assert fact.status == "REFUSED"
    assert fact.refusal_code == module.REFUSAL_SETTLEMENT_WRONG_ENDPOINT


def test_an_unsuccessful_capture_is_refused() -> None:
    item = _sample()[0]
    for status in ("FAILED", "PROVIDER_EMPTY"):
        fact = _build(item, settlement=replace(_evidence(item), capture_status=status))
        assert fact.status == "REFUSED"
        assert fact.refusal_code == module.REFUSAL_SETTLEMENT_CAPTURE_NOT_SUCCESSFUL


def test_a_fixture_identity_mismatch_is_refused() -> None:
    item = _sample()[0]
    fact = _build(item, settlement=replace(_evidence(item), provider_fixture_id="9999999"))
    assert fact.status == "REFUSED"
    assert fact.refusal_code == module.REFUSAL_FIXTURE_IDENTITY_MISMATCH


def test_a_missing_capture_identity_is_refused() -> None:
    item = _sample()[0]
    fact = _build(item, settlement=replace(_evidence(item), endpoint_capture_id=""))
    assert fact.status == "REFUSED"
    assert fact.refusal_code == module.REFUSAL_SETTLEMENT_CAPTURE_MISSING


def test_a_missing_settlement_payload_hash_is_refused() -> None:
    item = _sample()[0]
    fact = _build(item, settlement=replace(_evidence(item), raw_payload_sha256=""))
    assert fact.status == "REFUSED"
    assert fact.refusal_code == module.REFUSAL_SETTLEMENT_PAYLOAD_MISSING


def test_an_empty_quote_side_is_refused() -> None:
    item = _sample()[0]
    fact = _build(item, market_observations=[])
    assert fact.status == "REFUSED"
    assert fact.refusal_code == module.REFUSAL_MAINLINE_UNAVAILABLE


def test_a_quote_without_a_capture_identity_is_refused() -> None:
    item = _sample()[0]
    stripped = [
        {key: value for key, value in row.items() if key != "capture_id"}
        for row in item["observations"]
    ]
    fact = _build(item, market_observations=stripped)
    assert fact.status == "REFUSED"
    assert fact.refusal_code in {
        module.REFUSAL_QUOTE_CAPTURE_MISSING,
        module.REFUSAL_QUOTE_IDENTITY_INCOMPLETE,
    }


def test_a_quote_without_a_payload_hash_is_refused() -> None:
    item = _sample()[0]
    stripped = [
        {key: value for key, value in row.items() if key != "raw_payload_sha256"}
        for row in item["observations"]
    ]
    fact = _build(item, market_observations=stripped)
    assert fact.status == "REFUSED"
    assert fact.refusal_code in {
        module.REFUSAL_QUOTE_PAYLOAD_MISSING,
        module.REFUSAL_QUOTE_IDENTITY_INCOMPLETE,
    }


def test_a_post_kickoff_quote_is_refused() -> None:
    """Only pre-kickoff quotes may define the line."""
    item = _sample()[0]
    kickoff = _utc(item["fixture"]["kickoff_utc"])
    shifted = [
        {**row, "captured_at": (kickoff + timedelta(minutes=5)).isoformat()}
        for row in item["observations"]
    ]
    fact = _build(item, market_observations=shifted)
    assert fact.status == "REFUSED"
    assert fact.refusal_code == module.REFUSAL_MAINLINE_UNAVAILABLE


# --- 4: the type cannot carry an unproven observation time ----------------
def test_the_evidence_type_cannot_carry_a_confirmed_at() -> None:
    """`confirmed_at` is not merely unused -- it is unrepresentable.

    The column has two writers with different meanings and no discriminator, so
    the evidence type has no field for it; no caller can pass one in.
    """
    names = {field.name for field in fields(TerminalSettlementEvidence)}
    assert "confirmed_at" not in names
    assert {
        "observed_at",
        "endpoint_capture_id",
        "raw_payload_sha256",
        "capture_endpoint",
        "capture_status",
    } <= names


def test_the_refusal_path_never_returns_a_partial_fact() -> None:
    item = _sample()[0]
    fact = _build(item, settlement=replace(_evidence(item), status="NS"))
    assert fact.status == "REFUSED"
    for name in ("fact_id", "fact_hash", "canonical_key", "line", "source_observed_at"):
        assert getattr(fact, name) is None, name
    assert fact.home_settlement is None and fact.away_settlement is None


def test_the_module_does_not_read_confirmed_at_or_the_wall_clock() -> None:
    """The two forbidden sources are absent from the *code*, not merely unused.

    Scanned as an AST rather than as text: the module docstring names
    `results.confirmed_at` precisely to explain why it is refused, and a text
    scan could not tell that apart from actually reading the column.
    """
    import ast

    tree = ast.parse(Path(module.__file__).read_text())
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for forbidden in ("confirmed_at", "now", "utcnow", "today", "time"):
        assert forbidden not in attributes, f"reads .{forbidden}"
    for forbidden in ("utcnow", "time"):
        assert forbidden not in names, f"references {forbidden}"


@pytest.mark.parametrize("fixture_index", [0, 1, 2])
def test_the_fact_payload_round_trips_as_json(fixture_index: int) -> None:
    fact = _build(_sample()[fixture_index])
    payload = fact.as_payload()
    assert json.loads(json.dumps(payload)) == payload
    assert Decimal(str(payload["line"])) == fact.line
