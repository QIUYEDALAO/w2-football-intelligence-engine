from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from w2.strategy.candidate import (
    CandidatePolicy,
    HardGateReason,
    generate_candidate,
)

NOW = datetime(2026, 6, 25, 10, 0, tzinfo=UTC)


def fixture(*, kickoff_delta: timedelta = timedelta(hours=2)) -> dict[str, object]:
    return {
        "fixture_id": "1489404",
        "kickoff_utc": (NOW + kickoff_delta).isoformat().replace("+00:00", "Z"),
    }


def row(
    market: str,
    *,
    bookmaker_id: str,
    captured_delta: timedelta = timedelta(minutes=-2),
    suspended: bool = False,
    live: bool = False,
) -> dict[str, object]:
    return {
        "fixture_id": "1489404",
        "canonical_market": market,
        "selection": "HOME" if market != "TOTALS" else "OVER",
        "line": None if market == "ONE_X_TWO" else "2.5",
        "decimal_odds": "2.05",
        "bookmaker_id": bookmaker_id,
        "bookmaker_name": bookmaker_id,
        "captured_at": (NOW + captured_delta).isoformat().replace("+00:00", "Z"),
        "suspended": suspended,
        "live": live,
        "candidate": False,
        "formal_recommendation": False,
    }


def complete_observations() -> list[dict[str, object]]:
    return [
        row("ONE_X_TWO", bookmaker_id="pinnacle"),
        row("ASIAN_HANDICAP", bookmaker_id="sbo"),
        row("TOTALS", bookmaker_id="bet365"),
    ]


def reasons(payload: Any) -> list[str]:
    return [str(item) for item in payload]


def test_generates_watch_candidate_without_public_candidate_flag() -> None:
    candidate = generate_candidate(
        fixture=fixture(),
        observations=complete_observations(),
        as_of=NOW,
    )

    assert candidate.decision == "WATCH"
    assert candidate.candidate is False
    assert candidate.formal_recommendation is False
    assert candidate.as_dict()["candidate"] is False
    assert candidate.as_dict()["formal_recommendation"] is False


def test_skip_when_core_market_missing() -> None:
    candidate = generate_candidate(
        fixture=fixture(),
        observations=[row("ONE_X_TWO", bookmaker_id="pinnacle"), row("TOTALS", bookmaker_id="sbo")],
        as_of=NOW,
    )

    assert candidate.decision == "SKIP"
    assert HardGateReason.CORE_MARKET_MISSING.value in reasons(
        candidate.as_dict()["hard_gate_reasons"]
    )


def test_skip_when_odds_are_stale() -> None:
    observations = complete_observations()
    observations[0] = row("ONE_X_TWO", bookmaker_id="pinnacle", captured_delta=timedelta(hours=-2))

    candidate = generate_candidate(
        fixture=fixture(),
        observations=observations,
        as_of=NOW,
        policy=CandidatePolicy(max_odds_age_seconds=900),
    )

    assert candidate.decision == "SKIP"
    assert HardGateReason.ODDS_STALE.value in reasons(candidate.as_dict()["hard_gate_reasons"])


def test_skip_when_bookmaker_minimum_not_met() -> None:
    candidate = generate_candidate(
        fixture=fixture(),
        observations=[
            row("ONE_X_TWO", bookmaker_id="pinnacle"),
            row("ASIAN_HANDICAP", bookmaker_id="pinnacle"),
            row("TOTALS", bookmaker_id="pinnacle"),
        ],
        as_of=NOW,
        policy=CandidatePolicy(min_bookmakers=2),
    )

    assert candidate.decision == "SKIP"
    assert HardGateReason.BOOKMAKER_MIN_NOT_MET.value in reasons(
        candidate.as_dict()["hard_gate_reasons"]
    )


def test_skip_when_any_market_is_suspended() -> None:
    observations = complete_observations()
    observations[1] = row("ASIAN_HANDICAP", bookmaker_id="sbo", suspended=True)

    candidate = generate_candidate(fixture=fixture(), observations=observations, as_of=NOW)

    assert candidate.decision == "SKIP"
    assert HardGateReason.MARKET_SUSPENDED.value in reasons(
        candidate.as_dict()["hard_gate_reasons"]
    )


