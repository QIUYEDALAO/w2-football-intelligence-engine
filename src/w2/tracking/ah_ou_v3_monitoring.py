"""Read-only model monitoring at each 200 eligible settled fixtures per market.

Both FT workers call this in the settlement transaction. This module appends
facts and descriptive reports; it cannot send recommendations or fit a model.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.ah_ou_monitoring_models import (
    AhOuV3MonitoringFactModel,
    AhOuV3MonitoringReportModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.infrastructure.persistence.models import ResultModel
from w2.strategy.ah_ou_softmax import (
    load_ah_model,
    load_ou_model,
)
from w2.tracking.ah_ou_v3_monitoring_prediction import monitoring_class_probabilities
from w2.tracking.ah_ou_v3_postmatch import (
    _net_units,
    _result_source,
    verify_v3_monitoring_input_in_session,
)

REPORT_INTERVAL = 200
FIVE_STATES = ("LOSS", "HALF_LOSS", "PUSH", "HALF_WIN", "WIN")

logger = logging.getLogger(__name__)
FACT_SCHEMA = "w2.ah_ou_v3_monitoring_fact.v1"
REPORT_SCHEMA = "w2.ah_ou_v3_monitoring_report.v1"


def _digest(value: Any) -> str:
    return canonical_sha256(value, domain=HashDomain.RECOMMENDATION_DECISION_V4)


def _outcome(market: str, home: int, away: int, side: str, line: Decimal) -> str:
    if market == "ASIAN_HANDICAP":
        return settle_asian_handicap(home, away, side, line).value
    return settle_total_goals(home + away, side, line).value


def _fact(
    session: Session, decision: AhOuDecisionLedgerModel, result: ResultModel
) -> dict[str, Any]:
    source = _result_source(session, result)
    fixture = session.get(MatchdayFixtureIdentityModel, result.fixture_id)
    if fixture is None:
        raise ValueError("V3_MONITORING_FIXTURE_MISSING")
    payload: dict[str, Any] = {
        "schema_version": FACT_SCHEMA,
        "decision_id": decision.decision_id,
        "fixture_id": decision.fixture_id,
        "market": decision.market,
        "model_version": decision.model_version,
        "calibration_version": decision.calibration_version,
        "selected": decision.selected,
        "eligible": False,
        "exclusion_reason": None,
        "input_hash": decision.input_hash,
        "quote_identity_hash": decision.quote_identity_hash,
        "capture_id": decision.capture_id,
        "source_raw_hash": decision.source_capture_sha256,
        "result_id": result.id,
        "result_hash": result.result_hash,
        "result_source": source,
        "home_goals": result.home_goals,
        "away_goals": result.away_goals,
        "competition": fixture.competition_id,
        "month": fixture.kickoff_utc.strftime("%Y-%m"),
    }
    distribution = decision.full_distribution
    if decision.skip_reason:
        payload["exclusion_reason"] = decision.skip_reason
        return payload
    if result.result_status != "FT":
        payload["exclusion_reason"] = "V3_MONITORING_NON_FT_VOID"
        return payload
    # F4：selected 决策的投影权威是 frozen_terms（写入时 frozen_terms == monitoring_terms）；
    # below-threshold（未 selected）决策才依赖 full_distribution.monitoring_terms。缺投影的
    # selected 决策不再静默排除，而是用 frozen_terms + 动态重算补投影。
    terms_source = (
        decision.frozen_terms if decision.selected else distribution.get("monitoring_terms")
    )
    if not isinstance(terms_source, dict):
        payload["exclusion_reason"] = "V3_MONITORING_PREMATCH_PROJECTION_MISSING"
        return payload
    terms = verify_v3_monitoring_input_in_session(session, decision)
    if decision.model_version != _digest(
        {"ah_model": load_ah_model(), "ou_model": load_ou_model()}
    ):
        raise ValueError("V3_MONITORING_MODEL_BINDING_CONFLICT")
    probabilities = distribution.get("monitoring_probabilities")
    recomputed = monitoring_class_probabilities(distribution["features"], decision.market)
    if probabilities is None:
        # F4：缺投影的 selected 决策动态重算概率（features 冻结在 full_distribution）。
        probabilities = recomputed
    elif probabilities != recomputed:
        raise ValueError("V3_MONITORING_PROBABILITIES_CONFLICT")
    states = dict.fromkeys(FIVE_STATES, 0.0)
    for row in probabilities:
        probability = float(row["probability"])
        if not math.isfinite(probability) or probability < 0:
            raise ValueError("V3_MONITORING_PROBABILITY_INVALID")
        klass = int(row["class"])
        # AH model classes describe home minus away; OU classes describe totals.
        outcome = _outcome(
            decision.market, klass, 0, terms["selection"], Decimal(terms["selected_line"])
        )
        states[outcome] += probability
    if abs(sum(states.values()) - 1) > 1e-9:
        raise ValueError("V3_MONITORING_PROBABILITY_SUM_INVALID")
    outcome = _outcome(
        decision.market,
        result.home_goals,
        result.away_goals,
        terms["selection"],
        Decimal(terms["selected_line"]),
    )
    pair = distribution.get("monitoring_pair_prices")
    sides = ("home", "away") if decision.market == "ASIAN_HANDICAP" else ("over", "under")
    # F4：缺投影的 selected 决策从同一 capture 的 observation 重建双侧价格（原盘口，
    # 非 FT 新价）；有投影则对比校验，两者都不静默排除。
    pair_missing = not isinstance(pair, dict) or set(pair) != set(sides)
    if pair_missing:
        pair = {}
    # Bind both prices to the same original capture, rather than new FT odds.
    from w2.infrastructure.persistence.matchday_intake_models import MatchdayMarketObservationModel

    source_line = Decimal(terms["home_line"] or terms["total_line"])
    for side in sides:
        line = -source_line if side == "away" else source_line
        observations = session.scalars(
            select(MatchdayMarketObservationModel).where(
                MatchdayMarketObservationModel.capture_id == decision.capture_id,
                MatchdayMarketObservationModel.fixture_id == fixture.fixture_id,
                MatchdayMarketObservationModel.bookmaker_id == str(terms.get("bookmaker_id") or ""),
                MatchdayMarketObservationModel.canonical_market == decision.market,
                MatchdayMarketObservationModel.canonical_selection == side.upper(),
            )
        ).all()
        if pair_missing:
            line_matches = [
                row
                for row in observations
                if row.line is not None and Decimal(row.line) == line
            ]
            if len(line_matches) != 1:
                raise ValueError("V3_MONITORING_PAIR_PRICE_CONFLICT")
            pair[side] = float(line_matches[0].decimal_odds)
        else:
            matches = [
                row
                for row in observations
                if row.line is not None
                and Decimal(row.line) == line
                and Decimal(row.decimal_odds) == Decimal(str(pair[side]))
            ]
            if len(matches) != 1:
                raise ValueError("V3_MONITORING_PAIR_PRICE_CONFLICT")
    q = (1 / float(pair[sides[0]])) / sum(1 / float(pair[side]) for side in sides)
    pure_side = sides[0] if q >= 0.5 else sides[1]
    pure_line = -source_line if pure_side == "away" else source_line
    pure_outcome = _outcome(
        decision.market, result.home_goals, result.away_goals, pure_side.upper(), pure_line
    )
    captured_at = datetime.fromisoformat(terms["captured_at"])
    observed_state = FIVE_STATES.index(outcome)
    rps = (
        sum(
            (
                sum(states[state] for state in FIVE_STATES[: index + 1])
                - int(observed_state <= index)
            )
            ** 2
            for index in range(4)
        )
        / 4
    )
    payload.update(
        eligible=True,
        terms=terms,
        features=distribution["features"],
        probabilities=probabilities,
        five_state_probabilities=states,
        five_state=outcome,
        hypothetical_net_units=str(_net_units(outcome, Decimal(terms["entry_odds"]))),
        recommendation_net_units=(
            str(_net_units(outcome, Decimal(terms["entry_odds"]))) if decision.selected else "0"
        ),
        rps=rps,
        quote_age_seconds=(decision.decision_at - captured_at).total_seconds(),
        pure_market_side=pure_side.upper(),
        pure_market_q=max(q, 1 - q),
        pure_market_outcome=pure_outcome,
        pure_market_net_units=str(_net_units(pure_outcome, Decimal(str(pair[pure_side])))),
    )
    return payload


def build_cumulative_report(facts: list[dict[str, Any]]) -> dict[str, Any]:
    """Every 200 eligible FT fixtures; same-fixture equal-coverage comparator."""
    if not facts or len(facts) % REPORT_INTERVAL or any(not row["eligible"] for row in facts):
        raise ValueError("V3_MONITORING_MILESTONE_INVALID")
    if len({row["fixture_id"] for row in facts}) != len(facts):
        raise ValueError("V3_MONITORING_DUPLICATE_FIXTURE")
    if (
        len({(row["market"], row["model_version"], row["calibration_version"]) for row in facts})
        != 1
    ):
        raise ValueError("V3_MONITORING_VERSION_SET_CONFLICT")
    selected = [row for row in facts if row["selected"]]
    count = len(selected)
    comparator = sorted(facts, key=lambda row: (-row["pure_market_q"], row["fixture_id"]))[:count]
    breakdown: dict[str, dict[str, Any]] = {}
    for field in ("competition", "month"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in facts:
            groups[row[field]].append(row)
        breakdown[field] = {
            key: {
                "eligible_settled": len(rows),
                "selected": sum(row["selected"] for row in rows),
                "five_state_counts": dict(Counter(row["five_state"] for row in rows)),
                "mean_rps": sum(row["rps"] for row in rows) / len(rows),
            }
            for key, rows in sorted(groups.items())
        }
    return {
        "schema_version": REPORT_SCHEMA,
        "market": facts[0]["market"],
        "model_version": facts[0]["model_version"],
        "calibration_version": facts[0]["calibration_version"],
        "eligible_settled": len(facts),
        "recommended": count,
        "five_state_counts": dict(Counter(row["five_state"] for row in selected)),
        "cover_win_rate": (
            sum(row["five_state"] in {"WIN", "HALF_WIN"} for row in selected) / count
            if count
            else None
        ),
        "net_units": str(
            sum((Decimal(row["recommendation_net_units"]) for row in selected), Decimal(0))
        ),
        "mean_rps": sum(row["rps"] for row in facts) / len(facts),
        "quote_age_seconds_mean": sum(row["quote_age_seconds"] for row in facts) / len(facts),
        "quote_age_seconds_max": max(row["quote_age_seconds"] for row in facts),
        "pure_market_equal_coverage": {
            "eligible_fixture_ids": [row["fixture_id"] for row in facts],
            "selected_fixture_ids": [row["fixture_id"] for row in comparator],
            "recommended": len(comparator),
            "net_units": str(
                sum((Decimal(row["pure_market_net_units"]) for row in comparator), Decimal(0))
            ),
        },
        "breakdown": breakdown,
        "decision_ids": [row["decision_id"] for row in facts],
        "facts_hash": _digest(facts),
        "automatic_refit": False,
    }


def append_monitoring_in_session(
    session: Session, *, now: datetime | None = None
) -> dict[str, int]:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('v3-monitoring', 0))"))
        observed = session.scalar(text("SELECT clock_timestamp()"))
    else:
        observed = now or datetime.now(UTC)
    created = excluded = skipped_stale = reports = quarantined = 0
    decisions = list(
        session.scalars(
            select(AhOuDecisionLedgerModel)
            .where(AhOuDecisionLedgerModel.decision_contract == "w2.ah_ou_decision.v3.1")
            .order_by(
                AhOuDecisionLedgerModel.decision_id,
            )
        )
    )
    # 监控 fact 的唯一约束是 (fixture_id, market, model_version, calibration_version)，
    # 但同一 slot 可能因「旧 SKIP 重评估」存在多条决策（不同 decision_id）。监控只记录
    # 该 slot 的最终决策状态：优先 selected，否则取最新（decision_at 最大）。
    by_slot: dict[tuple[str, str, str, str], AhOuDecisionLedgerModel] = {}
    for decision in decisions:
        key = (
            decision.fixture_id,
            decision.market,
            decision.model_version,
            decision.calibration_version,
        )
        existing = by_slot.get(key)
        if existing is None or (
            decision.selected,
            decision.decision_at,
            decision.decision_id,
        ) > (
            existing.selected,
            existing.decision_at,
            existing.decision_id,
        ):
            by_slot[key] = decision
    for decision in decisions:
        key = (
            decision.fixture_id,
            decision.market,
            decision.model_version,
            decision.calibration_version,
        )
        if by_slot.get(key) is not decision:
            continue
        result = session.scalar(
            select(ResultModel).where(
                ResultModel.fixture_id
                == "api_football:" + decision.fixture_id.removeprefix("api_football:")
            )
        )
        if result is None:
            continue
        try:
            payload = _fact(session, decision, result)
        except ValueError as exc:
            code = str(exc)
            # 逐 fixture 隔离：赛果溯源失败（V3_RESULT_*）跳过该场监控 fact，
            # 不阻塞其余场次；与结算隔离口径一致。
            if code.startswith("V3_RESULT_"):
                continue
            # F（指令书 F，2026-10-10）：决策契约类失败（V3_PUBLIC_QUOTE_*）同样逐条隔离。
            # 现状（修复前）：一条违规决策让整个 append_monitoring_in_session 抛错 →
            #   ① 外层事务回滚，连 settlement 一起丢（违背 _settle_v3_postmatch 注释里
            #      「blocked 只表示部分场次未结算…必须 commit 而非整轮回滚，否则又变成
            #      一坏全滚连坐」的既有口径）；
            #   ② 每 300s 的 sweep 必然复发 → 结果后端积累 FAILURE 元数据，
            #      且 release 回读 f 项（部署后 Traceback=0）每次都红。
            # 隔离后：该决策进入 quarantine（不落 fact + 计数 + WARNING 留痕），
            # 其余场次照常落 fact，sweep 整体成功 ⇒ 不再产生 FAILURE，也不再阻塞发布。
            # 注：quarantine 是**跳过**而非豁免——欠下的 fact 在缺陷修好后由同一次幂等
            # sweep 自然补算（不存在「静默丢失」）。
            if code.startswith("V3_PUBLIC_QUOTE_"):
                quarantined += 1
                logger.warning(
                    "v3 monitoring fact quarantined: code=%s decision_id=%s fixture=%s market=%s",
                    code,
                    decision.decision_id,
                    decision.fixture_id,
                    decision.market,
                )
                continue
            raise
        stored = session.get(AhOuV3MonitoringFactModel, decision.decision_id)
        if stored is None:
            session.add(
                AhOuV3MonitoringFactModel(
                    decision_id=decision.decision_id,
                    fixture_id=decision.fixture_id,
                    market=decision.market,
                    model_version=decision.model_version,
                    calibration_version=decision.calibration_version,
                    payload=payload,
                    payload_hash=_digest(payload),
                    observed_at=observed,
                )
            )
            created += 1
        elif stored.payload != payload or stored.payload_hash != _digest(payload):
            # F4：旧 fact 因缺投影被排除（PREMATCH_PROJECTION_MISSING），新代码补投影后
            # payload 合法变化（eligible false→true）——fact 表 immutable 无法 UPDATE，
            # 跳过并保留旧 fact（承认历史缺口），不阻塞 settlement sweep。其余 payload
            # 变化仍是篡改，保留 CONFLICT 防线。
            if (
                stored.payload.get("eligible") is False
                and stored.payload.get("exclusion_reason")
                == "V3_MONITORING_PREMATCH_PROJECTION_MISSING"
                and payload.get("eligible") is True
            ):
                skipped_stale += 1
                continue
            raise ValueError("V3_MONITORING_FACT_CONFLICT")
        excluded += not payload["eligible"]
    session.flush()
    groups: dict[tuple[str, str, str], list[AhOuV3MonitoringFactModel]] = defaultdict(list)
    for row in session.scalars(
        select(AhOuV3MonitoringFactModel).order_by(
            AhOuV3MonitoringFactModel.observed_at, AhOuV3MonitoringFactModel.decision_id
        )
    ):
        if row.payload_hash != _digest(row.payload):
            raise ValueError("V3_MONITORING_FACT_HASH_CONFLICT")
        if row.payload["eligible"]:
            groups[(row.market, row.model_version, row.calibration_version)].append(row)
    for (market, model, calibration), rows in groups.items():
        for milestone in range(REPORT_INTERVAL, len(rows) + 1, REPORT_INTERVAL):
            payload = build_cumulative_report([row.payload for row in rows[:milestone]])
            identity = _digest(
                {
                    "market": market,
                    "model_version": model,
                    "calibration_version": calibration,
                    "eligible_settled": milestone,
                }
            )
            stored_report = session.get(AhOuV3MonitoringReportModel, identity)
            if stored_report is None:
                session.add(
                    AhOuV3MonitoringReportModel(
                        report_id=identity,
                        market=market,
                        model_version=model,
                        calibration_version=calibration,
                        eligible_settled_count=milestone,
                        payload=payload,
                        payload_hash=_digest(payload),
                        created_at=observed,
                    )
                )
                reports += 1
            elif stored_report.payload != payload or stored_report.payload_hash != _digest(payload):
                raise ValueError("V3_MONITORING_REPORT_CONFLICT")
    session.flush()
    return {
        "created_facts": created,
        "excluded_facts": excluded,
        "skipped_stale_facts": skipped_stale,
        "quarantined_facts": quarantined,
        "created_reports": reports,
    }
