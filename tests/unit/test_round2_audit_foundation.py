from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from apps.scheduler.main import (
    future_fixture_refresh_competition_ids,
    matchday_checkpoint_competition_ids,
)
from scripts.run_w2_league_whitelist_audit import build_cli_payload

from w2.competitions.audit_candidates import (
    AUDIT_ONLY_IDS,
    ROUND2_CANDIDATES_PATH,
    load_round2_audit_candidates,
)
from w2.competitions.league_whitelist_provider_audit import (
    ApiFootballLeagueAuditProvider,
    LocalProviderAuditLedger,
    ProviderAuditBudget,
    ProviderAuditStopped,
)
from w2.competitions.league_whitelist_scope import load_league_whitelist_scope
from w2.competitions.registry import CompetitionRegistry
from w2.ingestion.free_fixture_runtime import _runtime_policies

CURRENT_SEASON = datetime.now(UTC).year


def _league_row(
    *,
    league_id: int = 144,
    name: str = "Jupiler Pro League",
    country: str = "Belgium",
    season: int = CURRENT_SEASON,
) -> dict[str, Any]:
    return {
        "league": {"id": league_id, "name": name},
        "country": {"name": country},
        "seasons": [{"year": season}],
        "team_count": 16,
    }


def test_round2_descriptors_are_audit_only_and_have_no_provider_ids() -> None:
    raw = json.loads(ROUND2_CANDIDATES_PATH.read_text(encoding="utf-8"))
    entries = load_round2_audit_candidates()

    assert tuple(entries) == AUDIT_ONLY_IDS
    assert all(item["runtime_whitelist_member"] is False for item in raw["candidates"])
    assert all(item["scheduler_member"] is False for item in raw["candidates"])
    assert all(not any("league_id" in key for key in item) for item in raw["candidates"])
    assert all(not entry.enabled for entry in entries.values())
    assert all(not entry.provider_mapping["api_football_league_id"] for entry in entries.values())


def test_round2_dry_run_has_17_unique_rows_and_zero_calls() -> None:
    payload = build_cli_payload(
        group="round2_audit_union",
        audit_mode="evidence-only",
    )
    rows = payload["day0_17_row_matrix"]

    assert payload["status"] == "DRY_RUN_READY"
    assert payload["target_rows"] == 17
    assert payload["audit_union_count"] == 17
    assert payload["existing_whitelist_count"] == 13
    assert payload["net_new_audit_only_count"] == 4
    assert payload["planned_provider_calls"] == 68
    assert payload["actual_provider_calls"] == 0
    assert payload["db_business_writes"] == 0
    assert payload["checkpoint_writes"] == 0
    assert len(rows) == len({row["canonical_audit_id"] for row in rows}) == 17
    assert {
        row["canonical_audit_id"]
        for row in rows
        if not row["runtime_whitelist_member"]
    } == set(AUDIT_ONLY_IDS)


def test_audit_candidates_are_unreachable_from_runtime_paths() -> None:
    registered = set(load_league_whitelist_scope(CompetitionRegistry()).all_whitelist)
    assert len(registered) == 13
    assert registered.isdisjoint(AUDIT_ONLY_IDS)
    assert set(future_fixture_refresh_competition_ids()).isdisjoint(AUDIT_ONLY_IDS)
    assert set(matchday_checkpoint_competition_ids()).isdisjoint(AUDIT_ONLY_IDS)
    bridge_policies = _runtime_policies(CompetitionRegistry(), expected_whitelist_size=13)
    assert len(bridge_policies) == 13
    assert set(bridge_policies).isdisjoint(AUDIT_ONLY_IDS)

    for path in (
        Path("src/w2/competitions/registry.py"),
        Path("src/w2/ingestion/future_refresh.py"),
        Path("src/w2/ingestion/free_fixture_runtime.py"),
        Path("src/w2/matchday/intake_v2.py"),
        Path("apps/scheduler/main.py"),
        Path("src/w2/dashboard/day_view.py"),
        Path("src/w2/api/repository.py"),
    ):
        source = path.read_text(encoding="utf-8")
        assert "audit_candidates" not in source, path
        assert "config/audit_candidates" not in source, path


def test_provider_identity_resolution_is_exact_and_unambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requester = Round2Requester()

    payload = _run_candidate(tmp_path, requester=requester)
    row = payload["day0_17_row_matrix"][0]

    assert [endpoint for endpoint, _params in requester.calls] == [
        "leagues",
        "fixtures",
        "fixtures",
        "odds",
    ]
    assert "id" not in requester.calls[0][1]
    assert row["identity_status"] == "EXACT_AND_UNAMBIGUOUS"
    assert row["provider_league_id"] == "144"
    assert row["provider_name"] == "Jupiler Pro League"
    assert row["provider_country"] == "Belgium"
    assert row["market_status"] == "BOTH_PRESENT"
    assert row["line_and_price_observed"] is True
    assert row["quote_timestamp_observed"] is True
    assert row["promotion_authorized"] is False


