from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from w2.domain.decision_adapter import build_decision_contract_fields
from w2.domain.decision_contract import (
    CONTRACT_OWNED_FIELDS,
    REQUIRED_DECISION_CONTRACT_FIELDS,
    validate_decision_contract,
)
from w2.domain.enums import DataStatus, DecisionReasonCode, DecisionTier
from w2.markets.market_candidate import build_market_candidates
from w2.tracking.advisory_blind_spot_policy import (
    POLICY_CHECKPOINT_KEY,
    AdvisoryBlindSpotPolicyCheckpoint,
    build_advisory_blind_spot_policy,
)

NOW = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=4)
POLICY_PAYLOAD = build_advisory_blind_spot_policy(
    {
        "fixture-1": {
            "fixture_id": "fixture-1",
            "kickoff_utc": NOW.isoformat(),
            "evaluation_tier": "ADVISORY",
            "status": "NOT_SCORABLE",
        }
    },
    existing=None,
    now=NOW,
)
POLICY_CHECKPOINT = AdvisoryBlindSpotPolicyCheckpoint(
    checkpoint_key=POLICY_CHECKPOINT_KEY,
    source_hash=str(POLICY_PAYLOAD["business_projection_hash"]),
    created_at=NOW,
    payload=POLICY_PAYLOAD,
).as_dict()


