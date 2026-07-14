from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from w2.infrastructure.persistence.models import RecommendationLockModel
from w2.models.fair_market_estimate import verify_estimate_semantics, verify_estimate_snapshot

SNAPSHOT_SCHEMA_VERSION = "w2.recommendation_lock_snapshot.v1"


def canonical_snapshot_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_recommendation_lock_snapshot(
    *,
    recommendation_id: str,
    card: dict[str, Any],
    locked_at: datetime,
    reason: str,
    release_sha: str | None,
) -> RecommendationLockModel:
    if not release_sha:
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_RELEASE_SHA")
    recommendation = _dict(card.get("recommendation"))
    pricing = _dict(card.get("pricing_shadow"))
    current_ah = _dict(_dict(card.get("current_odds")).get("ah"))
    canonical_ah = _dict(pricing.get("canonical_ah_market"))
    data_refresh = _dict(card.get("data_refresh"))
    data_profile = _string(card.get("data_profile") or card.get("data_source"))
    if data_profile is None:
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_DATA_PROFILE")

    _require_formal_ah_recommendation(card, recommendation)
    _require_estimate_snapshot(card, recommendation)

    fixture_id = _string(card.get("fixture_id"))
    if fixture_id is None:
        raise ValueError("LOCK_SNAPSHOT_MISSING_FIXTURE_ID")
    as_of = _datetime(
        card.get("as_of")
        or card.get("generated_at")
        or recommendation.get("generated_at")
        or pricing.get("as_of")
        or pricing.get("locked_at")
    )
    kickoff_utc = _datetime(card.get("kickoff_utc"))
    if as_of is None:
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_AS_OF")
    if kickoff_utc is None:
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_KICKOFF")
    if as_of >= kickoff_utc or locked_at >= kickoff_utc:
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_PREMATCH")

    pick_line = _decimal(recommendation.get("line"))
    market_ah = _decimal(pricing.get("market_ah"))
    home_price = _decimal(current_ah.get("home_price") or canonical_ah.get("home_price"))
    away_price = _decimal(current_ah.get("away_price") or canonical_ah.get("away_price"))
    expected_value = _decimal(
        recommendation.get("expected_value") or recommendation.get("risk_adjusted_ev")
    )
    scoreline_top3 = _direction_top3(card)
    market_timeline = _dict_or_none(card.get("market_timeline"))
    settlement_distribution = _dict_or_none(recommendation.get("ah_settlement_distribution"))

    snapshot_payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "fixture_id": fixture_id,
        "recommendation_id": recommendation_id,
        "locked_at": _iso(locked_at),
        "as_of": _iso(as_of),
        "kickoff_utc": _iso(kickoff_utc),
        "teams": {
            "home": card.get("home_team_name"),
            "away": card.get("away_team_name"),
        },
        "competition": card.get("competition") or card.get("competition_name"),
        "recommendation": {
            "tier": recommendation.get("tier"),
            "market": recommendation.get("market"),
            "selection": recommendation.get("selection"),
            "selection_label_cn": recommendation.get("selection_label_cn"),
            "line": _decimal_text(pick_line),
            "odds": _decimal_text(_decimal(recommendation.get("odds"))),
            "expected_value": _decimal_text(expected_value),
            "ev_se": _decimal_text(_decimal(recommendation.get("ev_se"))),
            "reverse_factor_value": bool(recommendation.get("reverse_factor_value")),
        },
        "market": {
            "fair_ah": _decimal_text(_decimal(pricing.get("fair_ah"))),
            "market_ah": _decimal_text(market_ah),
            "edge_ah": _decimal_text(_decimal(pricing.get("edge_ah"))),
            "home_price": _decimal_text(home_price),
            "away_price": _decimal_text(away_price),
            "devig_method": pricing.get("devig_method"),
            "canonical_ah_market": canonical_ah or None,
        },
        "market_timeline": market_timeline,
        "ah_settlement_distribution": settlement_distribution,
        "scoreline_top3": scoreline_top3,
        "fair_market_estimate_ids": card.get("fair_market_estimate_ids"),
        "fair_market_estimate_snapshots": card.get("fair_market_estimate_snapshots"),
        "signals": {
            "independent_signal_count": pricing.get("independent_signal_count"),
            "groups": pricing.get("independent_signal_groups"),
            "missing_sources": pricing.get("missing_independent_sources"),
            "factors": pricing.get("factors"),
        },
        "data_status": {
            "lineups_status": data_refresh.get("lineups_status"),
            "xg_status": data_refresh.get("xg_status"),
            "data_profile": data_profile,
        },
        "versions": {
            "release_sha": release_sha,
            "model_version": pricing.get("model_version"),
            "calibration_version": pricing.get("calibration_version"),
        },
    }
    snapshot_payload_hash = canonical_snapshot_hash(snapshot_payload)

    return RecommendationLockModel(
        recommendation_id=recommendation_id,
        fixture_id=fixture_id,
        status="LOCKED",
        locked_at=locked_at,
        as_of=as_of,
        kickoff_utc=kickoff_utc,
        reason=reason,
        tier="FORMAL",
        pick_side=str(recommendation.get("selection")),
        pick_line=pick_line,
        our_fair_ah=_decimal(pricing.get("fair_ah")),
        market_ah=market_ah,
        home_price=home_price,
        away_price=away_price,
        expected_value=expected_value,
        devig_method=_string(pricing.get("devig_method")),
        snapshot_payload_json=snapshot_payload,
        snapshot_payload_hash=snapshot_payload_hash,
        release_sha=release_sha,
        market_timeline_json=market_timeline,
        ah_settlement_distribution_json=settlement_distribution,
        team_score_home=_decimal(pricing.get("team_score_home") or pricing.get("home_score")),
        team_score_away=_decimal(pricing.get("team_score_away") or pricing.get("away_score")),
        factors_json=pricing.get("factors"),
        independent_signal_count=_int(pricing.get("independent_signal_count")),
        signal_groups=pricing.get("independent_signal_groups"),
        missing_sources=pricing.get("missing_independent_sources"),
        scoreline_top3_json=scoreline_top3,
        lineups_status=_string(data_refresh.get("lineups_status")),
        xg_status=_string(data_refresh.get("xg_status")),
        model_version=_string(pricing.get("model_version")),
        calibration_version=_string(pricing.get("calibration_version")),
        coherent=_bool(pricing.get("coherent")),
        reverse_value=_bool(recommendation.get("reverse_factor_value")),
        data_profile=data_profile,
        reproducible=True,
        legacy_marker_only=False,
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
    )


