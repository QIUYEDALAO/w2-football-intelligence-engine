from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from w2.operations.result_backfill import (
    APPROVED_FIXTURE_IDS,
    discover_missing_validation_results,
    run_restricted_result_backfill,
)


class FakeClient:
    def __init__(self, *, status: str = "FT") -> None:
        self.status = status
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> SimpleNamespace:
        self.calls.append((endpoint, params))
        fixture_id = params["id"]
        return SimpleNamespace(
            captured_at=datetime(2026, 7, 12, 3, 0, tzinfo=UTC),
            payload={
                "response": [
                    {
                        "fixture": {"id": int(fixture_id), "status": {"short": self.status}},
                        "score": {"fulltime": {"home": 2, "away": 1}},
                    }
                ]
            },
        )


class FakeRepository:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def persist_result_backfill_payload(self, **kwargs: object) -> dict[str, object]:
        self.payloads.append(kwargs)
        return {"raw_payload_hash": "a" * 64, "events_inserted": 1}


def test_result_backfill_is_staging_only_allowlisted_and_results_endpoint_only() -> None:
    fixture_id = next(iter(APPROVED_FIXTURE_IDS))
    client = FakeClient()
    payload = run_restricted_result_backfill(
        [fixture_id], environment="staging", client=client, repository=None
    )
    assert payload["dry_run"] is True
    assert payload["provider_calls"] == 1
    assert client.calls == [("fixtures", {"id": fixture_id})]

    with pytest.raises(ValueError, match="STAGING_ONLY"):
        run_restricted_result_backfill(
            [fixture_id], environment="production", client=client, repository=None
        )
    with pytest.raises(ValueError, match="NOT_APPROVED"):
        run_restricted_result_backfill(
            ["999"], environment="staging", client=client, repository=None
        )


def test_result_backfill_writes_only_finished_scores() -> None:
    fixture_id = next(iter(APPROVED_FIXTURE_IDS))
    repository = FakeRepository()
    applied = run_restricted_result_backfill(
        [fixture_id],
        environment="staging",
        client=FakeClient(),
        repository=repository,
        apply=True,
    )
    assert applied["db_writes"] == 1
    assert len(repository.payloads) == 1

    pending_repository = FakeRepository()
    pending = run_restricted_result_backfill(
        [fixture_id],
        environment="staging",
        client=FakeClient(status="PST"),
        repository=pending_repository,
        apply=True,
    )
    assert pending["fixtures"][0]["state"] == "PENDING_RESULT"
    assert pending_repository.payloads == []


def test_discovers_only_old_unsettled_validation_captures(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    fixture_id = next(iter(APPROVED_FIXTURE_IDS))
    rows = [
        {
            "record_type": "capture",
            "fixture_id": fixture_id,
            "decision_tier": "ANALYSIS_PICK",
            "captured_at": "2026-07-11T10:00:00Z",
            "kickoff_utc": "2026-07-11T11:00:00Z",
            "pick": {"market": "TOTALS", "selection": "OVER", "line": "3.25"},
        },
        {
            "record_type": "capture",
            "fixture_id": "watch",
            "decision_tier": "WATCH",
            "captured_at": "2026-07-11T10:00:00Z",
            "kickoff_utc": "2026-07-11T11:00:00Z",
        },
    ]
    (root / "2026-07-11_staging.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows), encoding="utf-8"
    )

    discovered = discover_missing_validation_results(
        tmp_path, now=datetime(2026, 7, 11, 15, 0, tzinfo=UTC)
    )
    assert [row["fixture_id"] for row in discovered] == [fixture_id]