def _ready_policy_checkpoint(
    *,
    calibrated_at: datetime,
    corruption: str | None = None,
) -> dict[str, object]:
    strict_clv = 0.2 if corruption == "watch_false" else 0.01
    advisory_clv = 0.05 if corruption == "watch_false" else 0.02
    rows = {
        f"advisory-{index}": {
            "fixture_id": f"advisory-{index}",
            "kickoff_utc": (calibrated_at - timedelta(hours=index)).isoformat(),
            "evaluation_tier": "ADVISORY",
            "status": "SCORED",
            "canonical_settlement_outcome": "HIT",
            "clv_status": "AVAILABLE",
            "clv_decimal": advisory_clv,
        }
        for index in range(50)
    }
    rows["strict"] = {
        **rows["advisory-0"],
        "fixture_id": "strict",
        "evaluation_tier": "STRICT",
        "clv_decimal": strict_clv,
    }
    payload = build_advisory_blind_spot_policy(
        rows,
        existing=None,
        now=calibrated_at,
    )
    if corruption is not None:
        if corruption == "missing_next":
            payload.pop("next_recalibration_at")
        else:
            key, value = {
                "settled": ("calibration_advisory_canonical_settled_count", 49),
                "calibrated": ("last_calibrated_settled_count", 49),
                "seed": ("calibration_bootstrap_seed", 0),
                "strict_mean": ("calibration_strict_clv_mean", None),
                "advisory_mean": ("calibration_advisory_clv_mean", None),
                "zero_count_mean": ("calibration_strict_clv_sample_count", 0),
                "mean_nan": ("calibration_strict_clv_mean", float("nan")),
                "mean_infinity": ("calibration_advisory_clv_mean", float("inf")),
                "watch_only": ("watch_only", True),
                "watch_false": ("watch_only", False),
                "next": (
                    "next_recalibration_at",
                    (calibrated_at + timedelta(days=89)).isoformat(),
                ),
                "next_early": (
                    "next_recalibration_at",
                    (calibrated_at - timedelta(microseconds=1)).isoformat(),
                ),
            }[corruption]
            payload[key] = value
        projected = {
            key: value
            for key, value in payload.items()
            if key != "business_projection_hash"
        }
        payload["business_projection_hash"] = hashlib.sha256(
            json.dumps(
                projected,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        ).hexdigest()
    return AdvisoryBlindSpotPolicyCheckpoint(
        checkpoint_key=POLICY_CHECKPOINT_KEY,
        source_hash=str(payload["business_projection_hash"]),
        created_at=calibrated_at,
        payload=payload,
    ).as_dict()


def _complete_quote_audit() -> dict[str, object]:
    identity = {
        "identity_status": "COMPLETE",
        "freshness_status": "COMPLETE",
    }
    return {"ah": dict(identity), "ou": dict(identity)}


def _readiness(
    status: DataStatus = DataStatus.READY,
    *,
    reason: DecisionReasonCode | None = None,
    missing: tuple[str, ...] = (),
    stale: tuple[str, ...] = (),
    provider_budget_status: str = "AVAILABLE",
) -> dict[str, object]:
    return {
        "data_readiness": {
            "source": "w2.readiness.data_gate.v1",
            "data_status": status.value,
            "missing_fields": list(missing),
            "stale_fields": list(stale),
            "reason_code": reason.value if reason else None,
            "reason_human": "",
            "action": "",
            "next_eval_at": None,
            "provider_budget_status": provider_budget_status,
            "field_statuses": [],
        }
    }


def _quote_audit(market: str, line: object, odds: object) -> dict[str, object]:
    canonical_line = Decimal(str(line))
    sides = (
        {
            "home": {"line": str(canonical_line), "decimal_odds": odds},
            "away": {"line": str(-canonical_line), "decimal_odds": odds},
        }
        if market == "ASIAN_HANDICAP"
        else {
            "over": {"line": str(canonical_line), "decimal_odds": odds},
            "under": {"line": str(canonical_line), "decimal_odds": odds},
        }
    )
    return {
        "schema_version": "w2.quote_identity.v1",
        "market": market,
        "selected_line": str(canonical_line),
        "fixture_id": "fixture-1",
        "identity_status": "COMPLETE",
        "freshness_status": "COMPLETE",
        "observation_ids": {side: f"{side}-observation" for side in sides},
        "provider": "api-football",
        "bookmaker_id": "bookmaker-1",
        "capture_id": "capture-1",
        "captured_at": "2026-07-05T00:00:00Z",
        "source_revision": "a" * 40,
        "raw_payload_sha256": "b" * 64,
        "quote_identity_hash": "c" * 64,
        "quotes": sides,
    }


def _canonical_candidate(market: dict[str, object]) -> dict[str, object]:
    market_name = str(market.get("market") or "")
    selection = str(market.get("tendency") or market.get("selection") or "")
    key = "ou" if market_name == "TOTALS" else "ah"
    line = market.get("line", "-0.5")
    odds = market.get("odds", "1.95")
    fair_key, market_key = (
        ("fair_ou", "market_ou") if market_name == "TOTALS" else ("fair_ah", "market_ah")
    )
    lambda_home, lambda_away = (
        (0.5, 2.7)
        if selection in {"AWAY", "AWAY_AH"}
        else (0.5, 0.5)
        if selection in {"UNDER", "UNDER_TOTALS"}
        else (2.7, 0.5)
    )
    candidates = build_market_candidates(
        markets=[market],
        quote_identity_audit={key: _quote_audit(market_name, line, odds)},
        current_odds={},
        pricing_shadow={
            fair_key: market.get("fair_line", line),
            market_key: market.get("market_line", line),
        },
        simulation={
            "status": "READY",
            "model_version": "model-v1",
            "calibration_version": "calibration-v1",
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            "lambda_sigma_home": 0.08,
            "lambda_sigma_away": 0.07,
            "calibration": {
                "lambda_uncertainty_method": "deterministic_three_point",
                "params": {"dixon_coles_rho": 0.0},
            },
        },
        fixture_id="fixture-1",
        competition_id="world_cup_2026",
    )
    return {"market_candidates": {key: candidates[key]}}


def _fields(
    *,
    card: dict[str, object] | None = None,
    market: dict[str, object] | None = None,
    recommendation: dict[str, object] | None = None,
    readiness: dict[str, object] | None = None,
    environment: str = "staging",
    include_analysis_evidence: bool = True,
    competition_id: str = "world_cup_2026",
    advisory_policy_ready: bool = True,
    as_of: datetime = NOW,
) -> dict[str, object]:
    card_payload: dict[str, object] = {
        "source": "unit",
        "quote_identity_audit": _complete_quote_audit(),
    }
    card_payload.update(card or {})
    if advisory_policy_ready:
        card_payload.setdefault(
            "advisory_blind_spot_policy",
            POLICY_CHECKPOINT,
        )
    market_payload = dict(market or {})
    if not any(
        payload.get("decision_tier")
        for payload in (card_payload, market_payload, recommendation or {})
    ):
        decision = str(
            market_payload.get("decision") or market_payload.get("analysis_decision") or ""
        ).upper()
        tier = {
            "ANALYSIS_PICK": "ANALYSIS_PICK",
            "PICK": "ANALYSIS_PICK",
            "FORMAL": "ANALYSIS_PICK",
            "NO_EDGE": "SKIP",
            "WATCH": "WATCH",
        }.get(decision)
        if tier is not None:
            market_payload["decision_tier"] = tier
    if (
        include_analysis_evidence
        and market_payload.get("decision_tier") in {"ANALYSIS_PICK", "RECOMMEND"}
        and "market_candidates" not in card_payload
    ):
        card_payload.update(_canonical_candidate(market_payload))
    return build_decision_contract_fields(
        card=card_payload,
        market=market_payload or None,
        recommendation=recommendation,
        readiness=readiness or _readiness(),
        environment=environment,
        as_of=as_of,
        kickoff_utc=KICKOFF,
        competition_id=competition_id,
        fixture_id="fixture-1",
    )


def test_persisted_decision_contract_contains_complete_read_contract() -> None:
    fields = _fields()
    contract = fields["decision_contract"]

    assert isinstance(contract, dict)
    assert set(REQUIRED_DECISION_CONTRACT_FIELDS).issubset(contract)
    for field in CONTRACT_OWNED_FIELDS:
        if field in fields:
            assert contract.get(field) == fields[field]
    assert (
        validate_decision_contract(
            contract,
            fixture_id="fixture-1",
            card=fields,
        )
        == contract
    )


def test_lineup_requirement_and_risks_are_required_and_fail_closed() -> None:
    advisory = _fields()
    assert advisory["lineup_requirement"] == "ADVISORY"
    assert advisory["risk_reason_codes"] == ["LINEUP_UNOBSERVABLE"]

    strict = _fields(competition_id="premier_league")
    assert strict["lineup_requirement"] == "STRICT"
    assert strict["risk_reason_codes"] == []

    invalid = dict(advisory["decision_contract"])  # type: ignore[arg-type]
    invalid["risk_reason_codes"] = ["LINEUP_UNOBSERVABLE", "LINEUP_UNOBSERVABLE"]
    with pytest.raises(ValueError, match="risk_reason_codes"):
        validate_decision_contract(invalid, fixture_id="fixture-1")
    invalid["risk_reason_codes"] = ["UNKNOWN"]
    with pytest.raises(ValueError, match="risk_reason_codes"):
        validate_decision_contract(invalid, fixture_id="fixture-1")
    del invalid["risk_reason_codes"]
    with pytest.raises(ValueError, match="DECISION_CONTRACT_INCOMPLETE"):
        validate_decision_contract(invalid, fixture_id="fixture-1")


def test_high_rotation_prior_adds_risk_without_numerical_adjustment() -> None:
    fields = _fields(
        card={
            "lineup_provenance": {
                "requirement": "ADVISORY",
                "rotation_priors": [{"status": "READY", "classification": "HIGH_ROTATION"}],
                "lineup_ah_adjustment": 0.0,
                "lineup_totals_adjustment": 0.0,
            }
        }
    )

    assert fields["risk_reason_codes"] == [
        "HIGH_ROTATION_PRIOR",
        "LINEUP_UNOBSERVABLE",
    ]


def test_advisory_moved_pick_downgrades_but_strict_pick_does_not() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME_AH",
        "line": "-0.5",
        "odds": "1.95",
    }
    card = _canonical_candidate(market)
    candidate = card["market_candidates"]["ah"]  # type: ignore[index]
    candidate["divergence_origin"] = {"effective_risk_class": "MOVED_CONSERVATIVE"}
    card["lineup_provenance"] = {"requirement": "ADVISORY"}

    advisory = _fields(card=card, market=market)
    strict = _fields(
        card={**card, "lineup_provenance": {"requirement": "STRICT"}},
        market=market,
        competition_id="premier_league",
    )

    assert advisory["decision_tier"] == "WATCH"
    assert advisory["pick"] is None
    assert advisory["non_pick"]["reason_code"] == "MARKET_MOVED_AGAINST_BLIND_SPOT"  # type: ignore[index]
    assert advisory["outcome_tracked"] is False
    assert advisory["lock_eligible"] is False
    assert strict["decision_tier"] == "ANALYSIS_PICK"


