from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from w2.competitions.league_whitelist_audit import MIN_BOOKMAKER_DEPTH
from w2.domain.factor_registry import load_factor_registry
from w2.domain.recommendation_decision_v4 import CANDIDATE_QUOTE_MAX_AGE_SECONDS

MARKETS = ("ASIAN_HANDICAP", "TOTALS")
MIN_XG_MATCHES = 3
ROLE_VALUES = {"HARD_GATE", "ENHANCEMENT", "NOT_APPLICABLE", "POLICY_DISABLED"}
DISPLAY_NAMES = {
    "F1_MARKET_MOVEMENT": "盘口变化",
    "F2_BOOKMAKER_INTENT": "机构意图",
    "F3_REST_FITNESS": "休息与体能",
    "F4_MATCH_IMPORTANCE": "比赛重要性",
    "F5_RECENT_AH_COVER": "近期让球覆盖",
    "F6_H2H": "交锋记录",
    "F7_STRENGTH_FORM": "实力与状态",
    "F8_SQUAD_VALUE": "球队身价",
    "F9_TRUE_XG": "四字段 xG",
    "F10_LMM_V1": "首发阵容",
    "MK_EXACT_QUOTE": "精确报价身份",
    "MK_BOOKMAKER_DEPTH": "机构深度",
    "MK_QUOTE_AGE": "报价时效",
}


def build_fixture_factor_checklist(
    card: Mapping[str, Any],
    *,
    markets: Mapping[str, Mapping[str, Any]],
    market_collection: Mapping[str, Any],
    lineup_collection: Mapping[str, Any],
    home_identity_ready: bool,
    away_identity_ready: bool,
    shadow_candidate: Mapping[str, Any],
    generated_at: Any,
) -> dict[str, Any]:
    inputs = _mapping(card.get("factor_checklist_inputs"))
    readiness = _mapping(inputs.get("data_readiness"))
    contributions = _contributions(inputs.get("feature_contributions"))
    candidates = _mapping(card.get("market_candidates"))
    factors: list[dict[str, Any]] = []

    factors.append(_xg_factor(readiness, inputs, generated_at))
    for market in MARKETS:
        current = _mapping(markets.get(market))
        candidate = _mapping(candidates.get("ah" if market == "ASIAN_HANDICAP" else "ou"))
        factors.extend(
            _market_gate_factors(
                market,
                current,
                candidate,
                market_collection,
                generated_at,
            )
        )

    for factor_id in (
        "F3_REST_FITNESS",
        "F4_MATCH_IMPORTANCE",
        "F5_RECENT_AH_COVER",
        "F6_H2H",
        "F7_STRENGTH_FORM",
        "F8_SQUAD_VALUE",
    ):
        factors.append(
            _contribution_factor(factor_id, contributions.get(factor_id, []), generated_at)
        )
    factors.append(_lineup_factor(readiness, lineup_collection, generated_at))
    for market in MARKETS:
        current = _mapping(markets.get(market))
        factors.extend(_market_explanation_factors(market, current, generated_at))

    model_blockers: list[str] = []
    xg = factors[0]
    if xg["state"] != "READY":
        model_blockers.append("F9_TRUE_XG")
    if not (home_identity_ready and away_identity_ready):
        model_blockers.append("FIXTURE_TEAM_IDENTITY")

    per_market: dict[str, Any] = {}
    for market in MARKETS:
        blockers = list(model_blockers)
        for factor in factors:
            if (
                factor.get("market") == market
                and factor["role_shadow_candidate"] == "HARD_GATE"
                and factor["state"] != "READY"
            ):
                blockers.append(str(factor["factor_id"]))
        if not blockers and _text(shadow_candidate.get("status")) != "ACTIVE":
            blockers.append("DECISION_V4")
        per_market[market] = {
            "state": "READY" if not blockers else "BLOCKED",
            "blocking_factor_ids": list(dict.fromkeys(blockers)),
        }

    shadow_ready = any(item["state"] == "READY" for item in per_market.values())
    shadow_blockers = (
        []
        if shadow_ready
        else list(
            dict.fromkeys(
                blocker
                for market in MARKETS
                for blocker in per_market[market]["blocking_factor_ids"]
            )
        )
    )
    model_track = {
        "state": "READY" if not model_blockers else "BLOCKED",
        "blocking_factor_ids": model_blockers,
    }
    shadow_track = {
        "state": "READY" if shadow_ready else "BLOCKED",
        "blocking_factor_ids": shadow_blockers,
        "per_market": per_market,
    }
    return {
        "fixture_id": _text(card.get("fixture_id")),
        "competition_id": _optional_text(card.get("competition_id")),
        "kickoff_utc": card.get("kickoff_utc"),
        "as_of": generated_at,
        "conclusion_zh": _conclusion(model_track, shadow_track, factors),
        "track_model_forecast": model_track,
        "track_shadow_candidate": shadow_track,
        "factors": factors,
    }


