from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import CURRENT_SERIALIZER_VERSION
from w2.domain.recommendation_decision_v4 import (
    RECOMMENDATION_SCHEMA_VERSION,
    build_recommendation_decision_v4,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.tracking.forward_outcome_ledger import (
    append_capture_supersessions,
    backfill_outcomes,
    build_forward_outcome_records,
    pending_outcome_entries,
    run_forward_outcome_ledger,
)
from w2.tracking.outcome_ledger_repository import (
    OutcomeLedgerError,
    OutcomeLedgerRepository,
)


def _day_view() -> dict[str, object]:
    return {
        "football_day": "2026-07-07",
        "environment": "staging",
        "cards": [
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": "2026-07-07T16:00:00Z",
                "competition_id": "world_cup_2026",
                "competition_name": "World Cup",
                "home_team_name": "Argentina",
                "away_team_name": "Egypt",
                "decision_tier": "WATCH",
                "data_status": "READY",
                "reason_code": "EDGE_INSUFFICIENT",
                "action": "盯价格变动",
                "probability_source": "MARKET_DEVIG",
                "model_market_divergence": {
                    "status": "READY",
                    "magnitude": 0.03,
                    "direction_allowed": False,
                    "model_fair_line": "-1.5",
                    "market_line": "-1.25",
                },
                "current_odds": {
                    "ah": {
                        "home_line": "-1.25",
                        "away_line": "+1.25",
                        "home_price": "1.91",
                        "away_price": "1.93",
                        "bookmaker_count": 4,
                    }
                },
                "card_hash": "hash-1",
                "outcome_tracked": False,
                "source": "decision_contract",
            }
        ],
    }


def _analysis_v4_decision() -> dict[str, object]:
    return build_recommendation_decision_v4(
        {
            "fixture_id": "fixture-1",
            "competition_id": "world_cup_2026",
            "season": "2026",
            "kickoff_utc": "2026-07-07T16:00:00Z",
            "kickoff_revision_or_fixture_identity_hash": "d" * 64,
            "provider": "api-football",
            "bookmaker_id": "unibet",
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY",
            "exact_line": "+1.25",
            "capture_id": "capture-1",
            "captured_at": "2026-07-07T12:00:00Z",
            "decision_evaluated_at": "2026-07-07T12:10:00Z",
            "quote_observation_ids": {
                "home": "observation-home",
                "away": "observation-away",
            },
            "raw_payload_sha256": "a" * 64,
            "source_revision": "e" * 40,
            "model_version": "model-v1",
            "calibration_version": "calibration-v1",
            "serializer_version": CURRENT_SERIALIZER_VERSION.value,
            "recommendation_schema_version": RECOMMENDATION_SCHEMA_VERSION,
            "quote_schema_version": "w2.quote_identity.v1",
            "model_input_manifest_hash": "b" * 64,
            "decimal_odds": "1.93",
            "canonical_mainline_identity": {
                "market": "ASIAN_HANDICAP",
                "line": "-1.25",
                "selected_side_line": "+1.25",
                "candidate_role": "MARKET_MAINLINE",
                "quote_identity_hash": "c" * 64,
            },
            "settlement_distribution": {
                "WIN": "0.5",
                "HALF_WIN": "0.1",
                "PUSH": "0.1",
                "HALF_LOSS": "0.1",
                "LOSS": "0.2",
            },
            "fair_odds": "1.4545",
            "expected_value": "0.2615",
            "uncertainty": "0.01",
            "readiness": {
                "status": "READY",
                "quote_identity_status": "COMPLETE",
                "quote_freshness_status": "COMPLETE",
                "quote_freshness_policy_version": "w2.quote_freshness.v1",
                "quote_age_seconds": 300,
                "quote_max_age_seconds": 1800,
                "model_status": "READY",
            },
            "capability_status": "FORMAL_DISABLED",
            "formal_admission": {
                "status": "DISABLED",
                "readiness_hash": None,
                "approval_hash": None,
                "candidate_identity_hash": None,
            },
        }
    ).as_dict()


