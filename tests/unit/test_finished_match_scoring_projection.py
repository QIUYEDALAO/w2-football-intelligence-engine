from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.tracking import finished_match_scoring_cli
from w2.tracking.finished_match_scoring_projection import (
    WRITE_CONFIRMATION_PHRASE,
    run_finished_match_scoring_projection,
)
from w2.tracking.forward_ledger_performance import (
    CLV_METHOD,
    _brier,
    _log_loss,
    _probability_vector,
    _rps,
)
from w2.tracking.outcome_ledger_repository import (
    IMPORT_CONFIRMATION_PHRASE,
    ImportRecord,
    OutcomeLedgerRepository,
    import_runtime_ledger,
    payload_sha256,
)
from w2.tracking.performance_scoring import brier, log_loss, probability_vector, rps

KICKOFF = datetime(2026, 7, 20, 16, 0, tzinfo=UTC)


def test_latest_complete_prekickoff_capture_scores_watch_without_pick(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-1", home=2, away=1)
    _seed_identity(repository, "fixture-1", kickoff=KICKOFF)
    old = _capture("fixture-1", KICKOFF - timedelta(hours=2), identity="old")
    latest = _capture(
        "fixture-1",
        KICKOFF - timedelta(minutes=5),
        identity="latest",
        model=(0.6, 0.2, 0.2),
        market=(0.4, 0.3, 0.3),
    )
    post = _capture("fixture-1", KICKOFF, identity="post")
    repository.append([old, latest, post], dry_run=False, write_db=True)

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, "performance:fixture:fixture-1")

    assert result["status"] == "PASS"
    assert result["scored_count"] == 1
    assert payload["status"] == "SCORED"
    assert payload["source_capture_identity_hash"] == "latest"
    assert payload["model_probabilities"] == [0.6, 0.2, 0.2]
    assert payload["clv_status"] == "NOT_APPLICABLE_NO_PICK"
    assert payload["clv_method"] == CLV_METHOD