def test_advisory_pick_fails_closed_when_delta_policy_is_missing() -> None:
    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        advisory_policy_ready=False,
    )

    assert fields["decision_tier"] == "WATCH"
    assert fields["non_pick"]["reason_code"] == "ADVISORY_DELTA_POLICY_NOT_READY"  # type: ignore[index]


@pytest.mark.parametrize(
    "corruption",
    (
        "settled",
        "calibrated",
        "seed",
        "strict_mean",
        "advisory_mean",
        "zero_count_mean",
        "mean_nan",
        "mean_infinity",
        "watch_only",
        "watch_false",
        "missing_next",
        "next",
        "next_early",
    ),
)
def test_advisory_pick_fails_closed_for_semantically_invalid_policy(
    corruption: str,
) -> None:
    fields = _fields(
        card={
            "advisory_blind_spot_policy": _ready_policy_checkpoint(
                calibrated_at=NOW,
                corruption=corruption,
            )
        },
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
    )

    assert fields["decision_tier"] == "WATCH"
    assert fields["pick"] is None
    assert fields["non_pick"] is not None
    assert fields["non_pick"]["reason_code"] == "ADVISORY_DELTA_POLICY_NOT_READY"  # type: ignore[index]
    assert fields["outcome_tracked"] is False
    assert fields["lock_eligible"] is False


def test_advisory_policy_expiry_boundary_and_strict_no_drift() -> None:
    calibrated_at = NOW - timedelta(days=90)
    policy = _ready_policy_checkpoint(calibrated_at=calibrated_at)
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }

    boundary = _fields(
        card={"advisory_blind_spot_policy": policy},
        market=market,
        as_of=NOW,
    )
    expired = _fields(
        card={"advisory_blind_spot_policy": policy},
        market=market,
        as_of=NOW + timedelta(microseconds=1),
    )
    strict = _fields(
        card={
            "advisory_blind_spot_policy": policy,
            "lineup_provenance": {"requirement": "STRICT"},
        },
        market=market,
        competition_id="premier_league",
        as_of=NOW + timedelta(microseconds=1),
    )

    assert boundary["decision_tier"] == "ANALYSIS_PICK"
    assert expired["decision_tier"] == "WATCH"
    assert expired["pick"] is None
    assert expired["non_pick"] is not None
    assert expired["non_pick"]["reason_code"] == "ADVISORY_DELTA_POLICY_NOT_READY"  # type: ignore[index]
    assert expired["outcome_tracked"] is False
    assert expired["lock_eligible"] is False
    assert strict["decision_tier"] == "ANALYSIS_PICK"
    assert strict["pick"] is not None