def _xg_factor(
    readiness: Mapping[str, Any], inputs: Mapping[str, Any], as_of: Any
) -> dict[str, Any]:
    home_count = max(0, _int(readiness.get("xg_home_match_count")))
    away_count = max(0, _int(readiness.get("xg_away_match_count")))
    home_shortfall = max(0, MIN_XG_MATCHES - home_count)
    away_shortfall = max(0, MIN_XG_MATCHES - away_count)
    ready = readiness.get("xg") is True or _text(readiness.get("xg_status")) == "READY"
    unsupported = inputs.get("provider_xg_unavailable_confirmed") is True
    if ready:
        state, cause, permanence = "READY", None, "NOT_APPLICABLE"
    elif unsupported:
        state, cause, permanence = "MISSING", "PROVIDER_NOT_AVAILABLE", "STRUCTURAL_PERMANENT"
    else:
        state, cause, permanence = (
            "PARTIAL" if home_count or away_count else "MISSING",
            "UNDER_SAMPLED",
            "SELF_RESOLVING",
        )
    return _factor(
        "F9_TRUE_XG",
        state=state,
        cause=cause,
        permanence=permanence,
        as_of=as_of,
        evidence={
            "source": "rolling_xg_snapshot+team_xg_match",
            "sample_count": min(home_count, away_count),
            "minimum_required": MIN_XG_MATCHES,
            "shortfall": max(home_shortfall, away_shortfall),
            "home_sample_count": home_count,
            "away_sample_count": away_count,
            "home_shortfall": home_shortfall,
            "away_shortfall": away_shortfall,
            "rolling_snapshot_count": max(0, _int(readiness.get("xg_snapshot_count"))),
            "provider_unavailable_confirmed": unsupported,
        },
    )


def _market_gate_factors(
    market: str,
    current: Mapping[str, Any],
    candidate: Mapping[str, Any],
    collection: Mapping[str, Any],
    as_of: Any,
) -> list[dict[str, Any]]:
    identity = _mapping(candidate.get("quote_identity"))
    exact_ready = _text(identity.get("identity_status")) == "COMPLETE"
    depth = max(0, _int(current.get("bookmaker_count")))
    age = _optional_int(current.get("quote_age_seconds"))
    age_ready = age is not None and age <= CANDIDATE_QUOTE_MAX_AGE_SECONDS
    next_window_at = collection.get("scheduled_at")
    temporal_cause = _collection_cause(collection)
    return [
        _factor(
            "MK_EXACT_QUOTE",
            market=market,
            state="READY" if exact_ready else "MISSING",
            cause=None if exact_ready else temporal_cause,
            permanence="NOT_APPLICABLE" if exact_ready else "TRANSIENT",
            next_window_at=None if exact_ready else next_window_at,
            as_of=as_of,
            evidence={
                "source": "canonical_mainline_identity",
                "identity_status": _optional_text(identity.get("identity_status")),
            },
        ),
        _factor(
            "MK_BOOKMAKER_DEPTH",
            market=market,
            state="READY" if depth >= MIN_BOOKMAKER_DEPTH else "PARTIAL" if depth else "MISSING",
            cause=None
            if depth >= MIN_BOOKMAKER_DEPTH
            else "UNDER_SAMPLED"
            if depth
            else temporal_cause,
            permanence="NOT_APPLICABLE"
            if depth >= MIN_BOOKMAKER_DEPTH
            else "SELF_RESOLVING"
            if depth
            else "TRANSIENT",
            next_window_at=None if depth >= MIN_BOOKMAKER_DEPTH else next_window_at,
            as_of=as_of,
            evidence={
                "source": "market_radar.current",
                "bookmaker_count": depth,
                "minimum_required": MIN_BOOKMAKER_DEPTH,
                "shortfall": max(0, MIN_BOOKMAKER_DEPTH - depth),
            },
        ),
        _factor(
            "MK_QUOTE_AGE",
            market=market,
            state="READY" if age_ready else "MISSING",
            cause=None if age_ready else temporal_cause,
            permanence="NOT_APPLICABLE" if age_ready else "TRANSIENT",
            next_window_at=None if age_ready else next_window_at,
            as_of=as_of,
            evidence={
                "source": "market_radar.latest_snapshot_at",
                "quote_age_seconds": age,
                "maximum_seconds": CANDIDATE_QUOTE_MAX_AGE_SECONDS,
            },
        ),
    ]


