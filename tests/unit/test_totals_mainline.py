from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.markets.totals_mainline import select_canonical_totals_mainline

CAPTURED_AT = datetime(2026, 7, 21, 16, 10, tzinfo=UTC)
KICKOFF = CAPTURED_AT + timedelta(hours=6)


def _pair(
    bookmaker: str,
    line: float,
    over: float,
    under: float,
    *,
    captured_at: datetime = CAPTURED_AT,
    suspended: bool = False,
    live: bool = False,
) -> list[dict[str, object]]:
    common: dict[str, object] = {
        "fixture_id": "fx",
        "canonical_market": "TOTALS",
        "raw_market_label": "Goals Over/Under",
        "bookmaker_id": bookmaker,
        "line": str(line),
        "captured_at": captured_at,
        "provider": "api_football",
        "suspended": suspended,
        "live": live,
        "model_probability": 0.99,
        "expected_value": 99.0,
    }
    return [
        {
            **common,
            "observation_id": f"{bookmaker}:{line}:over",
            "canonical_selection": "OVER",
            "decimal_odds": str(over),
        },
        {
            **common,
            "observation_id": f"{bookmaker}:{line}:under",
            "canonical_selection": "UNDER",
            "decimal_odds": str(under),
        },
    ]


def _select(rows: list[dict[str, object]]):
    return select_canonical_totals_mainline(
        rows,
        fixture_id="fx",
        target=CAPTURED_AT,
        kickoff=KICKOFF,
    )


def test_balanced_four_vote_line_can_override_six_vote_line_inside_floor() -> None:
    rows = [row for index in range(6) for row in _pair(f"wide-{index}", 2.5, 1.70, 2.10)]
    rows.extend(row for index in range(4) for row in _pair(f"balanced-{index}", 2.75, 1.91, 1.91))

    result = _select(rows)

    assert result.line is not None and float(result.line) == 2.75
    assert result.consensus_floor == 4
    selected = result.candidate_lines[0]
    assert selected["bookmaker_vote_count"] == 4
    assert selected["balanced_override_eligible"] is True


def test_balanced_five_vote_line_can_override_six_vote_line() -> None:
    rows = [row for index in range(6) for row in _pair(f"wide-{index}", 2.5, 1.70, 2.10)]
    rows.extend(row for index in range(5) for row in _pair(f"balanced-{index}", 2.75, 1.92, 1.92))

    assert float(_select(rows).line or 0) == 2.75


def test_single_book_balanced_line_cannot_override_consensus() -> None:
    rows = [row for index in range(6) for row in _pair(f"wide-{index}", 2.5, 1.70, 2.10)]
    rows.extend(_pair("single", 2.75, 1.92, 1.92))

    result = _select(rows)

    assert float(result.line or 0) == 2.5
    rejected = next(item for item in result.candidate_lines or [] if item["line"] == 2.75)
    assert rejected["reason"] == "MORE_BALANCED_BUT_BELOW_CONSENSUS_FLOOR"


def test_each_bookmaker_casts_only_one_vote_across_its_ladder() -> None:
    rows: list[dict[str, object]] = []
    for index in range(3):
        rows.extend(_pair(f"book-{index}", 2.5, 1.70, 2.10))
        rows.extend(_pair(f"book-{index}", 2.75, 1.91, 1.91))

    result = _select(rows)
    candidates = {item["line"]: item for item in result.candidate_lines or []}

    assert candidates[2.75]["bookmaker_vote_count"] == 3
    assert candidates[2.5]["bookmaker_vote_count"] == 0
    assert sum(item["bookmaker_vote_count"] for item in candidates.values()) == 3


def test_incomplete_suspended_and_live_pairs_are_not_candidates() -> None:
    rows = _pair("valid", 2.5, 1.90, 1.90)
    rows.extend(_pair("suspended", 2.75, 1.91, 1.91, suspended=True))
    rows.extend(_pair("live", 3.0, 1.92, 1.92, live=True))
    rows.append(_pair("incomplete", 3.25, 1.93, 1.93)[0])

    result = _select(rows)

    assert [item["line"] for item in result.candidate_lines or []] == [2.5]
    assert result.quarantine_reasons["PAIR_INCOMPLETE"] == 1
    assert result.quarantine_reasons["SUSPENDED_OR_LIVE"] == 4


def test_override_requires_reviewed_balance_improvement() -> None:
    rows = [row for index in range(6) for row in _pair(f"majority-{index}", 2.5, 1.84, 1.96)]
    rows.extend(row for index in range(4) for row in _pair(f"minority-{index}", 2.75, 1.90, 1.90))

    result = _select(rows)

    assert float(result.line or 0) == 2.5
    assert result.candidate_lines[0]["balanced_override_eligible"] is False


def test_model_and_ev_fields_do_not_affect_market_mainline() -> None:
    rows = _pair("a", 2.5, 1.90, 1.90) + _pair("b", 2.75, 1.70, 2.10)
    baseline = _select(rows)
    for row in rows:
        row["model_probability"] = 0.01 if row["line"] == "2.5" else 0.99
        row["expected_value"] = -100 if row["line"] == "2.5" else 100

    changed = _select(rows)

    assert baseline.line == changed.line
    assert baseline.candidate_ladder_hash == changed.candidate_ladder_hash