def test_superseded_capture_is_excluded_and_missing_vector_is_checkpointed(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    canonical = "api_football:1576809"
    _seed_result(repository, canonical, home=1, away=1)
    _seed_identity(
        repository,
        canonical,
        kickoff=KICKOFF,
        provider_fixture_id="1576809",
    )
    complete = _capture(
        "1576809",
        KICKOFF - timedelta(minutes=5),
        identity="superseded",
        kickoff=KICKOFF,
    )
    incomplete = _capture(
        canonical,
        KICKOFF - timedelta(minutes=10),
        identity="active",
        model=None,
        kickoff=KICKOFF,
    )
    repository.append(
        [
            complete,
            incomplete,
            {
                "schema_version": "w2.forward_outcome_ledger.v3",
                "record_type": "supersession",
                "fixture_id": canonical,
                "captured_at": (KICKOFF - timedelta(minutes=1)).isoformat(),
                "supersession_status": "SUPERSEDED",
                "target_capture_identity_hash": "superseded",
                "supersession_hash": "supersession-2",
            },
        ],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{canonical}")

    assert result["status"] == "PASS"
    assert result["not_scorable_count"] == 1
    assert payload["status"] == "NOT_SCORABLE"
    assert payload["reason_codes"] == ["MODEL_PROBABILITY_VECTOR_MISSING"]


def test_equal_timestamp_different_identity_is_blocked(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-3", home=0, away=2)
    _seed_identity(repository, "fixture-3", kickoff=KICKOFF)
    captured = KICKOFF - timedelta(minutes=10)
    first = _capture("fixture-3", captured, identity="capture-a")
    second = _capture(
        "fixture-3",
        captured,
        identity="capture-b",
        model=(0.2, 0.2, 0.6),
    )
    for capture in (first, second):
        capture["card_hash"] = "same-card"
        capture["artifact_provenance"] = {"artifact_hash": "same-artifact"}
    repository.append(
        [first, second],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, "performance:fixture:fixture-3")

    assert result["status"] == "BLOCKED"
    assert payload["status"] == "BLOCKED"
    assert payload["reason_codes"] == ["MODEL_PROBABILITY_VECTOR_CONFLICT"]


def test_latest_group_missing_identity_is_not_scorable_with_audit(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-missing-identity", home=1, away=0)
    _seed_identity(repository, "fixture-missing-identity", kickoff=KICKOFF)
    captures = [
        _capture(
            "fixture-missing-identity",
            KICKOFF - timedelta(minutes=5),
            identity=identity,
            model=None,
            market=None,
            kickoff=KICKOFF,
        )
        for identity in ("missing-a", "missing-b")
    ]
    for capture in captures:
        capture.pop("capture_identity_hash")
        capture.pop("probability_identity")
        capture["card_hash"] = "same-card"
        capture["artifact_provenance"] = {"artifact_hash": "same-artifact"}
    _distinguish_legacy_siblings(captures)
    repository.append(captures, dry_run=False, write_db=True)

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(
        repository,
        "performance:fixture:fixture-missing-identity",
    )

    assert result["status"] == "PASS"
    assert result["not_scorable_count"] == 1
    assert payload["status"] == "NOT_SCORABLE"
    assert payload["reason_codes"] == [
        "CAPTURE_IDENTITY_MISSING",
        "MARKET_PROBABILITY_VECTOR_MISSING",
        "MODEL_PROBABILITY_VECTOR_MISSING",
    ]
    assert payload["latest_group_capture_count"] == 2
    assert payload["latest_group_identity_bearing_count"] == 0
    assert payload["latest_group_identity_missing_count"] == 2
    assert payload["latest_group_fixture_signature_complete_count"] == 2
    assert payload["latest_group_fixture_signature_incomplete_count"] == 0
    assert payload["capture_selection_status"] == "CAPTURE_IDENTITY_MISSING"
    assert payload["source_capture_identity_hash"] is None
    assert payload["source_capture_group_hash"] is None
    assert payload["selected_scoring_capture_at"] is None


@pytest.mark.parametrize(
    ("vector_name", "reason"),
    [
        ("model", "MODEL_PROBABILITY_VECTOR_CONFLICT"),
        ("market", "MARKET_PROBABILITY_VECTOR_CONFLICT"),
    ],
)
def test_latest_missing_identity_does_not_mask_vector_conflict(
    tmp_path: Path,
    vector_name: str,
    reason: str,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = f"fixture-missing-{vector_name}-conflict"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    captured_at = KICKOFF - timedelta(minutes=5)
    first = _capture(
        fixture_id,
        captured_at,
        identity="first",
        kickoff=KICKOFF,
    )
    second = _capture(
        fixture_id,
        captured_at,
        identity="second",
        model=(0.2, 0.2, 0.6) if vector_name == "model" else (0.5, 0.3, 0.2),
        market=(0.2, 0.2, 0.6) if vector_name == "market" else (0.4, 0.35, 0.25),
        kickoff=KICKOFF,
    )
    for capture in (first, second):
        capture.pop("capture_identity_hash")
        capture["card_hash"] = "same-card"
        capture["artifact_provenance"] = {"artifact_hash": "same-artifact"}
    _distinguish_legacy_siblings([first, second])
    repository.append([first, second], dry_run=False, write_db=True)

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{fixture_id}")

    assert result["status"] == "BLOCKED"
    assert payload["reason_codes"] == [reason]


@pytest.mark.parametrize("conflict_field", ["card", "artifact"])
def test_latest_missing_identity_does_not_mask_business_identity_conflict(
    tmp_path: Path,
    conflict_field: str,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = f"fixture-missing-{conflict_field}-conflict"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    captured_at = KICKOFF - timedelta(minutes=5)
    captures = [
        _capture(
            fixture_id,
            captured_at,
            identity=identity,
            kickoff=KICKOFF,
        )
        for identity in ("first", "second")
    ]
    for capture in captures:
        capture.pop("capture_identity_hash")
        capture["card_hash"] = "same-card"
        capture["artifact_provenance"] = {"artifact_hash": "same-artifact"}
    _distinguish_legacy_siblings(captures)
    if conflict_field == "card":
        captures[1]["card_hash"] = "different-card"
    else:
        captures[1]["artifact_provenance"] = {
            "artifact_hash": "different-artifact"
        }
    repository.append(captures, dry_run=False, write_db=True)

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{fixture_id}")

    assert result["status"] == "BLOCKED"
    assert payload["reason_codes"] == [
        "EQUAL_TIMESTAMP_DIFFERENT_BUSINESS_IDENTITY"
    ]


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("checkpoint", "DYNAMIC_CHECKPOINT_CONFLICT"),
        ("lineup_input_hash", "DYNAMIC_LINEUP_HASH_CONFLICT"),
    ],
)
def test_latest_missing_identity_does_not_mask_lifecycle_conflict(
    tmp_path: Path,
    field: str,
    reason: str,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = f"fixture-missing-{field}-conflict"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    captured_at = KICKOFF - timedelta(minutes=5)
    captures = [
        _capture(
            fixture_id,
            captured_at,
            identity=identity,
            kickoff=KICKOFF,
        )
        for identity in ("first", "second")
    ]
    for capture in captures:
        capture.pop("capture_identity_hash")
        capture["card_hash"] = "same-card"
        capture["artifact_provenance"] = {"artifact_hash": "same-artifact"}
    _distinguish_legacy_siblings(captures)
    captures[0][field] = "first"
    captures[1][field] = "second"
    repository.append(captures, dry_run=False, write_db=True)

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{fixture_id}")

    assert result["status"] == "BLOCKED"
    assert payload["reason_codes"] == [reason]


def test_latest_fixture_signature_complete_incomplete_is_blocked(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-signature-mixed"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    captured_at = KICKOFF - timedelta(minutes=5)
    complete = _capture(
        fixture_id,
        captured_at,
        identity="complete",
        kickoff=KICKOFF,
    )
    incomplete = _capture(
        fixture_id,
        captured_at,
        identity="incomplete",
        kickoff=KICKOFF,
    )
    incomplete.pop("home_team_name")
    incomplete["fixture_identity"].pop("home_team_name")
    for capture in (complete, incomplete):
        capture["card_hash"] = "same-card"
        capture["artifact_provenance"] = {"artifact_hash": "same-artifact"}
    repository.append([complete, incomplete], dry_run=False, write_db=True)

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{fixture_id}")

    assert result["status"] == "BLOCKED"
    assert payload["reason_codes"] == [
        "COMPLETE_INCOMPLETE_SIBLING_CONFLICT"
    ]
    assert payload["latest_group_fixture_signature_complete_count"] == 1
    assert payload["latest_group_fixture_signature_incomplete_count"] == 1


@pytest.mark.parametrize("missing_field", ["home_team_name", "kickoff_utc"])
def test_single_latest_incomplete_fixture_signature_is_not_scorable(
    tmp_path: Path,
    missing_field: str,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = f"fixture-signature-incomplete-{missing_field}"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    capture = _capture(
        fixture_id,
        KICKOFF - timedelta(minutes=5),
        identity="incomplete",
        kickoff=KICKOFF,
    )
    capture.pop(missing_field)
    capture["fixture_identity"].pop(missing_field)
    repository.append([capture], dry_run=False, write_db=True)

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{fixture_id}")

    assert result["status"] == "PASS"
    assert payload["status"] == "NOT_SCORABLE"
    assert payload["reason_codes"] == ["FIXTURE_IDENTITY_MISSING"]
    assert payload["latest_group_fixture_signature_complete_count"] == 0
    assert payload["latest_group_fixture_signature_incomplete_count"] == 1


def test_older_missing_or_conflicting_captures_do_not_poison_latest(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-old-conflict"
    _seed_result(repository, fixture_id, home=2, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    old_at = KICKOFF - timedelta(hours=2)
    old_missing = _capture(
        fixture_id,
        KICKOFF - timedelta(hours=3),
        identity="old-missing",
        kickoff=KICKOFF,
    )
    old_missing.pop("capture_identity_hash")
    old_missing.pop("probability_identity")
    repository.append(
        [
            old_missing,
            _capture(fixture_id, old_at, identity="old-a", kickoff=KICKOFF),
            _capture(
                fixture_id,
                old_at,
                identity="old-b",
                model=(0.2, 0.2, 0.6),
                kickoff=KICKOFF,
            ),
            _capture(
                fixture_id,
                KICKOFF - timedelta(minutes=5),
                identity="latest",
                kickoff=KICKOFF,
            ),
        ],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{fixture_id}")

    assert result["scored_count"] == 1
    assert payload["status"] == "SCORED"
    assert payload["source_capture_identity_hash"] == "latest"
    assert payload["total_historical_prekickoff_capture_count"] == 4
    assert payload["older_identity_missing_capture_count"] == 1


def test_latest_identity_with_missing_vectors_is_not_scorable(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-latest-incomplete"
    _seed_result(repository, fixture_id, home=0, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    old = _capture(
        fixture_id,
        KICKOFF - timedelta(hours=2),
        identity="old-missing",
        kickoff=KICKOFF,
    )
    old.pop("capture_identity_hash")
    old.pop("probability_identity")
    repository.append(
        [
            old,
            _capture(
                fixture_id,
                KICKOFF - timedelta(minutes=5),
                identity="latest-incomplete",
                model=None,
                market=None,
                kickoff=KICKOFF,
            ),
        ],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{fixture_id}")

    assert result["status"] == "PASS"
    assert payload["reason_codes"] == [
        "MARKET_PROBABILITY_VECTOR_MISSING",
        "MODEL_PROBABILITY_VECTOR_MISSING",
    ]
    assert payload["capture_selection_status"] == "PROBABILITY_INCOMPLETE"
    assert payload["model_probability_complete"] is False
    assert payload["market_probability_complete"] is False
    assert payload["source_capture_identity_hash"] is None
    assert payload["selected_scoring_capture_at"] is None


def test_latest_complete_incomplete_siblings_are_blocked(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-complete-incomplete"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    captured_at = KICKOFF - timedelta(minutes=5)
    complete = _capture(
        fixture_id,
        captured_at,
        identity="complete",
        kickoff=KICKOFF,
    )
    incomplete = _capture(
        fixture_id,
        captured_at,
        identity="incomplete",
        model=None,
        kickoff=KICKOFF,
    )
    for capture in (complete, incomplete):
        capture["card_hash"] = "same-card"
        capture["artifact_provenance"] = {"artifact_hash": "same-artifact"}
    repository.append(
        [complete, incomplete],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{fixture_id}")

    assert result["status"] == "BLOCKED"
    assert payload["reason_codes"] == [
        "COMPLETE_INCOMPLETE_SIBLING_CONFLICT"
    ]
    assert payload["capture_selection_status"] == (
        "COMPLETE_INCOMPLETE_SIBLING_CONFLICT"
    )


def test_api_football_prefixed_result_matches_bare_capture(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    canonical = "api_football:1576804"
    _seed_result(repository, canonical, home=1, away=0)
    _seed_identity(
        repository,
        canonical,
        kickoff=KICKOFF,
        provider_fixture_id="1576804",
    )
    repository.append(
        [
            _capture(
                "1576804",
                KICKOFF - timedelta(minutes=5),
                identity="bare",
                kickoff=KICKOFF,
            )
        ],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )

    assert result["status"] == "PASS"
    assert _checkpoint(repository, f"performance:fixture:{canonical}")["status"] == "SCORED"


def test_bare_result_and_canonical_capture_use_canonical_checkpoint(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    canonical = "fixture-canonical-1576805"
    _seed_result(repository, "1576805", home=1, away=1)
    _seed_identity(
        repository,
        canonical,
        kickoff=KICKOFF,
        provider_fixture_id="1576805",
    )
    repository.append(
        [
            _capture(
                canonical,
                KICKOFF - timedelta(minutes=5),
                identity="canonical",
                kickoff=KICKOFF,
            )
        ],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{canonical}")

    assert result["status"] == "PASS"
    assert payload["fixture_id"] == canonical
    assert payload["status"] == "SCORED"


def test_outcome_ledger_envelope_payload_parity_allows_scoring(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-envelope-parity"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    repository.append(
        [
            _capture(
                fixture_id,
                KICKOFF - timedelta(minutes=5),
                identity="matching",
                kickoff=KICKOFF,
            )
        ],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    with Session(repository.engine) as session:
        row = session.scalar(select(OutcomeLedgerModel))
        assert row is not None
        assert row.payload_sha256 == payload_sha256(row.payload)

    assert result["status"] == "PASS"
    assert _checkpoint(
        repository,
        f"performance:fixture:{fixture_id}",
    )["status"] == "SCORED"


def test_b1_legacy_runtime_import_passes_effective_parity(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "db")
    fixture_id = "fixture-legacy-import"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    source = tmp_path / "runtime"
    ledger = source / "forward_outcome_ledger"
    ledger.mkdir(parents=True)
    capture = _capture(
        fixture_id,
        KICKOFF - timedelta(minutes=5),
        identity="legacy-import",
        kickoff=KICKOFF,
    )
    capture.pop("record_type")
    (ledger / "legacy.jsonl").write_text(
        json.dumps(capture) + "\n",
        encoding="utf-8",
    )

    import_runtime_ledger(
        repository,
        source,
        dry_run=False,
        write_db=True,
        confirm_write=IMPORT_CONFIRMATION_PHRASE,
    )
    result = run_finished_match_scoring_projection(
        engine=repository.engine,
    )
    with Session(repository.engine) as session:
        row = session.scalar(select(OutcomeLedgerModel))
        assert row is not None
        assert row.payload_sha256 == payload_sha256(row.payload)

    assert result["status"] == "PASS"
    assert result["scored_count"] == 1
    assert result["ledger_parity"] == {
        "status": "PASS_WITH_LEGACY_NORMALIZATION",
        "total_row_count": 1,
        "explicit_match_count": 0,
        "legacy_inferred_capture_count": 1,
        "legacy_formal_snapshot_count": 0,
        "legacy_formal_settlement_count": 0,
        "legacy_unknown_schema_count": 0,
        "explicit_conflict_count": 0,
        "unsupported_missing_count": 0,
        "mismatches_by_field": {},
        "affected_fixture_count": 0,
        "finished_result_affected_count": 0,
    }


@pytest.mark.parametrize(
    "source_artifact",
    ["db:forward_outcome_ledger", "unknown/legacy.jsonl"],
)
def test_missing_record_type_from_unsupported_source_is_blocked(
    tmp_path: Path,
    source_artifact: str,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-unsupported-source"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    capture = _capture(
        fixture_id,
        KICKOFF - timedelta(minutes=5),
        identity="unsupported",
        kickoff=KICKOFF,
    )
    capture.pop("record_type")
    _append_import_record(
        repository,
        capture,
        record_type="capture",
        source_artifact=source_artifact,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
    )

    assert result["status"] == "BLOCKED"
    assert result["ledger_parity"]["unsupported_missing_count"] == 1
    assert result["ledger_parity"]["mismatches_by_field"] == {
        "record_type": 1
    }


@pytest.mark.parametrize(
    ("record_type", "source_artifact", "identity_key"),
    [
        (
            "formal_snapshot",
            "formal_recommendation_snapshots/snapshot.json",
            "snapshot_id",
        ),
        (
            "formal_settlement",
            "formal_recommendation_settlements/settlement.json",
            "settlement_id",
        ),
    ],
)
def test_formal_directory_infers_effective_record_type(
    tmp_path: Path,
    record_type: str,
    source_artifact: str,
    identity_key: str,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = f"fixture-{record_type}"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    payload = {
        "schema_version": f"w2.{record_type}.v1",
        "fixture_id": fixture_id,
        identity_key: f"{record_type}-1",
        (
            "captured_at"
            if record_type == "formal_snapshot"
            else "evaluated_at"
        ): (KICKOFF - timedelta(minutes=5)).isoformat(),
    }
    _append_import_record(
        repository,
        payload,
        record_type=record_type,
        source_artifact=source_artifact,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
    )

    assert result["status"] == "PASS"
    assert result["blocked_count"] == 0
    assert result["ledger_parity"][
        f"legacy_{record_type}_count"
    ] == 1


def test_formal_directory_type_mismatch_is_blocked(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-formal-source-conflict"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    _append_import_record(
        repository,
        {
            "schema_version": "w2.formal_snapshot.v1",
            "fixture_id": fixture_id,
            "snapshot_id": "snapshot-conflict",
            "captured_at": (KICKOFF - timedelta(minutes=5)).isoformat(),
        },
        record_type="formal_snapshot",
        source_artifact=(
            "formal_recommendation_settlements/settlement.json"
        ),
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
    )

    assert result["status"] == "BLOCKED"
    assert result["ledger_parity"]["unsupported_missing_count"] == 1


def test_missing_schema_version_unknown_envelope_is_normalized(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-unknown-schema"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    capture = _capture(
        fixture_id,
        KICKOFF - timedelta(minutes=5),
        identity="unknown-schema",
        kickoff=KICKOFF,
    )
    capture.pop("schema_version")
    _append_import_record(
        repository,
        capture,
        record_type="capture",
        source_artifact="db:forward_outcome_ledger",
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
    )

    assert result["status"] == "PASS"
    assert result["ledger_parity"]["legacy_unknown_schema_count"] == 1


def test_missing_schema_version_non_unknown_envelope_is_blocked(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-schema-conflict"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    capture = _capture(
        fixture_id,
        KICKOFF - timedelta(minutes=5),
        identity="schema-conflict",
        kickoff=KICKOFF,
    )
    capture.pop("schema_version")
    _append_import_record(
        repository,
        capture,
        record_type="capture",
        source_artifact="db:forward_outcome_ledger",
    )
    _mutate_ledger_envelope(
        repository,
        schema_version="w2.forward_outcome_ledger.v3",
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
    )

    assert result["status"] == "BLOCKED"
    assert result["ledger_parity"]["explicit_conflict_count"] == 1
    assert result["ledger_parity"]["mismatches_by_field"] == {
        "schema_version": 1
    }


@pytest.mark.parametrize(
    ("envelope_change", "mismatch_field"),
    [
        ({"fixture_id": "fixture-envelope-other"}, "fixture_id"),
        ({"record_type": "outcome"}, "record_type"),
        (
            {"capture_identity_hash": "different-capture"},
            "capture_identity_hash",
        ),
        ({"decision_hash": "different-decision"}, "decision_hash"),
        (
            {"recommendation_scope": "FORMAL"},
            "recommendation_scope",
        ),
        (
            {"captured_at": KICKOFF - timedelta(minutes=6)},
            "captured_at",
        ),
        ({"payload_sha256": "0" * 64}, "payload_sha256"),
    ],
    ids=[
        "fixture-id",
        "record-type",
        "capture-identity",
        "decision-hash",
        "recommendation-scope",
        "captured-at",
        "payload-sha256",
    ],
)
def test_outcome_ledger_envelope_payload_mismatch_blocks_fixture(
    tmp_path: Path,
    envelope_change: dict[str, Any],
    mismatch_field: str,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-envelope-conflict"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    capture = _capture(
        fixture_id,
        KICKOFF - timedelta(minutes=5),
        identity="matching",
        kickoff=KICKOFF,
    )
    repository.append([capture], dry_run=False, write_db=True)
    _mutate_ledger_envelope(repository, **envelope_change)

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{fixture_id}")

    assert result["status"] == "BLOCKED"
    assert payload["status"] == "BLOCKED"
    assert payload["reason_codes"] == [
        "OUTCOME_LEDGER_ENVELOPE_PAYLOAD_CONFLICT"
    ]
    assert result["ledger_parity"]["mismatches_by_field"] == {
        mismatch_field: 1
    }


def test_envelope_parity_reports_all_independent_mismatches(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    fixture_id = "fixture-envelope-all-fields"
    _seed_result(repository, fixture_id, home=1, away=0)
    _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    repository.append(
        [
            _capture(
                fixture_id,
                KICKOFF - timedelta(minutes=5),
                identity="all-fields",
                kickoff=KICKOFF,
            )
        ],
        dry_run=False,
        write_db=True,
    )
    _mutate_ledger_envelope(
        repository,
        record_type="outcome",
        fixture_id="fixture-envelope-other",
        captured_at=KICKOFF - timedelta(minutes=6),
        recommendation_scope="FORMAL",
        capture_identity_hash="different-capture",
        decision_hash="different-decision",
        payload_sha256="0" * 64,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
    )

    assert result["status"] == "BLOCKED"
    assert result["ledger_parity"]["mismatches_by_field"] == {
        "capture_identity_hash": 1,
        "captured_at": 1,
        "decision_hash": 1,
        "fixture_id": 1,
        "payload_sha256": 1,
        "recommendation_scope": 1,
        "record_type": 1,
    }


def test_envelope_fixture_conflict_blocks_both_canonical_fixtures(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    for fixture_id in ("fixture-envelope-a", "fixture-envelope-b"):
        _seed_result(repository, fixture_id, home=1, away=0)
        _seed_identity(repository, fixture_id, kickoff=KICKOFF)
    repository.append(
        [
            _capture(
                "fixture-envelope-a",
                KICKOFF - timedelta(minutes=5),
                identity="matching",
                kickoff=KICKOFF,
            )
        ],
        dry_run=False,
        write_db=True,
    )
    _mutate_ledger_envelope(
        repository,
        fixture_id="fixture-envelope-b",
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )

    assert result["status"] == "BLOCKED"
    for fixture_id in ("fixture-envelope-a", "fixture-envelope-b"):
        assert _checkpoint(
            repository,
            f"performance:fixture:{fixture_id}",
        )["reason_codes"] == [
            "OUTCOME_LEDGER_ENVELOPE_PAYLOAD_CONFLICT"
        ]


@pytest.mark.parametrize(
    ("dry_run", "write_db"),
    [(True, False), (False, True)],
    ids=["dry-run", "write-mode"],
)
def test_unresolvable_envelope_conflict_suppresses_all_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dry_run: bool,
    write_db: bool,
) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-result", home=1, away=0)
    _seed_identity(repository, "fixture-result", kickoff=KICKOFF)
    repository.append(
        [
            _capture(
                "fixture-result",
                KICKOFF - timedelta(minutes=5),
                identity="matching",
                kickoff=KICKOFF,
            )
        ],
        dry_run=False,
        write_db=True,
    )
    run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    before = _performance_snapshot(repository)
    with repository.engine.begin() as connection:
        stored_payload = connection.execute(
            select(OutcomeLedgerModel.payload)
        ).scalar_one()
        payload = {
            **stored_payload,
            "fixture_id": "unresolvable-payload",
            "fixture_identity": {
                **stored_payload["fixture_identity"],
                "fixture_id": "unresolvable-payload",
            },
        }
        connection.execute(
            update(OutcomeLedgerModel).values(
                payload=payload,
                payload_sha256=payload_sha256(payload),
                fixture_id="unresolvable-envelope",
            )
        )
    monkeypatch.setattr(
        "w2.tracking.finished_match_scoring_projection._persist_checkpoint",
        lambda *_args, **_kwargs: pytest.fail(
            "_persist_checkpoint called behind hard batch gate"
        ),
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=dry_run,
        write_db=write_db,
    )

    assert result["status"] == "BLOCKED"
    assert result["persistence_gate"] == "BLOCKED_BATCH_ENVELOPE_CONFLICT"
    assert result["persistence_suppressed"] is True
    assert result["written"] == 0
    assert result["would_write"] == 0
    assert result["db_writes"] == 0
    assert result["skipped_existing"] == 0
    assert result["fixture_checkpoint_count"] == 0
    assert result["cohort_checkpoint_count"] == 0
    assert result["projected_fixture_checkpoint_count"] == 1
    assert result["projected_cohort_checkpoint_count"] > 0
    assert result["persisted_fixture_checkpoint_count"] == 0
    assert result["persisted_cohort_checkpoint_count"] == 0
    assert result["blockers"] == [
        "batch:OUTCOME_LEDGER_ENVELOPE_PAYLOAD_CONFLICT"
    ]
    assert _performance_snapshot(repository) == before


@pytest.mark.parametrize(
    ("dry_run", "write_db"),
    [(True, False), (False, True)],
    ids=["dry-run", "write-mode"],
)
def test_non_finished_fixture_envelope_conflict_suppresses_all_persistence(
    tmp_path: Path,
    dry_run: bool,
    write_db: bool,
) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-result", home=1, away=0)
    _seed_identity(repository, "fixture-result", kickoff=KICKOFF)
    repository.append(
        [
            _capture(
                "fixture-result",
                KICKOFF - timedelta(minutes=5),
                identity="result",
                kickoff=KICKOFF,
            )
        ],
        dry_run=False,
        write_db=True,
    )
    run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    before = _performance_snapshot(repository)
    _seed_identity(repository, "fixture-orphan", kickoff=KICKOFF)
    repository.append(
        [
            _capture(
                "fixture-orphan",
                KICKOFF - timedelta(minutes=5),
                identity="orphan",
                kickoff=KICKOFF,
            )
        ],
        dry_run=False,
        write_db=True,
    )
    with repository.engine.begin() as connection:
        connection.execute(
            update(OutcomeLedgerModel)
            .where(
                OutcomeLedgerModel.fixture_id == "fixture-orphan"
            )
            .values(record_type="outcome")
        )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=dry_run,
        write_db=write_db,
    )

    assert result["status"] == "BLOCKED"
    assert result["persistence_suppressed"] is True
    assert result["would_write"] == 0
    assert result["db_writes"] == 0
    assert result["blockers"] == [
        "batch:OUTCOME_LEDGER_ENVELOPE_PAYLOAD_CONFLICT"
    ]
    assert result["ledger_parity"]["affected_fixture_count"] == 1
    assert result["ledger_parity"]["finished_result_affected_count"] == 0
    assert _performance_snapshot(repository) == before


def test_finished_fixture_envelope_conflict_is_isolated(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    for fixture_id in ("fixture-conflict", "fixture-valid"):
        _seed_result(repository, fixture_id, home=1, away=0)
        _seed_identity(repository, fixture_id, kickoff=KICKOFF)
        repository.append(
            [
                _capture(
                    fixture_id,
                    KICKOFF - timedelta(minutes=5),
                    identity=fixture_id,
                    kickoff=KICKOFF,
                )
            ],
            dry_run=False,
            write_db=True,
        )
    run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    trusted_conflict = _checkpoint(
        repository,
        "performance:fixture:fixture-conflict",
    )
    with repository.engine.begin() as connection:
        connection.execute(
            update(OutcomeLedgerModel)
            .where(
                OutcomeLedgerModel.fixture_id == "fixture-conflict"
            )
            .values(record_type="outcome")
        )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )

    assert result["status"] == "BLOCKED"
    assert result["blocked_count"] == 1
    assert result["scored_count"] == 1
    assert result["persistence_suppressed"] is False
    assert result["persistence_gate"] == "PASS"
    assert not any(blocker.startswith("batch:") for blocker in result["blockers"])
    assert (
        _checkpoint(repository, "performance:fixture:fixture-conflict")
        == trusted_conflict
    )
    assert (
        _checkpoint(repository, "performance:fixture:fixture-valid")["status"]
        == "SCORED"
    )


def test_ambiguous_exact_fixture_mapping_is_blocked(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "1576806", home=1, away=0)
    _seed_identity(
        repository,
        "1576806",
        kickoff=KICKOFF,
        provider_fixture_id="provider-a",
    )
    _seed_identity(
        repository,
        "fixture-canonical-b",
        kickoff=KICKOFF,
        provider_fixture_id="1576806",
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, "performance:fixture:1576806")

    assert result["status"] == "BLOCKED"
    assert payload["reason_codes"] == ["FIXTURE_IDENTITY_CONFLICT"]


def test_same_card_market_siblings_collapse_with_order_invariant_hash(
    tmp_path: Path,
) -> None:
    hashes: list[str] = []
    for order in (("ah", "ou"), ("ou", "ah")):
        repository = _repository(tmp_path / "-".join(order))
        _seed_result(repository, "fixture-siblings", home=2, away=1)
        _seed_identity(repository, "fixture-siblings", kickoff=KICKOFF)
        siblings = _market_siblings("fixture-siblings", order)
        repository.append(siblings, dry_run=False, write_db=True)

        result = run_finished_match_scoring_projection(
            engine=repository.engine,
            dry_run=False,
            write_db=True,
        )
        payload = _checkpoint(repository, "performance:fixture:fixture-siblings")

        assert result["scored_count"] == 1
        assert payload["status"] == "SCORED"
        assert payload["contributing_capture_identity_hashes"] == ["ah", "ou"]
        assert payload["clv_status"] == "NOT_APPLICABLE_NO_PICK"
        hashes.append(payload["source_capture_group_hash"])

    assert hashes[0] == hashes[1]


def test_same_time_different_card_or_artifact_is_blocked(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-artifact-conflict", home=1, away=0)
    _seed_identity(repository, "fixture-artifact-conflict", kickoff=KICKOFF)
    captured = KICKOFF - timedelta(minutes=5)
    repository.append(
        [
            _capture(
                "fixture-artifact-conflict",
                captured,
                identity="a",
                kickoff=KICKOFF,
            ),
            _capture(
                "fixture-artifact-conflict",
                captured,
                identity="b",
                kickoff=KICKOFF,
            ),
        ],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(
        repository,
        "performance:fixture:fixture-artifact-conflict",
    )

    assert result["status"] == "BLOCKED"
    assert payload["reason_codes"] == [
        "EQUAL_TIMESTAMP_DIFFERENT_BUSINESS_IDENTITY"
    ]


def test_dynamic_metadata_uses_canonical_fixture_join(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    canonical = "api_football:1576807"
    captured = KICKOFF - timedelta(minutes=5)
    _seed_result(repository, canonical, home=1, away=0)
    _seed_identity(
        repository,
        canonical,
        kickoff=KICKOFF,
        provider_fixture_id="1576807",
    )
    capture = _capture("1576807", captured, identity="dynamic", kickoff=KICKOFF)
    capture.pop("checkpoint", None)
    capture.pop("lineup_input_hash", None)
    repository.append([capture], dry_run=False, write_db=True)
    _seed_dynamic(repository, "1576807", captured)

    run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{canonical}")

    assert payload["checkpoint"] == "T-30m"
    assert payload["lineup_input_hash"] == "lineup-canonical"


def test_fixture_clv_uses_existing_selection_and_method(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    canonical = "api_football:1576808"
    _seed_result(repository, canonical, home=2, away=0)
    _seed_identity(
        repository,
        canonical,
        kickoff=KICKOFF,
        provider_fixture_id="1576808",
    )
    entry = _capture(
        "1576808",
        KICKOFF - timedelta(hours=24),
        identity="clv-entry",
        kickoff=KICKOFF,
    )
    closing = _capture(
        "1576808",
        KICKOFF - timedelta(minutes=5),
        identity="clv-closing",
        kickoff=KICKOFF,
    )
    for record, price in ((entry, 2.0), (closing, 1.9)):
        record["pick"] = {"market": "ASIAN_HANDICAP", "selection": "HOME_AH"}
        record["recommendation_scope"] = "VALIDATION"
        record["current_odds"] = {
            "ah": {
                "home_line": "-1",
                "away_line": "+1",
                "home_price": price,
                "away_price": 1.9,
            }
        }
    repository.append([entry, closing], dry_run=False, write_db=True)

    run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, f"performance:fixture:{canonical}")

    assert payload["clv_status"] == "AVAILABLE"
    assert payload["clv_decimal"] == 0.1
    assert payload["clv_method"] == CLV_METHOD


def test_same_source_with_different_payload_fails_closed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-conflict", home=1, away=0)
    _seed_identity(repository, "fixture-conflict", kickoff=KICKOFF)
    repository.append(
        [
            _capture(
                "fixture-conflict",
                KICKOFF - timedelta(minutes=5),
                identity="stable-source",
                kickoff=KICKOFF,
            )
        ],
        dry_run=False,
        write_db=True,
    )
    run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    with Session(repository.engine) as session:
        row = session.scalar(
            select(ReadModelCheckpointModel).where(
                ReadModelCheckpointModel.checkpoint_key
                == "performance:fixture:fixture-conflict"
            )
        )
        assert row is not None
        row.payload = {**row.payload, "model_log_loss": 999.0}
        session.commit()

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )

    assert result["status"] == "BLOCKED"
    assert any(
        "SAME_SOURCE_PAYLOAD_CONFLICT" in blocker
        for blocker in result["blockers"]
    )
    assert (
        _checkpoint(
            repository,
            "performance:fixture:fixture-conflict",
        )["model_log_loss"]
        == 999.0
    )


def test_projection_and_cohorts_are_idempotent_and_windowed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    for index, days in enumerate((0, 7, 8, 30, 31), start=1):
        fixture_id = f"window-{index}"
        kickoff = KICKOFF - timedelta(days=days)
        _seed_result(repository, fixture_id, home=1, away=0)
        _seed_identity(repository, fixture_id, kickoff=kickoff)
        repository.append(
            [_capture(fixture_id, kickoff - timedelta(hours=1), identity=f"capture-{index}")],
            dry_run=False,
            write_db=True,
        )

    first = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    hashes = _performance_hashes(repository)
    second = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    cohort = _checkpoint(repository, "performance:cohort:all")

    assert first["fixture_checkpoint_count"] == 5
    assert second["db_writes"] == 0
    assert _performance_hashes(repository) == hashes
    assert cohort["windows"]["7d"]["finished_result_count"] == 2
    assert cohort["windows"]["30d"]["finished_result_count"] == 4
    assert cohort["windows"]["90d"]["finished_result_count"] == 5
    assert cohort["windows"]["7d"]["scored_count"] == 2


def test_all_not_scorable_fixtures_still_generate_stable_cohorts(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    for index in range(35):
        fixture_id = f"not-scorable-{index:02d}"
        kickoff = KICKOFF - timedelta(hours=index)
        _seed_result(repository, fixture_id, home=1, away=0)
        _seed_identity(repository, fixture_id, kickoff=kickoff)
        capture = _capture(
            fixture_id,
            kickoff - timedelta(minutes=5),
            identity=f"missing-{index}",
            model=None,
            market=None,
            kickoff=kickoff,
        )
        if index < 31:
            capture.pop("capture_identity_hash")
        capture.pop("probability_identity")
        repository.append([capture], dry_run=False, write_db=True)

    first = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    hashes = _performance_hashes(repository)
    second = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    cohort = _checkpoint(repository, "performance:cohort:all")
    window = cohort["windows"]["90d"]

    assert first["fixture_checkpoint_count"] == 35
    assert first["fixture_projection_coverage"] == 1.0
    assert first["eligible_scoring_coverage"] == 1.0
    assert (
        first["eligible_scoring_coverage_semantics"]
        == "CHECKPOINT_COVERAGE_ONLY"
    )
    assert first["scorable_fixture_count"] == 0
    assert first["scorable_rate"] == 0.0
    assert first["not_scorable_count"] == 35
    assert first["blocked_count"] == 0
    assert first["not_scorable_by_reason"] == {
        "CAPTURE_IDENTITY_MISSING": 31,
        "MARKET_PROBABILITY_VECTOR_MISSING": 35,
        "MODEL_PROBABILITY_VECTOR_MISSING": 35,
    }
    assert first["cohort_checkpoint_count"] == 4
    assert window["finished_result_count"] == 35
    assert window["fixture_checkpoint_count"] == 35
    assert window["scored_count"] == 0
    assert window["not_scorable_count"] == 35
    assert window["blocked_count"] == 0
    assert window["model_log_loss"] is None
    assert window["market_log_loss"] is None
    assert window["model_ece"] is None
    assert window["market_ece"] is None
    assert window["paired_log_loss_bootstrap"] == {
        "status": "INSUFFICIENT",
        "sample_count": 0,
    }
    assert window["clv_sample_count"] == 0
    assert second["db_writes"] == 0
    assert _performance_hashes(repository) == hashes


@pytest.mark.parametrize(
    ("home", "away", "actual"),
    [(2, 1, 0), (1, 1, 1), (0, 2, 2)],
)
def test_shared_scoring_math_matches_existing_golden_semantics(
    home: int,
    away: int,
    actual: int,
) -> None:
    record = {
        "probability_identity": {
            "model_probabilities": {
                "one_x_two": {
                    "probabilities": {"HOME": 0.5, "DRAW": 0.3, "AWAY": 0.2}
                }
            }
        }
    }
    vector = probability_vector(record, "model_probabilities")

    assert actual == (0 if home > away else (1 if home == away else 2))
    assert vector == _probability_vector(record, "model_probabilities")
    assert vector is not None
    assert log_loss(vector, actual) == _log_loss(vector, actual)
    assert brier(vector, actual) == _brier(vector, actual)
    assert rps(vector, actual) == _rps(vector, actual)


def test_operator_cli_exit_and_confirmation_semantics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = {
        "status": "PASS",
        "finished_result_count": 1,
        "fixture_checkpoint_count": 1,
        "cohort_checkpoint_count": 4,
        "scored_count": 1,
        "not_scorable_count": 0,
        "blocked_count": 0,
        "db_writes": 0,
        "provider_calls": 0,
    }
    monkeypatch.setattr(
        finished_match_scoring_cli,
        "run_finished_match_scoring_projection",
        lambda **_kwargs: payload,
    )

    assert finished_match_scoring_cli.main(["--json"]) == 0
    assert '"status": "PASS"' in capsys.readouterr().out
    assert (
        finished_match_scoring_cli.main(
            [
                "--no-dry-run",
                "--write-db",
                "--confirm-write",
                WRITE_CONFIRMATION_PHRASE,
            ]
        )
        == 0
    )
    with pytest.raises(SystemExit):
        finished_match_scoring_cli.main(
            ["--no-dry-run", "--write-db"]
        )
    monkeypatch.setattr(
        finished_match_scoring_cli,
        "run_finished_match_scoring_projection",
        lambda **_kwargs: {**payload, "status": "BLOCKED"},
    )
    assert finished_match_scoring_cli.main([]) == 1


def _repository(root: Path) -> OutcomeLedgerRepository:
    root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{root / 'scoring.db'}")
    for table in (
        ResultModel.__table__,
        OutcomeLedgerModel.__table__,
        MatchdayFixtureIdentityModel.__table__,
        DynamicPrematchEvaluationModel.__table__,
        ReadModelCheckpointModel.__table__,
    ):
        table.create(engine, checkfirst=True)
    return OutcomeLedgerRepository(engine)


def _seed_result(
    repository: OutcomeLedgerRepository,
    fixture_id: str,
    *,
    home: int,
    away: int,
) -> None:
    identity = sha256(f"{fixture_id}:{home}:{away}".encode()).hexdigest()
    with Session(repository.engine) as session:
        session.add(
            ResultModel(
                fixture_id=fixture_id,
                home_goals=home,
                away_goals=away,
                result_status="FT",
                confirmed_at=KICKOFF + timedelta(hours=2),
                source_payload_sha256=identity,
                source_capture_id=None,
                result_hash=identity,
            )
        )
        session.commit()


def _seed_identity(
    repository: OutcomeLedgerRepository,
    fixture_id: str,
    *,
    kickoff: datetime,
    provider_fixture_id: str | None = None,
) -> None:
    digest = sha256(fixture_id.encode()).hexdigest()
    provider_id = provider_fixture_id or fixture_id
    with Session(repository.engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id=fixture_id,
                provider="api_football",
                provider_fixture_id=provider_id,
                competition_id="premier_league",
                provider_league_id="39",
                season="2026",
                kickoff_utc=kickoff,
                fixture_status="FT",
                home_provider_team_id="1",
                away_provider_team_id="2",
                home_w2_team_id="home",
                away_w2_team_id="away",
                team_identity_status="COMPLETE",
                raw_payload_sha256=digest,
                endpoint_capture_id=None,
                captured_at=kickoff + timedelta(hours=2),
                identity_hash=digest,
                payload={},
            )
        )
        session.commit()


def _seed_dynamic(
    repository: OutcomeLedgerRepository,
    fixture_id: str,
    captured_at: datetime,
) -> None:
    with Session(repository.engine) as session:
        session.add(
            DynamicPrematchEvaluationModel(
                evaluation_id=f"evaluation-{fixture_id}",
                identity_hash=sha256(f"dynamic:{fixture_id}".encode()).hexdigest(),
                fixture_id=fixture_id,
                market="ASIAN_HANDICAP",
                selection="HOME_AH",
                checkpoint="T-30m",
                capture_id=None,
                quote_identity_hash=None,
                model_input_hash=None,
                lineup_input_hash="lineup-canonical",
                evaluated_at=captured_at,
                capture_at=captured_at,
                original_state="WATCH",
                payload={},
            )
        )
        session.commit()


def _market_siblings(
    fixture_id: str,
    order: tuple[str, str],
) -> list[dict[str, Any]]:
    captured_at = KICKOFF - timedelta(minutes=5)
    siblings: dict[str, dict[str, Any]] = {}
    for market in ("ah", "ou"):
        capture = _capture(
            fixture_id,
            captured_at,
            identity=market,
            kickoff=KICKOFF,
        )
        capture["card_hash"] = "shared-card"
        capture["artifact_provenance"] = {"artifact_hash": "shared-artifact"}
        capture["shadow_pick"] = (
            {"market": "ASIAN_HANDICAP", "selection": "HOME_AH"}
            if market == "ah"
            else {"market": "TOTALS", "selection": "OVER"}
        )
        siblings[market] = capture
    return [siblings[market] for market in order]


def _distinguish_legacy_siblings(
    captures: list[dict[str, Any]],
) -> None:
    captures[0]["shadow_pick"] = {
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
    }
    captures[1]["shadow_pick"] = {
        "market": "TOTALS",
        "selection": "OVER",
    }


def _capture(
    fixture_id: str,
    captured_at: datetime,
    *,
    identity: str,
    model: tuple[float, float, float] | None = (0.5, 0.3, 0.2),
    market: tuple[float, float, float] | None = (0.4, 0.35, 0.25),
    kickoff: datetime | None = None,
) -> dict[str, Any]:
    def probabilities(
        values: tuple[float, float, float] | None,
    ) -> dict[str, Any]:
        if values is None:
            return {}
        return {
            "one_x_two": {
                "probabilities": dict(
                    zip(("HOME", "DRAW", "AWAY"), values, strict=True)
                )
            }
        }

    resolved_kickoff = kickoff or (
        KICKOFF
        if fixture_id in {"fixture-1", "fixture-2", "fixture-3"}
        else captured_at + timedelta(hours=1)
    )
    return {
        "schema_version": "w2.forward_outcome_ledger.v3",
        "record_type": "capture",
        "fixture_id": fixture_id,
        "captured_at": captured_at.isoformat(),
        "kickoff_utc": resolved_kickoff.isoformat(),
        "competition_id": "premier_league",
        "competition_name": "Test League",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "fixture_identity": {
            "fixture_id": fixture_id,
            "kickoff_utc": resolved_kickoff.isoformat(),
            "competition_id": "premier_league",
            "competition_name": "Test League",
            "home_team_name": "Home",
            "away_team_name": "Away",
        },
        "capture_identity_hash": identity,
        "card_hash": f"card-{identity}",
        "artifact_provenance": {"artifact_hash": f"artifact-{identity}"},
        "probability_identity": {
            "model_probabilities": probabilities(model),
            "market_probabilities": probabilities(market),
        },
        "evaluation_tier": "STRICT",
        "decision_tier": "WATCH",
        "recommendation_scope": "NONE",
        "pick": None,
    }


def _checkpoint(
    repository: OutcomeLedgerRepository,
    key: str,
) -> dict[str, Any]:
    with Session(repository.engine) as session:
        row = session.scalar(
            select(ReadModelCheckpointModel).where(
                ReadModelCheckpointModel.checkpoint_key == key
            )
        )
        assert row is not None
        return dict(row.payload)


def _append_import_record(
    repository: OutcomeLedgerRepository,
    payload: dict[str, Any],
    *,
    record_type: str,
    source_artifact: str,
) -> None:
    repository._append_imports(
        [
            ImportRecord(
                payload=payload,
                record_type=record_type,
                source_artifact=source_artifact,
                source_line_number=1,
            )
        ],
        dry_run=False,
        write_db=True,
    )


def _mutate_ledger_envelope(
    repository: OutcomeLedgerRepository,
    **values: Any,
) -> None:
    with repository.engine.begin() as connection:
        connection.execute(update(OutcomeLedgerModel).values(**values))


def _performance_hashes(repository: OutcomeLedgerRepository) -> dict[str, str]:
    with Session(repository.engine) as session:
        return {
            row.checkpoint_key: row.source_hash
            for row in session.scalars(
                select(ReadModelCheckpointModel).where(
                    ReadModelCheckpointModel.checkpoint_key.like("performance:%")
                )
            )
        }


def _performance_snapshot(
    repository: OutcomeLedgerRepository,
) -> dict[str, tuple[str, datetime, str]]:
    with Session(repository.engine) as session:
        return {
            row.checkpoint_key: (
                row.source_hash,
                row.created_at,
                payload_sha256(row.payload),
            )
            for row in session.scalars(
                select(ReadModelCheckpointModel)
                .where(
                    ReadModelCheckpointModel.checkpoint_key.like(
                        "performance:%"
                    )
                )
                .order_by(ReadModelCheckpointModel.checkpoint_key)
            )
        }
