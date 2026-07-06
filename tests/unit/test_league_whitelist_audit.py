from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from w2.competitions.league_whitelist_audit import (
    AUDIT_ENDPOINT_ALLOWLIST,
    AuditItemStatus,
    build_hard_cap_blocked_result,
    evaluate_league_whitelist_audit,
    planned_provider_calls_by_endpoint,
    planned_provider_calls_for_audit,
)
from w2.competitions.registry import CompetitionRegistry
from w2.refresh.matchday_schedule import AUTHORIZED_MATCHDAY_ENDPOINTS


def test_mock_provider_all_seven_items_pass_can_enable() -> None:
    result = evaluate_league_whitelist_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=MockAuditProvider(),
    )

    assert result.overall_status == "PASS"
    assert result.can_enable is True
    assert [item.status for item in result.items] == [AuditItemStatus.PASS] * 7
    assert "fixture-future-1" in result.evidence_fixture_ids
    assert result.provider_calls == 7
    assert result.planned_provider_calls == 7
    assert result.actual_provider_calls == 7
    assert result.planned_provider_calls_by_endpoint == {
        "leagues": 1,
        "fixtures_future": 1,
        "fixtures_results": 1,
        "statistics": 1,
        "lineups": 1,
        "injuries": 1,
        "odds": 1,
        "squad_value": 0,
    }
    assert result.db_reads == 0
    assert result.db_writes == 0


def test_one_failed_item_blocks_enablement() -> None:
    provider = MockAuditProvider(statistics={})

    result = evaluate_league_whitelist_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=provider,
    )

    assert result.overall_status == "FAIL"
    assert result.can_enable is False
    assert "xg:FAIL" in result.blockers


def test_squad_value_unavailable_blocks_enablement() -> None:
    provider = MockAuditProvider(squad_value=None)

    result = evaluate_league_whitelist_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=provider,
    )

    assert result.can_enable is False
    assert "squad_value:CANNOT_VERIFY" in result.blockers


def test_bookmaker_depth_requires_minimum_bookmakers_with_lines() -> None:
    provider = MockAuditProvider(
        odds=[
            {"bookmaker": "b1", "market": "ASIAN_HANDICAP", "line": "-0.25"},
            {"bookmaker": "b1", "market": "TOTALS", "line": "2.5"},
        ]
    )

    result = evaluate_league_whitelist_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=provider,
    )

    items = {item.name: item for item in result.items}
    assert items["bookmaker_depth"].status == AuditItemStatus.FAIL
    assert items["bookmaker_depth"].observed_evidence == {
        "observed_ah_ou_market_names": ["ASIAN_HANDICAP", "TOTALS"],
        "observed_bookmaker_count": 1,
        "observed_has_ah": True,
        "observed_has_line": True,
        "observed_has_ou": True,
    }
    assert result.can_enable is False


def test_bookmaker_depth_requires_line_presence() -> None:
    provider = MockAuditProvider(
        odds=[
            {"bookmaker": "b1", "market": "ASIAN_HANDICAP"},
            {"bookmaker": "b2", "market": "TOTALS"},
            {"bookmaker": "b3", "market": "TOTALS"},
        ]
    )

    result = evaluate_league_whitelist_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=provider,
    )

    items = {item.name: item for item in result.items}
    assert items["bookmaker_depth"].status == AuditItemStatus.FAIL
    assert items["bookmaker_depth"].observed_evidence == {
        "observed_ah_ou_market_names": ["ASIAN_HANDICAP", "TOTALS"],
        "observed_bookmaker_count": 3,
        "observed_has_ah": True,
        "observed_has_line": False,
        "observed_has_ou": True,
    }
    assert result.can_enable is False


def test_bookmaker_depth_passes_with_minimum_bookmakers_ah_ou_and_lines() -> None:
    result = evaluate_league_whitelist_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=MockAuditProvider(),
    )

    items = {item.name: item for item in result.items}
    assert items["bookmaker_depth"].status == AuditItemStatus.PASS
    assert items["bookmaker_depth"].observed_evidence == {
        "observed_ah_ou_market_names": ["ASIAN_HANDICAP", "TOTALS"],
        "observed_bookmaker_count": 3,
        "observed_has_ah": True,
        "observed_has_line": True,
        "observed_has_ou": True,
    }