def test_historical_advisory_decision_cannot_consume_future_policy() -> None:
    policy = _ready_policy_checkpoint(calibrated_at=NOW)
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }

    advisory = _fields(
        card={"advisory_blind_spot_policy": policy},
        market=market,
        as_of=NOW - timedelta(microseconds=1),
    )
    strict = _fields(
        card={
            "advisory_blind_spot_policy": policy,
            "lineup_provenance": {"requirement": "STRICT"},
        },
        market=market,
        competition_id="premier_league",
        as_of=NOW - timedelta(microseconds=1),
    )

    assert advisory["decision_tier"] == "WATCH"
    assert advisory["non_pick"]["reason_code"] == "ADVISORY_DELTA_POLICY_NOT_READY"  # type: ignore[index]
    assert strict["decision_tier"] == "ANALYSIS_PICK"


def test_model_version_uses_only_canonical_card_or_adapter_default() -> None:
    assert _fields(card={"model_version": "canonical-model"})["model_version"] == "canonical-model"
    assert _fields()["model_version"] == "w2.decision_contract.v2.adapter"


@pytest.mark.parametrize(
    ("alias", "canonical"),
    (("HOME_AH", "HOME"), ("AWAY_AH", "AWAY")),
)
def test_real_ah_alias_candidate_stays_analysis_pick(
    alias: str,
    canonical: str,
) -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": alias,
        "line": "-0.5",
        "odds": "1.95",
    }
    card = _canonical_candidate(market)
    candidate = card["market_candidates"]["ah"]  # type: ignore[index]

    assert candidate["selection"] == canonical  # type: ignore[index]
    assert candidate["bookmaker_intent_selection"] == alias  # type: ignore[index]
    assert candidate["analysis_evidence"]["selection"] == canonical  # type: ignore[index]

    fields = _fields(
        card=card,
        market=market,
        recommendation={"market": "ASIAN_HANDICAP", "selection": alias},
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["pick"]["selection"] == canonical  # type: ignore[index]


@pytest.mark.parametrize(
    ("alias", "canonical"),
    (("OVER_TOTALS", "OVER"), ("UNDER_TOTALS", "UNDER")),
)
def test_real_totals_alias_candidate_is_canonicalized(
    alias: str,
    canonical: str,
) -> None:
    market = {
        "market": "TOTALS",
        "decision": "PICK",
        "tendency": alias,
        "line": "2.25",
        "odds": "1.95",
    }
    fields = _fields(
        card=_canonical_candidate(market),
        market=market,
        recommendation={"market": "TOTALS", "selection": alias},
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["pick"]["selection"] == canonical  # type: ignore[index]


@pytest.mark.parametrize("mismatch_source", ("candidate", "evidence", "market", "recommendation"))
def test_ah_alias_identity_mismatch_fails_closed(mismatch_source: str) -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME_AH",
        "line": "-0.5",
        "odds": "1.95",
    }
    card = _canonical_candidate(market)
    candidate = card["market_candidates"]["ah"]  # type: ignore[index]
    recommendation = {"market": "ASIAN_HANDICAP", "selection": "HOME_AH"}
    if mismatch_source == "candidate":
        candidate["selection"] = "AWAY_AH"  # type: ignore[index]
    elif mismatch_source == "evidence":
        candidate["analysis_evidence"]["selection"] = "AWAY"  # type: ignore[index]
    elif mismatch_source == "market":
        market["tendency"] = "AWAY_AH"
    else:
        recommendation["selection"] = "AWAY_AH"

    fields = _fields(card=card, market=market, recommendation=recommendation)

    assert fields["decision_tier"] == DecisionTier.NOT_READY.value
    assert fields["pick"] is None


@pytest.mark.parametrize(
    ("source", "market_name", "base_selection", "invalid_selection"),
    (
        ("candidate", "ASIAN_HANDICAP", "HOME_AH", "HOME_FAKE"),
        ("evidence", "ASIAN_HANDICAP", "HOME_AH", "HOME_FAKE"),
        ("market", "ASIAN_HANDICAP", "HOME_AH", "HOME_FAKE"),
        ("recommendation", "ASIAN_HANDICAP", "HOME_AH", "HOME_FAKE"),
        ("candidate", "ASIAN_HANDICAP", "HOME_AH", "OVER_TOTALS"),
        ("candidate", "TOTALS", "OVER_TOTALS", "HOME_AH"),
        ("candidate", "ASIAN_HANDICAP", "HOME_AH", "home_ah"),
    ),
)
def test_illegal_or_cross_market_selection_fails_closed(
    source: str,
    market_name: str,
    base_selection: str,
    invalid_selection: str,
) -> None:
    market = {
        "market": market_name,
        "decision": "PICK",
        "tendency": base_selection,
        "line": "2.25" if market_name == "TOTALS" else "-0.5",
        "odds": "1.95",
    }
    card = _canonical_candidate(market)
    key = "ou" if market_name == "TOTALS" else "ah"
    candidate = card["market_candidates"][key]  # type: ignore[index]
    recommendation = {"market": market_name, "selection": base_selection}
    if source == "candidate":
        candidate["selection"] = invalid_selection  # type: ignore[index]
    elif source == "evidence":
        candidate["analysis_evidence"]["selection"] = invalid_selection  # type: ignore[index]
    elif source == "market":
        market["tendency"] = invalid_selection
    else:
        recommendation["selection"] = invalid_selection

    fields = _fields(card=card, market=market, recommendation=recommendation)

    assert fields["decision_tier"] == DecisionTier.NOT_READY.value
    assert fields["pick"] is None


def test_missing_canonical_readiness_and_analysis_evidence_fail_closed() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }

    missing_readiness = _fields(market=market, readiness={"status": "READY"})
    missing_evidence = _fields(
        market=market,
        readiness=_readiness(),
        include_analysis_evidence=False,
    )

    assert missing_readiness["decision_tier"] == DecisionTier.NOT_READY.value
    assert missing_readiness["data_status"] == DataStatus.BLOCKED.value
    assert missing_readiness["missing_fields"] == ["data_readiness"]
    assert missing_evidence["decision_tier"] == DecisionTier.NOT_READY.value
    assert missing_evidence["pick"] is None
    assert missing_evidence["model_market_divergence"]["status"] == "MISSING"  # type: ignore[index]


