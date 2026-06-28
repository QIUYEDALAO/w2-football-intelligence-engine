from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from w2.ingestion.market_timeline import (
    find_lock_snapshot,
    select_mainline_snapshot,
    select_mainline_snapshot_result,
    timeline_path,
    validate_timeline_payload,
    write_timeline_snapshot,
)


def _obs(
    *,
    fixture_id: str = "fx1",
    captured_at: datetime,
    market: str = "ASIAN_HANDICAP",
    selection: str,
    line: float,
    odds: float,
    bookmaker: str = "book-a",
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
        "canonical_market": market,
        "selection": selection,
        "line": line,
        "decimal_odds": odds,
        "bookmaker_id": bookmaker,
        "raw_payload_sha256": f"{bookmaker}-{selection}-{line}",
    }


def test_selects_latest_complete_ah_mainline_before_lock() -> None:
    kickoff = datetime(2026, 6, 28, 12, tzinfo=UTC)
    older = kickoff - timedelta(hours=2)
    lock = kickoff - timedelta(minutes=20)
    observations = [
        _obs(captured_at=older, selection="HOME", line=-0.5, odds=2.0),
        _obs(captured_at=older, selection="AWAY", line=0.5, odds=1.8),
        _obs(captured_at=lock, selection="HOME", line=-0.25, odds=1.94),
        _obs(captured_at=lock, selection="AWAY", line=0.25, odds=1.97),
        _obs(captured_at=kickoff + timedelta(minutes=1), selection="HOME", line=-1, odds=2.2),
        _obs(captured_at=kickoff + timedelta(minutes=1), selection="AWAY", line=1, odds=1.7),
    ]

    snapshot = select_mainline_snapshot(
        observations=observations,
        fixture_id="fx1",
        kickoff=kickoff,
        checkpoint="lock",
        market="ASIAN_HANDICAP",
        generated_at=lock,
    )

    assert snapshot is not None
    assert snapshot["line"] == -0.25
    assert snapshot["home_price"] == 1.94
    assert snapshot["away_price"] == 1.97
    assert snapshot["as_of"] == "2026-06-28T11:40:00Z"
    assert snapshot["immutable"] is True


def test_rejects_stale_lock_observation() -> None:
    kickoff = datetime(2026, 6, 28, 19, tzinfo=UTC)
    stale = kickoff - timedelta(hours=6, minutes=18)
    observations = [
        _obs(captured_at=stale, selection="HOME", line=0.5, odds=2.0),
        _obs(captured_at=stale, selection="AWAY", line=0.5, odds=1.9),
    ]

    result = select_mainline_snapshot_result(
        observations=observations,
        fixture_id="fx1",
        kickoff=kickoff,
        checkpoint="lock",
        market="ASIAN_HANDICAP",
    )

    assert result.snapshot is None
    assert result.reason == "NO_FRESH_LOCK_OBSERVATION"


def test_accepts_fresh_lock_observation() -> None:
    kickoff = datetime(2026, 6, 28, 19, tzinfo=UTC)
    fresh = kickoff - timedelta(minutes=45)
    observations = [
        _obs(captured_at=fresh, selection="HOME", line=0.5, odds=2.0),
        _obs(captured_at=fresh, selection="AWAY", line=0.5, odds=1.9),
    ]

    result = select_mainline_snapshot_result(
        observations=observations,
        fixture_id="fx1",
        kickoff=kickoff,
        checkpoint="lock",
        market="ASIAN_HANDICAP",
    )

    assert result.reason is None
    assert result.snapshot is not None
    assert result.snapshot["checkpoint"] == "lock"
    assert result.snapshot["as_of"] == "2026-06-28T18:15:00Z"


def test_rejects_post_kickoff_lock_observation() -> None:
    kickoff = datetime(2026, 6, 28, 19, tzinfo=UTC)
    post = kickoff + timedelta(minutes=1)
    observations = [
        _obs(captured_at=post, selection="HOME", line=0.5, odds=2.0),
        _obs(captured_at=post, selection="AWAY", line=0.5, odds=1.9),
    ]

    result = select_mainline_snapshot_result(
        observations=observations,
        fixture_id="fx1",
        kickoff=kickoff,
        checkpoint="lock",
        market="ASIAN_HANDICAP",
    )

    assert result.snapshot is None
    assert result.reason == "POST_KICKOFF_REJECTED"


