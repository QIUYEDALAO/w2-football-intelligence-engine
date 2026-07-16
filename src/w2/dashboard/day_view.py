from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

from w2.dashboard.date_navigation import build_date_navigation
from w2.dashboard.degradation import build_dashboard_degradation
from w2.dashboard.scorelines import scoreline_picks_from_card, scoreline_reference_from_card
from w2.dashboard.team_localization import localize_team_name
from w2.domain.decision_policy import compute_outcome_tracked
from w2.domain.enums import DataStatus, DecisionTier, LifecycleStatus
from w2.domain.environment_policy import build_environment_policy_stamp
from w2.domain.legacy_decision_shim import legacy_decision_view
from w2.markets.devig import DevigMethod, devig

CARD_SOURCE_CONTRACT = "decision_contract"
CARD_SOURCE_LEGACY = "legacy_fallback"


def build_dashboard_day_view(
    dashboard_payload: Mapping[str, Any],
    *,
    environment: str,
    active_whitelist_count: int | None = None,
) -> dict[str, Any]:
    """Build a read-only DayView envelope from the existing dashboard payload."""
    football_day = _text(
        dashboard_payload.get("selected_football_day"),
        dashboard_payload.get("date"),
    )
    generated_at = _format_time(dashboard_payload.get("generated_at"))
    as_of = _parse_time(generated_at) or datetime.now(UTC)
    cards = [
        _day_view_card(card)
        for card in _dashboard_cards(dashboard_payload)
        if _is_prematch_card(card, as_of=as_of)
    ]
    counts = _counts(cards)
    view = {
        "generated_at": generated_at,
        "date": _text(dashboard_payload.get("date"), football_day),
        "football_day": football_day,
        "selected_football_day": football_day,
        "environment": environment,
        "active_whitelist_count": active_whitelist_count,
        "environment_policy": build_environment_policy_stamp(environment),
        "timezone": _text(dashboard_payload.get("timezone"), "Asia/Shanghai"),
        "window": _text(dashboard_payload.get("window"), "today"),
        "source": "dashboard_read_model",
        "version": _mapping_copy(dashboard_payload.get("version")),
        "read_degradation": _mapping_copy(dashboard_payload.get("read_degradation")),
        "checkpoint_key": f"dashboard:day_view:{football_day}",
        "would_write_checkpoint": False,
        "provider_calls": 0,
        "db_writes": 0,
        "counts": counts,
        "freshness": _freshness(dashboard_payload, cards, counts),
        "cards": cards,
    }
    view["navigation"] = build_date_navigation(
        football_day,
        as_of=generated_at,
        has_checkpoint=False,
        checkpoint_key=str(view["checkpoint_key"]),
    )
    view["degradation"] = build_dashboard_degradation(view)
    return view


def build_forward_capture_day_view(
    dashboard_payload: Mapping[str, Any],
    *,
    environment: str,
) -> dict[str, Any]:
    """Build the internal ledger view without exposing full evidence through public L1."""
    view = build_dashboard_day_view(dashboard_payload, environment=environment)
    source_by_fixture = {
        _text(row.get("fixture_id")): row for row in _dashboard_cards(dashboard_payload)
    }
    evidence_fields = (
        "fair_market_estimate_snapshots",
        "fair_market_estimate_ids",
        "fair_market_estimates",
        "analysis_gate",
        "analysis_gates",
        "analysis_gate_v2_shadow",
        "analysis_gate_v2_shadows",
        "model_market_divergence",
        "estimate_id",
        "model_basis_id",
    )
    for card in view["cards"]:
        source = source_by_fixture.get(_text(card.get("fixture_id")))
        if source is None:
            continue
        contract = _mapping(source.get("decision_contract"))
        for field in evidence_fields:
            value = _field(source, contract, field)
            if field in {
                "fair_market_estimate_snapshots",
                "fair_market_estimates",
                "analysis_gates",
                "analysis_gate_v2_shadows",
            }:
                card[field] = _mapping_list(value)
            elif field == "fair_market_estimate_ids":
                card[field] = _string_list(value)
            elif field in {
                "analysis_gate",
                "analysis_gate_v2_shadow",
                "model_market_divergence",
            }:
                card[field] = _mapping_copy(value)
            else:
                card[field] = value
    view["source"] = "internal_forward_capture_projection"
    return view