def test_legacy_readiness_summary_does_not_collapse_to_generic_coverage_none() -> None:
    fields = _fields(
        card={
            "data_readiness": {
                "market_observations": 0,
                "bookmakers": 0,
                "odds_snapshots": 0,
                "xg": False,
                "lineups_status": "NOT_REQUESTED",
            }
        },
        readiness={"status": "BLOCKED", "blockers": ["MARKET_NOT_READY"]},
    )

    assert fields["reason_code"] == DecisionReasonCode.MARKET_UNAVAILABLE.value
    assert fields["reason_code"] != DecisionReasonCode.COVERAGE_NONE.value


_DELETE = object()
_CANONICAL_MUTATIONS = (
    (("schema_version",), _DELETE),
    (("market",), "TOTALS"),
    (("selection",), "OVER"),
    (("line",), "invalid"),
    (("quote_status",), "STALE"),
    (("quote_usage",), "COMPARISON_ONLY"),
    (("quote_identity", "identity_status"), "CONFLICT"),
    (("quote_identity", "freshness_status"), "STALE"),
    (("quote_identity", "market"), "TOTALS"),
    (("quote_identity", "quote_identity_hash"), ""),
    (("quotes", "executable", "line"), "-0.75"),
    (("quotes", "executable", "decimal_odds"), "1"),
    (("analysis_evidence", "evidence_contract_version"), "w2.analysis-market-evidence.v1"),
    (("analysis_evidence", "status"), "NOT_READY"),
    (("analysis_evidence", "quote_usage"), "COMPARISON_ONLY"),
    (("analysis_evidence", "market"), "TOTALS"),
    (("analysis_evidence", "selection"), "AWAY"),
    (("analysis_evidence", "line"), "-0.75"),
    (("analysis_evidence", "quote_identity", "identity_status"), "CONFLICT"),
    (("analysis_evidence", "quote_identity", "freshness_status"), "STALE"),
    (("analysis_evidence", "quote_identity", "market"), "TOTALS"),
    (("analysis_evidence", "quote_identity", "quote_identity_hash"), "d" * 64),
    (("analysis_evidence", "model_probability", "status"), "NOT_READY"),
    (("analysis_evidence", "model_probability", "expected_value"), "invalid"),
    (("analysis_evidence", "model_probability", "ev_se"), _DELETE),
    (("analysis_evidence", "comparison", "status"), "NO_EDGE"),
    (("analysis_evidence", "comparison", "probability_delta"), "invalid"),
    (("analysis_evidence", "comparison", "analysis_direction_allowed"), False),
)


@pytest.mark.parametrize(
    ("path", "replacement"),
    _CANONICAL_MUTATIONS,
    ids=[".".join(path) for path, _ in _CANONICAL_MUTATIONS],
)
def test_each_malformed_canonical_pick_field_fails_closed(
    path: tuple[str, ...],
    replacement: object,
) -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
        "line": "-0.5",
        "odds": "1.95",
    }
    card = deepcopy(_canonical_candidate(market))
    candidate = card["market_candidates"]["ah"]  # type: ignore[index]
    target: dict[str, Any] = candidate  # type: ignore[assignment]
    for key in path[:-1]:
        target = target[key]
    if replacement is _DELETE:
        target.pop(path[-1])
    else:
        target[path[-1]] = replacement

    fields = _fields(card=card, market=market, readiness=_readiness())

    assert fields["decision_tier"] == DecisionTier.NOT_READY.value
    assert fields["pick"] is None


def test_non_quarter_executable_line_fails_closed_even_when_all_lines_match() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
        "line": "-0.5",
        "odds": "1.95",
    }
    card = _canonical_candidate(market)
    candidate = card["market_candidates"]["ah"]  # type: ignore[index]
    candidate["line"] = "-0.1"  # type: ignore[index]
    candidate["quotes"]["executable"]["line"] = "-0.1"  # type: ignore[index]
    candidate["analysis_evidence"]["line"] = "-0.1"  # type: ignore[index]

    fields = _fields(card=card, market={**market, "line": "-0.1"})

    assert fields["decision_tier"] == DecisionTier.NOT_READY.value
    assert fields["pick"] is None


