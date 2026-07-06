from __future__ import annotations

from w2.competitions.league_profile_validation import validate_league_profile_mapping
from w2.competitions.registry import CompetitionRegistry


def test_missing_observed_evidence_requires_provider_evidence_and_no_profile_edit() -> None:
    result = validate_league_profile_mapping(_entry("brasileirao_serie_a"), {})

    assert result.status == "NEEDS_PROVIDER_EVIDENCE"
    assert "NEEDS_PROVIDER_EVIDENCE" in result.blockers
    assert "observed_provider_league_id" in result.missing_observed_fields
    assert result.provider_calls == 0
    assert result.db_reads == 0
    assert result.db_writes == 0


def test_matching_observed_evidence_passes_profile_validation() -> None:
    result = validate_league_profile_mapping(
        _entry("brasileirao_serie_a"),
        {
            "observed_provider_league_id": "71",
            "observed_provider_league_name": "Campeonato Brasileiro Serie A",
            "observed_provider_country": "Brazil",
            "observed_provider_season": "2026",
            "observed_provider_team_count": 20,
        },
    )

    assert result.status == "PASS"
    assert result.blockers == ()


def test_mismatched_observed_evidence_requires_review_without_mutating_profile() -> None:
    result = validate_league_profile_mapping(
        _entry("brasileirao_serie_a"),
        {
            "observed_provider_league_id": "999",
            "observed_provider_league_name": "Other League",
            "observed_provider_country": "Brazil",
            "observed_provider_season": "2024",
            "observed_provider_team_count": 18,
        },
    )

    assert result.status == "PROFILE_REVIEW_REQUIRED"
    assert "PROFILE_LEAGUE_ID_REVIEW_REQUIRED" in result.blockers
    assert "PROFILE_SEASON_REVIEW_REQUIRED" in result.blockers
    assert "PROFILE_TEAM_COUNT_REVIEW_REQUIRED" in result.blockers
    assert result.warnings == ("PROFILE_NOT_MUTATED",)


def _entry(competition_id: str):
    return CompetitionRegistry().entries()[competition_id]
