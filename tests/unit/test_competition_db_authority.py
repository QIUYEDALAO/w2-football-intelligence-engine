from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from apps.scheduler.main import (
    future_fixture_refresh_competition_ids,
    matchday_checkpoint_competition_ids,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from w2.competitions.registry import CompetitionRegistry
from w2.competitions.seed import (
    apply_collection_policy_update,
    seed_competition_runtime_authority,
    set_competition_enabled,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.league_models import (
    LeagueReadinessAuditModel,
    LeagueSeasonModel,
)
from w2.ingestion.future_refresh import load_refresh_policy
from w2.matchday.intake_v2 import competition_policies, load_matchday_policy

# 现役非五大联赛（不含新联赛 seed input）。这是「集合成员」断言而非数量断言：
# 新增联赛若同时加入了 future/matchday policy，需在此追加其 id；否则保持现状。
ACTIVE_13 = {
    "premier_league",
    "la_liga",
    "bundesliga",
    "serie_a",
    "ligue_1",
    "brasileirao_serie_a",
    "argentina_primera",
    "mls",
    "chinese_super_league",
    "allsvenskan",
    "eliteserien",
    "eredivisie",
    "primeira_liga",
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


def _on_disk_competition_ids() -> set[str]:
    """从 config/competitions/ 目录实际读取全部 competition_id，不硬编码数量。"""
    import json

    root = Path("config/competitions")
    ids: set[str] = set()
    for path in sorted(root.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        competition_id = str(payload.get("competition_id") or "")
        if competition_id:
            ids.add(competition_id)
    return ids


def _on_disk_competition_count() -> int:
    return len(_on_disk_competition_ids())


def _seeded_engine(environment: str = "test"):  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    report = seed_competition_runtime_authority(
        engine,
        environment=environment,
        updated_by="unit-test-seed",
        now=datetime(2026, 7, 23, tzinfo=UTC),
    )
    assert report.conflicts == ()
    return engine, report


def test_seed_is_idempotent_and_reconciles_all_json_profiles() -> None:
    engine, first = _seeded_engine()
    second = seed_competition_runtime_authority(
        engine,
        environment="test",
        updated_by="unit-test-seed-rerun",
    )

    # 不硬编码联赛数量：以磁盘实际 config 档案数为准（新增联赛无需改此断言）。
    expected = _on_disk_competition_count()
    assert first.inserted_profiles == expected
    assert first.inserted_seasons == expected
    assert first.audits_written == expected
    assert second.inserted_profiles == 0
    assert second.inserted_seasons == 0
    assert second.unchanged == expected
    assert second.audits_written == 0


def test_staging_policy_is_seeded_into_database_without_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    engine, _report = _seeded_engine("staging")

    assert CompetitionRegistry(engine).enabled_ids() == {
        "world_cup_2026",
        "premier_league",
        "la_liga",
        "bundesliga",
        "serie_a",
        "ligue_1",
        "brasileirao_serie_a",
        "argentina_primera",
        "mls",
        "chinese_super_league",
        "allsvenskan",
        "eliteserien",
        "eredivisie",
        "primeira_liga",
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


def test_collection_policy_update_activates_exact_13_and_retires_world_cup(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_ENVIRONMENT", "production")
    engine, _report = _seeded_engine("production")

    updated = apply_collection_policy_update(
        engine,
        updated_by="unit-test-owner-authorization",
        now=datetime(2026, 8, 12, tzinfo=UTC),
    )
    registry = CompetitionRegistry(engine)
    enabled = registry.enabled_ids()

    # 不硬编码数量：
    #   - updated 覆盖所有已 seed 的 profile（现役 + 新联赛 + world_cup），数量随磁盘档案走；
    #   - enabled 只含「有 collection policy 且非 world_cup」的联赛（= ACTIVE_13），
    #     world_cup 退役、新联赛已有 policy 随 policy update 一并启用。
    all_ids = _on_disk_competition_ids()
    assert set(updated) == all_ids
    assert enabled == ACTIVE_13
    assert "world_cup_2026" not in enabled
    monkeypatch.setattr(
        "w2.competitions.registry.CompetitionRegistry",
        lambda: CompetitionRegistry(engine),
    )
    monkeypatch.setattr(
        "w2.matchday.intake_v2.CompetitionRegistry",
        lambda: CompetitionRegistry(engine),
    )
    assert set(future_fixture_refresh_competition_ids()) == ACTIVE_13
    assert set(matchday_checkpoint_competition_ids()) == ACTIVE_13
    for competition_id in enabled:
        entry = registry.require_enabled(competition_id)
        assert entry.refresh_switches == {"fixtures": True, "odds": True, "lineups": True}
        assert entry.future_refresh_policy is not None
        assert entry.matchday_policy is not None


def test_collection_policy_raises_on_single_sided_policy(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """一个已注册联赛只在 future 或只在 matchday 出现 → COLLECTION_POLICY_ASYMMETRIC。

    覆盖「手滑只改一个 policy 文件」造成的半配置状态，防止其被交集过滤静默吞掉。
    """
    import json

    monkeypatch.setenv("W2_ENVIRONMENT", "production")
    engine, _report = _seeded_engine("production")

    # 构造不对称 policy：brasileirao_serie_a 两边都有（对称，进入 active_ids），
    # argentina_primera 只在 future 里（不对称，应触发 ASYMMETRIC）。
    future = {"competitions": [
        {"competition_id": "brasileirao_serie_a"},
        {"competition_id": "argentina_primera"},
    ]}
    matchday = {"competitions": [
        {"competition_id": "brasileirao_serie_a"},
    ]}
    config_root = tmp_path / "config"
    (config_root / "policies").mkdir(parents=True)
    (config_root / "policies" / "future_fixture_refresh.v1.json").write_text(
        json.dumps(future), encoding="utf-8"
    )
    (config_root / "policies" / "matchday_intake.v2.json").write_text(
        json.dumps(matchday), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="COLLECTION_POLICY_ASYMMETRIC:argentina_primera"):
        apply_collection_policy_update(
            engine,
            config_root=config_root,
            updated_by="unit-test-owner-authorization",
            now=datetime(2026, 8, 12, tzinfo=UTC),
        )


def test_collection_policy_ignores_leagues_absent_from_both_policies(
    monkeypatch, tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """两个 policy 文件都没有的联赛（新联赛 seed-only）不触发任何 raise。"""
    import json

    monkeypatch.setenv("W2_ENVIRONMENT", "production")
    engine, _report = _seeded_engine("production")

    # 只保留 brasileirao_serie_a（对称），新联赛（如 england_championship）两个文件都没有，
    # 且已注册，但不应触发 ASYMMETRIC 或 MISSING。
    future = {"competitions": [{"competition_id": "brasileirao_serie_a"}]}
    matchday = {"competitions": [{"competition_id": "brasileirao_serie_a"}]}
    config_root = tmp_path / "config"
    (config_root / "policies").mkdir(parents=True)
    (config_root / "policies" / "future_fixture_refresh.v1.json").write_text(
        json.dumps(future), encoding="utf-8"
    )
    (config_root / "policies" / "matchday_intake.v2.json").write_text(
        json.dumps(matchday), encoding="utf-8"
    )

    updated = apply_collection_policy_update(
        engine,
        config_root=config_root,
        updated_by="unit-test-owner-authorization",
        now=datetime(2026, 8, 12, tzinfo=UTC),
    )
    # 只 enable 了有对称 policy 的联赛；新联赛（两个文件都没有）保持 disabled。
    # 注意：updated 覆盖所有被处理的 profile（含 disabled 的），enable 与否要看
    # registry.enabled_ids()（= active_ids = 对称 policy 联赛）。
    enabled = CompetitionRegistry(engine).enabled_ids()
    assert "brasileirao_serie_a" in enabled
    assert "england_championship" not in enabled
    assert "world_cup_2026" not in enabled


def test_enabled_change_is_visible_to_same_registry_without_deploy() -> None:
    engine, _report = _seeded_engine()
    registry = CompetitionRegistry(engine)
    assert registry.is_enabled("allsvenskan") is False

    audit_hash = set_competition_enabled(
        engine,
        competition_id="allsvenskan",
        enabled=True,
        updated_by="unit-test-operator",
        now=datetime(2026, 7, 23, 1, tzinfo=UTC),
    )

    assert registry.is_enabled("allsvenskan") is True
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(LeagueReadinessAuditModel)
                .where(LeagueReadinessAuditModel.audit_sha256 == audit_hash)
            )
            == 1
        )


def test_top_level_enabled_gates_registry_and_both_schedulers_in_same_process(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    engine, _report = _seeded_engine("staging")
    monkeypatch.setattr("w2.competitions.registry.create_engine", lambda: engine)
    registry = CompetitionRegistry(engine)

    def visible() -> tuple[bool, bool, bool]:
        return (
            "allsvenskan" in registry.enabled_ids(),
            "allsvenskan" in future_fixture_refresh_competition_ids(),
            "allsvenskan" in matchday_checkpoint_competition_ids(),
        )

    assert visible() == (True, True, True)
    set_competition_enabled(
        engine,
        competition_id="allsvenskan",
        enabled=False,
        updated_by="same-process-toggle-test",
    )
    assert visible() == (False, False, False)
    set_competition_enabled(
        engine,
        competition_id="allsvenskan",
        enabled=True,
        updated_by="same-process-rollback-test",
    )
    assert visible() == (True, True, True)


def test_seed_policy_enabled_is_not_an_independent_runtime_authority(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    engine, _report = _seeded_engine("staging")
    with Session(engine) as session:
        row = session.scalar(
            select(LeagueSeasonModel).where(
                LeagueSeasonModel.competition_id == "allsvenskan"
            )
        )
        assert row is not None
        payload = dict(row.payload)
        payload["future_refresh_policy"] = dict(payload["future_refresh_policy"]) | {
            "enabled": False
        }
        payload["matchday_policy"] = dict(payload["matchday_policy"]) | {"enabled": False}
        row.payload = payload
        session.commit()

    registry = CompetitionRegistry(engine)
    assert load_refresh_policy(competition_id="allsvenskan", registry=registry).enabled is True
    assert competition_policies(load_matchday_policy(registry))["allsvenskan"].enabled is True


def test_runtime_authority_modules_do_not_read_install_seed_json() -> None:
    paths = (
        "src/w2/competitions/registry.py",
        "src/w2/ingestion/future_refresh.py",
        "src/w2/matchday/intake_v2.py",
        "apps/scheduler/main.py",
    )
    forbidden = (
        "config/competitions",
        "future_fixture_refresh.v1.json",
        "matchday_intake.v2.json",
        "W2_STAGING_ENABLED_COMPETITIONS",
    )
    for path in paths:
        source = Path(path).read_text(encoding="utf-8")
        assert not any(value in source for value in forbidden), path


def test_production_code_cannot_read_competition_install_seed_files() -> None:
    allowed = {
        Path("src/w2/competitions/seed.py"),
        Path("src/w2/historical/existing_data_inventory.py"),
    }
    for root in (Path("src"), Path("apps")):
        for path in root.rglob("*.py"):
            if path in allowed:
                continue
            source = path.read_text(encoding="utf-8")
            assert "config/competitions" not in source, path
            assert "config_path.read_text" not in source, path
            assert "future_fixture_refresh.v1.json" not in source, path
            assert "matchday_intake.v2.json" not in source, path
