"""Reading back checkpoints written before the AH factor verdict existed.

The release that added the factor verdict to the candidate chain also put it into
the evaluation identity preimage. Evaluation identities are recomputed on every
read, so every checkpoint already on disk whose card carries a ``factor_score``
suddenly recomputed to a different identity, and the dashboard failed closed on
all of them: 235 of the 641 readable production checkpoints stopped reading, and
``/v1/dashboard/intelligence-workspace`` returned 503 for every date.

These tests read a checkpoint this repository did not write. The fixture was
produced offline by the 3ac86c14 implementation -- the last release that could
read those rows -- so it carries the older preimage for real, rather than being
whatever the current writer happens to emit. A test that writes with today's code
and reads it straight back cannot fail this way and would have caught nothing.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from w2.api.repository import Checkpoint, ReadModelRepository, SystemDegradedError
from w2.prematch.read_model_projection import (
    CURRENT_IDENTITY_PROFILE,
    LEGACY_IDENTITY_PROFILE,
    FrozenAnalysisError,
    validate_frozen_analysis_payload,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / (
    "legacy_analysis_checkpoint_3ac86c14.json"
)


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _checkpoint(fixture: dict[str, Any]) -> Checkpoint:
    return Checkpoint(
        key=fixture["checkpoint_key"],
        source_hash=fixture["source_hash"],
        created_at=datetime(2026, 9, 11, tzinfo=UTC),
        payload=deepcopy(fixture["payload"]),
    )


def _read(checkpoint: Checkpoint, fixture_id: str) -> dict[str, Any]:
    return ReadModelRepository()._analysis_card_from_checkpoint(checkpoint, fixture_id)


def test_fixture_was_generated_by_the_release_that_predates_the_factor_verdict() -> None:
    """The fixture's provenance is part of what it proves.

    If this were regenerated with current code it would still pass every other
    test here while testing nothing, so the release that produced it is recorded
    in the file and asserted.
    """
    fixture = _fixture()
    assert fixture["generated_by_release"] == "3ac86c14fb951b93167d7a24f84a319663a6b9d9"
    assert fixture["payload"]["source_evaluation_hashes"] == fixture["source_evaluation_hashes"]


def test_legacy_checkpoint_reads_back_under_the_legacy_profile() -> None:
    fixture = _fixture()
    artifact = validate_frozen_analysis_payload(fixture["fixture_id"], fixture["payload"])

    assert artifact.identity_profile == LEGACY_IDENTITY_PROFILE
    assert artifact.checkpoint_key == fixture["checkpoint_key"]
    assert artifact.source_hash == fixture["source_hash"]
    assert artifact.artifact_hash == fixture["artifact_hash"]
    assert sorted(item.identity_hash for item in artifact.evaluations) == fixture[
        "source_evaluation_hashes"
    ]


def test_legacy_card_content_survives_the_read_unchanged() -> None:
    """The compatibility path must return the card that was frozen, not a new one."""
    fixture = _fixture()
    card = _read(_checkpoint(fixture), fixture["fixture_id"])

    stored = fixture["payload"]["analysis_card"]
    for key, value in stored.items():
        assert card[key] == value, key
    assert card["read_model_projection"]["identity_profile"] == LEGACY_IDENTITY_PROFILE
    assert card["read_model_projection"]["source_hash"] == fixture["source_hash"]
    assert card["projection_health"] == {"status": "READY", "reason_code": None}


def test_current_writer_output_reads_back_under_the_current_profile() -> None:
    """A checkpoint carrying today's evaluation identities is never labelled legacy."""
    fixture = _fixture()
    payload = deepcopy(fixture["payload"])
    restamped = _restamp_under_current_identity(payload)

    artifact = validate_frozen_analysis_payload(fixture["fixture_id"], restamped)

    assert artifact.identity_profile == CURRENT_IDENTITY_PROFILE
    assert sorted(item.identity_hash for item in artifact.evaluations) == restamped[
        "source_evaluation_hashes"
    ]
    assert restamped["source_evaluation_hashes"] != fixture["source_evaluation_hashes"], (
        "the fixture must actually exercise the identity change, or this proves nothing"
    )


def _restamp_under_current_identity(payload: dict[str, Any]) -> dict[str, Any]:
    """Rewrite the fixture's identities the way the current writer would emit them."""
    from w2.domain.canonical_serialization import HashDomain
    from w2.prematch import read_model_projection as rmp

    payload = deepcopy(payload)
    manifest = payload["input_manifest"]
    card = payload["analysis_card"]
    evaluations = tuple(
        rmp._dynamic_evaluations(
            card,
            manifest,
            fixture_identity={
                str(key): str(value)
                for key, value in manifest["dynamic_fixture_identity"].items()
            },
            lineup_identity=manifest.get("dynamic_lineup_identity"),
        )
    )
    payload["source_evaluation_hashes"] = sorted(item.identity_hash for item in evaluations)
    payload["source_evaluation_ids"] = sorted(item.evaluation_id for item in evaluations)
    primary = min(evaluations, key=lambda item: item.evaluation_id)
    payload["source_evaluation_id"] = primary.evaluation_id
    payload["source_evaluation_hash"] = primary.identity_hash
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"projection_hash", "artifact_hash"}
    }
    payload["projection_hash"] = (
        rmp._projection_business_hash(body)
        if payload.get("checkpoint_namespace") == "shadow"
        else rmp.canonical_sha256(body, domain=HashDomain.PREMATCH_READ_MODEL_PROJECTION)
    )
    artifact_body = {key: value for key, value in payload.items() if key != "artifact_hash"}
    payload["artifact_hash"] = rmp.canonical_sha256(
        artifact_body, domain=HashDomain.PREMATCH_READ_MODEL_ARTIFACT
    )
    return payload


