"""DA-XG-01 时变攻防 xG 模型 —— 离线实现（候选，未冻结、未接生产）。

按计划书 v3.2 第 4 节候选公式离线实现：
- 对手赛前能力非递归收缩（原始 xG，不调用校正后强度，无循环依赖）；
- 按日指数衰减 w = c * 2^(-days/90)，窗口 20 场 / 365 天，上一季系数 0.5；
- 逐场校正 a_i = xGF_i / opp_defweak_i, d_i = xGA_i / opp_attack_i；
- 球队强度收缩 A = (Σw·a + 4)/(Σw + 4), D = (Σw·d + 4)/(Σw + 4)（未归一化权重）；
- 组合 b_home = m_l·A_home·D_away，主场 +0.30 球差，总量中间截断后单队截断。

baseline 与 challenger 同批、同 PIT、不同 model identity；不写共享 λ、不改 AH 路径。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.strategy.calibration import calibrate_lambdas

# 无 quant 专属 HashDomain（新增会改生产模块）；复用已有 offline-evidence domain，
# domain 字符串显式写进 preimage，未来新增 quant domain 是可见身份变化而非静默变化。
_DA_XG_HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE

# ============================================================================
# 候选参数（冻结假设，非已拟合最优值）
# ============================================================================


@dataclass(frozen=True, kw_only=True)
class DaXgParameters:
    half_life_days: float = 90.0
    team_window: int = 20
    season_window_days: float = 365.0
    prev_season_weight: float = 0.5
    shrinkage_k: float = 4.0
    home_advantage: float = 0.30
    league_baseline_window: int = 100
    league_baseline_min: int = 20
    min_team_history: int = 3
    total_clamp: tuple[float, float] = (1.35, 4.40)
    lambda_clamp: tuple[float, float] = (0.15, 4.25)
    # 消融开关（只解释候选，不从消融胜者挑选确认模型）
    ablate_opponent_correction: bool = False
    ablate_day_decay: bool = False
    ablate_shrinkage: bool = False


# 共同 T30 截点：预测信息截点 u = kickoff - 30 分钟（赛前 T30，计划书 5.1）。
T30_OFFSET = timedelta(minutes=30)


# ============================================================================
# 数据模型
# ============================================================================


@dataclass(frozen=True, kw_only=True)
class XgMatchRecord:
    """一场比赛（已从 team_xg_match 两侧合并为一行）。"""

    fixture_id: str
    competition: str
    season: str
    kickoff_utc: datetime
    captured_at: datetime  # PIT 可见时间（批量回补时 = 采集时间）
    home_team: str
    away_team: str
    home_xg: float  # 主队 xGF（= 客队 xGA）
    away_xg: float  # 客队 xGF（= 主队 xGA）
    home_goals: int
    away_goals: int
    neutral_site: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(self, "captured_at", _utc(self.captured_at, "captured_at"))

    @property
    def total_xg(self) -> float:
        return self.home_xg + self.away_xg


@dataclass(frozen=True, kw_only=True)
class DaXgPrediction:
    fixture_id: str
    model_identity: str
    as_of_utc: datetime
    lambda_home: float
    lambda_away: float
    total_projection: float
    home_team: str
    away_team: str
    coverage: dict[str, Any]
    artifact_hash: str


# ============================================================================
# 工具
# ============================================================================


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _finite(value: Any) -> float | None:
    # F1：bool 不是数，float(True)==1.0 不得通过。
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _day_weight(match: XgMatchRecord, at: datetime, params: DaXgParameters) -> float:
    """w = 2^(-days/90)。若消融日衰减则恒为 1。"""
    if params.ablate_day_decay:
        return 1.0
    days = (at - match.kickoff_utc).total_seconds() / 86400.0
    return float(2.0 ** (-days / params.half_life_days))


def _season_factor(match: XgMatchRecord, target_season: str, params: DaXgParameters) -> float:
    """上一季系数 0.5，当前季 1（更早赛季已在 _usable_history 过滤）。

    上季系数与日衰减消融无关：ablate_day_decay 只关日衰减，不得把上季系数一并置 1。
    """
    if match.season == target_season:
        return 1.0
    return params.prev_season_weight


def _usable_history(
    matches: Sequence[XgMatchRecord],
    *,
    team: str,
    competition: str,
    at: datetime,
    target_season: str,
    params: DaXgParameters,
) -> list[XgMatchRecord]:
    """严格 PIT + 窗口（20 场 / 365 天）+ 同联赛 + 当前及紧邻上一赛季的合格历史。

    同联赛隔离：球队窗口按 canonical competition 过滤（CUP 不得混进联赛窗口）。
    赛季过滤保留「当前季 + 紧邻上一季」，只排除更早赛季——上一季记录必须真正进入
    窗口，`_season_factor` 的 0.5 分支才可能触发。不用未来数据：kickoff < at 且
    captured_at < at（更强的历史赛前约束）。
    """
    prev_season = _previous_season(target_season)
    usable: list[XgMatchRecord] = []
    for match in matches:
        if match.competition != competition:
            continue  # 同联赛隔离：排除其他赛事（杯赛等）
        if match.home_team != team and match.away_team != team:
            continue
        if match.kickoff_utc >= at or match.captured_at >= at:
            continue
        if (at - match.kickoff_utc).total_seconds() > params.season_window_days * 86400:
            continue
        if match.season != target_season and match.season != prev_season:
            continue  # 排除更早赛季（非当前季、非紧邻上一季）
        usable.append(match)
    usable.sort(key=lambda m: m.kickoff_utc, reverse=True)
    return usable[: params.team_window]


def _previous_season(season: str) -> str | None:
    """紧邻上一季（season 为年份字符串，如 2026 -> 2025）；非年份格式返回 None。"""
    try:
        return str(int(season) - 1)
    except (TypeError, ValueError):
        return None


# ============================================================================
# 核心公式
# ============================================================================


def league_baseline(
    matches: Sequence[XgMatchRecord],
    *,
    competition: str,
    at: datetime,
    params: DaXgParameters,
) -> float | None:
    """m_l(u) = Σ(xGF_home + xGF_away) / (2 * fixture_count)，同联赛、365 天内、至少 20 场。

    联赛均值严格 PIT：历史行 captured_at < at（数据在 at 时点已可见），并显式按
    (kickoff_utc, fixture_id) 排序保证「最近 100 场」重放确定性。
    """
    eligible = [
        match
        for match in matches
        if match.competition == competition
        and match.kickoff_utc < at
        and match.captured_at < at
        and (at - match.kickoff_utc).total_seconds() <= params.season_window_days * 86400
    ]
    eligible.sort(key=lambda match: (match.kickoff_utc, match.fixture_id))
    eligible = eligible[-params.league_baseline_window :]
    if len(eligible) < params.league_baseline_min:
        return None
    total = sum(match.total_xg for match in eligible)
    baseline = total / (2 * len(eligible))
    return baseline if baseline > 0 and math.isfinite(baseline) else None


def _opponent_ability(
    matches: Sequence[XgMatchRecord],
    *,
    opponent_team: str,
    competition: str,
    at: datetime,
    target_season: str,
    baseline: float,
    params: DaXgParameters,
) -> tuple[float, float] | None:
    """对手 O 在 t 的赛前原始攻防收缩估计（非递归，不调用校正后强度）。"""
    history = _usable_history(
        matches,
        team=opponent_team,
        competition=competition,
        at=at,
        target_season=target_season,
        params=params,
    )
    if not history:
        return None  # 对手无历史 → 校正退化为中性（OPPONENT_PRIOR_ONLY）
    weighted = 0.0
    xgf_sum = 0.0
    xga_sum = 0.0
    for match in history:
        side = "home" if match.home_team == opponent_team else "away"
        xgf = match.home_xg if side == "home" else match.away_xg
        xga = match.away_xg if side == "home" else match.home_xg
        weight = _day_weight(match, at, params) * _season_factor(match, target_season, params)
        weighted += weight
        xgf_sum += weight * xgf
        xga_sum += weight * xga
    opp_attack = (xgf_sum + params.shrinkage_k * baseline) / (weighted + params.shrinkage_k)
    opp_defweak = (xga_sum + params.shrinkage_k * baseline) / (weighted + params.shrinkage_k)
    return opp_attack, opp_defweak


def _team_strength(
    matches: Sequence[XgMatchRecord],
    *,
    team: str,
    at: datetime,
    target_season: str,
    competition: str,
    baseline: float,
    params: DaXgParameters,
) -> tuple[float, float, int] | None:
    """A_T / D_T：逐场校正后收缩，未归一化权重。

    历史场次 i 的对手能力使用 t_i 时点的联赛基线 m_l(t_i)（非 target 时点 u 的基线），
    保证「历史对手用 t_i 时点基线」的非递归语义。
    """
    history = _usable_history(
        matches,
        team=team,
        competition=competition,
        at=at,
        target_season=target_season,
        params=params,
    )
    if len(history) < params.min_team_history:
        return None  # 不足最低历史 → 研究不可用
    weighted = 0.0
    a_sum = 0.0
    d_sum = 0.0
    for match in history:
        side = "home" if match.home_team == team else "away"
        xgf = match.home_xg if side == "home" else match.away_xg
        xga = match.away_xg if side == "home" else match.home_xg
        opponent = match.away_team if side == "home" else match.home_team
        # 历史对手用 t_i 时点联赛基线（非 target 时点 u 的基线，非递归、不用未来数据）。
        opp_baseline = league_baseline(
            matches, competition=competition, at=match.kickoff_utc, params=params
        )
        if opp_baseline is None:
            # t_i 时点联赛基线不可用：不得借用目标时点基线（未来数据），跳过该场校正。
            continue
        opp = _opponent_ability(
            matches,
            opponent_team=opponent,
            competition=competition,
            at=match.kickoff_utc,
            target_season=target_season,
            baseline=opp_baseline,
            params=params,
        )
        if params.ablate_opponent_correction or opp is None:
            opp_attack, opp_defweak = opp_baseline, opp_baseline
        else:
            opp_attack, opp_defweak = opp
        if opp_defweak <= 0 or opp_attack <= 0:
            continue
        a_i = xgf / opp_defweak
        d_i = xga / opp_attack
        weight = _day_weight(match, at, params) * _season_factor(match, target_season, params)
        weighted += weight
        a_sum += weight * a_i
        d_sum += weight * d_i
    if params.ablate_shrinkage:
        attack = a_sum / weighted if weighted else baseline
        defweak = d_sum / weighted if weighted else baseline
    else:
        attack = (a_sum + params.shrinkage_k) / (weighted + params.shrinkage_k)
        defweak = (d_sum + params.shrinkage_k) / (weighted + params.shrinkage_k)
    return attack, defweak, len(history)


def predict(
    *,
    fixture_id: str,
    home_team: str,
    away_team: str,
    kickoff_utc: datetime,
    matches: Sequence[XgMatchRecord],
    target_season: str,
    competition: str,
    neutral_site: bool = False,
    params: DaXgParameters | None = None,
    model_identity: str | None = None,
) -> DaXgPrediction | None:
    """对一场目标比赛在信息截点 u 生成预测；覆盖不足返回 None（不伪造）。

    信息截点 u = kickoff - 30 分钟（共同 T30 截点），非 kickoff 时点。
    model_identity 由参数快照 canonical digest 派生：改 H=90→180 必产生新 identity。
    """
    params = params or DaXgParameters()
    if model_identity is None:
        model_identity = f"da-xg-01.v1.halfline.candidate.{_params_identity(params)[:16]}"
    as_of = _utc(kickoff_utc, "kickoff_utc") - T30_OFFSET
    baseline = league_baseline(matches, competition=competition, at=as_of, params=params)
    if baseline is None:
        return None
    home = _team_strength(
        matches,
        team=home_team,
        at=as_of,
        target_season=target_season,
        competition=competition,
        baseline=baseline,
        params=params,
    )
    away = _team_strength(
        matches,
        team=away_team,
        at=as_of,
        target_season=target_season,
        competition=competition,
        baseline=baseline,
        params=params,
    )
    if home is None or away is None:
        return None
    a_home, d_home, n_home = home
    a_away, d_away, n_away = away
    b_home = baseline * a_home * d_away
    b_away = baseline * a_away * d_home
    total = _clip(b_home + b_away, *params.total_clamp)
    home_advantage = 0.0 if neutral_site else params.home_advantage
    diff = b_home - b_away + home_advantage
    lambda_home = _clip((total + diff) / 2, *params.lambda_clamp)
    lambda_away = _clip((total - diff) / 2, *params.lambda_clamp)
    coverage = {
        "league_baseline": round(baseline, 6),
        "home_history": n_home,
        "away_history": n_away,
        "home_attack": round(a_home, 6),
        "home_defweak": round(d_home, 6),
        "away_attack": round(a_away, 6),
        "away_defweak": round(d_away, 6),
        "clamped_total": total != b_home + b_away,
        "clamped_lambda": lambda_home + lambda_away != total,
        "excluded": False,
    }
    prediction = DaXgPrediction(
        fixture_id=fixture_id,
        model_identity=model_identity,
        as_of_utc=as_of,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        total_projection=total,
        home_team=home_team,
        away_team=away_team,
        coverage=coverage,
        artifact_hash="",
    )
    source_fixtures = sorted(match.fixture_id for match in matches)
    return replace(
        prediction,
        artifact_hash=_artifact_digest(
            prediction, params=params, source_fixtures=source_fixtures
        ),
    )


def _params_identity(params: DaXgParameters) -> str:
    """参数快照 canonical digest：全部候选参数变化（如 H=90→180）即 identity 变化。

    复用已有 offline-evidence domain（不新增 quant 专属 domain，避免改生产模块），
    domain 字符串显式写进 preimage，未来若新增 quant domain 是可见身份变化而非静默变化。
    """
    return canonical_sha256(
        {"hash_domain": str(_DA_XG_HASH_DOMAIN), "params": asdict(params)},
        domain=_DA_XG_HASH_DOMAIN,
    )


def _artifact_digest(
    prediction: DaXgPrediction, *, params: DaXgParameters, source_fixtures: list[str]
) -> str:
    """身份包含完整参数快照 + 完整来源（实际消费的历史 fixture 列表），经 canonical authority
    （w2.canonical-json.v2，非自建 json.dumps+sha256）计算。"""
    body = {
        "hash_domain": str(_DA_XG_HASH_DOMAIN),
        "fixture_id": prediction.fixture_id,
        "model_identity": prediction.model_identity,
        "as_of_utc": prediction.as_of_utc.isoformat(),
        "lambda_home": prediction.lambda_home,
        "lambda_away": prediction.lambda_away,
        "total_projection": prediction.total_projection,
        "home_team": prediction.home_team,
        "away_team": prediction.away_team,
        "coverage": prediction.coverage,
        "params": asdict(params),
        "source_fixtures": source_fixtures,
    }
    return canonical_sha256(body, domain=_DA_XG_HASH_DOMAIN)


# ============================================================================
# baseline（旧模型：窗口等权 xG 均值，无衰减/收缩/对手校正）
# ============================================================================


def predict_baseline(
    *,
    fixture_id: str,
    home_team: str,
    away_team: str,
    kickoff_utc: datetime,
    matches: Sequence[XgMatchRecord],
    target_season: str,
    competition: str,
    neutral_site: bool = False,
    params: DaXgParameters | None = None,
) -> DaXgPrediction | None:
    """冻结比较基线：现有 strategy/calibration.py 的精确重放（非乘法组合另一套）。

    输入为双方滚动 xGF/xGA 均值（窗口等权），经 calibrate_lambdas 输出 λ；elo/squad/
    lineup 输入均取 None/0（重放冻结基线），主场优势按中立场开关。信息截点同为 T30。
    """
    params = params or DaXgParameters()
    as_of = _utc(kickoff_utc, "kickoff_utc") - T30_OFFSET
    baseline = league_baseline(matches, competition=competition, at=as_of, params=params)
    if baseline is None:
        return None

    def raw_means(team: str) -> tuple[float, float] | None:
        history = _usable_history(
            matches,
            team=team,
            competition=competition,
            at=as_of,
            target_season=target_season,
            params=params,
        )
        if len(history) < params.min_team_history:
            return None
        xgf = 0.0
        xga = 0.0
        for match in history:
            side = "home" if match.home_team == team else "away"
            xgf += match.home_xg if side == "home" else match.away_xg
            xga += match.away_xg if side == "home" else match.home_xg
        return xgf / len(history), xga / len(history)

    home = raw_means(home_team)
    away = raw_means(away_team)
    if home is None or away is None:
        return None
    home_xg_for, home_xg_against = home
    away_xg_for, away_xg_against = away
    calibrated = calibrate_lambdas(
        home_xg_for=home_xg_for,
        home_xg_against=home_xg_against,
        away_xg_for=away_xg_for,
        away_xg_against=away_xg_against,
        home_elo=None,
        away_elo=None,
        home_squad_value_eur=None,
        away_squad_value_eur=None,
        lineup_strength_adjustment=0.0,
        lineup_ah_adjustment=0.0,
        lineup_totals_adjustment=0.0,
        apply_home_advantage=not neutral_site,
    )
    lambda_home = calibrated.lambda_home
    lambda_away = calibrated.lambda_away
    total = lambda_home + lambda_away
    prediction = DaXgPrediction(
        fixture_id=fixture_id,
        model_identity="da-xg-baseline.v1.frozen",
        as_of_utc=as_of,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        total_projection=total,
        home_team=home_team,
        away_team=away_team,
        coverage={"league_baseline": round(baseline, 6), "excluded": False},
        artifact_hash="",
    )
    source_fixtures = sorted(match.fixture_id for match in matches)
    return replace(
        prediction,
        artifact_hash=_artifact_digest(
            prediction, params=params, source_fixtures=source_fixtures
        ),
    )


# ============================================================================
# rolling-origin 回放 + 覆盖/排除报告
# ============================================================================


@dataclass(frozen=True, kw_only=True)
class ReplayResult:
    fixture_id: str
    challenger: DaXgPrediction | None
    baseline: DaXgPrediction | None
    excluded_reason: str | None


def rolling_origin_replay(
    matches: Sequence[XgMatchRecord],
    *,
    params: DaXgParameters | None = None,
) -> list[ReplayResult]:
    """rolling-origin：对每场历史比赛，用其赛前严格可见历史做 challenger + baseline 预测。

    每场只用一个数据角色；baseline 与 challenger 同批、同 PIT、不同 model identity。
    """
    params = params or DaXgParameters()
    ordered = sorted(matches, key=lambda m: (m.kickoff_utc, m.fixture_id))
    results: list[ReplayResult] = []
    for target in ordered:
        cutoff = target.kickoff_utc - T30_OFFSET
        history = [
            m
            for m in ordered
            if m.kickoff_utc < cutoff and m.captured_at < cutoff
        ]
        challenger = predict(
            fixture_id=target.fixture_id,
            home_team=target.home_team,
            away_team=target.away_team,
            kickoff_utc=target.kickoff_utc,
            matches=history,
            target_season=target.season,
            competition=target.competition,
            neutral_site=target.neutral_site,
            params=params,
        )
        baseline = predict_baseline(
            fixture_id=target.fixture_id,
            home_team=target.home_team,
            away_team=target.away_team,
            kickoff_utc=target.kickoff_utc,
            matches=history,
            target_season=target.season,
            competition=target.competition,
            neutral_site=target.neutral_site,
            params=params,
        )
        excluded = (
            "COVERAGE_INSUFFICIENT"
            if challenger is None or baseline is None
            else None
        )
        results.append(
            ReplayResult(
                fixture_id=target.fixture_id,
                challenger=challenger,
                baseline=baseline,
                excluded_reason=excluded,
            )
        )
    return results


def coverage_report(
    results: Sequence[ReplayResult],
) -> dict[str, Any]:
    """覆盖与排除报告：有效预测数、排除数、排除原因分布。"""
    total = len(results)
    covered = sum(1 for r in results if r.excluded_reason is None)
    excluded = total - covered
    return {
        "total": total,
        "covered": covered,
        "excluded": excluded,
        "coverage_rate": round(covered / total, 6) if total else 0.0,
        "exclusion_reasons": {
            reason: sum(1 for r in results if r.excluded_reason == reason)
            for reason in sorted(
                {r.excluded_reason for r in results if r.excluded_reason}
            )
        },
    }


# ============================================================================
# 独立算例（self-check）
# ============================================================================


def _demo() -> None:
    """独立算例：中性先验 / 强对手方向 / 主客交换 / 极值 clamp / 重复性哈希。"""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    params = DaXgParameters(league_baseline_min=5)

    def match(
        i: int, home: str, away: str, hxg: float, axg: float, season: str = "2026"
    ) -> XgMatchRecord:
        return XgMatchRecord(
            fixture_id=f"f{i}",
            competition="l1",
            season=season,
            kickoff_utc=base + timedelta(days=i),
            captured_at=base + timedelta(days=i, hours=2),
            home_team=home,
            away_team=away,
            home_xg=hxg,
            away_xg=axg,
            home_goals=0,
            away_goals=0,
        )

    # 强队 S（高 xG）、弱队 W（低 xG），每队各 5 场历史。
    matches = [
        match(0, "S", "X", 2.5, 0.5),
        match(1, "Y", "S", 0.5, 2.5),
        match(2, "S", "Z", 2.5, 0.5),
        match(3, "Z", "S", 0.5, 2.5),
        match(4, "S", "X", 2.5, 0.5),
        match(5, "X", "W", 2.0, 0.3),
        match(6, "W", "Y", 0.3, 2.0),
        match(7, "X", "W", 2.0, 0.3),
        match(8, "W", "Y", 0.3, 2.0),
        match(9, "X", "W", 2.0, 0.3),
    ]
    kickoff = base + timedelta(days=20)
    pred = predict(
        fixture_id="target",
        home_team="S",
        away_team="W",
        kickoff_utc=kickoff,
        matches=matches,
        target_season="2026",
        competition="l1",
        params=params,
    )
    assert pred is not None, "强队 vs 弱队应有足够历史"
    # 强队主场的进球期望应高于弱队。
    assert pred.lambda_home > pred.lambda_away, (pred.lambda_home, pred.lambda_away)
    # 主客交换：S 客场 vs W 主场，主场优势翻转。
    away = predict(
        fixture_id="target2",
        home_team="W",
        away_team="S",
        kickoff_utc=kickoff,
        matches=matches,
        target_season="2026",
        competition="l1",
        params=params,
    )
    assert away is not None
    assert away.lambda_away > away.lambda_home, (away.lambda_home, away.lambda_away)
    # 中性先验：无历史球队 → 覆盖不足返回 None（不伪造）。
    nohist = predict(
        fixture_id="target3",
        home_team="NEW1",
        away_team="NEW2",
        kickoff_utc=kickoff,
        matches=matches,
        target_season="2026",
        competition="l1",
        params=params,
    )
    assert nohist is None, "无历史球队应输出研究不可用而非伪造"
    # 极值 clamp：超高水平输入被 clamp 到 [1.35, 4.40] / [0.15, 4.25]。
    blast = [match(i, "S", "X", 9.0, 0.1) for i in range(5)] + [
        match(i + 5, "X", "W", 0.1, 9.0) for i in range(5)
    ]
    extreme = predict(
        fixture_id="target4",
        home_team="S",
        away_team="W",
        kickoff_utc=base + timedelta(days=20),
        matches=blast,
        target_season="2026",
        competition="l1",
        params=params,
    )
    assert extreme is not None
    assert 1.35 <= extreme.total_projection <= 4.40, extreme.total_projection
    assert 0.15 <= extreme.lambda_home <= 4.25
    assert 0.15 <= extreme.lambda_away <= 4.25
    # 重复性哈希：同输入两次预测 hash 一致。
    again = predict(
        fixture_id="target",
        home_team="S",
        away_team="W",
        kickoff_utc=kickoff,
        matches=matches,
        target_season="2026",
        competition="l1",
        params=params,
    )
    assert again is not None and again.artifact_hash == pred.artifact_hash
    # baseline 与 challenger 同批同 PIT 不同 identity。
    base_pred = predict_baseline(
        fixture_id="target",
        home_team="S",
        away_team="W",
        kickoff_utc=kickoff,
        matches=matches,
        target_season="2026",
        competition="l1",
        params=params,
    )
    assert base_pred is not None
    assert base_pred.model_identity != pred.model_identity
    print("DA-XG-01 demo: all worked examples passed")


if __name__ == "__main__":
    _demo()
