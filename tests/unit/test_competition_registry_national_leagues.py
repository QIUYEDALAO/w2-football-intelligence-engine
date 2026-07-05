from __future__ import annotations

from pathlib import Path

from w2.competitions.registry import CompetitionRegistry

NATIONAL_IDS = {
    "brasileirao_serie_a",
    "argentina_primera",
    "allsvenskan",
    "eliteserien",
    "mls",
    "chinese_super_league",
    "eredivisie",
    "primeira_liga",
}


def test_registry_discovers_national_league_profiles() -> None:
    entries = CompetitionRegistry().entries()

    assert NATIONAL_IDS.issubset(entries)
    assert len(
        [
            entry
            for entry in entries.values()
            if "national_leagues" in entry.config_path.parts
        ]
    ) == 8


def test_all_national_leagues_are_disabled_and_not_active() -> None:
    registry = CompetitionRegistry()
    entries = registry.entries()

    assert all(entries[competition_id].enabled is False for competition_id in NATIONAL_IDS)
    assert not (NATIONAL_IDS & registry.enabled_ids())
    assert registry.enabled_ids() == {"world_cup_2026"}


def test_national_league_schema_basic_fields_exist() -> None:
    for competition_id in NATIONAL_IDS:
        entry = CompetitionRegistry().entries()[competition_id]
        payload = entry.config_path.read_text(encoding="utf-8")

        assert entry.competition_id == competition_id
        assert entry.provider_mapping["api_football_league_id"]
        assert entry.coverage_profile.as_dict()
        assert '"enabled": false' in payload


def test_top_five_and_world_cup_registry_behavior_remains() -> None:
    registry = CompetitionRegistry()
    entries = registry.entries()

    assert {"premier_league", "serie_a", "la_liga", "bundesliga", "ligue_1"}.issubset(
        entries
    )
    assert registry.require_enabled("world_cup_2026").enabled is True
    assert all(entries[item].enabled is False for item in ("premier_league", "serie_a"))


def test_registry_does_not_read_env_or_call_provider(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import os

    def fail_getenv(name: str, default: str | None = None) -> str | None:
        raise AssertionError(f"registry unexpectedly read env {name}")

    monkeypatch.setattr(os, "getenv", fail_getenv)
    monkeypatch.setattr(os.environ, "get", fail_getenv)

    assert "argentina_primera" in CompetitionRegistry().entries()


def test_national_league_profile_files_exist() -> None:
    root = Path("config/competitions/national_leagues")

    assert (root / "README.md").is_file()
    assert len(list(root.glob("*.json"))) == 8