@pytest.mark.parametrize(
    ("market_override", "recommendation"),
    (
        ({"tendency": "AWAY"}, None),
        ({}, {"market": "TOTALS", "selection": "HOME"}),
        ({}, {"market": "ASIAN_HANDICAP", "selection": "AWAY"}),
    ),
)
def test_market_or_recommendation_identity_mismatch_fails_closed(
    market_override: dict[str, object],
    recommendation: dict[str, object] | None,
) -> None:
    canonical_market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
        "line": "-0.5",
        "odds": "1.95",
    }
    fields = _fields(
        card=_canonical_candidate(canonical_market),
        market={**canonical_market, **market_override},
        recommendation=recommendation,
        readiness=_readiness(),
    )

    assert fields["decision_tier"] == DecisionTier.NOT_READY.value
    assert fields["pick"] is None


def test_missing_lineups_soft_gate_is_advisory_for_analysis() -> None:
    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness=_readiness(missing=("lineups", "xg", "ratings", "team_value")),
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["data_status"] == DataStatus.READY.value
    assert fields["outcome_tracked"] is True
    assert fields["missing_fields"] == ["lineups", "xg", "ratings", "team_value"]
    assert fields["pick"] is not None
    assert fields["non_pick"] is None


def test_totals_pick_uses_canonical_analysis_evidence() -> None:
    fields = _fields(
        market={
            "market": "TOTALS",
            "decision": "PICK",
            "tendency": "OVER",
            "line": "2.25",
            "odds": "2.03",
            "fair_line": "2.75",
            "market_line": "2.25",
        },
        readiness=_readiness(),
    )

    pick = fields["pick"]
    assert isinstance(pick, dict)
    assert pick["market"] == "TOTALS"
    assert pick["line"] == "2.25"
    assert pick["fair_line"] == "2.75"
    assert pick["market_line"] == "2.25"
    assert pick["value_edge"] == pick["model_probability"]["expected_value"]
    divergence = fields["model_market_divergence"]
    assert isinstance(divergence, dict)
    assert divergence["model_fair_line"] is None
    assert divergence["market_line"] == "2.25"


def test_edge_and_market_and_data_blockers_map_to_reason_codes() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "WATCH",
        "line": "-0.25",
        "odds": "1.95",
    }
    assert (
        _fields(
            market=market,
            readiness=_readiness(reason=DecisionReasonCode.EDGE_INSUFFICIENT),
        )["reason_code"]
        == DecisionReasonCode.EDGE_INSUFFICIENT.value
    )
    assert (
        _fields(
            readiness=_readiness(
                DataStatus.BLOCKED,
                reason=DecisionReasonCode.MARKET_UNAVAILABLE,
                missing=("market",),
            ),
        )["reason_code"]
        == DecisionReasonCode.MARKET_UNAVAILABLE.value
    )
    assert (
        _fields(
            market=market,
            readiness=_readiness(
                DataStatus.BLOCKED,
                reason=DecisionReasonCode.DATA_MISSING_XG,
                missing=("xg",),
            ),
        )["reason_code"]
        == DecisionReasonCode.DATA_MISSING_XG.value
    )


def test_readiness_status_mapping_is_not_optimistic() -> None:
    ready_market = {
        "market": "ASIAN_HANDICAP",
        "decision": "WATCH",
        "line": "-0.25",
        "odds": "1.95",
    }
    assert _fields(market=ready_market, readiness=_readiness())["data_status"] == (
        DataStatus.READY.value
    )
    assert (
        _fields(
            market=ready_market,
            readiness=_readiness(missing=("lineups",)),
        )["data_status"]
        == DataStatus.READY.value
    )
    assert (
        _fields(
            market=ready_market,
            readiness=_readiness(
                DataStatus.STALE,
                reason=DecisionReasonCode.PROVIDER_BUDGET_EXHAUSTED,
            ),
        )["data_status"]
        == DataStatus.STALE.value
    )


def test_blocked_data_status_downgrades_explicit_pick_tiers() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }

    analysis = _fields(
        market={**market, "decision_tier": "ANALYSIS_PICK"},
        readiness=_readiness(
            DataStatus.BLOCKED,
            reason=DecisionReasonCode.MARKET_UNAVAILABLE,
            missing=("market",),
        ),
    )
    recommend = _fields(
        market={**market, "decision_tier": "RECOMMEND"},
        readiness=_readiness(
            DataStatus.BLOCKED,
            reason=DecisionReasonCode.MARKET_UNAVAILABLE,
            missing=("market",),
        ),
    )

    assert analysis["decision_tier"] == DecisionTier.NOT_READY.value
    assert recommend["decision_tier"] == DecisionTier.NOT_READY.value
    assert analysis["reason_code"] == DecisionReasonCode.MARKET_UNAVAILABLE.value
    assert recommend["reason_code"] == DecisionReasonCode.MARKET_UNAVAILABLE.value
    assert analysis["pick"] is None
    assert recommend["pick"] is None


