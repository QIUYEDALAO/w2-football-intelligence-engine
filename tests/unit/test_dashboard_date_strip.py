from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from w2.dashboard.date_strip import build_persisted_date_strip, next_available_date


def _fixture(
    fixture_id: str,
    kickoff_utc: datetime,
    *,
    competition_id: str = "allsvenskan",
    status: str = "NS",
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "competition_id": competition_id,
        "kickoff_utc": kickoff_utc,
        "fixture_status": status,
    }


def _plan(fixture_id: str, scheduled_at: datetime) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "scheduled_at": scheduled_at,
        "endpoints": ["odds"],
    }


def test_date_strip_uses_fifteen_noon_to_noon_football_days() -> None:
    selected = date(2026, 8, 10)
    strip = build_persisted_date_strip(
        selected,
        fixtures=[
            _fixture("before-cutoff", datetime(2026, 8, 10, 3, 59, tzinfo=UTC)),
            _fixture("at-cutoff", datetime(2026, 8, 10, 4, 0, tzinfo=UTC)),
            _fixture("end-exclusive", datetime(2026, 8, 11, 4, 0, tzinfo=UTC)),
        ],
        odds_plans=[],
        market_evidence_fixture_ids=set(),
        as_of=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
    )

    assert len(strip) == 15
    assert strip[0]["football_day"] == "2026-08-03"
    assert strip[7]["football_day"] == "2026-08-10"
    assert strip[-1]["football_day"] == "2026-08-17"
    assert strip[6]["fixture_count"] == 1
    assert strip[7]["fixture_count"] == 1
    assert strip[8]["fixture_count"] == 1


def test_future_market_state_uses_persisted_checkpoint_timing() -> None:
    selected = date(2026, 8, 10)
    as_of = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    fixtures = [
        _fixture("waiting", datetime(2026, 8, 12, 12, 0, tzinfo=UTC)),
        _fixture("due", datetime(2026, 8, 13, 12, 0, tzinfo=UTC)),
        _fixture("ready", datetime(2026, 8, 14, 12, 0, tzinfo=UTC)),
    ]
    strip = build_persisted_date_strip(
        selected,
        fixtures=fixtures,
        odds_plans=[
            _plan("waiting", as_of + timedelta(hours=6)),
            _plan("due", as_of - timedelta(minutes=1)),
            _plan("ready", as_of - timedelta(hours=1)),
        ],
        market_evidence_fixture_ids={"ready"},
        as_of=as_of,
    )
    by_day = {entry["football_day"]: entry for entry in strip}

    assert by_day["2026-08-12"]["display_state"] == (
        "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW"
    )
    assert by_day["2026-08-13"]["display_state"] == (
        "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY"
    )
    assert by_day["2026-08-14"]["display_state"] == "MARKET_EVIDENCE_AVAILABLE"
    assert by_day["2026-08-12"]["public_semantics"] == {
        "scope": "SELECTED_DAY",
        "cause": "NOT_YET_DUE",
    }
    assert by_day["2026-08-13"]["public_semantics"] == {
        "scope": "SELECTED_DAY",
        "cause": "AWAITING_COLLECTION",
    }
    assert by_day["2026-08-14"]["public_semantics"] == {
        "scope": "SELECTED_DAY",
        "cause": None,
    }


def test_date_strip_reports_partial_coverage_and_persisted_next_date_only() -> None:
    selected = date(2026, 8, 10)
    strip = build_persisted_date_strip(
        selected,
        fixtures=[
            _fixture(
                "later-one",
                datetime(2026, 8, 12, 6, 0, tzinfo=UTC),
                competition_id="allsvenskan",
            ),
            _fixture(
                "later-two",
                datetime(2026, 8, 12, 8, 0, tzinfo=UTC),
                competition_id="eliteserien",
            ),
        ],
        odds_plans=[],
        market_evidence_fixture_ids=set(),
        as_of=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
    )
    later = next(entry for entry in strip if entry["football_day"] == "2026-08-12")

    assert later["fixture_count"] == 2
    assert later["persisted_competition_coverage_count"] == 2
    assert later["active_whitelist_count"] == 13
    assert next_available_date(selected, strip) == "2026-08-12"
    assert next_available_date(date(2026, 8, 12), strip) is None


def test_finished_day_remains_finished_with_persisted_market_evidence() -> None:
    strip = build_persisted_date_strip(
        date(2026, 8, 10),
        fixtures=[
            _fixture(
                "finished",
                datetime(2026, 8, 10, 17, 0, tzinfo=UTC),
                status="FT",
            )
        ],
        odds_plans=[],
        market_evidence_fixture_ids={"finished"},
        as_of=datetime(2026, 8, 11, 3, 0, tzinfo=UTC),
    )

    selected = strip[7]
    assert selected["finished_fixture_count"] == 1
    assert selected["upcoming_fixture_count"] == 0
    assert selected["market_collection_window_status"] == "MARKET_EVIDENCE_AVAILABLE"
    assert selected["display_state"] == "FINISHED"