@pytest.mark.parametrize(
    "league_rows",
    [
        [
            _league_row(league_id=144),
            _league_row(league_id=145),
        ],
        [_league_row(league_id=144, country="Netherlands")],
        [_league_row(league_id=144, season=CURRENT_SEASON - 1)],
    ],
)
def test_ambiguous_or_mismatched_identity_stops_deeper_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    league_rows: list[dict[str, Any]],
) -> None:
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requester = Round2Requester(league_rows=league_rows)

    payload = _run_candidate(tmp_path, requester=requester)

    assert payload["results"][0]["overall_status"] == "IDENTITY_REVIEW_REQUIRED"
    assert payload["results"][0]["identity_status"] == "IDENTITY_REVIEW_REQUIRED"
    assert [endpoint for endpoint, _params in requester.calls] == ["leagues"]
    assert payload["actual_provider_calls"] == 1


def test_quota_reserve_stops_after_first_response_at_twenty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requester = Round2Requester(quota_remaining=20)

    payload = _run_candidate(tmp_path, requester=requester)

    assert [endpoint for endpoint, _params in requester.calls] == ["leagues"]
    assert payload["stopped_reason"] == "QUOTA_WARNING"
    assert payload["actual_provider_calls"] == 1
    assert payload["min_quota_remaining_observed"] == 20


def test_persistent_ledger_preserves_cumulative_call_indexes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    state = tmp_path / "round2-state.json"
    first = _run_candidate(tmp_path / "first", requester=Round2Requester(), state=state)
    second = _run_candidate(tmp_path / "second", requester=Round2Requester(), state=state)
    records = json.loads(state.read_text(encoding="utf-8"))

    assert first["round2_cumulative_provider_calls"] == 4
    assert second["round2_batch_provider_calls"] == 4
    assert second["round2_cumulative_provider_calls"] == 8
    assert [record["provider_call_index"] for record in records] == list(range(1, 9))
    assert len(records) == 8


def test_cumulative_cap_survives_resume_without_calling_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    state = tmp_path / "round2-state.json"
    yesterday = datetime.now(UTC) - timedelta(days=1)
    state.write_text(
        json.dumps(
            [
                {
                    "competition_id": "previous",
                    "endpoint": "leagues",
                    "league_id": None,
                    "fixture_id": None,
                    "status_code": 200,
                    "response_count": 1,
                    "provider_call_index": index,
                    "league_call_index": 1,
                    "quota_remaining": 100,
                    "captured_at": yesterday.isoformat(),
                    "error": None,
                }
                for index in range(1, 201)
            ]
        ),
        encoding="utf-8",
    )
    requester = Round2Requester()

    payload = _run_candidate(tmp_path, requester=requester, state=state)

    assert requester.calls == []
    assert payload["actual_provider_calls"] == 0
    assert payload["stopped_reason"] == "ROUND2_CUMULATIVE_HARD_CAP_REACHED"
    assert payload["round2_cumulative_provider_calls"] == 200


def test_network_error_has_no_automatic_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    calls = 0

    def fail(*_args: Any, **_kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    ledger = LocalProviderAuditLedger()
    provider = ApiFootballLeagueAuditProvider(
        competition_id="test",
        league_hard_cap=4,
        budget=ProviderAuditBudget(daily_hard_cap=80, cumulative_hard_cap=200),
        ledger=ledger,
        request_interval_seconds=0,
    )

    with pytest.raises(ProviderAuditStopped, match="PROVIDER_NETWORK_ERROR"):
        provider.get_league("1", "2026")

    assert calls == 1
    assert len(ledger.records) == 1
    assert ledger.records[0]["error"] == "PROVIDER_NETWORK_ERROR"


def _run_candidate(
    root: Path,
    *,
    requester: Round2Requester,
    state: Path | None = None,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    return build_cli_payload(
        competition_id="belgian_pro_league",
        real_provider_audit=True,
        approved_provider_calls=True,
        audit_mode="evidence-only",
        daily_hard_cap=80,
        request_interval_seconds=10,
        out_dir=root / "output",
        round2_state_json=state or root / "round2-state.json",
        requester_factory=lambda _competition_id: requester,
    )


class Round2Requester:
    def __init__(
        self,
        *,
        league_rows: list[dict[str, Any]] | None = None,
        quota_remaining: int = 99,
    ) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.league_rows = league_rows or [_league_row()]
        self.quota_remaining = quota_remaining

    def __call__(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        self.calls.append((endpoint, params))
        headers = {"x-ratelimit-requests-remaining": str(self.quota_remaining)}
        if endpoint == "leagues":
            return 200, headers, {"response": self.league_rows}
        if endpoint == "fixtures" and params.get("status") == "FT":
            return 200, headers, {"response": [{"fixture": {"id": 2}}]}
        if endpoint == "fixtures":
            return 200, headers, {"response": [{"fixture": {"id": 1}}]}
        if endpoint == "odds":
            return 200, headers, {
                "response": [
                    {
                        "update": "2026-08-08T00:00:00Z",
                        "bookmakers": [
                            {
                                "name": "BookA",
                                "bets": [
                                    {
                                        "name": "Asian Handicap",
                                        "values": [
                                            {"value": "Home -0.25", "odd": "1.95"}
                                        ],
                                    }
                                ],
                            },
                            {
                                "name": "BookB",
                                "bets": [
                                    {
                                        "name": "Asian Handicap",
                                        "values": [
                                            {"value": "Away +0.25", "odd": "1.95"}
                                        ],
                                    }
                                ],
                            },
                            {
                                "name": "BookC",
                                "bets": [
                                    {
                                        "name": "Goals Over/Under",
                                        "values": [
                                            {"value": "Over 2.5", "odd": "1.90"}
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ]
            }
        return 200, headers, {"response": []}