def persist_recommendation_lock_snapshot(
    session: Session,
    *,
    recommendation_id: str,
    card: dict[str, Any],
    locked_at: datetime,
    reason: str,
    release_sha: str | None,
) -> RecommendationLockModel:
    lock = build_recommendation_lock_snapshot(
        recommendation_id=recommendation_id,
        card=card,
        locked_at=locked_at,
        reason=reason,
        release_sha=release_sha,
    )
    session.add(lock)
    return lock


def _require_formal_ah_recommendation(
    card: dict[str, Any],
    recommendation: dict[str, Any],
) -> None:
    if card.get("formal_recommendation") is not True:
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_FORMAL")
    if str(recommendation.get("tier") or "").upper() != "FORMAL":
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_FORMAL_TIER")
    if str(recommendation.get("market") or "").upper() != "ASIAN_HANDICAP":
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_AH_MARKET")
    if recommendation.get("selection") not in {"HOME_AH", "AWAY_AH"}:
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_AH_SELECTION")
    if _decimal(recommendation.get("line")) is None:
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_LINE")


def _require_estimate_snapshot(
    card: dict[str, Any],
    recommendation: dict[str, Any],
) -> None:
    estimate_id = _string(recommendation.get("estimate_id"))
    if estimate_id is None:
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_ESTIMATE")
    ids = card.get("fair_market_estimate_ids")
    snapshots = card.get("fair_market_estimate_snapshots")
    if not isinstance(ids, list) or estimate_id not in {str(item) for item in ids}:
        raise ValueError("LOCK_SNAPSHOT_ESTIMATE_MISMATCH")
    if not isinstance(snapshots, list):
        raise ValueError("LOCK_SNAPSHOT_REQUIRES_ESTIMATE")
    snapshot = next(
        (
            item
            for item in snapshots
            if isinstance(item, dict) and item.get("estimate_id") == estimate_id
        ),
        None,
    )
    if snapshot is None:
        raise ValueError("LOCK_SNAPSHOT_ESTIMATE_MISMATCH")
    if not verify_estimate_snapshot(snapshot):
        raise ValueError("LOCK_SNAPSHOT_INVALID_ESTIMATE")
    if not verify_estimate_semantics(snapshot):
        raise ValueError("LOCK_SNAPSHOT_ESTIMATE_SEMANTIC_FAIL")
    if snapshot.get("market") != recommendation.get("market"):
        raise ValueError("LOCK_SNAPSHOT_ESTIMATE_MARKET_MISMATCH")


def _direction_top3(card: dict[str, Any]) -> Any | None:
    reference = _dict(card.get("scoreline_reference"))
    rows = reference.get("direction_scorelines") or reference.get("direction_top3")
    if isinstance(rows, list):
        return rows
    return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