def test_argentina_mock_requires_28_teams_country_and_season() -> None:
    entry = _entry("argentina_primera")
    passing = evaluate_league_whitelist_audit(
        entry,
        environment="staging",
        provider=MockAuditProvider(
            league={
                "id": "128",
                "name": "Liga Profesional de Futbol",
                "country": "Argentina",
                "season": "2026",
                "team_count": 28,
            }
        ),
    )
    failing = evaluate_league_whitelist_audit(
        entry,
        environment="staging",
        provider=MockAuditProvider(
            league={
                "id": "128",
                "name": "Liga Profesional de Futbol",
                "country": "Argentina",
                "season": "2026",
                "team_count": 27,
            }
        ),
    )

    assert passing.can_enable is True
    assert passing.warnings == (
        "ARGENTINA_PRIMERA_PLANNED_CHECK: expected_team_count=28, country/name/season exact match",
    )
    assert failing.can_enable is False
    assert "provider_mapping:FAIL" in failing.blockers


def test_audit_allowlist_is_separate_from_matchday_allowlist() -> None:
    assert {"statistics", "injuries"}.issubset(AUDIT_ENDPOINT_ALLOWLIST)
    assert AUTHORIZED_MATCHDAY_ENDPOINTS == frozenset({"status", "fixtures", "odds", "lineups"})
    assert "statistics" not in AUTHORIZED_MATCHDAY_ENDPOINTS
    assert "injuries" not in AUTHORIZED_MATCHDAY_ENDPOINTS


def test_hard_cap_exceeded_blocks_with_zero_provider_calls() -> None:
    result = build_hard_cap_blocked_result(
        _entry("brasileirao_serie_a"),
        environment="staging",
        hard_cap=6,
        planned_provider_calls=planned_provider_calls_for_audit(),
    )

    assert result.overall_status == "BLOCKED_BY_HARD_CAP"
    assert result.provider_calls == 0
    assert result.actual_provider_calls == 0
    assert result.planned_provider_calls == 7
    assert planned_provider_calls_for_audit() == 7
    assert sum(planned_provider_calls_by_endpoint().values()) == 7
    assert result.can_enable is False


def _entry(competition_id: str):
    return CompetitionRegistry().entries()[competition_id]


class MockAuditProvider:
    def __init__(
        self,
        *,
        league: Mapping[str, Any] | None = None,
        statistics: Mapping[str, Any] | None = None,
        odds: Sequence[Mapping[str, Any]] | None = None,
        squad_value: Mapping[str, Any] | None = {"teams": {"home": 100, "away": 90}},
    ) -> None:
        self.league = league
        self.statistics = (
            {"home": {"xg": 1.4}, "away": {"xg": 0.9}}
            if statistics is None
            else statistics
        )
        self.odds = odds
        self.squad_value = squad_value

    def get_league(self, league_id: str, season: str) -> Mapping[str, Any]:
        if self.league is not None:
            return self.league
        return {
            "id": league_id,
            "name": "Campeonato Brasileiro Serie A",
            "country": "Brazil",
            "season": season,
            "team_count": 20,
        }

    def get_fixtures(
        self,
        league_id: str,
        season: str,
        status: str,
    ) -> Sequence[Mapping[str, Any]]:
        return [{"fixture_id": "fixture-future-1"}]

    def get_results(self, league_id: str, season: str) -> Sequence[Mapping[str, Any]]:
        return [{"fixture_id": "fixture-result-1", "score": "2-1"}]

    def get_fixture_statistics(self, fixture_id: str) -> Mapping[str, Any]:
        return self.statistics

    def get_fixture_lineups(self, fixture_id: str) -> Sequence[Mapping[str, Any]]:
        return [{"team": "home", "players": []}]

    def get_injuries(
        self,
        league_id: str,
        fixture_id: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        return []

    def get_odds(self, fixture_id: str) -> Sequence[Mapping[str, Any]]:
        if self.odds is not None:
            return self.odds
        return [
            {"bookmaker": "b1", "market": "ASIAN_HANDICAP", "line": "-0.25"},
            {"bookmaker": "b2", "market": "ASIAN_HANDICAP", "line": "-0.25"},
            {"bookmaker": "b3", "market": "TOTALS", "line": "2.5"},
        ]

    def get_squad_value_mapping(self, competition_id: str) -> Mapping[str, Any] | None:
        return self.squad_value
