from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from w2.tracking.outcome_result_refresh import run_outcome_result_refresh


class FakeRepository:
    def __init__(self, calls_today: int = 0) -> None:
        self.calls_today = calls_today
        self.saved: list[dict[str, Any]] = []

    def request_count_since(self, since: datetime) -> int:
        del since
        return self.calls_today

    def save_raw_payload(self, **payload: Any) -> str:
        self.saved.append(payload)
        return f"db://raw_payload/{payload['sha256']}"


class FakeClient:
    def __init__(self, payloads: dict[str, dict[str, Any]]) -> None:
        self.payloads = payloads
        self.calls: list[str] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> Any:
        assert endpoint == "fixtures"
        fixture_id = params["id"]
        self.calls.append(fixture_id)
        return SimpleNamespace(
            payload=self.payloads[fixture_id],
            captured_at=datetime(2026, 7, 19, 4, 0, tzinfo=UTC),
        )


def test_result_refresh_fetches_pending_fixture_and_settles_total(tmp_path: Path) -> None:
    _write_capture(tmp_path, fixture_id="101", market="TOTALS", selection="OVER")
    client = FakeClient(
        {
            "101": _fixture_payload(
                fixture_id="101",
                status="FT",
                fulltime=(2, 1),
                goals=(2, 1),
            )
        }
    )
    repository = FakeRepository()

    result = run_outcome_result_refresh(
        runtime_root=tmp_path,
        client=client,
        repository=repository,  # type: ignore[arg-type]
        now=datetime(2026, 7, 19, 4, 0, tzinfo=UTC),
        dry_run=False,
        write_artifacts=True,
    )

    assert result["status"] == "PASS"
    assert result["provider_calls"] == 1
    assert result["db_writes"] == 1
    assert result["settlement"]["written"] == 1
    assert repository.saved[0]["endpoint"] == "fixtures"
    rows = _ledger_rows(tmp_path)
    outcome = [row for row in rows if row.get("record_type") == "outcome"][0]
    assert outcome["settlement_outcome"] == "HALF_WIN"


def test_result_refresh_voids_postponement_over_48_hours(tmp_path: Path) -> None:
    _write_capture(tmp_path, fixture_id="102", market="ASIAN_HANDICAP", selection="HOME_AH")
    client = FakeClient(
        {"102": _fixture_payload(fixture_id="102", status="PST", fulltime=None, goals=None)}
    )

    result = run_outcome_result_refresh(
        runtime_root=tmp_path,
        client=client,
        repository=FakeRepository(),  # type: ignore[arg-type]
        now=datetime(2026, 7, 19, 4, 0, tzinfo=UTC),
        dry_run=False,
        write_artifacts=True,
    )

    assert result["status"] == "PASS"
    outcome = [row for row in _ledger_rows(tmp_path) if row.get("record_type") == "outcome"][0]
    assert outcome["settlement_outcome"] == "VOID"
    assert outcome["void_reason"] == "VOID_POSTPONED_OVER_48H"


def test_result_refresh_respects_daily_cap(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("W2_PROVIDER_DAILY_HARD_CAP", "120")
    _write_capture(tmp_path, fixture_id="103", market="ASIAN_HANDICAP", selection="HOME_AH")
    client = FakeClient({})

    result = run_outcome_result_refresh(
        runtime_root=tmp_path,
        client=client,
        repository=FakeRepository(calls_today=120),  # type: ignore[arg-type]
        now=datetime(2026, 7, 19, 4, 0, tzinfo=UTC),
    )

    assert result["status"] == "PARTIAL"
    assert result["provider_calls"] == 0
    assert result["blockers"] == ["PROVIDER_DAILY_HARD_CAP_REACHED"]
    assert client.calls == []


def test_finished_unsettleable_capture_is_not_requeried(tmp_path: Path) -> None:
    _write_capture(tmp_path, fixture_id="104", market="TOTALS", selection="OVER")
    ledger_path = tmp_path / "forward_outcome_ledger" / "2026-07-10_staging.jsonl"
    capture = json.loads(ledger_path.read_text(encoding="utf-8"))
    capture.update(
        {
            "decision_tier": "WATCH",
            "recommendation_scope": "SHADOW",
            "outcome_tracked": False,
            "pick": None,
            "shadow_pick": {"market": "TOTALS", "selection": "OVER"},
            "current_odds": {},
        }
    )
    ledger_path.write_text(json.dumps(capture, sort_keys=True) + "\n", encoding="utf-8")
    client = FakeClient(
        {
            "104": _fixture_payload(
                fixture_id="104",
                status="FT",
                fulltime=(2, 1),
                goals=(2, 1),
            )
        }
    )
    repository = FakeRepository()

    first = run_outcome_result_refresh(
        runtime_root=tmp_path,
        client=client,
        repository=repository,  # type: ignore[arg-type]
        now=datetime(2026, 7, 19, 4, 0, tzinfo=UTC),
        dry_run=False,
        write_artifacts=True,
    )
    second = run_outcome_result_refresh(
        runtime_root=tmp_path,
        client=client,
        repository=repository,  # type: ignore[arg-type]
        now=datetime(2026, 7, 19, 5, 0, tzinfo=UTC),
        dry_run=False,
        write_artifacts=True,
    )

    assert first["status"] == "PARTIAL"
    assert first["selected"][0]["status"] == "SETTLEMENT_ERROR"
    assert first["provider_calls"] == 1
    assert second["status"] == "NO_DUE_WORK"
    assert second["provider_calls"] == 0
    assert client.calls == ["104"]


def _write_capture(
    root: Path,
    *,
    fixture_id: str,
    market: str,
    selection: str,
) -> None:
    ledger = root / "forward_outcome_ledger"
    ledger.mkdir()
    odds = (
        {"ah": {"home_line": "-0.5", "home_price": "1.9", "away_line": "+0.5", "away_price": "1.9"}}
        if market == "ASIAN_HANDICAP"
        else {"ou": {"line": "2.75", "over_price": "1.9", "under_price": "1.9"}}
    )
    capture = {
        "schema_version": "w2.forward_outcome_ledger.v3",
        "record_type": "capture",
        "captured_at": "2026-07-10T00:00:00Z",
        "football_day": "2026-07-10",
        "environment": "staging",
        "fixture_id": fixture_id,
        "kickoff_utc": "2026-07-10T02:00:00Z",
        "competition_id": "league-1",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "card_hash": f"card-{fixture_id}",
        "capture_identity_hash": f"capture-{fixture_id}",
        "recommendation_scope": "VALIDATION",
        "outcome_tracked": True,
        "pick": {"market": market, "selection": selection},
        "current_odds": odds,
    }
    (ledger / "2026-07-10_staging.jsonl").write_text(
        json.dumps(capture, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fixture_payload(
    *,
    fixture_id: str,
    status: str,
    fulltime: tuple[int, int] | None,
    goals: tuple[int, int] | None,
) -> dict[str, Any]:
    return {
        "response": [
            {
                "fixture": {
                    "id": int(fixture_id),
                    "date": "2026-07-10T02:00:00Z",
                    "status": {"short": status},
                },
                "score": {
                    "fulltime": {
                        "home": fulltime[0] if fulltime else None,
                        "away": fulltime[1] if fulltime else None,
                    }
                },
                "goals": {
                    "home": goals[0] if goals else None,
                    "away": goals[1] if goals else None,
                },
            }
        ]
    }


def _ledger_rows(root: Path) -> list[dict[str, Any]]:
    path = root / "forward_outcome_ledger/2026-07-10_staging.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
