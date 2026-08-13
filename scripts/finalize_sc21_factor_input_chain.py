#!/usr/bin/env python3
"""Build deterministic SC21 before/after and candidate-chain acceptance artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_acceptance(trace: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    aggregates: list[dict[str, Any]] = []
    for fixture in trace["traces"]:
        market_results = []
        xg = fixture["factors"]["xg_four_fields"]
        simulation = fixture["factors"]["simulation"]
        calibration = fixture["factors"]["calibration"]
        capability = fixture["factors"]["capability"]
        decision = fixture["decision_v4"]
        blockers = set(decision["blockers"])
        manifest_ready = (
            not {
                "MISSING_MODEL_INPUT_MANIFEST_HASH",
                "INVALID_MODEL_INPUT_MANIFEST_HASH",
            }
            & blockers
        )
        settlement_ready = (
            not {
                "MISSING_SETTLEMENT_DISTRIBUTION",
                "INVALID_SETTLEMENT_DISTRIBUTION",
            }
            & blockers
        )
        for name in ("ASIAN_HANDICAP", "TOTALS"):
            market = fixture["markets"][name]
            checks = {
                "market_observation": market["observation"]["reason"] == "READY",
                "market_freshness": market["freshness"]["reason"] == "READY",
                "bookmaker_depth": market["bookmaker_depth"]["reason"] == "READY",
                "exact_executable_quote": market["exact_executable_quote"]["current_ready"],
                "xg_four_fields": bool(xg["ready"]),
                "simulation": bool(simulation["ready"]),
                "calibration_status_explicit": bool(calibration["status"]),
                "capability_status_explicit": bool(capability["status"]),
                "model_input_manifest": manifest_ready,
                "five_state_settlement_distribution": settlement_ready,
                "recommendation_decision_v4": decision["outcome"]
                in {
                    "ANALYSIS_PICK",
                    "NO_EDGE",
                },
            }
            current_ready = all(checks.values())
            immutable = market["immutable_forward_record"]
            rows.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "competition_id": fixture["competition_id"],
                    "market": name,
                    "checks": checks,
                    "current_status": "READY" if current_ready else "NOT_READY",
                    "failed_checks": sorted(key for key, ready in checks.items() if not ready),
                    "immutable_forward_record": immutable,
                    "decision_v4_outcome": decision["outcome"],
                    "decision_v4_blockers": decision["blockers"],
                }
            )
            market_results.append(current_ready)
        aggregates.append(
            {
                "fixture_id": fixture["fixture_id"],
                "status": (
                    "READY"
                    if all(market_results)
                    else "PARTIAL"
                    if any(market_results)
                    else "NOT_READY"
                ),
            }
        )
    return {
        "schema_version": "w2.sc21-shadow-candidate-chain-acceptance.v1",
        "evidence_as_of": trace["evidence_as_of"],
        "provider_calls": 0,
        "database_writes": 0,
        "market_rows": rows,
        "fixture_aggregate": aggregates,
        "summary": {
            "fixture_count": len(aggregates),
            "market_count": len(rows),
            "current_market_ready": sum(row["current_status"] == "READY" for row in rows),
            "fixture_ready": sum(row["status"] == "READY" for row in aggregates),
            "fixture_partial": sum(row["status"] == "PARTIAL" for row in aggregates),
            "immutable_shadow_candidate_records": sum(
                bool(row["immutable_forward_record"]["selected"]) for row in rows
            ),
        },
    }


def build_before_after(
    trace: dict[str, Any],
    materialization: dict[str, Any],
    xg_dry_run: dict[str, Any],
) -> dict[str, Any]:
    fixtures = trace["traces"]
    markets = [market for fixture in fixtures for market in fixture["markets"].values()]
    base = {
        "fixture_count": len(fixtures),
        "xg_four_field_ready": sum(f["factors"]["xg_four_fields"]["ready"] for f in fixtures),
        "simulation_ready": sum(f["factors"]["simulation"]["ready"] for f in fixtures),
        "rating_bilateral_ready": materialization["rating"]["future_fixture_bilateral_coverage"],
        "team_value_bilateral_ready": sum(
            f["factors"]["team_value_asof"]["ready"] for f in fixtures
        ),
        "due_lineup_ready": sum(f["factors"]["lineup"]["ready"] for f in fixtures),
        "ah_current_market_ready": sum(
            f["markets"]["ASIAN_HANDICAP"]["freshness"]["reason"] == "READY" for f in fixtures
        ),
        "ou_current_market_ready": sum(
            f["markets"]["TOTALS"]["freshness"]["reason"] == "READY" for f in fixtures
        ),
        "ah_exact_quote_ready": sum(
            f["markets"]["ASIAN_HANDICAP"]["exact_executable_quote"]["current_ready"]
            for f in fixtures
        ),
        "ou_exact_quote_ready": sum(
            f["markets"]["TOTALS"]["exact_executable_quote"]["current_ready"] for f in fixtures
        ),
        "market_depth_ready": sum(m["bookmaker_depth"]["reason"] == "READY" for m in markets),
        "immutable_shadow_candidate_active": sum(
            f["shadow_candidate"]["status"] == "ACTIVE" for f in fixtures
        ),
    }
    after = dict(base)
    after["xg_saved_raw_would_insert_matches"] = int(
        xg_dry_run.get("team_xg_match_rows_would_insert") or 0
    )
    after["xg_saved_raw_would_upsert_rolling_snapshots"] = int(
        xg_dry_run.get("rolling_snapshot_rows_would_upsert") or 0
    )
    after["rating_new_snapshot_candidates"] = materialization["rating"][
        "new_snapshot_candidate_count"
    ]
    after["team_value_expected_artifacts"] = materialization["team_value"][
        "expected_artifact_count"
    ]
    return {
        "schema_version": "w2.sc21-before-after-coverage.v1",
        "evidence_as_of": trace["evidence_as_of"],
        "provider_calls": 0,
        "database_writes": 0,
        "before": base,
        "after_saved_raw_dry_run": after,
        "interpretation": (
            "Saved-raw xG, Rating and TeamValue dry-runs do not increase current T+7 "
            "readiness. Existing forward records remain immutable."
        ),
    }


def report_markdown(
    trace: dict[str, Any],
    blockers: dict[str, Any],
    materialization: dict[str, Any],
    before_after: dict[str, Any],
    acceptance: dict[str, Any],
) -> str:
    summary = blockers["summary"]
    before = before_after["before"]
    lineup_reasons = Counter(f["factors"]["lineup"]["reason"] for f in trace["traces"])
    fixtures = before["fixture_count"]
    markets = summary["market_count"]
    return "\n".join(
        [
            "# SC21 Factor Input Chain Final Report",
            "",
            f"- Evidence as-of: `{trace['evidence_as_of']}`",
            f"- Exact-13 T+7 fixtures: `{summary['fixture_count']}`",
            "- Provider calls by SC21 audit/materialization: `0`",
            "- Business writes before guarded materialization: `0`",
            "- Candidate mode: `SHADOW_ONLY`",
            "- Formal / Lock / Production / Round 4: `OFF / OFF / OFF / NOT_STARTED`",
            "",
            "## Coverage truth",
            "",
            f"- Four-field xG READY: `{before['xg_four_field_ready']}/{fixtures}`",
            f"- Simulation READY: `{before['simulation_ready']}/{fixtures}`",
            f"- Rating bilateral READY: `{before['rating_bilateral_ready']}/{fixtures}`",
            f"- TeamValueAsOf bilateral READY: `{before['team_value_bilateral_ready']}/{fixtures}`",
            f"- Lineup READY: `{before['due_lineup_ready']}/{fixtures}`",
            f"- Lineup causes: `{dict(sorted(lineup_reasons.items()))}`",
            f"- Market stale: `{summary['market_stale_count']}/{markets}`",
            f"- Bookmaker depth insufficient: "
            f"`{summary['bookmaker_depth_insufficient_count']}/{markets}`",
            f"- Current exact quote not ready: "
            f"`{summary['exact_quote_not_ready_count']}/{markets}`",
            f"- BASELINE_PRIOR: `{summary['baseline_prior_fixtures']}` fixtures",
            f"- Immutable Shadow candidates: `{summary['shadow_candidate_active']}`",
            "- Current fully-ready market chains: "
            f"`{acceptance['summary']['current_market_ready']}`",
            "",
            "## Materialization findings",
            "",
            f"- Rating snapshots: `{materialization['rating']['existing_snapshot_count']}`; "
            f"new candidates: `{materialization['rating']['new_snapshot_candidate_count']}`.",
            "- Rating source is canonical match history and excludes rolling xG proxy; "
            "there is no automatic result-to-Elo refresh consumer.",
            f"- Player valuations: `{materialization['team_value']['player_valuation_rows']}`; "
            f"registered rosters: `{materialization['team_value']['registered_roster_rows']}`; "
            f"TeamValue artifacts: `{materialization['team_value']['team_value_artifact_rows']}`.",
            "- TeamValue remains fail-closed pending reviewed as-of roster evidence.",
            "- Saved-raw xG dry-run found no new true-xG rows for current T+7; Statistics "
            "remains policy-disabled pending Owner decision.",
            "",
            "## Authority and safety",
            "",
            "AH and OU are audited independently at fixture × market scope. Radar medians "
            "are not executable quotes. Current quote age does not rewrite historical "
            "forward records. No threshold, cadence, whitelist, model, Decision V4, "
            "Candidate, Formal, Lock or Production policy was relaxed.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--blockers", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--xg-dry-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    trace = _load(args.trace)
    blockers = _load(args.blockers)
    materialization = _load(args.materialization)
    xg_dry_run = _load(args.xg_dry_run)
    acceptance = build_acceptance(trace)
    before_after = build_before_after(trace, materialization, xg_dry_run)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("SC21_BEFORE_AFTER_COVERAGE.json", before_after),
        ("SC21_SHADOW_CANDIDATE_CHAIN_ACCEPTANCE.json", acceptance),
    ):
        (args.output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (args.output_dir / "SC21_FACTOR_INPUT_CHAIN_FINAL_REPORT.md").write_text(
        report_markdown(trace, blockers, materialization, before_after, acceptance),
        encoding="utf-8",
    )
    print(json.dumps(acceptance["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
