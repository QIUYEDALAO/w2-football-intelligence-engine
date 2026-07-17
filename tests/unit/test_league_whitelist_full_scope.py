from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.run_w2_league_whitelist_audit import build_cli_payload
from scripts.summarize_w2_league_whitelist_scope import (
    build_scope_summary,
    remaining_provider_cap,
)

from w2.competitions.league_whitelist_scope import REMAINING_UNAUDITED_WHITELIST


def test_full_scope_inventory_has_fourteen_competitions() -> None:
    payload = build_scope_summary()
    inventory = {item["competition_id"]: item for item in payload["inventory"]}

    assert payload["competition_count"] == 14
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0
    assert set(inventory) == {
        "premier_league",
        "la_liga",
        "bundesliga",
        "serie_a",
        "ligue_1",
        "world_cup_2026",
        "brasileirao_serie_a",
        "argentina_primera",
        "mls",
        "chinese_super_league",
        "allsvenskan",
        "eliteserien",
        "eredivisie",
        "primeira_liga",
    }


def test_remaining_unaudited_whitelist_has_eight_competitions() -> None:
    payload = build_cli_payload(
        group="remaining_unaudited_whitelist",
        audit_mode="coverage-inventory",
    )
    ids = [result["competition_id"] for result in payload["results"]]

    assert payload["competition_count"] == 8
    assert tuple(ids) == REMAINING_UNAUDITED_WHITELIST
    assert ids == [
        "premier_league",
        "la_liga",
        "bundesliga",
        "serie_a",
        "ligue_1",
        "world_cup_2026",
        "eredivisie",
        "primeira_liga",
    ]
    assert payload["provider_calls"] == 0


def test_scope_marks_existing_world_cup_without_new_enablement() -> None:
    payload = build_scope_summary()
    world_cup = _inventory_item(payload, "world_cup_2026")

    assert world_cup["enabled"] is True
    assert world_cup["audit_status"] == "ENABLED_EXISTING"
    assert world_cup["audit_mode"] == "COVERAGE_INVENTORY_AUDIT"
    assert world_cup["can_enable"] is False
    assert "not a new enablement" in world_cup["reason"]


def test_top_five_disabled_entries_are_not_enabled_by_inventory() -> None:
    payload = build_scope_summary()
    top_five = [item for item in payload["inventory"] if item["group"] == "top_five"]

    assert len(top_five) == 5
    assert all(item["enabled"] is False for item in top_five)
    assert all(item["can_enable"] is False for item in top_five)
    assert all(item["audit_mode"] == "COVERAGE_INVENTORY_AUDIT" for item in top_five)


def test_national_leagues_remain_disabled() -> None:
    payload = build_scope_summary()
    national = [item for item in payload["inventory"] if item["group"] == "national_leagues"]

    assert len(national) == 8
    assert all(item["enabled"] is False for item in national)


def test_coverage_inventory_audit_mode_is_not_enablement_audit() -> None:
    payload = build_cli_payload(group="top_five", audit_mode="coverage-inventory")

    assert payload["audit_mode"] == "coverage-inventory"
    assert payload["provider_calls"] == 0
    assert {result["audit_mode"] for result in payload["results"]} == {
        "coverage-inventory"
    }


def test_remaining_provider_cap_calculation() -> None:
    assert remaining_provider_cap(36) == 54
    assert remaining_provider_cap(78) == 12
    assert remaining_provider_cap(90) == 0
    assert build_scope_summary(provider_calls_used_today=78)["remaining_cap"] == 12


def test_coverage_inventory_runs_partial_when_cap_is_insufficient(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requesters: dict[str, _FakeRequester] = {}

    payload = build_cli_payload(
        group="remaining_unaudited_whitelist",
        audit_mode="coverage-inventory",
        real_provider_audit=True,
        approved_provider_calls=True,
        daily_hard_cap=1,
        out_dir=tmp_path,
        requester_factory=lambda competition_id: requesters.setdefault(
            competition_id,
            _FakeRequester(),
        ),
    )

    assert payload["status"] == "PROVIDER_AUDIT_STOPPED_EARLY"
    assert payload["actual_provider_calls"] == 1
    assert payload["partial_leagues"] == ["premier_league"]
    assert payload["completed_leagues"] == []
    assert payload["unstarted_leagues"] == list(REMAINING_UNAUDITED_WHITELIST[1:])
    assert payload["results"][0]["can_enable"] is False
    assert payload["results"][0]["audit_mode"] == "coverage-inventory"


def _inventory_item(payload: dict[str, Any], competition_id: str) -> dict[str, Any]:
    return next(item for item in payload["inventory"] if item["competition_id"] == competition_id)


class _FakeRequester:
    def __call__(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        if endpoint == "leagues":
            return 200, {"x-ratelimit-requests-remaining": "90"}, {
                "response": [
                    {
                        "league": {"id": int(params.get("id") or 39), "name": "Example League"},
                        "country": {"name": "England"},
                        "seasons": [{"year": 2026}],
                        "team_count": 20,
                    }
                ]
            }
        return 200, {"x-ratelimit-requests-remaining": "90"}, {"response": []}
