from __future__ import annotations

import json
from pathlib import Path

from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot
from w2.tracking.frozen_capture_identity import audit_capture_id
from w2.tracking.frozen_capture_lookup import clear_frozen_capture_cache, find_frozen_capture


def _write(root: Path, *rows: dict[str, object]) -> Path:
    ledger = root / "forward_outcome_ledger"
    ledger.mkdir(parents=True)
    path = ledger / "2026-07-07_staging.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _capture(hash_value: str, *, estimate_id: str = "fme-1") -> dict[str, object]:
    return {
        "fixture_id": "fixture-1",
        "capture_hash": hash_value,
        "evidence_hash": f"evidence-{hash_value}",
        "card_hash": f"card-{hash_value}",
        "fair_market_estimate_ids": [estimate_id],
        "fair_market_estimate_snapshots": [{"estimate_id": estimate_id}],
    }


def _eligible_capture(captured_at: str) -> dict[str, object]:
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="fixture-1",
        estimate=FairMarketEstimate(
            market="TOTALS",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=2.5,
            probabilities={"OVER": 0.52, "UNDER": 0.48},
            home_mu=1.5,
            away_mu=1.0,
            feature_as_of="2026-07-17T00:00:00Z",
            train_cutoff="2026-06-30T00:00:00Z",
            artifact_hash="artifact",
            artifact_version="v1",
        ),
        odds_snapshot={"ou": {"line": 2.5, "over_price": 1.9}},
        feature_snapshot={"home_xg": 1.5, "away_xg": 1.0},
        created_at=captured_at,
    ).as_dict()
    return {
        "fixture_id": "fixture-1",
        "football_day": "2026-07-17",
        "environment": "staging",
        "captured_at": captured_at,
        "capture_hash": "shared-hash",
        "pick": {"market": "TOTALS", "estimate_id": snapshot["estimate_id"]},
        "fair_market_estimate_ids": [snapshot["estimate_id"]],
        "fair_market_estimate_snapshots": [snapshot],
    }


def test_exact_capture_id_resolves_duplicate_content_hash(tmp_path: Path) -> None:
    first = _eligible_capture("2026-07-17T00:00:00Z")
    second = _eligible_capture("2026-07-17T00:01:00Z")
    _write(tmp_path, first, second)
    capture_id = audit_capture_id(second)
    estimate_id = str(second["fair_market_estimate_ids"][0])  # type: ignore[index]

    ambiguous = find_frozen_capture(
        tmp_path,
        fixture_id="fixture-1",
        capture_hash="shared-hash",
        estimate_id=estimate_id,
    )
    exact = find_frozen_capture(
        tmp_path,
        fixture_id="fixture-1",
        capture_id=capture_id,
        capture_hash="shared-hash",
        estimate_id=estimate_id,
    )

    assert ambiguous.reason == "AMBIGUOUS_CAPTURE"
    assert exact.source_status == "PASS"
    assert exact.capture == second
    assert exact.requested_capture_id == capture_id


def test_exact_capture_id_cross_validates_hash_and_estimate(tmp_path: Path) -> None:
    capture = _eligible_capture("2026-07-17T00:00:00Z")
    _write(tmp_path, capture)
    capture_id = audit_capture_id(capture)

    wrong_hash = find_frozen_capture(
        tmp_path,
        fixture_id="fixture-1",
        capture_id=capture_id,
        capture_hash="wrong",
    )
    wrong_estimate = find_frozen_capture(
        tmp_path,
        fixture_id="fixture-1",
        capture_id=capture_id,
        capture_hash="shared-hash",
        estimate_id="fme_wrong",
    )

    assert wrong_hash.reason == "CAPTURE_IDENTITY_MISMATCH"
    assert wrong_estimate.reason == "ESTIMATE_IDENTITY_MISMATCH"


def test_hash_and_estimate_resolve_one_of_duplicate_hash_records(tmp_path: Path) -> None:
    first = _capture("shared", estimate_id="fme-first")
    second = _capture("shared", estimate_id="fme-second")
    _write(tmp_path, first, second)

    result = find_frozen_capture(
        tmp_path,
        fixture_id="fixture-1",
        capture_hash="shared",
        estimate_id="fme-second",
    )

    assert result.source_status == "PASS"
    assert result.capture == second


