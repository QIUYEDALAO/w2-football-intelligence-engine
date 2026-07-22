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
    if not isinstance(candidate, Mapping):
        return False
    quotes = candidate.get("quotes")
    executable = quotes.get("executable") if isinstance(quotes, Mapping) else None
    price = _selected_price(_mapping(executable), candidate.get("selection"))
    return bool(
        isinstance(candidate, Mapping)
        and candidate.get("quote_status") == "COMPLETE"
        and candidate.get("quote_usage") == "EXECUTABLE"
        and _text(candidate.get("selection")) in {"HOME", "AWAY", "OVER", "UNDER"}
        and candidate.get("line") is not None
        and isinstance(executable, Mapping)
        and price is not None
        and price > 1
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
    selection = market_row.get("tendency")
    line = market_row.get("line")
    if line is None:
        line = audit.get("selected_line")
    quote_complete = identity_status == "COMPLETE" and freshness_status == "COMPLETE"
    if selection is None and quote_complete and line is not None:
        comparison_evidence = build_analysis_market_evidence(
            fixture_id=fixture_id,
            competition_id=competition_id,
            market=market,
            selection=None,
            line=line,
            quote_identity_audit={_KEYS[market]: audit},
            simulation=simulation,
        )
        selection = _best_analysis_side(comparison_evidence)
    selected_quote = _authoritative_executable_quote(audit, selection)
    selected_side_line = selected_quote.get("line") if selected_quote else None
    executable_odds = selected_quote if selection is not None else {}
    selected_side_quote = bool(selected_quote)
    if selection is not None and selected_side_line is not None:
        line = selected_side_line
    executable_price = _selected_price(executable_odds, selection)
    quote_executable = bool(
        quote_complete
        and selection is not None
        and selected_side_line is not None
        and selected_side_quote
        and executable_price is not None
        and executable_price > 1
    )
    quote_status = (
        "COMPLETE"
        if quote_complete
        else "CONFLICT"
        if identity_status == "CONFLICT"
        else ("STALE" if freshness_status == "STALE" else "INCOMPLETE")
    )
    blockers = [str(item) for item in audit.get("blockers", []) if item]
    blockers.extend(str(item) for item in audit.get("freshness_blockers", []) if item)
    evidence = build_analysis_market_evidence(
        fixture_id=fixture_id,
        competition_id=competition_id,
        market=market,
        selection=selection,
        line=audit.get("selected_line"),
        quote_identity_audit={_KEYS[market]: audit},
        simulation=simulation,
    )
    model = _mapping(evidence.get("model_probability"))
    comparison = _mapping(evidence.get("comparison"))
    model_status = _text(model.get("status"), "NOT_READY")
    side_identity_conflict = evidence.get("status") in {
        "AH_SIDE_LINE_IDENTITY_CONFLICT",
        "TOTALS_SIDE_LINE_IDENTITY_CONFLICT",
    }
    executable = quote_executable and not side_identity_conflict
    if side_identity_conflict:
        blockers.append(str(evidence["status"]))
    if quote_complete and not executable:
        blockers.append("NO_DIRECTION_SELECTED" if selection is None else "QUOTE_NOT_EXECUTABLE")
    elif not executable and not blockers:
        blockers.append("QUOTE_NOT_EXECUTABLE")
    reference = _reference_quote(audit)
    ladder_evaluation = _ladder_evaluation(
        market=market,
        odds=odds,
        simulation=simulation,
        fixture_id=fixture_id,
        competition_id=competition_id,
        selected_line=line,
        selected_selection=selection,
    )
    candidate_role = "MARKET_MAINLINE" if _same_line(line, odds.get("line")) else "ALTERNATE_LINE"
    return {
        "schema_version": MARKET_CANDIDATE_SCHEMA_VERSION,
        "market": market,
        "analysis_capability": "AVAILABLE" if market_row else "NOT_AVAILABLE",
        "formal_capability": (
            "CODE_PRESENT_BUT_DISABLED" if market == "ASIAN_HANDICAP" else "NOT_IMPLEMENTED"
        ),
        "selection": selection,
        "line": evidence.get("selected_side_line") if selection is not None else line,
        "candidate_role": candidate_role,
        "market_mainline": _market_mainline_contract(odds),
        "analysis_selected_candidate": {
            "market": market,
            "selection": selection,
            "line": evidence.get("selected_side_line") if selection is not None else line,
            "candidate_role": candidate_role,
            "model_probability": model.get("effective_probability"),
            "market_probability": _selected_market_probability(evidence, selection),
            "probability_delta": comparison.get("probability_delta"),
            "expected_value": model.get("expected_value"),
            "uncertainty": model.get("ev_se"),
            "quote_identity_hash": audit.get("quote_identity_hash"),
        },
        "execution_quote": dict(selected_quote) if selected_quote else None,
        "market_ladder_evaluation": ladder_evaluation,
        "quote_status": quote_status,
        "quote_usage": "EXECUTABLE"
        if executable
        else "COMPARISON_ONLY"
        if quote_complete
        else "REFERENCE_ONLY",
        "quotes": {
            "executable": executable_odds if executable else None,
            "opening_reference": None,
            "last_known_reference": reference,
        },
        "quote_identity": {
            "schema_version": audit.get("schema_version"),
            "market": audit.get("market") or market,
            "selected_line": audit.get("selected_line"),
            "fixture_id": audit.get("fixture_id"),
            "identity_status": identity_status,
            "freshness_status": freshness_status,
            "observation_ids": dict(_mapping(audit.get("observation_ids"))),
            "provider": audit.get("provider"),
            "bookmaker_id": audit.get("bookmaker_id"),
            "capture_id": audit.get("capture_id"),
            "captured_at": audit.get("captured_at"),
            "source_revision": audit.get("source_revision"),
            "raw_payload_sha256": audit.get("raw_payload_sha256"),
            "quote_identity_hash": audit.get("quote_identity_hash"),
            "quotes": {
                key: dict(value)
                for key, value in _mapping(audit.get("quotes")).items()
                if isinstance(value, Mapping)
            },
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
        "ev_eligible": (
            executable
            and model_status == "READY"
            and evidence.get("status") == "COMPLETE"
            and comparison.get("analysis_direction_allowed") is True
        ),
        "formal_eligible": False,
        "lock_eligible": False,
        "blockers": sorted(set(blockers)),
        "warnings": ["REFERENCE_QUOTE_NOT_FOR_EV"] if not executable and reference else [],
    }


def _market_mainline_contract(odds: Mapping[str, Any]) -> dict[str, Any]:
    candidate_lines = odds.get("candidate_lines")
    selected = (
        next(
            (
                item
                for item in candidate_lines
                if isinstance(item, Mapping) and item.get("status") == "SELECTED_MARKET_MAINLINE"
            ),
            None,
        )
        if isinstance(candidate_lines, Sequence)
        else None
    )
    selected_row = dict(selected) if isinstance(selected, Mapping) else {}
    return {
        "line": odds.get("line"),
        "selection_policy": odds.get("selection_policy"),
        "candidate_ladder_hash": odds.get("candidate_ladder_hash"),
        "complete_pair_bookmaker_count": selected_row.get(
            "complete_pair_bookmaker_count",
            selected_row.get("bookmaker_count"),
        ),
        "bookmaker_vote_count": selected_row.get("bookmaker_vote_count"),
        "median_over_price": selected_row.get("median_over_price"),
        "median_under_price": selected_row.get("median_under_price"),
        "median_home_price": selected_row.get("median_home_price"),
        "median_away_price": selected_row.get("median_away_price"),
        "devig_over_probability": selected_row.get("devig_over_probability"),
        "devig_under_probability": selected_row.get("devig_under_probability"),
        "balance_distance": selected_row.get("balance_distance"),
        "captured_at": selected_row.get("captured_at") or selected_row.get("as_of"),
    }


def _ladder_evaluation(
    *,
    market: str,
    odds: Mapping[str, Any],
    simulation: Mapping[str, Any] | None,
    fixture_id: str,
    competition_id: str,
    selected_line: object,
    selected_selection: object,
) -> dict[str, Any]:
    raw_candidates = odds.get("candidate_lines")
    audits = _mapping(odds.get("ladder_quote_identity_audits"))
    if not isinstance(raw_candidates, Sequence):
        raw_candidates = []
    candidates: list[dict[str, Any]] = []
    edge_count = 0
    for raw in raw_candidates:
        if not isinstance(raw, Mapping) or raw.get("line") is None:
            continue
        line = raw.get("line")
        audit = _mapping(audits.get(str(line)))
        evidence = build_analysis_market_evidence(
            fixture_id=fixture_id,
            competition_id=competition_id,
            market=market,
            selection=None,
            line=line,
            quote_identity_audit={_KEYS[market]: audit},
            simulation=simulation,
        )
        side_evidence = _mapping(evidence.get("side_evidence"))
        market_probability = _mapping(_mapping(evidence.get("market_probability")).get("devig"))
        role = "MARKET_MAINLINE" if _same_line(line, odds.get("line")) else "ALTERNATE_LINE"
        for side, side_raw in side_evidence.items():
            side_row = _mapping(side_raw)
            model = _mapping(side_row.get("model_probability"))
            comparison = _mapping(side_row.get("comparison"))
            allowed = comparison.get("analysis_direction_allowed") is True
            edge_count += int(allowed)
            candidates.append(
                {
                    "market": market,
                    "selection": side,
                    "line": side_row.get("line") or line,
                    "candidate_role": role,
                    "admission": "ANALYSIS_ELIGIBLE"
                    if role == "MARKET_MAINLINE"
                    else "COMPARISON_ONLY",
                    "selected": (
                        role == "MARKET_MAINLINE"
                        and _same_line(side_row.get("line") or line, selected_line)
                        and str(side) == str(selected_selection or "")
                    ),
                    "model_probability": model.get("effective_probability"),
                    "market_probability": market_probability.get(str(side)),
                    "probability_delta": comparison.get("probability_delta"),
                    "expected_value": model.get("expected_value"),
                    "uncertainty": model.get("ev_se"),
                    "analysis_direction_allowed": allowed,
                    "reason_code": comparison.get("reason_code"),
                    "quote_identity_hash": audit.get("quote_identity_hash"),
                    "quote_status": audit.get("identity_status"),
                    "freshness_status": audit.get("freshness_status"),
                }
            )
    return {
        "schema_version": "w2.market_ladder_evaluation.v1",
        "selection_policy": odds.get("selection_policy"),
        "candidate_ladder_hash": odds.get("candidate_ladder_hash"),
        "evaluated_candidate_count": len(candidates),
        "edge_count": edge_count,
        "mainline_candidates": [
            row for row in candidates if row["candidate_role"] == "MARKET_MAINLINE"
        ],
        "alternate_candidates": [
            row for row in candidates if row["candidate_role"] == "ALTERNATE_LINE"
        ],
        "candidates": candidates,
        "alternate_admission_policy": "COMPARISON_ONLY_NO_REVIEWED_ADMISSION_POLICY",
    }


def _selected_market_probability(evidence: Mapping[str, Any], selection: object) -> Any:
    side = _text(selection)
    return _mapping(_mapping(evidence.get("market_probability")).get("devig")).get(side)


def _same_line(first: object, second: object) -> bool:
    try:
        return abs(float(first) - float(second)) <= 0.0001  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(first) == str(second)


def _best_analysis_side(evidence: Mapping[str, Any]) -> str | None:
    side_evidence = _mapping(evidence.get("side_evidence"))
    candidates: list[tuple[float, str]] = []
    for side, raw in side_evidence.items():
        row = _mapping(raw)
        comparison = _mapping(row.get("comparison"))
        model = _mapping(row.get("model_probability"))
        if comparison.get("analysis_direction_allowed") is not True:
            continue
        ev = _number(model.get("expected_value"))
        if ev is None:
            continue
        candidates.append((ev, str(side)))
    if not candidates:
        return None
    return max(candidates)[1]


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
    return (
        {
            "line": quote.get("line"),
            "decimal_odds": price,
            "provider": quote.get("provider"),
            "bookmaker_id": quote.get("bookmaker_id"),
            "bookmaker_name": quote.get("bookmaker_name"),
            "capture_id": quote.get("capture_id"),
            "captured_at": quote.get("captured_at"),
            "observation_id": quote.get("observation_id"),
        }
        if price and quote.get("line") is not None
        else {}
    )


def _normalize_selected_odds(odds: Mapping[str, Any], selection: object) -> dict[str, Any]:
    if not odds:
        return {}
    return dict(odds)


def _selected_price(odds: Mapping[str, Any], selection: object) -> float | None:
    text = _text(selection).replace("_AH", "").replace("_TOTALS", "")
    keys = (
        ("decimal_odds", "home_price")
        if text.startswith("HOME")
        else ("decimal_odds", "away_price")
        if text.startswith("AWAY")
        else ("decimal_odds", "over_price")
        if text.startswith("OVER")
        else ("decimal_odds", "under_price")
        if text.startswith("UNDER")
        else ("decimal_odds",)
    )
    for key in keys:
        value = _number(odds.get(key))
        if value is not None:
            return value
    return None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object, default: str = "") -> str:
    return value.strip().upper() if isinstance(value, str) and value.strip() else default


def _number(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
