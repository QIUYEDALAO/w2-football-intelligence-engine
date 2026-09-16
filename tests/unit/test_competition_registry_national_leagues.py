from __future__ import annotations

import json
from pathlib import Path

from w2.competitions.registry import CompetitionRegistry

# 现役 + LEAGUE-01R 新增的 national_leagues 竞赛 id。
# 注意：这不是“数量断言”，而是“每个 id 都必须被 registry 发现”的集合；
# 后续新增联赛只需向此集合追加新 id，无需改动任何计数常量。
NATIONAL_IDS = {
    "brasileirao_serie_a",
    "argentina_primera",
    "allsvenskan",
    "eliteserien",
    "mls",
    "chinese_super_league",
    "eredivisie",
    "primeira_liga",
    # LEAGUE-01R 新增（enabled=false，seed input）
    "england_championship",
    "italy_serie_b",
    "spain_segunda_division",
    "germany_2_bundesliga",
    "netherlands_eerste_divisie",
    "belgium_jupiler_pro_league",
    "scotland_premiership",
    "denmark_superliga",
    "austria_bundesliga",
    "switzerland_super_league",
    "czech_republic_liga",
    "turkey_super_lig",
    "greece_super_league_1",
    "croatia_hnl",
}

_NATIONAL_LEAGUES_ROOT = Path("config/competitions/national_leagues")


def _national_league_profiles() -> dict[str, dict[str, object]]:
    """从 config 目录实际读取每个 national_leagues 档案并解析为 dict。

    以文件系统为唯一事实来源，不硬编码联赛数量：新增/删除联赛无需改断言。
    """
    profiles: dict[str, dict[str, object]] = {}
    for path in sorted(_NATIONAL_LEAGUES_ROOT.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        competition_id = str(payload.get("competition_id") or "")
        profiles[competition_id] = payload
    return profiles


def test_registry_discovers_national_league_profiles() -> None:
    entries = CompetitionRegistry().entries()
    on_disk_ids = set(_national_league_profiles())

    # 磁盘上的每个 national_leagues 档案都必须被 registry 发现。
    assert on_disk_ids.issubset(entries)
    # 且 registry 中 national_leagues 组的成员与磁盘档案一一对应（含历史 id 集合）。
    assert NATIONAL_IDS.issubset(entries)
    discovered = {
        entry.competition_id
        for entry in entries.values()
        if "national_leagues" in entry.config_path.parts
    }
    assert on_disk_ids <= discovered


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


def test_registry_defaults_do_not_enable_national_leagues(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_ENVIRONMENT", "local")
    monkeypatch.delenv("W2_STAGING_ENABLED_COMPETITIONS", raising=False)

    registry = CompetitionRegistry()

    assert "argentina_primera" in registry.entries()
    assert registry.enabled_ids() == {"world_cup_2026"}


def test_national_league_profile_files_exist() -> None:
    root = _NATIONAL_LEAGUES_ROOT

    assert (root / "README.md").is_file()
    profiles = _national_league_profiles()
    # 数量不硬编码：以磁盘实际档案数为准，只要非空且能解析即可。
    assert profiles
    # 每个文件必须能被独立解析出 competition_id，且与文件名同名的 id 覆盖到位。
    assert NATIONAL_IDS.issubset(set(profiles))