def test_analysis_pick_and_lock_policy_are_environmental() -> None:
    card = {
        "source": "unit",
        "data_status": "READY",
    }
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }
    readiness = _readiness()

    staging = _fields(card=card, market=market, readiness=readiness, environment="staging")
    production = _fields(card=card, market=market, readiness=readiness, environment="production")

    assert staging["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert staging["outcome_tracked"] is True
    assert staging["lock_eligible"] is False
    assert production["lock_eligible"] is False
    assert staging["card_hash"] == production["card_hash"]
    assert "分析参考" in staging["pick"]["disclaimer"]  # type: ignore[index]
    assert "非稳赢" in staging["pick"]["disclaimer"]  # type: ignore[index]


def test_advisory_readiness_keeps_analysis_pick() -> None:
    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness=_readiness(missing=("lineups",)),
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["pick"] is not None
    assert fields["non_pick"] is None
    assert fields["outcome_tracked"] is True
    assert fields["lock_eligible"] is False
    assert fields["data_status"] == DataStatus.READY.value


def test_no_edge_analysis_stays_non_pick_with_edge_reason() -> None:
    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "NO_EDGE",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.2,
        },
        readiness=_readiness(),
    )

    assert fields["decision_tier"] == DecisionTier.SKIP.value
    assert fields["reason_code"] == DecisionReasonCode.EDGE_INSUFFICIENT.value
    assert fields["pick"] is None
    assert fields["non_pick"] is not None
    assert fields["outcome_tracked"] is False
    assert fields["quote_provenance_status"] == "COMPLETE"
    assert fields["available_quote_provenance"] == {"AH": "COMPLETE", "OU": "COMPLETE"}


def test_no_selected_market_keeps_available_quote_evidence_distinct() -> None:
    fields = _fields(market=None, readiness=_readiness())

    assert fields["quote_provenance_status"] == "MISSING"
    assert fields["available_quote_provenance"] == {"AH": "COMPLETE", "OU": "COMPLETE"}


def test_low_confidence_pick_is_fail_closed_to_watch() -> None:
    fields = _fields(
        market={
            "market": "TOTALS",
            "decision": "PICK",
            "tendency": "OVER",
            "line": "2.5",
            "odds": "1.90",
            "confidence": 0.49,
        },
        readiness=_readiness(),
    )

    assert fields["decision_tier"] == DecisionTier.WATCH.value
    assert fields["reason_code"] == DecisionReasonCode.EDGE_INSUFFICIENT.value
    assert fields["pick"] is None
    assert fields["non_pick"] is not None


def test_decision_contract_exposes_canonical_probability_and_divergence() -> None:
    fields = _fields(
        card={"current_odds": {"ah": {"home_line": "-0.25"}}},
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.72,
        },
        readiness=_readiness(),
    )

    assert fields["probability_source"] == "MARKET_DEVIG"
    assert fields["decision_contract"]["probability_source"] == "MARKET_DEVIG"  # type: ignore[index]
    divergence = fields["model_market_divergence"]
    assert divergence["status"] == "READY"  # type: ignore[index]
    assert (
        divergence["magnitude"]
        == fields["analysis_evidence"]["comparison"][  # type: ignore[index]
            "probability_delta"
        ]
    )
    assert divergence["model_fair_line"] is None  # type: ignore[index]
    assert divergence["compatibility_only"] is False  # type: ignore[index]
    assert fields["decision_contract"]["model_market_divergence"] == divergence  # type: ignore[index]


def test_market_anchor_display_flag_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("W2_MARKET_ANCHOR_DISPLAY_ENABLED", raising=False)

    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.72,
        },
        readiness=_readiness(),
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["pick"] is not None


def test_market_anchor_display_requires_market_probability(monkeypatch) -> None:
    monkeypatch.setenv("W2_MARKET_ANCHOR_DISPLAY_ENABLED", "true")

    fields = _fields(
        card={"probability_source": "MODEL_FALLBACK"},
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.72,
        },
        readiness=_readiness(),
    )

    assert fields["probability_source"] == "MODEL_FALLBACK"
    assert fields["decision_tier"] == DecisionTier.WATCH.value
    assert fields["reason_code"] == DecisionReasonCode.EDGE_INSUFFICIENT.value
    assert fields["pick"] is None
    assert fields["non_pick"] is not None


def test_top_level_divergence_cannot_override_canonical_evidence(monkeypatch) -> None:
    monkeypatch.setenv("W2_MARKET_ANCHOR_DISPLAY_ENABLED", "true")

    fields = _fields(
        card={
            "probability_source": "MARKET_DEVIG",
            "model_market_divergence": {
                "status": "READY",
                "magnitude": 0.2,
                "direction_allowed": False,
            },
        },
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.72,
        },
        readiness=_readiness(),
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["model_market_divergence"]["direction_allowed"] is True  # type: ignore[index]
    assert fields["pick"] is not None


def test_market_anchor_display_allows_canonical_market_divergence(monkeypatch) -> None:
    monkeypatch.setenv("W2_MARKET_ANCHOR_DISPLAY_ENABLED", "true")

    fields = _fields(
        card={"probability_source": "MARKET_DEVIG"},
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.72,
        },
        readiness=_readiness(),
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["pick"] is not None
    assert fields["non_pick"] is None


def test_staging_lock_requires_market_line_and_odds() -> None:
    ready = _readiness()
    base_market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
    }

    missing_odds = _fields(
        market={**base_market, "line": "-0.25"},
        readiness=ready,
        environment="staging",
    )
    missing_line = _fields(
        market={**base_market, "odds": "1.95"},
        readiness=ready,
        environment="staging",
    )
    complete = _fields(
        market={**base_market, "line": "-0.25", "odds": "1.95"},
        readiness=ready,
        environment="staging",
    )
    production_analysis = _fields(
        market={**base_market, "line": "-0.25", "odds": "1.95"},
        readiness=ready,
        environment="production",
    )

    assert missing_odds["lock_eligible"] is False
    assert missing_line["lock_eligible"] is False
    assert complete["lock_eligible"] is False
    assert production_analysis["lock_eligible"] is False