def test_streaming_lookup_uses_exact_hash_and_keeps_only_target_fixture(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"fixture_id": "other", "capture_hash": "other", "blob": "x" * 1000},
        _capture("exact"),
        {"fixture_id": "fixture-1", "record_type": "outcome"},
    )

    result = find_frozen_capture(
        tmp_path, fixture_id="fixture-1", capture_hash="exact", estimate_id="fme-1"
    )

    assert result.source_status == "PASS"
    assert result.capture is not None
    assert result.capture["capture_hash"] == "exact"
    assert len(result.fixture_records) == 2
    assert result.scanned_record_count == 3
    assert result.matched_file == "2026-07-07_staging.jsonl"


def test_hash_fallback_order_and_newer_capture_does_not_replace_requested(tmp_path: Path) -> None:
    requested = _capture("old")
    requested.pop("capture_hash")
    requested["evidence_hash"] = "requested"
    newer = _capture("new")
    newer["captured_at"] = "2099-01-01T00:00:00Z"
    _write(tmp_path, requested, newer)

    result = find_frozen_capture(tmp_path, fixture_id="fixture-1", capture_hash="requested")

    assert result.capture == requested


def test_ambiguous_legacy_card_hash_fails_closed(tmp_path: Path) -> None:
    first = _capture("first")
    second = _capture("second")
    for row in (first, second):
        row.pop("capture_hash")
        row.pop("evidence_hash")
        row["card_hash"] = "legacy"
    _write(tmp_path, first, second)

    result = find_frozen_capture(tmp_path, fixture_id="fixture-1", capture_hash="legacy")

    assert result.source_status == "BLOCKED"
    assert result.reason == "AMBIGUOUS_LEGACY_CAPTURE"
    assert result.capture is None


def test_estimate_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, _capture("exact"))

    result = find_frozen_capture(
        tmp_path, fixture_id="fixture-1", capture_hash="exact", estimate_id="fme-other"
    )

    assert result.source_status == "BLOCKED"
    assert result.reason == "ESTIMATE_IDENTITY_MISMATCH"


def test_corrupt_tail_is_degraded_not_not_found(tmp_path: Path) -> None:
    path = _write(tmp_path, _capture("exact"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"broken":')

    result = find_frozen_capture(tmp_path, fixture_id="missing", capture_hash="missing")

    assert result.source_status == "DEGRADED"
    assert result.reason == "LEDGER_CORRUPTION"
    assert result.corruption_count == 1


def test_fixture_record_and_line_limits_fail_closed(tmp_path: Path) -> None:
    _write(tmp_path, _capture("exact"), {"fixture_id": "fixture-1", "record_type": "outcome"})
    too_many = find_frozen_capture(
        tmp_path,
        fixture_id="fixture-1",
        capture_hash="exact",
        max_fixture_records=1,
    )
    assert too_many.reason == "FIXTURE_RECORD_LIMIT_EXCEEDED"

    clear_frozen_capture_cache()
    oversized_root = tmp_path / "oversized"
    _write(oversized_root, {**_capture("exact"), "blob": "x" * 100})
    oversized = find_frozen_capture(
        oversized_root,
        fixture_id="fixture-1",
        capture_hash="exact",
        max_line_bytes=32,
    )
    assert oversized.reason == "LEDGER_LINE_LIMIT_EXCEEDED"


def test_unrelated_fixture_history_does_not_block_exact_capture(tmp_path: Path) -> None:
    exact = _capture("exact")
    related_outcome = {
        "fixture_id": "fixture-1",
        "record_type": "outcome",
        "source_capture_hash": "exact",
    }
    unrelated = [
        {
            "fixture_id": "fixture-1",
            "capture_hash": f"unrelated-{index}",
        }
        for index in range(10)
    ]
    _write(tmp_path, *unrelated, exact, related_outcome)

    result = find_frozen_capture(
        tmp_path,
        fixture_id="fixture-1",
        capture_hash="exact",
        max_fixture_records=2,
    )

    assert result.source_status == "PASS"
    assert result.capture == exact
    assert result.fixture_records == (exact, related_outcome)


def test_cache_key_changes_when_ledger_fingerprint_changes(tmp_path: Path) -> None:
    path = _write(tmp_path, _capture("exact"))
    first = find_frozen_capture(tmp_path, fixture_id="fixture-1", capture_hash="exact")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"fixture_id": "fixture-1", "record_type": "outcome"}) + "\n")
    second = find_frozen_capture(tmp_path, fixture_id="fixture-1", capture_hash="exact")

    assert len(first.fixture_records) == 1
    assert len(second.fixture_records) == 2