@pytest.mark.parametrize(
    "field",
    [
        "artifact_hash",
        "projection_hash",
        "source_event_hash",
        "source_evaluation_hash",
        "source_evaluation_hashes",
        "projection_version",
    ],
)
def test_tampered_payload_field_still_fails_closed(field: str) -> None:
    """A legacy profile is a second preimage, not a second chance.

    Every hash is still recomputed and compared; nothing is accepted because the
    stored value says so.
    """
    fixture = _fixture()
    payload = deepcopy(fixture["payload"])
    value = payload[field]
    payload[field] = (
        [*value[:-1], "0" * 64]
        if isinstance(value, list)
        else ("0" * 64 if isinstance(value, str) and len(value) == 64 else f"{value}-tampered")
    )

    with pytest.raises(FrozenAnalysisError):
        validate_frozen_analysis_payload(fixture["fixture_id"], payload)


def test_tampered_source_hash_is_reported_as_an_identity_mismatch() -> None:
    """The row's own identity is checked against the recomputed one, as before."""
    fixture = _fixture()
    checkpoint = Checkpoint(
        key=fixture["checkpoint_key"],
        source_hash="0" * 64,
        created_at=datetime(2026, 9, 11, tzinfo=UTC),
        payload=deepcopy(fixture["payload"]),
    )

    with pytest.raises(SystemDegradedError, match="ANALYSIS_PROJECTION_IDENTITY_MISMATCH"):
        _read(checkpoint, fixture["fixture_id"])


def test_tampered_checkpoint_key_is_reported_as_an_identity_mismatch() -> None:
    fixture = _fixture()
    checkpoint = Checkpoint(
        key="analysis-card:shadow:v1:9999999",
        source_hash=fixture["source_hash"],
        created_at=datetime(2026, 9, 11, tzinfo=UTC),
        payload=deepcopy(fixture["payload"]),
    )

    with pytest.raises(SystemDegradedError, match="ANALYSIS_PROJECTION_IDENTITY_MISMATCH"):
        _read(checkpoint, fixture["fixture_id"])


def test_checkpoint_read_for_another_fixture_is_refused() -> None:
    fixture = _fixture()

    with pytest.raises(FrozenAnalysisError):
        validate_frozen_analysis_payload("9900002", fixture["payload"])


def test_incomplete_checkpoint_is_refused() -> None:
    fixture = _fixture()
    payload = deepcopy(fixture["payload"])
    del payload["source_event_hash"]

    with pytest.raises(FrozenAnalysisError):
        validate_frozen_analysis_payload(fixture["fixture_id"], payload)


def test_card_fixture_identity_conflict_is_refused() -> None:
    fixture = _fixture()
    payload = deepcopy(fixture["payload"])
    payload["analysis_card"] = deepcopy(payload["analysis_card"])
    payload["analysis_card"]["fixture_id"] = "9900002"

    with pytest.raises(FrozenAnalysisError):
        validate_frozen_analysis_payload(fixture["fixture_id"], payload)


def test_a_batch_of_legacy_and_current_checkpoints_all_read_without_degrading() -> None:
    """The dashboard reads a window of cards, not one, and must not 503 on any.

    Production carries both generations side by side; a reader that handles each
    alone but trips when they are interleaved would still take the dashboard down.
    """
    fixture = _fixture()
    legacy_payload = deepcopy(fixture["payload"])
    current_payload = _restamp_under_current_identity(fixture["payload"])

    profiles = []
    for payload, expected in (
        (legacy_payload, LEGACY_IDENTITY_PROFILE),
        (current_payload, CURRENT_IDENTITY_PROFILE),
        (deepcopy(legacy_payload), LEGACY_IDENTITY_PROFILE),
        (deepcopy(current_payload), CURRENT_IDENTITY_PROFILE),
    ):
        artifact = validate_frozen_analysis_payload(fixture["fixture_id"], payload)
        card = _read(
            Checkpoint(
                key=artifact.checkpoint_key,
                source_hash=artifact.source_hash,
                created_at=datetime(2026, 9, 11, tzinfo=UTC),
                payload=payload,
            ),
            fixture["fixture_id"],
        )
        assert card["read_model_projection"]["identity_profile"] == expected
        profiles.append(expected)

    assert profiles == [
        LEGACY_IDENTITY_PROFILE,
        CURRENT_IDENTITY_PROFILE,
        LEGACY_IDENTITY_PROFILE,
        CURRENT_IDENTITY_PROFILE,
    ]
