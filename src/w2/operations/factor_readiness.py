"""四因子（F3/F5/F6/F9）READY 率巡检。

每日统计目标 fixture 上各因子的 READY 率，对比基线（F6 >= 90%）与上一巡检快照，
某因子骤降（如新出现 NO_H2H_HISTORY 批量）即告警（日志 + OperationalAlert），不自动重试。

- F3 REST_FITNESS：双方在 canonical_team_match_history 有历史（开球 < 目标开球）。
- F5 RECENT_AH_COVER：双方在 canonical_historical_ah_facts 有已结算 AH 事实。
- F6 H2H：主客对在 canonical_team_match_history 有交锋历史。
- F9 TRUE_XG：双方在 team_xg_rolling_snapshot 有 xG 快照。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.operations.alerts import AlertSeverity, AlertStore, OperationalAlert

logger = logging.getLogger("w2.operations.factor_readiness")

F6_READY_RATE_BASELINE = 0.90
READY_RATE_DROP_THRESHOLD = 0.10
BASELINE_FILE_ENV = "W2_FACTOR_READINESS_BASELINE_FILE"
# 容器内可写运行时目录（host /opt/w2/shared/runtime 挂载到 /app/runtime）。
DEFAULT_BASELINE_FILE = "/app/runtime/factor_readiness_baseline.json"

FACTOR_IDS = ("F3_REST_FITNESS", "F5_RECENT_AH_COVER", "F6_H2H", "F9_TRUE_XG")


def _target_fixtures(session: Session, *, now: datetime) -> list[MatchdayFixtureIdentityModel]:
    return list(
        session.scalars(
            select(MatchdayFixtureIdentityModel).where(
                MatchdayFixtureIdentityModel.kickoff_utc.is_not(None)
            )
        )
    )


def compute_factor_readiness(
    session: Session, *, now: datetime | None = None
) -> dict[str, Any]:
    """统计四因子的 READY 率（按目标 fixture 全量口径）。

    每个因子逐场判定 READY/缺失，附带缺失原因计数（如 NO_H2H_HISTORY）。
    """
    resolved = now or datetime.now(UTC)
    fixtures = _target_fixtures(session, now=resolved)

    # 1) F3/F6 历史集合：team_w2_id -> 该队最早历史开球；pair -> 最早交锋开球。
    history_teams: dict[str, datetime] = {}
    history_pairs: dict[tuple[str, str], datetime] = {}
    for row in session.execute(
        text(
            "SELECT team_w2_id, opponent_w2_id, kickoff_utc "
            "FROM canonical_team_match_history"
        )
    ):
        team = row.team_w2_id
        opponent = row.opponent_w2_id
        kickoff = row.kickoff_utc
        if team:
            prior = history_teams.get(team)
            if prior is None or kickoff < prior:
                history_teams[team] = kickoff
        if team and opponent:
            key = (team, opponent)
            prior = history_pairs.get(key)
            if prior is None or kickoff < prior:
                history_pairs[key] = kickoff

    # 2) F5 AH 事实集合：provider_team_id -> 该队最早已结算 AH 事实开球。
    ah_teams: dict[str, datetime] = {}
    for row in session.execute(
        text(
            "SELECT home_team_provider_id, away_team_provider_id, kickoff_utc "
            "FROM canonical_historical_ah_facts"
        )
    ):
        for team in (row.home_team_provider_id, row.away_team_provider_id):
            if not team:
                continue
            prior = ah_teams.get(str(team))
            if prior is None or row.kickoff_utc < prior:
                ah_teams[str(team)] = row.kickoff_utc

    # 3) F9 xG 快照集合：provider team_id -> 最早 as_of_time。
    xg_teams: dict[str, datetime] = {}
    for row in session.execute(
        text("SELECT team_id, as_of_time FROM team_xg_rolling_snapshot")
    ):
        if not row.team_id:
            continue
        prior = xg_teams.get(str(row.team_id))
        if prior is None or row.as_of_time < prior:
            xg_teams[str(row.team_id)] = row.as_of_time

    counts = {factor: {"ready": 0, "missing": 0} for factor in FACTOR_IDS}
    reasons: dict[str, dict[str, int]] = {factor: {} for factor in FACTOR_IDS}
    for fixture in fixtures:
        kickoff = fixture.kickoff_utc
        home_w2 = fixture.home_w2_team_id
        away_w2 = fixture.away_w2_team_id
        home_pid = fixture.home_provider_team_id
        away_pid = fixture.away_provider_team_id

        # F3
        f3_ready = (
            home_w2 in history_teams
            and history_teams[home_w2] < kickoff
            and away_w2 in history_teams
            and history_teams[away_w2] < kickoff
        )
        counts["F3_REST_FITNESS"]["ready" if f3_ready else "missing"] += 1
        if not f3_ready:
            _bump(reasons, "F3_REST_FITNESS", "REST_HISTORY_UNAVAILABLE")

        # F5
        f5_ready = (
            home_pid in ah_teams
            and ah_teams[home_pid] < kickoff
            and away_pid in ah_teams
            and ah_teams[away_pid] < kickoff
        )
        counts["F5_RECENT_AH_COVER"]["ready" if f5_ready else "missing"] += 1
        if not f5_ready:
            _bump(reasons, "F5_RECENT_AH_COVER", "F5_TEAM_INSUFFICIENT")

        # F6
        pair_kickoff = history_pairs.get((home_w2, away_w2))
        f6_ready = pair_kickoff is not None and pair_kickoff < kickoff
        counts["F6_H2H"]["ready" if f6_ready else "missing"] += 1
        if not f6_ready:
            _bump(reasons, "F6_H2H", "NO_H2H_HISTORY")

        # F9
        f9_ready = (
            home_pid in xg_teams
            and xg_teams[home_pid] < kickoff
            and away_pid in xg_teams
            and xg_teams[away_pid] < kickoff
        )
        counts["F9_TRUE_XG"]["ready" if f9_ready else "missing"] += 1
        if not f9_ready:
            _bump(reasons, "F9_TRUE_XG", "XG_DATA_UNAVAILABLE")

    total = len(fixtures)
    rates = {}
    for factor in FACTOR_IDS:
        ready = counts[factor]["ready"]
        rates[factor] = {
            "ready": ready,
            "missing": counts[factor]["missing"],
            "total": total,
            "rate": round(ready / total, 6) if total else None,
            "missing_reasons": reasons[factor],
        }
    return {"fixture_total": total, "as_of": resolved.isoformat(), "factors": rates}


def _bump(reasons: dict[str, dict[str, int]], factor: str, reason: str) -> None:
    reasons[factor][reason] = reasons[factor].get(reason, 0) + 1


def _baseline_path() -> str:
    return os.environ.get(BASELINE_FILE_ENV, DEFAULT_BASELINE_FILE)


def _load_baseline() -> dict[str, Any]:
    try:
        with open(_baseline_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_baseline(report: dict[str, Any]) -> None:
    path = _baseline_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "as_of": report["as_of"],
                "fixture_total": report["fixture_total"],
                "rates": {
                    factor: report["factors"][factor]["rate"]
                    for factor in FACTOR_IDS
                },
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def evaluate_alerts(
    report: dict[str, Any], *, baseline: dict[str, Any] | None = None
) -> list[OperationalAlert]:
    """告警规则：F6 低于基线 90%；任一因子较上次巡检骤降 > 10pp。"""
    alerts: list[OperationalAlert] = []
    baseline_rates = (baseline or {}).get("rates", {})
    factors = report["factors"]
    f6_rate = factors["F6_H2H"]["rate"]
    if f6_rate is not None and f6_rate < F6_READY_RATE_BASELINE:
        alerts.append(
            OperationalAlert(
                alert_key="factor_readiness.F6_below_baseline",
                severity=AlertSeverity.WARNING,
                reason="F6_READY_RATE_BELOW_BASELINE",
                payload={"rate": f6_rate, "baseline": F6_READY_RATE_BASELINE},
            )
        )
    for factor in FACTOR_IDS:
        rate = factors[factor]["rate"]
        previous = baseline_rates.get(factor)
        if rate is not None and previous is not None and previous - rate > READY_RATE_DROP_THRESHOLD:
            alerts.append(
                OperationalAlert(
                    alert_key=f"factor_readiness.{factor}_drop",
                    severity=AlertSeverity.WARNING,
                    reason="FACTOR_READY_RATE_DROP",
                    payload={
                        "factor": factor,
                        "rate": rate,
                        "previous": previous,
                        "drop": round(previous - rate, 6),
                    },
                )
            )
    return alerts


def factor_readiness_report(
    *, now: datetime | None = None, engine: Any | None = None
) -> dict[str, Any]:
    """巡检主入口：统计 READY 率 + 评估告警 + 写基线 + 记日志。"""
    resolved = now or datetime.now(UTC)
    with Session(engine or create_engine()) as session:
        report = compute_factor_readiness(session, now=resolved)

    baseline = _load_baseline()
    alerts = evaluate_alerts(report, baseline=baseline)
    store = AlertStore()
    for alert in alerts:
        store.raise_alert(alert)
        logger.warning(
            "w2 factor readiness alert key=%s reason=%s payload=%s",
            alert.alert_key,
            alert.reason,
            alert.payload,
        )
    try:
        _save_baseline(report)
    except OSError:
        logger.exception("w2 factor readiness baseline save failed")
    logger.info("w2 factor readiness %s", report)
    return {
        "report": report,
        "alerts": [{"key": a.alert_key, "reason": a.reason, "payload": a.payload} for a in alerts],
    }
