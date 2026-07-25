from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from w2.dashboard.date_navigation import build_date_navigation
from w2.dashboard.degradation import build_dashboard_degradation
from w2.domain.decision_contract import validate_decision_contract
from w2.domain.enums import DataStatus, DecisionTier, LifecycleStatus
from w2.domain.environment_policy import build_environment_policy_stamp
from w2.prematch.simulation_reconciliation import (
    PublicSimulationReadViolation,
    canonical_public_simulation,
)

CARD_SOURCE_CONTRACT = "decision_contract"
ANALYSIS_CARD_CONTRACT_VERSION = "w2.analysis-card.contract.v1"


class ProjectionCardContractViolation(RuntimeError):
    """Raised when a canonical projection card violates the M1 contract."""


def build_dashboard_day_view(
    dashboard_payload: Mapping[str, Any],
    *,
    environment: str,
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
        "environment_policy": build_environment_policy_stamp(environment),
        "timezone": _text(dashboard_payload.get("timezone"), "Asia/Shanghai"),
        "window": _text(dashboard_payload.get("window"), "today"),
        "source": "dashboard_read_model",
        "version": _mapping_copy(dashboard_payload.get("version")),
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
    try:
        canonical_public_simulation(card)
    except PublicSimulationReadViolation as exc:
        raise ProjectionCardContractViolation(str(exc)) from exc
    contract = validate_decision_contract(
        card.get("decision_contract"),
        fixture_id=card.get("fixture_id"),
        card=card,
    )
    projected = _contract_card(card, contract)
    _validate_projection_card(projected)
    return projected


def _contract_card(card: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    decision_tier = str(contract["decision_tier"])
    data_status = str(contract["data_status"])
    lifecycle_status = str(contract["lifecycle_status"])
    market_context = _market_context_fields(card)
    if data_status != DataStatus.READY.value or decision_tier == DecisionTier.NOT_READY.value:
        market_context["current_odds"] = {}
        market_context["market_probabilities"] = {}
    decision_pick = contract["pick"]
    has_directional_pick = decision_tier in {
        DecisionTier.ANALYSIS_PICK.value,
        DecisionTier.RECOMMEND.value,
    } and isinstance(decision_pick, Mapping)
    if not has_directional_pick:
        market_context["scoreline_picks"] = []
        market_context["scoreline_reference"] = {}
    return {
        **_fixture_fields(card),
        "source": CARD_SOURCE_CONTRACT,
        "analysis_card_contract_version": ANALYSIS_CARD_CONTRACT_VERSION,
        "simulation": _simulation_projection(card),
        "decision_tier": decision_tier,
        "data_status": data_status,
        "lifecycle_status": lifecycle_status,
        "outcome_tracked": contract["outcome_tracked"],
        "lock_eligible": contract["lock_eligible"],
        "recommendation_id": _optional_text(contract["recommendation_id"]),
        "reason_code": _optional_text(contract.get("reason_code")),
        "action": _optional_text(contract.get("action")),
        "next_eval_at": _format_time(contract.get("next_eval_at")),
        "provider_budget_status": _optional_text(contract.get("provider_budget_status")),
        "probability_source": _optional_text(contract.get("probability_source")),
        "model_market_divergence": _mapping_copy(contract.get("model_market_divergence")),
        "missing_fields": _string_list(contract.get("missing_fields")),
        "stale_fields": _string_list(contract.get("stale_fields")),
        "data_readiness": _mapping_copy(contract.get("data_readiness")),
        **market_context,
        "pick": _mapping_copy(decision_pick) if isinstance(decision_pick, Mapping) else None,
        "secondary_picks": [
            _mapping_copy(item)
            for item in card.get("secondary_picks", [])
            if isinstance(item, Mapping)
        ][:1]
        if has_directional_pick
        else [],
        "market_selection_audit": [
            _mapping_copy(item)
            for item in card.get("market_selection_audit", [])
            if isinstance(item, Mapping)
        ],
        "lineup_provenance": _mapping_copy(card.get("lineup_provenance")),
        "dynamic_prematch": _mapping_copy(card.get("dynamic_prematch")),
        "non_pick": _mapping_copy(contract["non_pick"])
        if isinstance(contract["non_pick"], Mapping)
        else None,
        "one_liner": _optional_text(contract.get("one_liner")),
        "card_hash": _optional_text(contract.get("card_hash")),
        "quote_identity_audit": _mapping_copy(card.get("quote_identity_audit")),
        "frozen_artifact_provenance": _mapping_copy(card.get("frozen_artifact_provenance")),
        "artifact_hash": _optional_text(card.get("artifact_hash")),
        "recommendation_decision_v3": _mapping_copy(card.get("recommendation_decision_v3")),
    }


def _fixture_fields(card: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": _text(card.get("fixture_id")),
        "kickoff_utc": _format_time(card.get("kickoff_utc")),
        "kickoff_beijing": _optional_text(card.get("kickoff_beijing")),
        "competition_id": _optional_text(card.get("competition_id")),
        "competition_name": _optional_text(card.get("competition_name")),
        "home_team_name": _optional_text(card.get("home_team_name")),
        "away_team_name": _optional_text(card.get("away_team_name")),
        "status": _optional_text(card.get("status")),
    }


def _market_context_fields(card: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "current_odds": _mapping_copy(card.get("current_odds")),
        "market_candidates": _mapping_copy(card.get("market_candidates")),
        "last_known_odds": _mapping_copy(card.get("last_known_odds")),
        "market_probabilities": _market_probabilities(card),
        "odds_movement": _mapping_copy(card.get("odds_movement")),
        "market_strip": _mapping_list(card.get("market_strip")),
        "data_refresh": _mapping_copy(card.get("data_refresh")),
        "analysis_readiness": _mapping_copy(card.get("analysis_readiness")),
        "missing_inputs": _string_list(card.get("missing_inputs")),
        "scoreline_picks": _mapping_list(card.get("scoreline_picks")),
        "scoreline_reference": _mapping_copy(card.get("scoreline_reference")),
        "scoreline_readiness": _mapping_copy(card.get("scoreline_readiness")),
        "scoreline_simulations": _scoreline_simulations(card),
    }


def _scoreline_simulations(card: Mapping[str, Any]) -> int | None:
    simulation = _mapping(canonical_public_simulation(card))
    value = simulation.get("simulations")
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None


def _simulation_projection(card: Mapping[str, Any]) -> dict[str, Any]:
    """Project the canonical top-level ``card["simulation"]`` by its real status.

    The only source is the top-level simulation produced upstream by
    analysis_calculator; this never backfills, rebuilds, or computes a
    simulation. When the source status is ``READY`` the inner object is passed through as a
    canonical full object, so ``canonical_sha256`` of the projected inner object
    equals that of the source. Other states carry no payload; an unknown or
    missing source status fails closed.
    """
    source = canonical_public_simulation(card)
    if source is None:
        return {"status": "UNAVAILABLE", "simulation": None}
    source_status = source.get("status")
    if source_status == "READY":
        return {"status": "READY", "simulation": _mapping_copy(source)}
    if source_status == "INSUFFICIENT_INPUTS":
        return {
            "status": "UNAVAILABLE",
            "simulation": None,
            "source_status": "INSUFFICIENT_INPUTS",
        }
    identity = _optional_text(card.get("fixture_id")) or "UNKNOWN"
    raise ProjectionCardContractViolation(
        f"PROJECTION_CARD_INVALID:{identity}:simulation_source_status"
    )


def _validate_projection_card(projected: Mapping[str, Any]) -> None:
    """Fail closed when a canonical projection card breaks the M1 contract.

    Requires: explicit ``decision_tier``; an explicit public-market selection
    (``pick``) or an explicit no-selection state (``non_pick``); and a
    top-level ``simulation`` whose status is exactly ``READY`` or
    ``UNAVAILABLE``. ``market_candidate`` stays optional evidence.
    """
    identity = _optional_text(projected.get("fixture_id")) or "UNKNOWN"
    if not _optional_text(projected.get("decision_tier")):
        raise ProjectionCardContractViolation(
            f"PROJECTION_CARD_INVALID:{identity}:decision_tier"
        )
    if projected.get("pick") is None and projected.get("non_pick") is None:
        raise ProjectionCardContractViolation(
            f"PROJECTION_CARD_INVALID:{identity}:market_selection"
        )
    simulation = projected.get("simulation")
    if not isinstance(simulation, Mapping):
        raise ProjectionCardContractViolation(
            f"PROJECTION_CARD_INVALID:{identity}:simulation_status"
        )
    status = simulation.get("status")
    inner = simulation.get("simulation")
    if status == "READY":
        if not isinstance(inner, Mapping) or inner.get("status") != "READY":
            raise ProjectionCardContractViolation(
                f"PROJECTION_CARD_INVALID:{identity}:simulation_status"
            )
    elif status == "UNAVAILABLE":
        if inner is not None:
            raise ProjectionCardContractViolation(
                f"PROJECTION_CARD_INVALID:{identity}:simulation_status"
            )
    else:
        raise ProjectionCardContractViolation(
            f"PROJECTION_CARD_INVALID:{identity}:simulation_status"
        )


def _market_probabilities(card: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping_copy(card.get("market_probabilities"))


def _counts(cards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_decision_tier = {tier.value: 0 for tier in DecisionTier}
    by_data_status = {status.value: 0 for status in DataStatus}
    by_lifecycle_status = {status.value: 0 for status in LifecycleStatus}
    lock_eligible = 0
    outcome_tracked = 0
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

    return {
        "total": len(cards),
        "lock_eligible": lock_eligible,
        "outcome_tracked": outcome_tracked,
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
        "page_updated_at": _format_time(
            _first(payload.get("page_updated_at"), payload.get("generated_at"))
        ),
        "odds_last_confirmed_at": _format_time(payload.get("odds_last_confirmed_at")),
        # Kept for one compatibility window; it is explicitly the page time,
        # never an odds timestamp.
        "last_refresh": _format_time(
            _first(payload.get("page_updated_at"), payload.get("generated_at"))
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
