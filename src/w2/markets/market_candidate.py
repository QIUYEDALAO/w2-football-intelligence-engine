"""Canonical, market-scoped candidate projection for recommendation V3.

This module intentionally projects evidence already present on an analysis card.  It
does not select a line, query a provider, or infer quote identity from legacy
``READY`` flags.  A candidate is executable only when its authoritative two-sided
quote has both complete identity and complete freshness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from w2.markets.analysis_evidence import build_analysis_market_evidence

MARKET_CANDIDATE_SCHEMA_VERSION = "w2.market_candidate.v1"

_KEYS = {"ASIAN_HANDICAP": "ah", "TOTALS": "ou"}


def build_market_candidates(
    *,
    markets: Sequence[Mapping[str, Any]] | None,
    quote_identity_audit: Mapping[str, Any] | None,
    current_odds: Mapping[str, Any] | None,
    pricing_shadow: Mapping[str, Any] | None,
    simulation: Mapping[str, Any] | None = None,
    fixture_id: str = "",
    competition_id: str = "",
) -> dict[str, dict[str, Any]]:
    """Return one deterministic candidate per supported market.

    ``current_odds`` is only copied into ``executable`` after the matching audit
    is COMPLETE.  Stale or incomplete values remain auditable references and are
    explicitly ineligible for EV, formal admission, and locking.
    """
    by_market = {
        str(row.get("market") or ""): row for row in (markets or []) if isinstance(row, Mapping)
    }
    audit = quote_identity_audit or {}
    odds = current_odds or {}
    pricing = pricing_shadow or {}
    return {
        key: _candidate(
            market=market,
            market_row=by_market.get(market, {}),
            audit=_mapping(audit.get(key)),
            odds=_mapping(odds.get(key)),
            pricing=pricing,
            simulation=simulation,
            fixture_id=fixture_id,
            competition_id=competition_id,
        )
        for market, key in _KEYS.items()
    }


def candidate_is_executable(candidate: Mapping[str, Any] | None) -> bool:
    return bool(
        isinstance(candidate, Mapping)
        and candidate.get("quote_status") == "COMPLETE"
        and candidate.get("quote_usage") == "EXECUTABLE"
    )


def _candidate(
    *,
    market: str,
    market_row: Mapping[str, Any],
    audit: Mapping[str, Any],
    odds: Mapping[str, Any],
    pricing: Mapping[str, Any],
    simulation: Mapping[str, Any] | None,
    fixture_id: str,
    competition_id: str,
) -> dict[str, Any]:
    identity_status = _text(audit.get("identity_status"), "INCOMPLETE")
    freshness_status = _text(audit.get("freshness_status"), "INCOMPLETE")
    executable_odds = dict(odds) or _authoritative_executable_quote(
        audit, market_row.get("tendency")
    )
    quote_complete = identity_status == "COMPLETE" and freshness_status == "COMPLETE"
    executable = quote_complete and bool(executable_odds)
    quote_status = (
        "COMPLETE"
        if quote_complete
        else "CONFLICT"
        if identity_status == "CONFLICT"
        else ("STALE" if freshness_status == "STALE" else "INCOMPLETE")
    )
    blockers = [str(item) for item in audit.get("blockers", []) if item]
    blockers.extend(str(item) for item in audit.get("freshness_blockers", []) if item)
    if not odds and executable:
        blockers.append("EXECUTABLE_ODDS_MISSING")
    if quote_complete and not executable:
        blockers.append("NO_DIRECTION_SELECTED")
    elif not executable and not blockers:
        blockers.append("QUOTE_NOT_EXECUTABLE")
    line = market_row.get("line")
    if line is None:
        line = audit.get("selected_line")
    evidence = build_analysis_market_evidence(
        fixture_id=fixture_id,
        competition_id=competition_id,
        market=market,
        selection=market_row.get("tendency"),
        line=line,
        quote_identity_audit={_KEYS[market]: audit},
        simulation=simulation,
    )
    model = _mapping(evidence.get("model_probability"))
    comparison = _mapping(evidence.get("comparison"))
    model_status = _text(model.get("status"), "NOT_READY")
    quote_usage = str(evidence.get("quote_usage") or "")
    reference = _reference_quote(audit)
    return {
        "schema_version": MARKET_CANDIDATE_SCHEMA_VERSION,
        "market": market,
        "analysis_capability": "AVAILABLE" if market_row else "NOT_AVAILABLE",
        "formal_capability": (
            "CODE_PRESENT_BUT_DISABLED" if market == "ASIAN_HANDICAP" else "NOT_IMPLEMENTED"
        ),
        "selection": market_row.get("tendency"),
        "line": line,
        "quote_status": quote_status,
        "quote_usage": "EXECUTABLE"
        if executable
        else "COMPARISON_ONLY"
        if quote_complete and quote_usage == "COMPARISON_ONLY"
        else "REFERENCE_ONLY",
        "quotes": {
            "executable": executable_odds if executable else None,
            "opening_reference": None,
            "last_known_reference": reference,
        },
        "quote_identity": {
            "identity_status": identity_status,
            "freshness_status": freshness_status,
            "observation_ids": dict(_mapping(audit.get("observation_ids"))),
            "provider": audit.get("provider"),
            "bookmaker_id": audit.get("bookmaker_id"),
            "captured_at": audit.get("captured_at"),
        },
        "model_status": model_status,
        "model_probability": model,
        "market_probability": evidence.get("market_probability"),
        "fair_line": (
            pricing.get("fair_ah") if market == "ASIAN_HANDICAP" else pricing.get("fair_ou")
        ),
        "market_line": (
            pricing.get("market_ah") if market == "ASIAN_HANDICAP" else pricing.get("market_ou")
        ),
        "edge": comparison.get("probability_delta"),
        "calibration": {
            "status": market_row.get("calibration_status") or "UNKNOWN",
            "error": market_row.get("calibration_error"),
        },
        "settlement_contract": market_row.get("settlement_contract"),
        "analysis_evidence": evidence,
        "analysis_evidence_status": evidence.get("status"),
        "analysis_direction_allowed": comparison.get("analysis_direction_allowed") is True,
        "side_evidence": evidence.get("side_evidence", {}),
        "evidence_hash": evidence.get("evidence_hash"),
        "ev_eligible": executable and model_status == "READY",
        "formal_eligible": False,
        "lock_eligible": False,
        "blockers": sorted(set(blockers)),
        "warnings": ["REFERENCE_QUOTE_NOT_FOR_EV"] if not executable and reference else [],
    }


def _reference_quote(audit: Mapping[str, Any]) -> dict[str, Any] | None:
    quotes = _mapping(audit.get("quotes"))
    if not quotes:
        return None
    return {
        "captured_at": audit.get("captured_at"),
        "provider": audit.get("provider"),
        "bookmaker_id": audit.get("bookmaker_id"),
        "quotes": {key: dict(value) for key, value in quotes.items() if isinstance(value, Mapping)},
    }


def _authoritative_executable_quote(audit: Mapping[str, Any], selection: object) -> dict[str, Any]:
    """Use only the selected side from the already-audited same-line quote pair."""
    text = _text(selection).replace("_AH", "").replace("_TOTALS", "")
    side = (
        "home"
        if text.startswith("HOME")
        else "away"
        if text.startswith("AWAY")
        else "over"
        if text.startswith("OVER")
        else "under"
        if text.startswith("UNDER")
        else ""
    )
    quote = _mapping(_mapping(audit.get("quotes")).get(side))
    price = quote.get("decimal_odds")
    return {"line": quote.get("line"), "decimal_odds": price} if price else {}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object, default: str = "") -> str:
    return value.strip().upper() if isinstance(value, str) and value.strip() else default