def test_forward_outcome_ledger_dry_run_does_not_write(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    payload = run_forward_outcome_ledger(
        _day_view(),
        repository=repository,
        dry_run=True,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["lock_capture_write"] is False
    assert payload["settlement_write"] is False
    assert payload["record_count"] == 1
    assert payload["written"] == 0
    assert repository.records() == []


def test_capture_supersession_is_append_only_and_removes_pending_entry(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card.update(  # type: ignore[union-attr]
        {
            "decision_tier": "ANALYSIS_PICK",
            "outcome_tracked": True,
            "pick": {
                "market": "ASIAN_HANDICAP",
                "selection": "AWAY",
                "line": "+1.25",
            },
        }
    )
    run_forward_outcome_ledger(
        day_view,
        repository=repository,
        dry_run=False,
        write_db=True,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    capture_hash = repository.records()[0]["capture_identity_hash"]
    assert len(pending_outcome_entries(repository=repository)) == 1

    result = append_capture_supersessions(
        [{"fixture_id": "fixture-1", "capture_identity_hash": capture_hash}],
        repository=repository,
        reason_code="AH_SELECTED_SIDE_LINE_MISMATCH",
        superseded_at=datetime(2026, 7, 7, 13, 0, tzinfo=UTC),
        dry_run=False,
        write_db=True,
    )

    assert result["written"] == 1
    assert len(pending_outcome_entries(repository=repository)) == 0
    row = repository.records({"supersession"})[0]
    assert row["supersession_status"] == "SUPERSEDED"
    assert row["target_capture_identity_hash"] == capture_hash


def test_forward_capture_does_not_consume_legacy_secondary_picks_without_v4() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["secondary_picks"] = [  # type: ignore[index]
        {"market": "TOTALS", "selection": "UNDER", "line": "2.5"},
        {"market": "ASIAN_HANDICAP", "selection": "HOME_AH", "line": "-0.5"},
    ]
    records = build_forward_outcome_records(
        day_view,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    assert records[0]["secondary_picks"] == []


def test_forward_outcome_ledger_write_is_idempotent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    first = run_forward_outcome_ledger(
        _day_view(),
        repository=repository,
        dry_run=False,
        write_db=True,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    second = run_forward_outcome_ledger(
        _day_view(),
        repository=repository,
        dry_run=False,
        write_db=True,
        captured_at=datetime(2026, 7, 7, 12, 5, tzinfo=UTC),
    )

    rows = repository.records()
    assert first["written"] == 1
    assert second["written"] == 0
    assert second["skipped_existing"] == 1
    assert len(rows) == 1
    assert rows[0]["schema_version"] == "w2.forward_outcome_ledger.v3"
    assert rows[0]["recommendation_scope"] == "SHADOW"
    assert rows[0]["fixture_identity"] == {
        "fixture_id": "fixture-1",
        "kickoff_utc": "2026-07-07T16:00:00Z",
        "competition_id": "world_cup_2026",
        "competition_name": "World Cup",
        "home_team_id": None,
        "home_team_name": "Argentina",
        "away_team_id": None,
        "away_team_name": "Egypt",
    }
    assert len(rows[0]["capture_identity_hash"]) == 64
    assert rows[0]["quote_provenance"]["schema_version"] == "w2.quote_provenance.v1"
    assert rows[0]["artifact_provenance"]["artifact_hash"] == "hash-1"
    assert rows[0]["not_a_lock"] is True
    assert rows[0]["posthoc_only"] is True
    assert rows[0]["record_type"] == "capture"
    assert rows[0]["shadow_pick"] == {
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
        "model_fair_line": -1.5,
        "market_line_at_capture": -1.25,
        "divergence_line_units": -0.25,
        "derived_from": "model_market_divergence",
        "display_tier_at_capture": "WATCH",
        "shadow": True,
        "not_a_recommendation": True,
        "not_displayed": True,
    }
    assert rows[0]["current_odds"]["ah"]["bookmaker_count"] == 4


def test_forward_outcome_ledger_writes_changed_card_at_next_tick(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    first = _day_view()
    second = _day_view()
    second["cards"][0]["card_hash"] = "hash-2"  # type: ignore[index]

    run_forward_outcome_ledger(
        first,
        repository=repository,
        dry_run=False,
        write_db=True,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    result = run_forward_outcome_ledger(
        second,
        repository=repository,
        dry_run=False,
        write_db=True,
        captured_at=datetime(2026, 7, 7, 12, 5, tzinfo=UTC),
    )

    assert result["written"] == 1
    assert len(repository.records()) == 2


def test_independent_repositories_dedupe_runtime_retry_and_reject_conflict(
    tmp_path: Path,
) -> None:
    first_repository = _repository(tmp_path)
    second_repository = OutcomeLedgerRepository(first_repository.engine)
    first_record = build_forward_outcome_records(
        _day_view(),
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )[0]
    retry_record = build_forward_outcome_records(
        _day_view(),
        captured_at=datetime(2026, 7, 7, 12, 5, tzinfo=UTC),
    )[0]

    first_repository.append([first_record], dry_run=False, write_db=True)
    retry = second_repository.append([retry_record], dry_run=False, write_db=True)

    assert retry["written"] == 0
    assert retry["already_imported"] == 1
    assert len(first_repository.records()) == 1

    conflict = dict(retry_record)
    conflict["reason_code"] = "CHANGED_WITHOUT_IDENTITY_CHANGE"
    with pytest.raises(OutcomeLedgerError, match="LEDGER_IMPORT_IDENTITY_CONFLICT"):
        second_repository.append([conflict], dry_run=False, write_db=True)
    assert len(first_repository.records()) == 1


def test_forward_outcome_ledger_validation_pick_binds_entry_quote(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card.update(  # type: ignore[union-attr]
        {
            "decision_tier": "ANALYSIS_PICK",
            "reason_code": "ANALYSIS_ONLY",
            "outcome_tracked": True,
            "pick": {
                "market": "ASIAN_HANDICAP",
                "selection": "AWAY",
                "line": "+1.25",
                "odds": None,
            },
            "recommendation_decision_v4": _analysis_v4_decision(),
            "recommendation_decision_v3": {
                "schema_version": "w2.recommendation_decision.v3",
                "outcome": "ANALYSIS_PICK",
                "selected_candidate": {
                    "market": "ASIAN_HANDICAP",
                    "selection": "HOME",
                    "line": "-1.25",
                    "odds": "1.91",
                },
                "decision_hash": "legacy-v3-decision-hash",
            },
        }
    )
    card["current_odds"]["ah"]["away_line"] = "+1.5"
    card["current_odds"]["ah"]["away_price"] = "2.05"

    payload = run_forward_outcome_ledger(
        day_view,
        repository=repository,
        dry_run=False,
        write_db=True,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    rows = repository.records()
    assert payload["written"] == 1
    assert rows[0]["recommendation_scope"] == "VALIDATION"
    assert rows[0]["outcome_tracked"] is True
    assert rows[0]["lock_eligible"] is False
    assert rows[0]["pick"]["selection"] == "AWAY_AH"
    assert rows[0]["pick"]["entry_line"] == "1.25"
    assert rows[0]["pick"]["entry_price"] == "1.93"
    assert rows[0]["pick"]["odds"] == "1.93"
    assert rows[0]["decision_hash"] == _analysis_v4_decision()["decision_hash"]


def test_forward_outcome_ledger_never_first_captures_after_kickoff() -> None:
    payload = run_forward_outcome_ledger(
        _day_view(),
        dry_run=True,
        captured_at=datetime(2026, 7, 7, 16, 0, tzinfo=UTC),
    )

    assert payload["record_count"] == 0
    assert payload["records"] == []


def test_forward_outcome_ledger_rejects_tampered_v4_without_v3_fallback() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    decision = _analysis_v4_decision()
    decision["selected_candidate"]["selection"] = "HOME"
    card["recommendation_decision_v4"] = decision  # type: ignore[index]
    card["recommendation_decision_v3"] = {  # type: ignore[index]
        "outcome": "ANALYSIS_PICK",
        "selected_candidate": {
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY",
            "line": "+1.25",
            "odds": "1.93",
        },
    }

    with pytest.raises(
        ValueError,
        match="FORWARD_CAPTURE_RECOMMENDATION_DECISION_V4_INVALID",
    ):
        build_forward_outcome_records(
            day_view,
            captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
        )


def test_forward_outcome_ledger_uses_public_team_name_fallbacks(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card.pop("home_team_name")  # type: ignore[union-attr]
    card.pop("away_team_name")  # type: ignore[union-attr]
    card["home_name"] = "Public Home"  # type: ignore[index]
    card["away_name"] = "Public Away"  # type: ignore[index]

    payload = run_forward_outcome_ledger(
        day_view,
        repository=repository,
        dry_run=False,
        write_db=True,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    rows = repository.records()
    assert payload["written"] == 1
    assert rows[0]["fixture_identity"]["home_team_name"] == "Public Home"
    assert rows[0]["fixture_identity"]["away_team_name"] == "Public Away"


def test_forward_outcome_ledger_captures_and_settles_independent_ou_shadow(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["current_odds"]["ou"] = {  # type: ignore[index]
        "line": "2.5",
        "over_price": "1.91",
        "under_price": "1.93",
    }
    card["pricing_shadow"] = {"fair_ou": 2.75, "market_ou": 2.5}  # type: ignore[index]

    capture = run_forward_outcome_ledger(
        day_view,
        repository=repository,
        dry_run=False,
        write_db=True,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert capture["written"] == 2
    capture_rows = repository.records({"capture"})
    assert {
        (row["shadow_pick"]["market"], row["shadow_pick"]["selection"])
        for row in capture_rows
    } == {("ASIAN_HANDICAP", "HOME_AH"), ("TOTALS", "OVER")}
    assert all(row["shadow_pick"]["not_a_recommendation"] is True for row in capture_rows)
    assert all(row["shadow_pick"]["not_displayed"] is True for row in capture_rows)

    _seed_results(repository, [_result("fixture-1", 2, 1)])
    settlement = backfill_outcomes(repository=repository, dry_run=False, write_db=True)

    assert settlement["written"] == 2
    outcomes = repository.records({"outcome"})
    assert {(row["market"], row["selection"], row["settlement_outcome"]) for row in outcomes} == {
        ("ASIAN_HANDICAP", "HOME_AH", "HALF_LOSS"),
        ("TOTALS", "OVER", "WIN"),
    }


def test_forward_outcome_ledger_rejects_cross_line_ou_shadow(tmp_path: Path) -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["current_odds"]["ou"] = {  # type: ignore[index]
        "line": "2.75",
        "over_price": "1.91",
        "under_price": "1.93",
    }
    card["pricing_shadow"] = {"fair_ou": 2.75, "market_ou": 2.5}  # type: ignore[index]

    records = build_forward_outcome_records(
        day_view,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert [row["shadow_pick"]["market"] for row in records] == ["ASIAN_HANDICAP"]


def test_legacy_v3_pick_cannot_create_new_recommendation_capture() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["decision_tier"] = "ANALYSIS_PICK"  # type: ignore[index]
    card["outcome_tracked"] = True  # type: ignore[index]
    card["pick"] = {  # type: ignore[index]
        "market": "ASIAN_HANDICAP",
        "selection": "AWAY",
        "line": "+1.25",
        "odds": "1.93",
    }
    card["recommendation_decision_v3"] = {  # type: ignore[index]
        "schema_version": "w2.recommendation_decision.v3",
        "outcome": "ANALYSIS_PICK",
        "selected_candidate": {
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY",
            "line": "+1.25",
            "odds": "1.93",
        },
        "decision_hash": "legacy-v3-decision-hash",
    }
    card["current_odds"]["ou"] = {  # type: ignore[index]
        "line": "2.5",
        "over_price": "1.91",
        "under_price": "1.93",
    }
    card["pricing_shadow"] = {"fair_ou": 2.75, "market_ou": 2.5}  # type: ignore[index]

    records = build_forward_outcome_records(
        day_view,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert {(row["recommendation_scope"], row["shadow_pick"]["market"]) for row in records} == {
        ("SHADOW", "ASIAN_HANDICAP"),
        ("SHADOW", "TOTALS"),
    }
    assert all(row["not_a_lock"] is True for row in records)
    assert all(row["decision_hash"] is None for row in records)
    assert all(row["decision_tier"] == "NOT_READY" for row in records)
    assert all(row["outcome_tracked"] is False for row in records)
    assert all(row["pick"]["selection"] != "AWAY_AH" for row in records)


def test_forward_outcome_backfill_deduplicates_same_capture_across_day_files(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    capture = _capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")
    next_day = dict(capture)
    repository.append([capture, next_day], dry_run=False, write_db=True)
    _seed_results(repository, [_result("fixture-1", 2, 0)])

    payload = backfill_outcomes(
        repository=repository,
        dry_run=False,
        write_db=True,
    )

    outcomes = repository.records({"outcome"})
    assert payload["written"] == 1
    assert payload["record_count"] == 1
    assert len(outcomes) == 1


def test_forward_outcome_backfill_does_not_void_shadow_without_quote(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    capture = _capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")
    capture["decision_tier"] = "WATCH"
    capture["recommendation_scope"] = "SHADOW"
    capture["outcome_tracked"] = False
    capture["pick"] = None
    capture["shadow_pick"] = {
        "market": "TOTALS",
        "selection": "OVER",
        "not_a_recommendation": True,
        "not_displayed": True,
    }
    repository.append([capture], dry_run=False, write_db=True)
    _seed_results(repository, [_result("fixture-1", 2, 1)])

    payload = backfill_outcomes(
        repository=repository,
        dry_run=False,
        write_db=True,
    )

    assert payload["written"] == 0
    assert payload["record_count"] == 0
    assert payload["unresolved_count"] == 1
    assert payload["status"] == "PARTIAL"


def test_forward_outcome_ledger_shadow_pick_is_null_without_lines(
    tmp_path: Path,
) -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    divergence = card["model_market_divergence"]  # type: ignore[index]
    divergence.pop("model_fair_line")  # type: ignore[union-attr]

    payload = run_forward_outcome_ledger(
        day_view,
        dry_run=True,
        repository=_repository(tmp_path),
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert payload["records"][0]["shadow_pick"] is None


def test_forward_outcome_ledger_cli_import_dry_run_text_and_json(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    source_root = tmp_path / "runtime"
    ledger_root = source_root / "forward_outcome_ledger"
    ledger_root.mkdir(parents=True)
    _write_jsonl(
        ledger_root / "2026-07-07_staging.jsonl",
        [_capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")],
    )

    text_result = _run_import_cli(tmp_path, source_root)
    json_result = _run_import_cli(tmp_path, source_root, "--json")

    assert text_result.returncode == 0
    assert "source_records=1" in text_result.stdout
    assert "reconciliation=PASS" in text_result.stdout
    assert json_result.returncode == 0
    payload = json.loads(json_result.stdout)
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["source_record_count"] == 1
    assert payload["reconciliation_status"] == "PASS"


def test_forward_outcome_ledger_cli_write_and_idempotent_text_exit_zero(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    source_root = tmp_path / "runtime"
    ledger_root = source_root / "forward_outcome_ledger"
    ledger_root.mkdir(parents=True)
    _write_jsonl(
        ledger_root / "capture.jsonl",
        [_capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")],
    )
    write_args = (
        "--no-dry-run",
        "--write-db",
        "--confirm-write",
        "EVAL_01A_IMPORT_RUNTIME_LEDGER",
    )

    first = _run_import_cli(tmp_path, source_root, *write_args)
    second = _run_import_cli(tmp_path, source_root, *write_args)

    assert first.returncode == 0
    assert "db_writes=1" in first.stdout
    assert second.returncode == 0
    assert "already_imported=1" in second.stdout
    assert "db_writes=0" in second.stdout


def test_forward_outcome_ledger_cli_import_failures_exit_nonzero(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    cases: list[tuple[str, str]] = []

    malformed = tmp_path / "malformed" / "forward_outcome_ledger"
    malformed.mkdir(parents=True)
    (malformed / "broken.jsonl").write_text("{broken}\n", encoding="utf-8")
    cases.append(("malformed", str(malformed.parent)))

    identity = tmp_path / "identity" / "forward_outcome_ledger"
    identity.mkdir(parents=True)
    first_capture = _capture("fixture-1", "same", home_line="-1", home_price="1.9")
    conflict_capture = dict(first_capture)
    conflict_capture["decision_hash"] = "different"
    _write_jsonl(identity / "conflict.jsonl", [first_capture, conflict_capture])
    cases.append(("identity", str(identity.parent)))

    result = tmp_path / "result" / "forward_outcome_ledger"
    result.mkdir(parents=True)
    _write_jsonl(
        result / "conflict.jsonl",
        [
            _cli_outcome("capture-1", home=2),
            _cli_outcome("capture-2", home=3),
        ],
    )
    cases.append(("result", str(result.parent)))

    for name, source_root in cases:
        completed = _run_import_cli(
            tmp_path,
            Path(source_root),
            "--no-dry-run",
            "--write-db",
            "--confirm-write",
            "EVAL_01A_IMPORT_RUNTIME_LEDGER",
        )
        assert completed.returncode != 0, name


def test_forward_outcome_ledger_cli_missing_confirmation_exits_nonzero(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    source_root = tmp_path / "runtime"
    ledger_root = source_root / "forward_outcome_ledger"
    ledger_root.mkdir(parents=True)
    _write_jsonl(
        ledger_root / "capture.jsonl",
        [_capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")],
    )

    completed = _run_import_cli(
        tmp_path,
        source_root,
        "--no-dry-run",
        "--write-db",
    )

    assert completed.returncode != 0


@pytest.mark.parametrize(
    ("status", "reconciliation_status"),
    (("BLOCKED", "PASS"), ("PASS", "BLOCKED"), ("FAIL", "PASS"), ("PASS", "FAIL")),
)
def test_forward_outcome_ledger_cli_blocked_or_failed_payload_exits_nonzero(
    tmp_path: Path,
    status: str,
    reconciliation_status: str,
) -> None:
    code = f"""
import sys
from scripts import run_w2_forward_outcome_ledger as cli
cli.import_runtime_ledger = lambda *args, **kwargs: {{
    "status": {status!r},
    "reconciliation_status": {reconciliation_status!r},
    "malformed_count": 0,
    "result_conflict_count": 0,
}}
sys.argv = [
    "run_w2_forward_outcome_ledger.py",
    "--import-runtime-ledger",
    "--source-root",
    {str(tmp_path)!r},
    "--json",
]
raise SystemExit(cli.main())
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0


def test_forward_outcome_ledger_cli_output_failure_exits_nonzero(
    tmp_path: Path,
) -> None:
    code = f"""
import sys
from scripts import run_w2_forward_outcome_ledger as cli
cli.import_runtime_ledger = lambda *args, **kwargs: {{
    "status": "PASS",
    "reconciliation_status": "PASS",
}}
sys.argv = [
    "run_w2_forward_outcome_ledger.py",
    "--import-runtime-ledger",
    "--source-root",
    {str(tmp_path)!r},
]
raise SystemExit(cli.main())
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0


def test_forward_outcome_backfill_writes_win_push_half_loss_and_fails_closed_without_quote(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    repository.append(
        [
            _capture("fixture-win", "hash-win", home_line="-1", home_price="1.9"),
            _capture("fixture-push", "hash-push", home_line="-1", home_price="1.9"),
            _capture("fixture-half-loss", "hash-half", home_line="-0.25", home_price="1.9"),
            _capture("fixture-void", "hash-void", home_line=None, home_price="1.9"),
        ],
        dry_run=False,
        write_db=True,
    )
    _seed_results(
        repository,
        [
            _result("fixture-win", 2, 0),
            _result("fixture-push", 1, 0),
            _result("fixture-half-loss", 0, 0),
            _result("fixture-void", 2, 0),
        ],
    )

    payload = backfill_outcomes(
        repository=repository,
        dry_run=False,
        write_db=True,
        settled_at=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
    )

    outcomes = {row["fixture_id"]: row for row in repository.records({"outcome"})}
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 3
    assert payload["settlement_write"] is False
    assert payload["written"] == 3
    assert outcomes["fixture-win"]["settlement_outcome"] == "WIN"
    assert outcomes["fixture-push"]["settlement_outcome"] == "PUSH"
    assert outcomes["fixture-half-loss"]["settlement_outcome"] == "HALF_LOSS"
    assert "fixture-void" not in outcomes
    assert outcomes["fixture-win"]["settled_side"] == "pick"
    assert outcomes["fixture-win"]["final_score"] == {
        "home": 2,
        "away": 0,
        "status": "FT",
    }


def test_forward_outcome_backfill_is_idempotent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.append(
        [_capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")],
        dry_run=False,
        write_db=True,
    )
    _seed_results(repository, [_result("fixture-1", 2, 0)])

    first = backfill_outcomes(repository=repository, dry_run=False, write_db=True)
    second = backfill_outcomes(repository=repository, dry_run=False, write_db=True)

    assert first["written"] == 1
    assert second["written"] == 0
    assert second["skipped_existing"] == 0
    assert second["status"] == "NO_DUE_WORK"


def test_forward_outcome_backfill_ignores_non_ft_results(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.append(
        [_capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")],
        dry_run=False,
        write_db=True,
    )

    payload = backfill_outcomes(
        repository=repository,
        dry_run=False,
        write_db=True,
    )

    assert payload["record_count"] == 0
    assert payload["written"] == 0


def test_forward_outcome_backfill_settles_shadow_pick_separately(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    capture = _capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")
    capture["shadow_pick"] = {
        "market": "ASIAN_HANDICAP",
        "selection": "AWAY_AH",
        "not_a_recommendation": True,
        "not_displayed": True,
    }
    capture["current_odds"]["ah"]["away_line"] = "+1"
    capture["current_odds"]["ah"]["away_price"] = "1.8"
    repository.append([capture], dry_run=False, write_db=True)
    _seed_results(repository, [_result("fixture-1", 2, 0)])

    payload = backfill_outcomes(
        repository=repository,
        dry_run=False,
        write_db=True,
    )

    outcomes = repository.records({"outcome"})
    assert payload["written"] == 2
    assert {row["settled_side"] for row in outcomes} == {"pick", "shadow_pick"}
    shadow = [row for row in outcomes if row["settled_side"] == "shadow_pick"][0]
    assert shadow["settlement_outcome"] == "LOSS"
    assert shadow["selection"] == "AWAY_AH"


def test_forward_outcome_backfill_settles_totals_and_uses_fulltime_score(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    capture = _capture("fixture-ou", "hash-ou", home_line="-1", home_price="1.9")
    capture["pick"] = {"market": "TOTALS", "selection": "OVER"}
    capture["current_odds"] = {"ou": {"line": "2.75", "over_price": "1.9", "under_price": "1.9"}}
    repository.append([capture], dry_run=False, write_db=True)
    _seed_results(
        repository,
        [
            {
                "fixture_id": "fixture-ou",
                "status": "AET",
                "home_score": 1,
                "away_score": 1,
            }
        ],
    )

    payload = backfill_outcomes(
        repository=repository,
        dry_run=False,
        write_db=True,
    )

    outcome = repository.records({"outcome"})[0]
    assert payload["status"] == "PASS"
    assert outcome["final_score"] == {"home": 1, "away": 1, "status": "AET"}
    assert outcome["settlement_outcome"] == "LOSS"


def test_pending_entries_and_zero_result_are_not_false_pass(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    capture = _capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")
    repository.append([capture], dry_run=False, write_db=True)

    pending = pending_outcome_entries(
        repository=repository,
        now=datetime(2026, 7, 8, 6, 0, tzinfo=UTC),
    )
    payload = backfill_outcomes(repository=repository)

    assert len(pending) == 1
    assert pending[0]["due"] is True
    assert payload["status"] == "PARTIAL"
    assert payload["pending_count"] == 1
    assert payload["unresolved_count"] == 1


def test_v3_validation_identity_conflict_is_not_settled(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    first = _capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")
    first.update(
        {
            "schema_version": "w2.forward_outcome_ledger.v3",
            "recommendation_scope": "VALIDATION",
            "outcome_tracked": True,
            "capture_identity_hash": "capture-1",
            "competition_id": "league-1",
            "home_team_name": "Home",
            "away_team_name": "Away",
        }
    )
    conflict = dict(first)
    conflict["captured_at"] = "2026-07-07T01:00:00Z"
    conflict["capture_identity_hash"] = "capture-2"
    conflict["pick"] = {"market": "ASIAN_HANDICAP", "selection": "AWAY_AH"}
    repository.append([first, conflict], dry_run=False, write_db=True)
    _seed_results(repository, [_result("fixture-1", 2, 0)])

    payload = backfill_outcomes(
        repository=repository,
    )

    assert payload["status"] == "NO_DUE_WORK"
    assert payload["record_count"] == 0


def _capture(
    fixture_id: str,
    card_hash: str,
    *,
    home_line: str | None,
    home_price: str | None,
) -> dict[str, object]:
    ah = {
        "away_line": "+1",
        "away_price": "1.8",
    }
    if home_line is not None:
        ah["home_line"] = home_line
    if home_price is not None:
        ah["home_price"] = home_price
    return {
        "schema_version": "w2.forward_outcome_ledger.v2",
        "record_type": "capture",
        "captured_at": "2026-07-07T00:00:00Z",
        "football_day": "2026-07-07",
        "environment": "staging",
        "fixture_id": fixture_id,
        "kickoff_utc": "2026-07-08T02:00:00Z",
        "competition_id": "world_cup_2026",
        "competition_name": "World Cup",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "card_hash": card_hash,
        "decision_tier": "ANALYSIS_PICK",
        "recommendation_scope": "VALIDATION",
        "outcome_tracked": True,
        "pick": {"market": "ASIAN_HANDICAP", "selection": "HOME_AH"},
        "current_odds": {"ah": ah},
    }


def _result(
    fixture_id: str,
    home: int,
    away: int,
    *,
    status: str = "FT",
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "status": status,
        "home_score": home,
        "away_score": away,
    }


def _repository(root: Path) -> OutcomeLedgerRepository:
    engine = create_engine(f"sqlite+pysqlite:///{root / 'outcome-ledger.db'}")
    ResultModel.__table__.create(engine, checkfirst=True)
    OutcomeLedgerModel.__table__.create(engine, checkfirst=True)
    return OutcomeLedgerRepository(engine)


def _run_import_cli(
    root: Path,
    source_root: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_forward_outcome_ledger.py",
            "--import-runtime-ledger",
            "--source-root",
            str(source_root),
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "W2_DATABASE_URL": f"sqlite+pysqlite:///{root / 'outcome-ledger.db'}",
        },
    )


def _cli_outcome(capture_hash: str, *, home: int) -> dict[str, object]:
    return {
        "schema_version": "w2.forward_outcome_ledger.v3",
        "record_type": "outcome",
        "fixture_id": "101",
        "settled_at": "2026-07-08T03:00:00Z",
        "capture_identity_hash": capture_hash,
        "settled_side": "pick",
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
        "final_score": {"home": home, "away": 1, "status": "FT"},
        "settlement_outcome": "WIN",
    }


def _seed_results(
    repository: OutcomeLedgerRepository,
    rows: list[dict[str, object]],
) -> None:
    with Session(repository.engine) as session:
        for row in rows:
            status = str(row["status"])
            if status not in {"FT", "AET", "PEN"}:
                continue
            fixture_id = str(row["fixture_id"])
            home = int(row["home_score"])
            away = int(row["away_score"])
            identity = f"{fixture_id}:{home}:{away}"
            session.add(
                ResultModel(
                    fixture_id=fixture_id,
                    home_goals=home,
                    away_goals=away,
                    result_status=status,
                    confirmed_at=datetime(2026, 7, 8, tzinfo=UTC),
                    source_payload_sha256=sha256(identity.encode()).hexdigest(),
                    source_capture_id=None,
                    result_hash=sha256(f"result:{identity}".encode()).hexdigest(),
                )
            )
        session.commit()


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows),
        encoding="utf-8",
    )