def _contribution_factor(
    factor_id: str, rows: list[Mapping[str, Any]], as_of: Any
) -> dict[str, Any]:
    statuses = {_text(row.get("status")) for row in rows}
    ready_count = sum(status == "READY" for status in statuses)
    if rows and statuses == {"READY"}:
        state, cause, permanence = "READY", None, "NOT_APPLICABLE"
    elif rows and ready_count:
        state, cause, permanence = "PARTIAL", "UNDER_SAMPLED", "SELF_RESOLVING"
    else:
        state, cause, permanence = "MISSING", "UNDER_SAMPLED", "SELF_RESOLVING"
    return _factor(
        factor_id,
        state=state,
        cause=cause,
        permanence=permanence,
        as_of=as_of,
        evidence={
            "source": "+".join(
                sorted({_text(row.get("source_group")) for row in rows if row.get("source_group")})
            )
            or load_factor_registry()[factor_id]["source_group"],
            "sample_count": len(rows),
            "statuses": sorted(status for status in statuses if status),
        },
    )


def _lineup_factor(
    readiness: Mapping[str, Any], collection: Mapping[str, Any], as_of: Any
) -> dict[str, Any]:
    ready = readiness.get("lineups") is True or _text(readiness.get("lineups_status")) == "READY"
    cause = None if ready else _collection_cause(collection)
    return _factor(
        "F10_LMM_V1",
        state="READY" if ready else "MISSING",
        cause=cause,
        permanence="NOT_APPLICABLE" if ready else "TRANSIENT",
        next_window_at=None if ready else collection.get("scheduled_at"),
        as_of=as_of,
        evidence={
            "source": "lineup_provenance",
            "status": _optional_text(readiness.get("lineups_status")),
        },
    )


def _market_explanation_factors(
    market: str, current: Mapping[str, Any], as_of: Any
) -> list[dict[str, Any]]:
    snapshot_count = max(0, _int(current.get("snapshot_count")))
    bookmaker_count = max(0, _int(current.get("bookmaker_count")))
    return [
        _factor(
            "F1_MARKET_MOVEMENT",
            market=market,
            state="READY" if snapshot_count >= 2 else "PARTIAL" if snapshot_count else "MISSING",
            cause=None if snapshot_count >= 2 else "UNDER_SAMPLED",
            permanence="NOT_APPLICABLE" if snapshot_count >= 2 else "SELF_RESOLVING",
            as_of=as_of,
            evidence={
                "source": "market_radar.timeline",
                "sample_count": snapshot_count,
                "minimum_required": 2,
                "shortfall": max(0, 2 - snapshot_count),
            },
        ),
        _factor(
            "F2_BOOKMAKER_INTENT",
            market=market,
            state="READY" if bookmaker_count else "MISSING",
            cause=None if bookmaker_count else "UNDER_SAMPLED",
            permanence="NOT_APPLICABLE" if bookmaker_count else "SELF_RESOLVING",
            as_of=as_of,
            evidence={"source": "market_radar.current", "sample_count": bookmaker_count},
        ),
    ]


def _factor(
    factor_id: str,
    *,
    state: str,
    cause: str | None,
    permanence: str,
    as_of: Any,
    evidence: Mapping[str, Any],
    market: str | None = None,
    next_window_at: Any = None,
) -> dict[str, Any]:
    role = _role_authority()["fixture_factor_roles"][factor_id]
    authority_factor = str(role["authority_factor"])
    result = {
        "factor_id": factor_id,
        "display_name_zh": DISPLAY_NAMES[factor_id],
        "role_model_forecast": role["role_model_forecast"],
        "role_shadow_candidate": role["role_shadow_candidate"],
        "state": state,
        "cause": cause,
        "permanence": permanence,
        "next_window_at": next_window_at,
        "evidence": {
            "as_of": as_of,
            **dict(evidence),
            "authority_factor": authority_factor,
            "authority_roles": dict(_role_authority()["factors"][authority_factor]),
        },
    }
    if market is not None:
        result["market"] = market
    return result


