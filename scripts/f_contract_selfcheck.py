"""F/D 合同独立验收：手算反例再跑脚本，验证「合同正确」而非 passed 数量。

每个反例都给出「手算期望值」并 assert，覆盖：
- D 跨赛季上季×0.5（ablate_day_decay 不吞上季系数）。
- D baseline = strategy/calibration.py 精确重放（手算 calibrate_lambdas）。
- D 联赛均值严格 PIT（captured_at >= at 排除）。
- D 共同 T30 截点（as_of = kickoff - 30min）。
- F 半球线事件 threshold（OVER L = 总进球 >= ceil(L)）。
- F 完整比分分布投影 == 一维泊松（rho=0 泊松可加性）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from f1_paired_variance import _block_bootstrap_se, _mean
from f2_sd_market_fade import _p_over_poisson, p_over_full

from w2.quant_research.da_xg_offline import (
    T30_OFFSET,
    DaXgParameters,
    XgMatchRecord,
    _previous_season,
    _season_factor,
    _team_strength,
    _usable_history,
    league_baseline,
    predict,
    predict_baseline,
)
from w2.strategy.calibration import calibrate_lambdas


def _match(i: int, *, season: str, kick: datetime, cap: datetime) -> XgMatchRecord:
    return XgMatchRecord(
        fixture_id=f"f{i}",
        competition="l1",
        season=season,
        kickoff_utc=kick,
        captured_at=cap,
        home_team="S" if i % 2 == 0 else "W",
        away_team="W" if i % 2 == 0 else "S",
        home_xg=1.2 if i % 2 == 0 else 0.8,
        away_xg=0.8 if i % 2 == 0 else 1.2,
        home_goals=1,
        away_goals=0,
    )


def main() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)

    # 1) D 跨赛季上季×0.5：ablate_day_decay 只关日衰减，不得吞上季系数。
    prev = _match(0, season="2025", kick=base, cap=base + timedelta(hours=2))
    assert _season_factor(prev, "2026", DaXgParameters()) == 0.5
    assert _season_factor(prev, "2026", DaXgParameters(ablate_day_decay=True)) == 0.5, (
        "上季系数被 ablate_day_decay 错误置 1"
    )
    print("D-1 上季×0.5：通过（ablate_day_decay 下仍 0.5）")

    # 1b) D 上一季真正进入窗口：2026/2025/2024 三季，usable seasons == ['2025','2026']。
    records = [
        _match(0, season="2026", kick=base, cap=base + timedelta(hours=2)),
        _match(
            1, season="2025", kick=base + timedelta(days=1),
            cap=base + timedelta(days=1, hours=2),
        ),
        _match(
            2, season="2024", kick=base + timedelta(days=2),
            cap=base + timedelta(days=2, hours=2),
        ),
    ]
    at3 = base + timedelta(days=30)
    hist3 = _usable_history(
        records, team="S", competition="l1", at=at3, target_season="2026",
        params=DaXgParameters(),
    )
    usable_seasons = sorted(m.season for m in hist3)
    assert usable_seasons == ["2025", "2026"], usable_seasons
    assert _previous_season("2026") == "2025"
    prev_match = next(m for m in hist3 if m.season == "2025")
    assert _season_factor(prev_match, "2026", DaXgParameters()) == 0.5
    print("D-1b 上一季选入窗口 + ×0.5：通过（usable=['2025','2026']，2024 排除）")

    # 1c) D 同联赛隔离：球队窗口按 competition 过滤，CUP 记录不得进入联赛窗口。
    cup = XgMatchRecord(
        fixture_id="cup1", competition="cup1", season="2026", kickoff_utc=base,
        captured_at=base + timedelta(hours=2), home_team="S", away_team="X",
        home_xg=5.0, away_xg=0.1, home_goals=1, away_goals=0,
    )
    league = XgMatchRecord(
        fixture_id="l0", competition="l1", season="2026", kickoff_utc=base,
        captured_at=base + timedelta(hours=2), home_team="S", away_team="X",
        home_xg=1.2, away_xg=0.8, home_goals=1, away_goals=0,
    )
    win = _usable_history(
        [cup, league], team="S", competition="l1", at=base + timedelta(days=30),
        target_season="2026", params=DaXgParameters(),
    )
    assert [m.fixture_id for m in win] == ["l0"], [m.fixture_id for m in win]
    print("D-2 同联赛隔离：通过（CUP 被排除，仅 league 进入窗口）")

    # 2) D 联赛均值严格 PIT：captured_at >= at 的历史不得计入联赛基线。
    at = base + timedelta(days=10)
    before = _match(0, season="2026", kick=base, cap=base + timedelta(hours=2))
    late = _match(1, season="2026", kick=base + timedelta(days=1), cap=at + timedelta(hours=2))
    # 只有 before 满足 captured_at < at；late 被排除。
    bl = league_baseline(
        [before, late], competition="l1", at=at, params=DaXgParameters(league_baseline_min=1)
    )
    assert bl is not None and abs(bl - before.total_xg / 2) < 1e-9, bl
    print("D-2 联赛均值 PIT：通过（captured_at>=at 被排除）")

    # 3) D baseline == calibrate_lambdas 精确重放（手算）。
    # 单场历史（min_team_history 放宽到 1 便于手算）。
    hist = [_match(0, season="2026", kick=base, cap=base + timedelta(hours=2))]
    target = base + timedelta(days=3)
    params = DaXgParameters(min_team_history=1, league_baseline_min=1)
    got = predict_baseline(
        fixture_id="t", home_team="S", away_team="W", kickoff_utc=target,
        matches=hist, target_season="2026", competition="l1", neutral_site=True, params=params,
    )
    assert got is not None
    cal = calibrate_lambdas(
        home_xg_for=1.2, home_xg_against=0.8, away_xg_for=0.8, away_xg_against=1.2,
        home_elo=None, away_elo=None, home_squad_value_eur=None, away_squad_value_eur=None,
        apply_home_advantage=False,
    )
    assert abs(got.lambda_home - cal.lambda_home) < 1e-6, (got.lambda_home, cal.lambda_home)
    assert abs(got.lambda_away - cal.lambda_away) < 1e-6, (got.lambda_away, cal.lambda_away)
    print(f"D-3 baseline==calibrate_lambdas：通过（λh={cal.lambda_home}, λa={cal.lambda_away}）")

    # 4) D 共同 T30 截点：T30_OFFSET = 30min。
    assert T30_OFFSET == timedelta(minutes=30)
    print("D-4 共同 T30 截点：通过（T30_OFFSET=30min）")

    # 4b) D 历史对手 t_i 时点基线；t_i 基线不可用则跳过（不借 target 时点基线）。
    def _sm(fid: str, h: str, a: str, day: int, hxg: float, axg: float) -> XgMatchRecord:
        return XgMatchRecord(
            fixture_id=fid, competition="l1", season="2026",
            kickoff_utc=base + timedelta(days=day),
            captured_at=base + timedelta(days=day, hours=2),
            home_team=h, away_team=a, home_xg=hxg, away_xg=axg,
            home_goals=0, away_goals=0,
        )

    d5 = [
        _sm("s0", "S", "X", 0, 2.0, 0.5),  # S 唯一历史，t_i=day0 时联赛均值 None
        _sm("w0", "Y", "W", 1, 0.5, 2.0),
    ]
    p5 = DaXgParameters(min_team_history=1, league_baseline_min=1)
    strength = _team_strength(
        d5, team="S", at=base + timedelta(days=20), target_season="2026",
        competition="l1", baseline=1.5, params=p5,
    )
    assert strength is not None and abs(strength[0] - 1.0) < 1e-9, strength
    print("D-5 历史对手 t_i 基线不可用即跳过：通过（strength=1.0 中性，未借 target 基线 1.5）")

    # 4c) D 参数身份：H=90→180 必须改变 model_identity 与 artifact_hash。
    d6 = [
        _sm("a0", "S", "X", 0, 2.5, 0.5), _sm("a1", "Y", "S", 1, 0.5, 2.5),
        _sm("a2", "S", "Z", 2, 2.5, 0.5), _sm("a3", "Z", "S", 3, 0.5, 2.5),
        _sm("a4", "S", "X", 4, 2.5, 0.5),
        _sm("a5", "X", "W", 5, 2.0, 0.3), _sm("a6", "W", "Y", 6, 0.3, 2.0),
        _sm("a7", "X", "W", 7, 2.0, 0.3), _sm("a8", "W", "Y", 8, 0.3, 2.0),
        _sm("a9", "X", "W", 9, 2.0, 0.3),
    ]
    ko = base + timedelta(days=20)
    id90 = predict(
        fixture_id="t", home_team="S", away_team="W", kickoff_utc=ko, matches=d6,
        target_season="2026", competition="l1",
        params=DaXgParameters(half_life_days=90, league_baseline_min=5),
    )
    id180 = predict(
        fixture_id="t", home_team="S", away_team="W", kickoff_utc=ko, matches=d6,
        target_season="2026", competition="l1",
        params=DaXgParameters(half_life_days=180, league_baseline_min=5),
    )
    assert id90 is not None and id180 is not None
    assert id90.model_identity != id180.model_identity
    assert id90.artifact_hash != id180.artifact_hash
    print("D-6 参数身份：通过（H=90→180 改变 model_identity 与 artifact_hash）")

    # 5) F 半球线事件 threshold：OVER L = 总进球 >= ceil(L)。
    assert abs(_p_over_poisson(2.5, 2.5) - 0.456187) < 1e-4, _p_over_poisson(2.5, 2.5)
    assert abs(_p_over_poisson(2.5, 3.5) - 0.242424) < 1e-4
    print("F-1 半球线 threshold：通过（OVER2.5=0.456187, OVER3.5=0.242424）")

    # 6) F 完整比分分布投影 == 一维泊松（rho=0 泊松可加性）。
    for lh, la in ((1.2, 1.3), (2.0, 0.5)):
        full = p_over_full(lh, la, 2.5)
        simple = _p_over_poisson(lh + la, 2.5)
        assert abs(full - simple) < 1e-6, (full, simple)
    print("F-2 完整比分投影==一维泊松：通过")

    # 7) F bootstrap 统计对象 = 每场等权均值（Codex 独立例：100 场 0 + 1 场 1）。
    diffs_boot = [0.0] * 100 + [1.0]
    wk_base = datetime(2026, 1, 5, tzinfo=UTC)  # 周一
    kick_boot = [wk_base + timedelta(minutes=i) for i in range(100)] + [
        wk_base + timedelta(weeks=1)
    ]
    boot_res = _block_bootstrap_se(diffs_boot, kick_boot, seed=1, boot=50000)
    # 每场等权均值 = 1/101；旧「周均值等权」中心 = 0.5，其 se=0.356。修复后 se 应远小于 0.356。
    assert abs(_mean(diffs_boot) - 1 / 101) < 1e-9, _mean(diffs_boot)
    assert boot_res["se"] < 0.1, boot_res["se"]  # 贴每场等权对象，非周均值 0.356
    print(
        "F-3 bootstrap 统计对象：通过"
        f"（每场等权均值={1 / 101:.4f}, se={boot_res['se']:.4f} < 0.356）"
    )

    print("ALL CONTRACT COUNTEREXAMPLES PASSED")


if __name__ == "__main__":
    main()
