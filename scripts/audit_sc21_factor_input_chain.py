#!/usr/bin/env python3
"""Build the SC21 factor-input audit from persisted, read-only evidence exports."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from w2.competitions.league_whitelist_audit import MIN_BOOKMAKER_DEPTH
from w2.domain.recommendation_decision_v4 import CANDIDATE_QUOTE_MAX_AGE_SECONDS
from w2.matchday.intake_v2 import REQUIRED_MATCHDAY_COMPETITIONS

SCHEMA_VERSION = "w2.sc21-factor-coverage.v2"
MARKETS = ("ASIAN_HANDICAP", "TOTALS")
ALLOWED_REASONS = frozenset(
    {
        "READY",
        "NOT_YET_DUE",
        "DUE_NOT_COLLECTED",
        "RAW_EVIDENCE_ABSENT",
        "RAW_PRESENT_NOT_MATERIALIZED",
        "IDENTITY_NOT_MAPPED",
        "UNDER_SAMPLED",
        "STALE",
        "CONFLICTED",
        "PROVIDER_NOT_AVAILABLE",
        "POLICY_DISABLED",
        "OWNER_DECISION_REQUIRED",
    }
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _reason(value: str) -> str:
    if value not in ALLOWED_REASONS:
        raise ValueError(f"unsupported SC21 reason: {value}")
    return value


def _collection_reason(collection: dict[str, Any], has_evidence: bool) -> str:
    if has_evidence:
        return _reason("READY")
    cause = (collection.get("public_semantics") or {}).get("cause")
    if cause == "NOT_YET_DUE":
        return _reason("NOT_YET_DUE")
    if cause == "AWAITING_COLLECTION":
        return _reason("DUE_NOT_COLLECTED")
    return _reason("RAW_EVIDENCE_ABSENT")


def _market_audit(match: dict[str, Any], market_name: str) -> dict[str, Any]:
    market = match["market_radar"]["markets"][market_name]
    eligibility = market["eligibility"]
    observed = market.get("status") == "READY" and int(market.get("observation_count") or 0) > 0
    quote_age = market.get("quote_age_seconds")
    fresh = (
        observed
        and quote_age is not None
        and 0 <= int(quote_age) <= CANDIDATE_QUOTE_MAX_AGE_SECONDS
    )
    depth = int(market.get("bookmaker_count") or 0)
    depth_ready = depth >= MIN_BOOKMAKER_DEPTH
    quote_identity_ready = eligibility.get("candidate_quote_identity_status") == "READY"
    current_exact_quote_ready = quote_identity_ready and fresh and depth_ready
    model_ready = eligibility.get("candidate_model_status") == "READY"
    current_candidate_ready = current_exact_quote_ready and model_ready
    shadow = match["shadow_candidate"]
    ledger_selected = shadow.get("status") == "ACTIVE" and shadow.get("market") == market_name
    return {
        "market": market_name,
        "observation": {
            "reason": _reason("READY" if observed else "RAW_EVIDENCE_ABSENT"),
            "observation_count": int(market.get("observation_count") or 0),
            "snapshot_count": int(market.get("snapshot_count") or 0),
            "latest_snapshot_at": market.get("latest_snapshot_at"),
        },
        "freshness": {
            "reason": _reason("READY" if fresh else "STALE"),
            "quote_age_seconds": quote_age,
            "max_age_seconds": CANDIDATE_QUOTE_MAX_AGE_SECONDS,
            "authority": "w2.quote_freshness.v1",
        },
        "bookmaker_depth": {
            "reason": _reason("READY" if depth_ready else "UNDER_SAMPLED"),
            "bookmaker_count": depth,
            "minimum_existing_contract": MIN_BOOKMAKER_DEPTH,
        },
        "exact_executable_quote": {
            "reason": _reason(
                "READY"
                if current_exact_quote_ready
                else "STALE"
                if quote_identity_ready and not fresh
                else "UNDER_SAMPLED"
                if not depth_ready
                else "RAW_PRESENT_NOT_MATERIALIZED"
            ),
            "identity_status": eligibility.get("candidate_quote_identity_status"),
            "current_ready": current_exact_quote_ready,
        },
        "candidate_eligibility": {
            "reason": _reason(
                "READY"
                if current_candidate_ready
                else "STALE"
                if not fresh
                else "UNDER_SAMPLED"
                if not depth_ready
                else "RAW_PRESENT_NOT_MATERIALIZED"
            ),
            "current_ready": current_candidate_ready,
            "source_status": eligibility.get("candidate_eligibility_status"),
            "source_blockers": eligibility.get("blockers", []),
        },
        "immutable_forward_record": {
            "selected": ledger_selected,
            "status": shadow.get("status") if ledger_selected else "NOT_SELECTED",
            "captured_at": shadow.get("captured_at") if ledger_selected else None,
            "decision_hash": shadow.get("decision_hash") if ledger_selected else None,
            "note": "Historical forward facts are not reinterpreted by current quote age.",
        },
    }


def _factor_audit(
    match: dict[str, Any], db: dict[str, Any], meta: dict[str, Any]
) -> dict[str, Any]:
    xg_values = {
        key: db.get(key)
        for key in ("home_xg_for", "home_xg_against", "away_xg_for", "away_xg_against")
    }
    xg_ready = bool(db.get("xg_ready")) and all(value is not None for value in xg_values.values())
    rating_ready = bool(db.get("ratings_ready")) and all(
        db.get(key) is not None for key in ("home_elo", "away_elo")
    )
    value_ready = bool(db.get("squad_value_ready"))
    lineup_ready = (
        int(db.get("lineup_snapshot_count") or 0) > 0 or int(db.get("lineup_event_count") or 0) > 0
    )
    simulation_ready = db.get("simulation_status") == "READY" and xg_ready
    calibration = match["model_lab"]["w2_model"].get("calibration_status")
    xg_reason = {
        "READY": "READY",
        "INSUFFICIENT_HISTORY": "UNDER_SAMPLED",
        "PARTIAL_HISTORY": "UNDER_SAMPLED",
        "PROVIDER_EMPTY_OR_UNAVAILABLE": "PROVIDER_NOT_AVAILABLE",
    }.get(str(db.get("xg_status")), "RAW_PRESENT_NOT_MATERIALIZED")
    xg_first_break = {
        "READY": "READY",
        "INSUFFICIENT_HISTORY": "ROLLING_WINDOW_MIN_SAMPLE",
        "PARTIAL_HISTORY": "BILATERAL_ROLLING_WINDOW_COVERAGE",
        "PROVIDER_EMPTY_OR_UNAVAILABLE": "SAVED_RAW_STATISTICS_ABSENT_OR_XG_FIELD_EMPTY",
    }.get(str(db.get("xg_status")), "RAW_TO_XG_PROJECTION_NOT_READY")
    return {
        "xg_four_fields": {
            "reason": _reason(xg_reason),
            "ready": xg_ready,
            "source_status": db.get("xg_status"),
            "first_break": xg_first_break,
            "values": xg_values,
            "home_match_count": db.get("home_xg_match_count"),
            "away_match_count": db.get("away_xg_match_count"),
        },
        "rating_elo": {
            "reason": _reason("READY" if rating_ready else "RAW_PRESENT_NOT_MATERIALIZED"),
            "ready": rating_ready,
            "home": {"value": db.get("home_elo"), "source": db.get("home_rating_source")},
            "away": {"value": db.get("away_elo"), "source": db.get("away_rating_source")},
            "proxy_excluded": bool(db.get("proxy_elo_excluded")),
        },
        "team_value_asof": {
            "reason": _reason("READY" if value_ready else "RAW_PRESENT_NOT_MATERIALIZED"),
            "ready": value_ready,
            "raw_player_valuations_available": int(meta["player_valuation_rows"]),
            "materialized_artifacts": int(meta["team_value_rows"]),
        },
        "lineup": {
            "reason": _collection_reason(match.get("lineup_collection") or {}, lineup_ready),
            "ready": lineup_ready,
            "snapshot_count": int(db.get("lineup_snapshot_count") or 0),
            "event_count": int(db.get("lineup_event_count") or 0),
            "plans": db.get("lineup_plans", []),
        },
        "injuries": {"reason": _reason("POLICY_DISABLED"), "ready": False},
        "statistics": {"reason": _reason("POLICY_DISABLED"), "ready": False},
        "h2h": {
            "reason": _reason("READY" if db.get("h2h_ready") else "UNDER_SAMPLED"),
            "ready": bool(db.get("h2h_ready")),
        },
        "historical_settled_ah": {
            "reason": _reason("READY" if db.get("history_ready") else "RAW_EVIDENCE_ABSENT"),
            "ready": bool(db.get("history_ready")),
        },
        "simulation": {
            "reason": _reason("READY" if simulation_ready else xg_reason),
            "ready": simulation_ready,
            "status": db.get("simulation_status"),
            "simulations_completed": db.get("simulations_completed"),
        },
        "calibration": {
            "reason": _reason(
                "OWNER_DECISION_REQUIRED" if calibration == "BASELINE_PRIOR" else "READY"
            ),
            "status": calibration or "NOT_AVAILABLE",
        },
        "capability": {
            "reason": _reason(
                "READY" if db.get("capability_status") == "FORMAL_READY" else "POLICY_DISABLED"
            ),
            "status": db.get("capability_status"),
        },
    }


def _role_matrix() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "authority": {
            "factor_registry": "config/factors/factor_registry.v1.json",
            "simulation": "src/w2/models/simulate.py",
            "decision_v4": "src/w2/domain/recommendation_decision_v4.py",
            "formal": "src/w2/strategy/readiness.py",
        },
        "factors": {
            "xg_four_fields": {
                "simulation_role": "HARD_GATE",
                "analysis_factor_role": "ACTIVE_SCORING_F9",
                "candidate_role": "HARD_GATE_THROUGH_SIMULATION",
                "formal_role": "HARD_GATE_THROUGH_SIMULATION",
                "public_presentation_role": "MODEL_CORE_INPUT_READINESS",
            },
            "rating_elo": {
                "simulation_role": "OPTIONAL_CANONICAL_NON_PROXY_LAMBDA_ENHANCEMENT",
                "analysis_factor_role": "ACTIVE_SCORING_F7",
                "candidate_role": "ENHANCEMENT_NOT_HARD_GATE",
                "formal_role": "INDEPENDENT_SIGNAL_INPUT_NOT_SOLE_GATE",
                "public_presentation_role": "RATING_ENHANCEMENT_READINESS",
            },
            "team_value_asof": {
                "simulation_role": "OPTIONAL_LAMBDA_ENHANCEMENT",
                "analysis_factor_role": "ACTIVE_SCORING_F8",
                "candidate_role": "ENHANCEMENT_NOT_HARD_GATE",
                "formal_role": "F8_IDENTITY_VALUE_HARD_GATE",
                "public_presentation_role": "TEAM_VALUE_ENHANCEMENT_READINESS",
            },
            "lineup": {
                "simulation_role": "OPTIONAL_CURRENT_EXACT13",
                "analysis_factor_role": "F10_GATE_AND_EXPLANATION_NUMERIC_DISABLED",
                "candidate_role": "ADVISORY_CURRENT_EXACT13",
                "formal_role": "FIXTURE_AND_OFFLINE_EVIDENCE_REQUIRED",
                "public_presentation_role": "COLLECTION_WINDOW_AWARE",
            },
            "h2h": {
                "simulation_role": "NOT_A_HARD_GATE",
                "analysis_factor_role": "ACTIVE_SCORING_F6",
                "candidate_role": "DIAGNOSTIC_NOT_HARD_GATE",
                "formal_role": "INDEPENDENT_SIGNAL_INPUT",
                "public_presentation_role": "HISTORICAL_DIAGNOSTIC_SAMPLE",
            },
            "market_observation_freshness_depth_exact_quote": {
                "simulation_role": "NOT_A_SIMULATION_INPUT",
                "analysis_factor_role": "MARKET_DIAGNOSTIC_INPUT",
                "candidate_role": "PER_MARKET_HARD_GATES",
                "formal_role": "AH_FORMAL_MARKET_EVIDENCE_GATE_OU_FORMAL_DISABLED",
                "public_presentation_role": "RADAR_AND_EXACT_QUOTE_MUST_REMAIN_DISTINCT",
            },
            "injuries_statistics": {
                "simulation_role": "POLICY_DISABLED",
                "analysis_factor_role": "POLICY_DISABLED",
                "candidate_role": "NOT_A_CURRENT_GATE",
                "formal_role": "OWNER_AUTHORITY_REQUIRED_TO_ENABLE",
                "public_presentation_role": "POLICY_DISABLED",
            },
            "historical_settled_ah": {
                "simulation_role": "NOT_A_HARD_GATE",
                "analysis_factor_role": "F5_RECENT_AH_COVER",
                "candidate_role": "NOT_A_SHADOW_HARD_GATE",
                "formal_role": "F5_HARD_GATE",
                "public_presentation_role": "HISTORICAL_VALIDATION_EVIDENCE",
            },
            "calibration_capability": {
                "simulation_role": "SIMULATION_CAN_RUN_WITH_BASELINE_PRIOR",
                "analysis_factor_role": "DIAGNOSTIC_ONLY_WHEN_NOT_PROVEN",
                "candidate_role": "SHADOW_ANALYSIS_ALLOWED_BASELINE_PRIOR",
                "formal_role": "PROVEN_CAPABILITY_AND_OWNER_AUTHORITY_REQUIRED",
                "public_presentation_role": "PRIOR_ONLY_NOT_INCREMENTAL_ABILITY",
            },
        },
    }


def build_audit(
    workspace_documents: list[dict[str, Any]],
    db_rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> dict[str, Any]:
    matches = [match for document in workspace_documents for match in document.get("matches", [])]
    workspace_by_id = {str(match["fixture_id"]): match for match in matches}
    db_by_id = {str(row["fixture_id"]): row for row in db_rows}
    if len(workspace_by_id) != len(matches):
        raise ValueError("duplicate fixture_id in workspace evidence")
    if len(db_by_id) != len(db_rows):
        raise ValueError("duplicate fixture_id in DB evidence")
    if set(workspace_by_id) != set(db_by_id):
        raise ValueError("workspace and persisted T+7 fixture sets differ")
    competitions = {match["competition_id"] for match in matches}
    if not competitions <= REQUIRED_MATCHDAY_COMPETITIONS:
        raise ValueError(
            f"non-authorized competitions: {sorted(competitions - REQUIRED_MATCHDAY_COMPETITIONS)}"
        )

    fixtures = []
    for fixture_id in sorted(workspace_by_id, key=int):
        match = workspace_by_id[fixture_id]
        db = db_by_id[fixture_id]
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "competition_id": match["competition_id"],
                "kickoff_utc": match["kickoff_utc"],
                "teams": {
                    "home": match["home_team_name"],
                    "away": match["away_team_name"],
                    "identity_status": db.get("team_identity_status"),
                },
                "markets": {name: _market_audit(match, name) for name in MARKETS},
                "factors": _factor_audit(match, db, meta),
                "decision_v4": {
                    "outcome": db.get("decision_v4_outcome"),
                    "blockers": db.get("decision_v4_blockers", []),
                },
                "shadow_candidate": match["shadow_candidate"],
            }
        )

    market_rows = [market for fixture in fixtures for market in fixture["markets"].values()]
    summary = {
        "fixture_count": len(fixtures),
        "market_count": len(market_rows),
        "competition_count": len(competitions),
        "competitions": sorted(competitions),
        "xg_four_field_missing_fixtures": sum(
            not fixture["factors"]["xg_four_fields"]["ready"] for fixture in fixtures
        ),
        "market_stale_count": sum(
            market["freshness"]["reason"] == "STALE" for market in market_rows
        ),
        "bookmaker_depth_insufficient_count": sum(
            market["bookmaker_depth"]["reason"] == "UNDER_SAMPLED" for market in market_rows
        ),
        "exact_quote_not_ready_count": sum(
            not market["exact_executable_quote"]["current_ready"] for market in market_rows
        ),
        "simulation_not_ready_fixtures": sum(
            not fixture["factors"]["simulation"]["ready"] for fixture in fixtures
        ),
        "baseline_prior_fixtures": sum(
            fixture["factors"]["calibration"]["status"] == "BASELINE_PRIOR" for fixture in fixtures
        ),
        "rating_bilateral_ready_fixtures": sum(
            fixture["factors"]["rating_elo"]["ready"] for fixture in fixtures
        ),
        "team_value_bilateral_ready_fixtures": sum(
            fixture["factors"]["team_value_asof"]["ready"] for fixture in fixtures
        ),
        "lineup_ready_fixtures": sum(fixture["factors"]["lineup"]["ready"] for fixture in fixtures),
        "shadow_candidate_active": sum(
            fixture["shadow_candidate"]["status"] == "ACTIVE" for fixture in fixtures
        ),
        "decision_v4_outcomes": dict(
            sorted(Counter(fixture["decision_v4"]["outcome"] for fixture in fixtures).items())
        ),
        "decision_v4_blockers": dict(
            sorted(
                Counter(
                    blocker
                    for fixture in fixtures
                    for blocker in fixture["decision_v4"]["blockers"]
                ).items()
            )
        ),
    }
    generated_values = sorted(
        document.get("generated_at")
        for document in workspace_documents
        if document.get("generated_at")
    )
    evidence_as_of = max(generated_values) if generated_values else meta.get("captured_at")
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_generated_at": evidence_as_of,
        "evidence_as_of": evidence_as_of,
        "provider_calls_by_audit": 0,
        "business_writes_by_audit": 0,
        "set_reconciliation": {
            "persisted_t_plus_7": len(db_rows),
            "dashboard_visible": len(matches),
            "shadow_scan_input": len(matches),
            "sets_equal": True,
            "exact_13_only": True,
        },
        "summary": summary,
        "fixtures": fixtures,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_outputs(output_dir: Path, audit: dict[str, Any], meta: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fixtures = audit["fixtures"]
    _write_json(output_dir / "SC21_STAGE14_FACTOR_COVERAGE_MATRIX_V2.json", audit)
    _write_json(
        output_dir / "SC21_FUTURE_FIXTURE_FACTOR_TRACE.json",
        {
            "schema_version": SCHEMA_VERSION,
            "evidence_as_of": audit["evidence_as_of"],
            "traces": fixtures,
        },
    )
    _write_json(output_dir / "SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json", _role_matrix())
    _write_json(
        output_dir / "SC21_CANDIDATE_BLOCKER_DECOMPOSITION.json",
        {
            "schema_version": SCHEMA_VERSION,
            "summary": audit["summary"],
            "fixtures": [
                {
                    "fixture_id": fixture["fixture_id"],
                    "markets": fixture["markets"],
                    "decision_v4": fixture["decision_v4"],
                    "shadow_candidate": fixture["shadow_candidate"],
                }
                for fixture in fixtures
            ],
        },
    )
    summary = audit["summary"]
    fixtures = summary["fixture_count"]
    markets = summary["market_count"]
    report = "\n".join(
        [
            "# SC21 Stage14 Factor Coverage Audit V2",
            "",
            "## Evidence boundary",
            "",
            f"- Evidence as-of: `{audit['evidence_as_of']}`",
            "- Provider calls by audit: `0`",
            "- Business writes by audit: `0`",
            f"- Exact-13 persisted T+7 / Dashboard / Shadow scan sets: "
            f"`{fixtures}` / `{fixtures}` / `{fixtures}` (equal)",
            f"- Player valuation source rows observed: `{meta['player_valuation_rows']}`",
            "",
            "## Current truth",
            "",
            f"- Four-field xG missing fixtures: "
            f"**{summary['xg_four_field_missing_fixtures']} / {fixtures}**",
            f"- Stale markets at audit time: **{summary['market_stale_count']} / {markets}**",
            f"- Insufficient bookmaker-depth markets: "
            f"**{summary['bookmaker_depth_insufficient_count']} / {markets}**",
            f"- Current exact quote not ready: "
            f"**{summary['exact_quote_not_ready_count']} / {markets}**",
            f"- Simulation not ready: **{summary['simulation_not_ready_fixtures']} / {fixtures}**",
            f"- Baseline-prior simulations: **{summary['baseline_prior_fixtures']} / {fixtures}**",
            f"- Bilateral Rating ready: "
            f"**{summary['rating_bilateral_ready_fixtures']} / {fixtures}**",
            f"- Bilateral TeamValueAsOf ready: "
            f"**{summary['team_value_bilateral_ready_fixtures']} / {fixtures}**",
            f"- Lineup ready: **{summary['lineup_ready_fixtures']} / {fixtures}**",
            "- Shadow Candidate ACTIVE (immutable forward records): "
            f"**{summary['shadow_candidate_active']} / {fixtures}**",
            "",
            "## Interpretation",
            "",
            "The current market audit and an already-written forward record are separate facts. "
            "A quote that is stale now does not rewrite an earlier valid Shadow decision. "
            "AH and OU are audited independently at `fixture × market` grain. "
            "Radar evidence is never treated as an executable quote.",
            "",
            "Calibration `BASELINE_PRIOR` permits Shadow analysis but does not prove "
            "incremental ability and cannot open Formal authority. Injuries and Statistics "
            "remain policy-disabled. No threshold, cadence, allowlist, model, or historical "
            "ledger record was changed by this audit.",
            "",
        ]
    )
    (output_dir / "SC21_STAGE14_FACTOR_COVERAGE_REPORT_V2.md").write_text(report, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-dir", type=Path, required=True)
    parser.add_argument("--db-fixtures", type=Path, required=True)
    parser.add_argument("--db-meta", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    workspace_documents = [_load_json(path) for path in sorted(args.workspace_dir.glob("*.json"))]
    audit = build_audit(
        workspace_documents, _load_jsonl(args.db_fixtures), _load_json(args.db_meta)
    )
    write_outputs(args.output_dir, audit, _load_json(args.db_meta))
    print(json.dumps(audit["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