def test_skip_when_any_market_is_live() -> None:
    observations = complete_observations()
    observations[2] = row("TOTALS", bookmaker_id="bet365", live=True)

    candidate = generate_candidate(fixture=fixture(), observations=observations, as_of=NOW)

    assert candidate.decision == "SKIP"
    assert HardGateReason.MARKET_LIVE.value in reasons(candidate.as_dict()["hard_gate_reasons"])


def test_skip_when_settlement_rule_is_unknown() -> None:
    observations = complete_observations()
    observations.append(row("CORNERS", bookmaker_id="book-x"))

    candidate = generate_candidate(fixture=fixture(), observations=observations, as_of=NOW)

    assert candidate.decision == "SKIP"
    assert HardGateReason.SETTLEMENT_RULE_UNKNOWN.value in reasons(
        candidate.as_dict()["hard_gate_reasons"]
    )


def test_skip_when_fixture_already_kicked_off() -> None:
    candidate = generate_candidate(
        fixture=fixture(kickoff_delta=timedelta(minutes=-1)),
        observations=complete_observations(),
        as_of=NOW,
    )

    assert candidate.decision == "SKIP"
    assert HardGateReason.KICKOFF_PASSED.value in reasons(candidate.as_dict()["hard_gate_reasons"])


@pytest.mark.parametrize("kickoff", [None, "not-a-time", "2026-06-25T12:00:00"])
def test_invalid_kickoff_skips_without_exception(kickoff: str | None) -> None:
    invalid_fixture = fixture()
    invalid_fixture["kickoff_utc"] = kickoff

    candidate = generate_candidate(
        fixture=invalid_fixture, observations=complete_observations(), as_of=NOW
    )

    assert candidate.decision == "SKIP"
    assert HardGateReason.KICKOFF_TIME_INVALID in candidate.hard_gate_reasons


@pytest.mark.parametrize("captured_at", [None, "not-a-time"])
def test_missing_or_invalid_capture_time_skips(captured_at: str | None) -> None:
    observations = complete_observations()
    if captured_at is None:
        observations[0].pop("captured_at")
    else:
        observations[0]["captured_at"] = captured_at

    candidate = generate_candidate(fixture=fixture(), observations=observations, as_of=NOW)

    assert candidate.decision == "SKIP"
    assert HardGateReason.ODDS_CAPTURE_TIME_MISSING in candidate.hard_gate_reasons


@pytest.mark.parametrize("bad_odds", ["N/A", None, "NaN", "Infinity", "0"])
def test_invalid_odds_row_is_filtered_before_best_quote(bad_odds: object) -> None:
    observations = complete_observations()
    observations[0]["decimal_odds"] = bad_odds

    candidate = generate_candidate(fixture=fixture(), observations=observations, as_of=NOW)

    assert candidate.decision == "SKIP"  # A core market has no executable quote.
    assert HardGateReason.CORE_MARKET_MISSING in candidate.hard_gate_reasons
    assert candidate.decimal_odds is None


def test_invalid_quote_is_not_selected_when_valid_quote_remains() -> None:
    observations = complete_observations()
    observations.append(row("TOTALS", bookmaker_id="bad-book"))
    observations[-1]["decimal_odds"] = "N/A"

    candidate = generate_candidate(fixture=fixture(), observations=observations, as_of=NOW)

    assert candidate.decision == "WATCH"
    assert candidate.decimal_odds == Decimal("2.05")
    assert candidate.hard_gate_reasons == ()


def test_all_invalid_odds_skip_without_watch() -> None:
    observations = complete_observations()
    for observation, bad_odds in zip(observations, ("N/A", None, "NaN"), strict=True):
        observation["decimal_odds"] = bad_odds

    candidate = generate_candidate(fixture=fixture(), observations=observations, as_of=NOW)

    assert candidate.decision == "SKIP"
    assert HardGateReason.ODDS_INVALID in candidate.hard_gate_reasons
    assert candidate.decimal_odds is None
