from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.run_w2_wc_replay_backtest_10 import (
    CLV_NA_REASON,
    MAX_PROVIDER_CALLS,
    build_postmatch_results,
    build_prematch_cards,
    build_prematch_inputs,
    build_validation_report,
    capture_forward_ledger_integrity,
    run_wc_replay_backtest_10,
    select_finished_fixtures,
)


def test_selects_finished_fixtures_from_july_2_first_and_limits() -> None:
    rows = [
        _fixture("future", "2026-07-01T12:00:00Z", status="NS"),
        _fixture("old", "2026-07-01T18:00:00Z", status="FT"),
        _fixture("first", "2026-07-02T00:00:00Z", status="FT"),
        _fixture("second", "2026-07-02T03:00:00Z", status="AET"),
        _fixture("third", "2026-07-03T03:00:00Z", status="PEN"),
    ]

    selected = select_finished_fixtures(
        rows,
        limit=2,
        date_from="2026-07-02",
        date_to="2026-07-09",
    )

    assert [row["fixture_id"] for row in selected] == ["first", "second"]
    assert {row["status"] for row in selected} == {"FT", "AET"}


def test_prematch_inputs_redact_results_and_use_kickoff_minus_30m() -> None:
    selected = [
        {
            "fixture_id": "fixture-1",
            "competition_id": "world_cup_2026",
            "kickoff_utc": "2026-07-02T04:00:00+00:00",
            "teams": {"home": "Home", "away": "Away"},
            "status": "FT",
            "score": {"fulltime": {"home": 2, "away": 1}},
        }
    ]
    payload = build_prematch_inputs(
        selected,
        raw_odds_by_fixture={"fixture-1": _odds_payload("fixture-1")},
        as_of_mode="kickoff_minus_30m",
    )
    serialized = json.dumps(payload)

    item = payload["items"][0]
    assert item["as_of"] == "2026-07-02T03:30:00+00:00"
    assert item["odds_source"] == "RETROSPECTIVE_PROVIDER_ARCHIVE"
    assert item["odds_timeline_warning"] is True
    assert "final_score" not in serialized
    assert "settlement" not in serialized
    assert "result_status" not in serialized


def test_postmatch_validation_happens_after_frozen_cards_and_clv_is_na() -> None:
    selected = [
        {
            "fixture_id": "fixture-1",
            "competition_id": "world_cup_2026",
            "kickoff_utc": "2026-07-02T04:00:00+00:00",
            "teams": {"home": "Home", "away": "Away"},
            "status": "FT",
            "score": {
                "goals": {"home": 2, "away": 1},
                "fulltime": {"home": 2, "away": 1},
            },
        }
    ]
    prematch = build_prematch_inputs(
        selected,
        raw_odds_by_fixture={"fixture-1": _odds_payload("fixture-1")},
        as_of_mode="kickoff_minus_30m",
    )
    cards = build_prematch_cards(prematch)
    results = build_postmatch_results(selected)
    validation = build_validation_report(cards["cards"], results["results"])

    assert cards["cards_frozen_before_outcomes"] is True
    assert results["results_read_after_cards_frozen"] is True
    assert validation["clv"] == "N/A"
    assert validation["clv_reason"] == CLV_NA_REASON
    assert validation["summary"]["data_leakage_fail_count"] == 0
    assert validation["summary"]["recommendation_count"] == 0


def test_forward_ledger_integrity_hash_is_stable(tmp_path: Path) -> None:
    ledger = tmp_path / "runtime" / "forward_outcome_ledger"
    performance = tmp_path / "runtime" / "forward_ledger_performance"
    ledger.mkdir(parents=True)
    performance.mkdir(parents=True)
    (ledger / "records.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    (performance / "summary.json").write_text('{"sample_count":0}\n', encoding="utf-8")

    before = capture_forward_ledger_integrity(tmp_path)
    after = capture_forward_ledger_integrity(tmp_path)

    assert before["forward_outcome_ledger"] == after["forward_outcome_ledger"]
    assert before["forward_ledger_performance"] == after["forward_ledger_performance"]


def test_runner_respects_provider_cap_and_writes_isolated_outputs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "runtime").mkdir(parents=True)
    calls: list[tuple[str, dict[str, str]]] = []

    def requester(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        calls.append((endpoint, params))
        if endpoint == "fixtures":
            return {
                "response": [
                    _fixture(f"fixture-{index}", f"2026-07-0{index + 2}T04:00:00Z")
                    for index in range(3)
                ],
                "errors": [],
            }
        if endpoint == "odds":
            return _odds_payload(params["fixture"])
        raise AssertionError(endpoint)

    payload = run_wc_replay_backtest_10(
        limit=3,
        fixture_date_from="2026-07-02",
        fixture_date_to="2026-07-09",
        capture_public=True,
        output_root=tmp_path / "out",
        requester=requester,
        now=datetime(2026, 7, 9, tzinfo=UTC),
        repo_root=repo_root,
    )

    assert payload["status"] == "PASS"
    assert payload["provider_calls_actual"] == 4
    assert payload["provider_calls_actual"] <= MAX_PROVIDER_CALLS
    assert payload["forward_ledger_unchanged"] is True
    assert payload["forward_ledger_performance_unchanged"] is True
    assert payload["db_writes"] == 0
    assert payload["direction_allowed_changes"] == []
    output_dir = Path(payload["output_dir"])
    assert (output_dir / "prematch_cards.json").exists()
    assert (output_dir / "validation_report.json").exists()
    assert (output_dir / "public_capture" / "fixtures.json").exists()


def _fixture(
    fixture_id: str,
    kickoff: str,
    *,
    status: str = "FT",
) -> dict[str, object]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff,
            "status": {"short": status},
        },
        "teams": {
            "home": {"name": f"Home {fixture_id}", "winner": True},
            "away": {"name": f"Away {fixture_id}", "winner": False},
        },
        "goals": {"home": 2, "away": 1},
        "score": {
            "fulltime": {"home": 2, "away": 1},
            "extratime": {"home": None, "away": None},
            "penalty": {"home": None, "away": None},
        },
    }


def _odds_payload(fixture_id: str) -> dict[str, object]:
    return {
        "response": [
            {
                "fixture": {"id": fixture_id},
                "bookmakers": [
                    {
                        "name": "Fixture Book",
                        "bets": [
                            {
                                "name": "Asian Handicap",
                                "values": [
                                    {"value": "Home -0.5", "odd": "1.91"},
                                    {"value": "Away +0.5", "odd": "1.93"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
        "errors": [],
    }