def _conclusion(
    model_track: Mapping[str, Any],
    shadow_track: Mapping[str, Any],
    factors: Sequence[Mapping[str, Any]],
) -> str:
    if model_track["state"] == "BLOCKED":
        detail = _blocker_detail(str(model_track["blocking_factor_ids"][0]), factors)
        return f"本场不可进入模型预测账本 —— 卡在 {detail}"
    if shadow_track["state"] == "READY":
        return "本场可进入模型预测账本，也具备形成影子候选的输入条件。"
    blocker = str(shadow_track["blocking_factor_ids"][0])
    return f"本场可进入模型预测账本；不能形成影子候选 —— 卡在 {_blocker_detail(blocker, factors)}"


def _blocker_detail(blocker: str, factors: Sequence[Mapping[str, Any]]) -> str:
    row = next(
        (
            item
            for item in factors
            if item.get("factor_id") == blocker and item.get("state") != "READY"
        ),
        None,
    )
    if row is None:
        return "Decision V4 尚未通过" if blocker == "DECISION_V4" else "比赛或球队身份尚未解析"
    evidence = _mapping(row.get("evidence"))
    if blocker == "F9_TRUE_XG" and row.get("cause") == "PROVIDER_NOT_AVAILABLE":
        return "四字段 xG（Provider 无该字段，Free 模式下永久不可得）"
    if blocker == "F9_TRUE_XG":
        return (
            f"四字段 xG（滚动样本不足，至少一队还差 {max(0, _int(evidence.get('shortfall')))} 场）"
        )
    if blocker == "MK_QUOTE_AGE":
        age = _optional_int(evidence.get("quote_age_seconds"))
        age_text = "无可用快照" if age is None else f"距最新快照 {_duration(age)}"
        window = row.get("next_window_at")
        suffix = f"，下次采集 {window}" if window else ""
        return f"报价时效（{age_text}，需 <=30m{suffix}）"
    if blocker == "MK_BOOKMAKER_DEPTH":
        return f"机构深度（当前 {max(0, _int(evidence.get('bookmaker_count')))} 家，需 >=3 家）"
    if blocker == "MK_EXACT_QUOTE":
        return "精确报价身份"
    return str(row.get("display_name_zh") or blocker)


def _collection_cause(collection: Mapping[str, Any]) -> str:
    if collection.get("overdue") is True:
        return "COLLECTION_WINDOW_MISSED"
    cause = _text(_mapping(collection.get("public_semantics")).get("cause"))
    return cause if cause in {"NOT_YET_DUE", "AWAITING_COLLECTION"} else "AWAITING_COLLECTION"


def _contributions(value: Any) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return result
    for item in value:
        if isinstance(item, Mapping) and _text(item.get("id")):
            result.setdefault(_text(item.get("id")), []).append(item)
    return result


@lru_cache(maxsize=1)
def _role_authority() -> dict[str, Any]:
    relative = Path(
        "docs/review_packages/SC21_FACTOR_INPUT_CHAIN/SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json"
    )
    candidates = (Path.cwd() / relative, Path(__file__).resolve().parents[3] / relative)
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise FileNotFoundError("SC21_FACTOR_ROLE_AUTHORITY_MATRIX_NOT_FOUND")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("SC21_FACTOR_ROLE_AUTHORITY_INVALID")
    payload: dict[str, Any] = raw
    roles = payload.get("fixture_factor_roles")
    if not isinstance(roles, dict) or set(roles) != set(DISPLAY_NAMES):
        raise ValueError("SC21_FIXTURE_FACTOR_ROLES_INVALID")
    for role in roles.values():
        if (
            not isinstance(role, dict)
            or {role.get("role_model_forecast"), role.get("role_shadow_candidate")} - ROLE_VALUES
        ):
            raise ValueError("SC21_FIXTURE_FACTOR_ROLE_INVALID")
    return payload


def _duration(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes = remainder // 60
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _optional_text(value: Any) -> str | None:
    return _text(value) or None


def _int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None