def test_recommend_requires_prerequisites_before_lock_eligible() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision_tier": "RECOMMEND",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }
    readiness = _readiness()

    without_evidence = _fields(
        recommendation={"recommendation_id": "rec-1"},
        market=market,
        readiness=readiness,
        environment="staging",
    )
    with_evidence = _fields(
        card={"forward_ev_evidence_satisfied": True},
        recommendation={"recommendation_id": "rec-1"},
        market=market,
        readiness=readiness,
        environment="staging",
    )

    assert without_evidence["lock_eligible"] is False
    assert without_evidence["decision_tier"] == DecisionTier.WATCH.value
    assert without_evidence["recommendation_id"] is None
    assert with_evidence["decision_tier"] == DecisionTier.RECOMMEND.value
    assert with_evidence["lock_eligible"] is False


def test_canonical_analysis_pick_has_no_compatibility_marker() -> None:
    fields = _fields(
        card={"decision_tier": "ANALYSIS_PICK"},
        market={
            "decision_tier": "ANALYSIS_PICK",
            "market": "ASIAN_HANDICAP",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness=_readiness(),
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert "legacy_formal" not in fields
    assert fields["recommendation_id"] is None


def test_adapter_outputs_valid_decision_card_shapes() -> None:
    analysis = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness=_readiness(),
    )
    watch = _fields(
        market={"market": "ASIAN_HANDICAP", "decision": "WATCH", "line": "-0.25", "odds": "1.95"},
        readiness=_readiness(reason=DecisionReasonCode.EDGE_INSUFFICIENT),
    )
    blocked = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision_tier": "ANALYSIS_PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness=_readiness(
            DataStatus.BLOCKED,
            reason=DecisionReasonCode.FIXTURE_LIVE_OR_FINISHED,
        ),
    )

    assert analysis["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert analysis["pick"] is not None
    assert analysis["non_pick"] is None
    assert watch["decision_tier"] == DecisionTier.WATCH.value
    assert watch["pick"] is None
    assert watch["non_pick"] is not None
    assert blocked["decision_tier"] == DecisionTier.NOT_READY.value
    assert blocked["pick"] is None
    assert blocked["non_pick"] is not None


def test_incomplete_or_conflicting_quote_provenance_forces_not_ready() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }
    missing = _fields(
        card={"quote_identity_audit": {}},
        market=market,
        readiness=_readiness(),
    )
    conflict = _fields(
        card={
            "recommendation_id": "rec-conflict",
            "quote_identity_audit": {
                "ah": {"identity_status": "CONFLICT", "freshness_status": "INCOMPLETE"}
            },
        },
        market=market,
        readiness=_readiness(),
    )

    for fields in (missing, conflict):
        assert fields["decision_tier"] == DecisionTier.NOT_READY.value
        assert fields["pick"] is None
        assert fields["recommendation_id"] is None
        assert fields["outcome_tracked"] is False
        assert fields["lock_eligible"] is False


def test_stale_quote_provenance_forces_watch_and_clears_executable_odds() -> None:
    fields = _fields(
        card={
            "recommendation_id": "rec-stale",
            "quote_identity_audit": {
                "ah": {"identity_status": "COMPLETE", "freshness_status": "STALE"}
            },
        },
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness=_readiness(),
    )

    assert fields["decision_tier"] == DecisionTier.WATCH.value
    assert fields["pick"] is None
    assert fields["recommendation_id"] is None
    assert fields["outcome_tracked"] is False
    assert fields["lock_eligible"] is False


def test_provider_budget_exhausted_is_stale_readiness() -> None:
    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness=_readiness(
            DataStatus.STALE,
            reason=DecisionReasonCode.PROVIDER_BUDGET_EXHAUSTED,
            provider_budget_status="EXHAUSTED",
        ),
    )

    assert fields["data_status"] == DataStatus.STALE.value
    assert fields["reason_code"] == DecisionReasonCode.PROVIDER_BUDGET_EXHAUSTED.value
    assert fields["provider_budget_status"] == "EXHAUSTED"


def test_data_gate_fields_pass_through_decision_contract() -> None:
    fields = _fields(
        market={"market": "ASIAN_HANDICAP", "decision": "WATCH"},
        readiness={
            "data_readiness": {
                "source": "w2.readiness.data_gate.v1",
                "data_status": "STALE",
                "missing_fields": ["xg"],
                "stale_fields": ["odds"],
                "reason_code": "DATA_STALE_ODDS",
                "reason_human": "盘口数据陈旧",
                "action": "触发盘口刷新或等下一 tick",
                "next_eval_at": "2026-07-05T00:30:00Z",
                "provider_budget_status": "AVAILABLE",
                "field_statuses": [],
            }
        },
    )

    assert fields["data_status"] == DataStatus.STALE.value
    assert fields["missing_fields"] == ["xg"]
    assert fields["stale_fields"] == ["odds"]
    assert fields["decision_contract"]["data_readiness"]["source"] == (  # type: ignore[index]
        "w2.readiness.data_gate.v1"
    )