def _dashboard_cards(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = payload.get("all")
    if not isinstance(rows, Sequence) or isinstance(rows, str | bytes | bytearray):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _is_prematch_card(card: Mapping[str, Any], *, as_of: datetime) -> bool:
    status = str(card.get("status") or "").upper()
    if status in {
        "FT",
        "AET",
        "PEN",
        "FINISHED",
        "LIVE",
        "1H",
        "HT",
        "2H",
        "ET",
        "BT",
        "P",
        "INT",
        "SUSP",
    }:
        return False
    kickoff = _parse_time(card.get("kickoff_utc"))
    if kickoff is not None and kickoff <= as_of.astimezone(UTC):
        return False
    return True


def _day_view_card(card: Mapping[str, Any]) -> dict[str, Any]:
    contract = _mapping(card.get("decision_contract"))
    if _has_contract_fields(card, contract):
        return _contract_card(card, contract)
    return _legacy_card(card)


def _contract_card(card: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    decision_tier = _text(_field(card, contract, "decision_tier"), DecisionTier.SKIP.value)
    data_status = _text(_field(card, contract, "data_status"), DataStatus.PARTIAL.value)
    lifecycle_status = _text(
        _field(card, contract, "lifecycle_status"),
        LifecycleStatus.DRAFT.value,
    )
    raw_pick = _field(card, contract, "pick")
    pick = _compact_pick(raw_pick) if isinstance(raw_pick, Mapping) else None
    return {
        **_fixture_fields(card),
        "source": CARD_SOURCE_CONTRACT,
        "decision_tier": decision_tier,
        "data_status": data_status,
        "lifecycle_status": lifecycle_status,
        "outcome_tracked": _bool_or_default(
            _field(card, contract, "outcome_tracked"),
            compute_outcome_tracked(DecisionTier(decision_tier))
            if _is_decision_tier(decision_tier)
            else False,
        ),
        "lock_eligible": _bool_or_default(_field(card, contract, "lock_eligible"), False),
        "recommendation_id": _optional_text(_field(card, contract, "recommendation_id")),
        "reason_code": _optional_text(_field(card, contract, "reason_code")),
        "primary_blocker": _optional_text(_field(card, contract, "primary_blocker")),
        "primary_blocker_layer": _optional_text(
            _field(card, contract, "primary_blocker_layer")
        ),
        "action": _optional_text(_field(card, contract, "action")),
        "next_eval_at": _format_time(_field(card, contract, "next_eval_at")),
        "provider_budget_status": _optional_text(_field(card, contract, "provider_budget_status")),
        **_market_context_fields(card),
        **_analysis_context_fields(card, pick=pick),
        "pick": pick,
        "non_pick": _mapping_copy(_field(card, contract, "non_pick"))
        if isinstance(_field(card, contract, "non_pick"), Mapping)
        else None,
        "one_liner": _optional_text(_field(card, contract, "one_liner")),
        "card_hash": _optional_text(_field(card, contract, "card_hash")),
        **_audit_identity_fields(card, pick),
    }


def _legacy_card(card: Mapping[str, Any]) -> dict[str, Any]:
    recommendation = _mapping(card.get("recommendation"))
    legacy = legacy_decision_view(card, recommendation)
    return {
        **_fixture_fields(card),
        "source": CARD_SOURCE_LEGACY,
        "decision_tier": legacy.decision_tier.value,
        "data_status": _text(card.get("data_status"), DataStatus.PARTIAL.value),
        "lifecycle_status": _text(card.get("lifecycle_status"), LifecycleStatus.DRAFT.value),
        "outcome_tracked": compute_outcome_tracked(legacy.decision_tier),
        "lock_eligible": legacy.lock_eligible,
        "recommendation_id": legacy.recommendation_id,
        "reason_code": _optional_text(card.get("reason_code")),
        "primary_blocker": _optional_text(card.get("primary_blocker")),
        "primary_blocker_layer": _optional_text(card.get("primary_blocker_layer")),
        "action": _optional_text(card.get("action")),
        "next_eval_at": _format_time(card.get("next_eval_at")),
        "provider_budget_status": _optional_text(card.get("provider_budget_status")),
        **_market_context_fields(card),
        **_analysis_context_fields(card, pick=None),
        "pick": None,
        "non_pick": _mapping_copy(card.get("non_pick"))
        if isinstance(card.get("non_pick"), Mapping)
        else None,
        "one_liner": _optional_text(card.get("one_liner")),
        "card_hash": _optional_text(card.get("card_hash")),
        **_audit_identity_fields(card, None),
    }


def _fixture_fields(card: Mapping[str, Any]) -> dict[str, Any]:
    competition_id = _optional_text(card.get("competition_id"))
    home_team_id = _optional_text(card.get("home_team_id"))
    away_team_id = _optional_text(card.get("away_team_id"))
    home_provider_name = _optional_text(card.get("home_team_name"))
    away_provider_name = _optional_text(card.get("away_team_name"))
    home = localize_team_name(
        competition_id=competition_id,
        provider_team_id=home_team_id,
        provider_name=home_provider_name,
        missing_name_fallback="主队",
    )
    away = localize_team_name(
        competition_id=competition_id,
        provider_team_id=away_team_id,
        provider_name=away_provider_name,
        missing_name_fallback="客队",
    )
    return {
        "fixture_id": _text(card.get("fixture_id")),
        "kickoff_utc": _format_time(card.get("kickoff_utc")),
        "kickoff_beijing": _optional_text(card.get("kickoff_beijing")),
        "competition_id": competition_id,
        "competition_name": _optional_text(card.get("competition_name")),
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "home_team_name": home_provider_name,
        "away_team_name": away_provider_name,
        "home_team_name_zh": home.name_zh,
        "away_team_name_zh": away.name_zh,
        "home_team_display_name": home.display_name,
        "away_team_display_name": away.display_name,
        "home_team_provider_name": home.provider_name,
        "away_team_provider_name": away.provider_name,
        "home_team_localization_status": home.status,
        "away_team_localization_status": away.status,
        "status": _optional_text(card.get("status")),
    }


def _market_context_fields(card: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "current_odds": _mapping_copy(card.get("current_odds")),
        "data_refresh": _mapping_copy(card.get("data_refresh")),
        "analysis_readiness": _mapping_copy(card.get("analysis_readiness")),
        "missing_inputs": _string_list(card.get("missing_inputs")),
    }


def _analysis_context_fields(
    card: Mapping[str, Any],
    *,
    pick: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not pick:
        return {
            "compact_provenance": {},
            "scoreline_picks": [],
            "scoreline_readiness": _mapping_copy(card.get("scoreline_readiness")),
            "audit_available": bool(_optional_text(card.get("audit_capture_hash"))),
            "audit_links": _audit_links(card),
        }
    card_dict = dict(card)
    card_dict["pick"] = dict(pick)
    derived_reference = scoreline_reference_from_card(
        card_dict,
        recommendation=dict(_mapping(card.get("recommendation"))) or None,
    )
    scoreline_reference = derived_reference or _mapping_copy(card.get("scoreline_reference"))
    scoreline_picks = (
        _mapping_list(scoreline_reference.get("top_scorelines"))
        if isinstance(scoreline_reference, Mapping)
        else []
    )
    if not scoreline_picks:
        scoreline_picks = scoreline_picks_from_card(card_dict)
    if not scoreline_picks:
        scoreline_picks = _mapping_list(card.get("scoreline_picks"))
    compact_scorelines = [
        {"scoreline": scoreline}
        for item in scoreline_picks
        if (scoreline := _optional_text(item.get("scoreline")))
    ]
    explicit_provenance = _mapping_copy(card.get("compact_provenance"))
    return {
        "compact_provenance": explicit_provenance or _compact_provenance(card),
        "scoreline_picks": compact_scorelines,
        "scoreline_readiness": _mapping_copy(card.get("scoreline_readiness")),
        "audit_available": bool(_optional_text(card.get("audit_capture_hash"))),
        "audit_links": _audit_links(card),
    }


def _compact_pick(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "market",
        "selection",
        "line",
        "odds",
        "fair_line",
        "estimate_id",
        "model_basis_id",
    )
    return {key: value[key] for key in allowed if value.get(key) is not None}


def _compact_provenance(card: Mapping[str, Any]) -> dict[str, Any]:
    snapshots = _mapping_list(card.get("fair_market_estimate_snapshots"))
    pick = _mapping(card.get("pick"))
    estimate_id = _optional_text(pick.get("estimate_id"))
    market = _optional_text(pick.get("market"))
    selected = next(
        (
            snapshot
            for snapshot in snapshots
            if estimate_id and _optional_text(snapshot.get("estimate_id")) == estimate_id
        ),
        None,
    )
    if selected is None:
        selected = next(
            (
                snapshot
                for snapshot in snapshots
                if market and _optional_text(snapshot.get("market")) == market
            ),
            snapshots[0] if len(snapshots) == 1 else None,
        )
    if not selected:
        return {}
    integrity = _mapping(selected.get("integrity"))
    model_context = _mapping(selected.get("model_context"))
    return {
        key: value
        for key, value in {
            "estimate_id": _optional_text(selected.get("estimate_id")),
            "model_basis_id": _optional_text(selected.get("model_basis_id")),
            "market": _optional_text(selected.get("market")),
            "schema_version": _optional_text(
                selected.get("schema_version") or selected.get("schema")
            ),
            "status": _optional_text(selected.get("status")),
            "integrity_status": _optional_text(
                selected.get("integrity_status") or integrity.get("status")
            ),
            "semantic_status": _optional_text(selected.get("semantic_status")),
            "artifact_hash": _optional_text(
                selected.get("artifact_hash") or model_context.get("artifact_hash")
            ),
            "artifact_version": _optional_text(
                selected.get("artifact_version") or model_context.get("artifact_version")
            ),
            "feature_as_of": _format_time(
                selected.get("feature_as_of") or model_context.get("feature_as_of")
            ),
        }.items()
        if value is not None
    }


def _audit_links(card: Mapping[str, Any]) -> dict[str, str]:
    fixture_id = _optional_text(card.get("fixture_id"))
    capture_id = _optional_text(card.get("audit_capture_id"))
    capture_hash = _optional_text(card.get("audit_capture_hash"))
    estimate_id = _optional_text(card.get("audit_estimate_id"))
    if (
        not fixture_id
        or not capture_id
        or not capture_hash
        or not estimate_id
        or _optional_text(card.get("audit_identity_status")) != "PASS"
    ):
        return {}
    query = (
        f"capture_id={quote(capture_id, safe='')}&"
        f"capture_hash={quote(capture_hash, safe='')}&"
        f"estimate_id={quote(estimate_id, safe='')}"
    )
    return {"audit_detail_url": f"/v1/fixtures/{quote(fixture_id, safe='')}/audit-detail?{query}"}


def _audit_identity_fields(
    card: Mapping[str, Any],
    pick: Mapping[str, Any] | None,
) -> dict[str, Any]:
    capture_id = _optional_text(card.get("audit_capture_id"))
    capture_hash = _optional_text(
        card.get("audit_capture_hash")
        or card.get("capture_hash")
        or card.get("evidence_hash")
        or card.get("card_hash")
    )
    estimate_id = _optional_text(
        card.get("audit_estimate_id")
        or (pick.get("estimate_id") if isinstance(pick, Mapping) else None)
    )
    fixture_id = _optional_text(card.get("fixture_id"))
    identity_status = _optional_text(card.get("audit_identity_status"))
    blocker = _optional_text(card.get("audit_blocker"))
    available = bool(
        capture_id
        and capture_hash
        and estimate_id
        and identity_status == "PASS"
        and not blocker
    )
    detail_url = None
    if fixture_id and capture_id and capture_hash and estimate_id and available:
        query = (
            f"capture_id={quote(capture_id, safe='')}&"
            f"capture_hash={quote(capture_hash, safe='')}&"
            f"estimate_id={quote(estimate_id, safe='')}"
        )
        detail_url = f"/v1/fixtures/{quote(fixture_id, safe='')}/audit-detail?{query}"
    return {
        "audit_capture_id": capture_id,
        "audit_capture_hash": capture_hash,
        "audit_estimate_id": estimate_id,
        "audit_identity_status": identity_status,
        "audit_blocker": blocker,
        "audit_available": available,
        "audit_detail_url": detail_url,
    }


def _market_probabilities(card: Mapping[str, Any]) -> dict[str, Any]:
    explicit = _mapping(card.get("market_probabilities"))
    if explicit:
        return dict(explicit)
    current_odds = _mapping(card.get("current_odds"))
    markets: dict[str, Any] = {}
    for key, labels in (
        ("ah", ("HOME_AH", "AWAY_AH")),
        ("ou", ("OVER", "UNDER")),
        ("one_x_two", ("HOME", "DRAW", "AWAY")),
    ):
        market = _mapping(current_odds.get(key))
        prices = _market_prices(market, labels)
        if len(prices) < 2:
            continue
        result = devig(prices, DevigMethod.POWER)
        markets[key] = {
            "method": result.method.value,
            "probabilities": {
                selection: round(probability, 6)
                for selection, probability in result.probabilities.items()
            },
            "overround": round(result.overround, 6),
        }
    return markets


def _market_prices(market: Mapping[str, Any], labels: Sequence[str]) -> dict[str, Decimal]:
    candidates: tuple[tuple[str, str], ...]
    if labels == ("HOME_AH", "AWAY_AH"):
        candidates = (("HOME_AH", "home_price"), ("AWAY_AH", "away_price"))
    elif labels == ("OVER", "UNDER"):
        candidates = (("OVER", "over_price"), ("UNDER", "under_price"))
    else:
        candidates = (
            ("HOME", "home_price"),
            ("DRAW", "draw_price"),
            ("AWAY", "away_price"),
        )
    prices: dict[str, Decimal] = {}
    for label, field in candidates:
        price = _decimal_price(market.get(field))
        if price is not None:
            prices[label] = price
    return prices


def _decimal_price(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return price if price > Decimal("1.0") else None


def _counts(cards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_decision_tier = {tier.value: 0 for tier in DecisionTier}
    by_data_status = {status.value: 0 for status in DataStatus}
    by_lifecycle_status = {status.value: 0 for status in LifecycleStatus}
    lock_eligible = 0
    outcome_tracked = 0
    legacy_fallback = 0

    for card in cards:
        decision_tier = _optional_text(card.get("decision_tier"))
        data_status = _optional_text(card.get("data_status"))
        lifecycle_status = _optional_text(card.get("lifecycle_status"))
        if decision_tier in by_decision_tier:
            by_decision_tier[decision_tier] += 1
        if data_status in by_data_status:
            by_data_status[data_status] += 1
        if lifecycle_status in by_lifecycle_status:
            by_lifecycle_status[lifecycle_status] += 1
        if card.get("lock_eligible") is True:
            lock_eligible += 1
        if card.get("outcome_tracked") is True:
            outcome_tracked += 1
        if card.get("source") == CARD_SOURCE_LEGACY:
            legacy_fallback += 1

    return {
        "total": len(cards),
        "lock_eligible": lock_eligible,
        "outcome_tracked": outcome_tracked,
        "legacy_fallback": legacy_fallback,
        "analysis_pick": by_decision_tier[DecisionTier.ANALYSIS_PICK.value],
        "recommend": by_decision_tier[DecisionTier.RECOMMEND.value],
        "watch": by_decision_tier[DecisionTier.WATCH.value],
        "not_ready": by_decision_tier[DecisionTier.NOT_READY.value],
        "skip": by_decision_tier[DecisionTier.SKIP.value],
        "ready": by_data_status[DataStatus.READY.value],
        "partial": by_data_status[DataStatus.PARTIAL.value],
        "stale": by_data_status[DataStatus.STALE.value],
        "blocked": by_data_status[DataStatus.BLOCKED.value],
        "by_decision_tier": by_decision_tier,
        "by_data_status": by_data_status,
        "by_lifecycle_status": by_lifecycle_status,
    }


def _freshness(
    payload: Mapping[str, Any],
    cards: Sequence[Mapping[str, Any]],
    counts: Mapping[str, Any],
) -> dict[str, Any]:
    data_status_summary = _mapping_copy(counts.get("by_data_status"))
    stale = int(data_status_summary.get(DataStatus.STALE.value, 0))
    blocked = int(data_status_summary.get(DataStatus.BLOCKED.value, 0))
    return {
        "last_refresh": _format_time(
            _first(payload.get("last_refresh"), payload.get("generated_at"))
        ),
        "next_refresh_tick": _format_time(
            _first(
                payload.get("next_refresh_tick"),
                _mapping(payload.get("debug")).get("next_refresh_tick"),
                _mapping(payload.get("performance")).get("next_refresh_tick"),
            )
        ),
        "provider_budget_status": _provider_budget_status(payload, cards),
        "refreshing": _bool_or_default(
            _first(
                payload.get("refreshing"),
                _mapping(payload.get("debug")).get("refreshing"),
                _mapping(payload.get("performance")).get("refreshing"),
            ),
            False,
        ),
        "staleness": {
            "stale_cards": stale,
            "blocked_cards": blocked,
            "stale_or_blocked_cards": stale + blocked,
        },
        "data_status_summary": data_status_summary,
    }


def _provider_budget_status(
    payload: Mapping[str, Any],
    cards: Sequence[Mapping[str, Any]],
) -> str:
    direct = _optional_text(
        _first(
            payload.get("provider_budget_status"),
            _mapping(payload.get("debug")).get("provider_budget_status"),
            _mapping(payload.get("performance")).get("provider_budget_status"),
        )
    )
    if direct:
        return direct
    statuses = [
        status
        for status in (_optional_text(card.get("provider_budget_status")) for card in cards)
        if status
    ]
    if "EXHAUSTED" in statuses:
        return "EXHAUSTED"
    if statuses:
        return statuses[0]
    return "UNKNOWN"


def _has_contract_fields(card: Mapping[str, Any], contract: Mapping[str, Any]) -> bool:
    return any(
        value is not None
        for value in (
            card.get("decision_tier"),
            card.get("data_status"),
            contract.get("decision_tier"),
            contract.get("data_status"),
        )
    )


def _field(card: Mapping[str, Any], contract: Mapping[str, Any], key: str) -> Any:
    value = contract.get(key)
    if value is not None:
        return value
    return card.get(key)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_copy(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _text(*values: Any) -> str:
    value = _first(*values)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _parse_time(value: Any) -> datetime | None:
    raw = _format_time(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [str(item) for item in value if item is not None]
    if value is None:
        return []
    return [str(value)]


def _bool_or_default(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _is_decision_tier(value: str) -> bool:
    try:
        DecisionTier(value)
    except ValueError:
        return False
    return True