def test_non_lock_checkpoint_can_use_older_observation() -> None:
    kickoff = datetime(2026, 6, 28, 19, tzinfo=UTC)
    t6 = kickoff - timedelta(hours=6, minutes=18)
    observations = [
        _obs(captured_at=t6, selection="HOME", line=0.5, odds=2.0),
        _obs(captured_at=t6, selection="AWAY", line=0.5, odds=1.9),
    ]

    snapshot = select_mainline_snapshot(
        observations=observations,
        fixture_id="fx1",
        kickoff=kickoff,
        checkpoint="T-6h",
        market="ASIAN_HANDICAP",
    )

    assert snapshot is not None
    assert snapshot["checkpoint"] == "T-6h"


def test_selects_provider_text_ah_selection_pairs() -> None:
    kickoff = datetime(2026, 6, 28, 12, tzinfo=UTC)
    as_of = kickoff - timedelta(minutes=30)
    observations = [
        _obs(captured_at=as_of, selection="Home -0.25", line=-0.25, odds=1.94),
        _obs(captured_at=as_of, selection="Away +0.25", line="+0.25", odds=1.97),
    ]

    snapshot = select_mainline_snapshot(
        observations=observations,
        fixture_id="fx1",
        kickoff=kickoff,
        checkpoint="lock",
        market="ASIAN_HANDICAP",
    )

    assert snapshot is not None
    assert snapshot["line"] == -0.25
    assert snapshot["home_price"] == 1.94
    assert snapshot["away_price"] == 1.97


def test_write_snapshot_is_idempotent_and_rejects_mutation(tmp_path) -> None:
    kickoff = datetime(2026, 6, 28, 12, tzinfo=UTC)
    as_of = kickoff - timedelta(minutes=30)
    observations = [
        _obs(captured_at=as_of, selection="HOME", line=-0.25, odds=1.94),
        _obs(captured_at=as_of, selection="AWAY", line=0.25, odds=1.97),
    ]
    snapshot = select_mainline_snapshot(
        observations=observations,
        fixture_id="fx1",
        kickoff=kickoff,
        checkpoint="lock",
        market="ASIAN_HANDICAP",
    )
    assert snapshot is not None

    first = write_timeline_snapshot(
        root=tmp_path,
        fixture_id="fx1",
        kickoff=kickoff,
        snapshot=snapshot,
    )
    second = write_timeline_snapshot(
        root=tmp_path,
        fixture_id="fx1",
        kickoff=kickoff,
        snapshot=snapshot,
    )
    changed = dict(snapshot)
    changed["home_price"] = 2.01
    changed["source_hash"] = "different"
    conflict = write_timeline_snapshot(
        root=tmp_path,
        fixture_id="fx1",
        kickoff=kickoff,
        snapshot=changed,
    )

    assert first.status == "WRITTEN"
    assert second.status == "ALREADY_LOCKED"
    assert conflict.status == "IMMUTABLE_CONFLICT"
    payload = json.loads(timeline_path(tmp_path, "fx1").read_text(encoding="utf-8"))
    assert validate_timeline_payload(payload) == []
    assert find_lock_snapshot(root=tmp_path, fixture_id="fx1", kickoff=kickoff) is not None


def test_post_kickoff_snapshot_is_rejected(tmp_path) -> None:
    kickoff = datetime(2026, 6, 28, 12, tzinfo=UTC)
    snapshot = {
        "schema_version": "w2.market_timeline.v1",
        "fixture_id": "fx1",
        "checkpoint": "lock",
        "market": "ASIAN_HANDICAP",
        "as_of": "2026-06-28T12:00:00Z",
        "kickoff_utc": "2026-06-28T12:00:00Z",
        "line": -0.25,
        "home_price": 1.94,
        "away_price": 1.97,
        "bookmaker_count": 1,
        "source_hash": "hash",
        "immutable": True,
    }

    result = write_timeline_snapshot(
        root=tmp_path,
        fixture_id="fx1",
        kickoff=kickoff,
        snapshot=snapshot,
    )

    assert result.status == "POST_KICKOFF_AS_OF_REJECTED"
