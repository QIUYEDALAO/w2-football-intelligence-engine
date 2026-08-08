from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.debug_w2_formal_eligibility import build_audit, render_markdown_summary


def _match(
    home: str,
    away: str,
    *,
    fixture_id: str,
    blockers: list[str] | None = None,
    formal_suppressed_reason: str | None = None,
    signal_count: int = 4,
    market_ah: float | None = -1.5,
    canonical_status: str = "READY",
    canonical_blocker: str | None = None,
    fair_ah: float | None = -0.75,
    edge_ah: float | None = -0.75,
    recommendation: dict[str, object] | None = None,
) -> dict[str, object]:
    recommendation = recommendation or {
        "tier": "ANALYSIS_PICK",
        "market": "TOTALS",
        "selection": "OVER",
        "line": "1",
        "odds": "1.94",
    }
    return {
        "fixture_id": fixture_id,
        "home_team_name": home,
        "away_team_name": away,
        "kickoff_utc": "2026-07-02T00:00:00Z",
        "formal_recommendation": False,
        "formal_suppressed_reason": formal_suppressed_reason,
        "recommendation": recommendation,
        "current_odds": {
            "ah": {
                "display_line_cn": "主队 -1.5",
                "home_line": str(market_ah) if market_ah is not None else None,
                "away_line": str(-market_ah) if market_ah is not None else None,
                "line": str(abs(market_ah)) if market_ah is not None else None,
            },
        },
        "pricing_shadow": {
            "status": "SIMULATION_READY",
            "independent_signal_count": signal_count,
            "missing_independent_sources": ["h2h"],
            "calibration_version": "w2.formal.lambda_baseline_prior.v1",
            "fair_ah": fair_ah,
            "market_ah": market_ah,
            "edge_ah": edge_ah,
            "formal_eligible": False,
            "formal_blockers": blockers or [],
            "canonical_ah_market_validation_status": canonical_status,
            "canonical_ah_market_blocker": canonical_blocker,
            "simulation_status": "READY",
            "simulation": {
                "calibration_version": "w2.formal.lambda_baseline_prior.v1",
            },
        },
        "scoreline_reference": {"direction_top3": []},
        "market_timeline": {"status": "READY"},
    }


def _payload(rows: list[dict[str, object]]) -> dict[str, object]:
    return {"generated_at": "2026-07-02T00:00:00Z", "all": rows}


def test_audit_extracts_required_records_and_classifies_payload_missing() -> None:
    audit = build_audit(
        _payload(
            [
                _match(
                    "England",
                    "Congo DR",
                    fixture_id="1567307",
                    blockers=["FIXTURE_NOT_PREMATCH"],
                    formal_suppressed_reason="FIXTURE_STARTED_NO_PREMATCH_FORMAL",
                ),
                _match(
                    "Belgium",
                    "Senegal",
                    fixture_id="1567308",
                    blockers=["W2_FORMAL_RECOMMENDATION_ENABLED=false"],
                    market_ah=0.0,
                    fair_ah=-0.25,
                    edge_ah=0.25,
                    recommendation={
                        "tier": "ANALYSIS_PICK",
                        "market": "FIRST_HALF_GOALS",
                        "selection": "1H_OVER",
                    },
                ),
                _match(
                    "USA",
                    "Bosnia & Herzegovina",
                    fixture_id="1562586",
                    blockers=["W2_FORMAL_RECOMMENDATION_ENABLED=false"],
                    market_ah=-1.25,
                    edge_ah=-0.5,
                ),
            ],
        ),
    )

    assert audit["summary"]["audited_count"] == 3
    assert audit["summary"]["category_counts"] == {"D": 3}
    assert audit["summary"]["provider_calls"] == 0
    first = audit["records"][0]
    assert first["fixture_id"] == "1567307"
    assert first["pricing_shadow.status"] == "SIMULATION_READY"
    assert first["independent_signal_count"] == 4
    assert first["current_odds.ah.display_line_cn"] == "主队 -1.5"
    assert first["formal_result"]["formal_eligible"] is False
    assert first["formal_result"]["recommendation"] is None
    assert first["formal_result"]["blockers"] == ["FIXTURE_NOT_PREMATCH"]
    assert first["root_cause_category"]["code"] == "D"


def test_audit_classifies_independent_signal_market_ev_and_s1_causes() -> None:
    rows = [
        _match("England", "Congo DR", fixture_id="a", signal_count=2),
        _match(
            "Belgium",
            "Senegal",
            fixture_id="b",
            canonical_status="BLOCKED",
            canonical_blocker="AH_MAINLINE_AMBIGUOUS",
        ),
        _match(
            "USA",
            "Bosnia & Herzegovina",
            fixture_id="c",
            blockers=["AH_EV_BELOW_FORMAL_THRESHOLD"],
        ),
    ]
    audit = build_audit(_payload(rows))

    assert [row["root_cause_category"]["code"] for row in audit["records"]] == [
        "A",
        "B",
        "C",
    ]


def test_audit_classifies_s1_when_fair_ah_or_settlement_is_missing() -> None:
    audit = build_audit(
        _payload(
            [
                _match(
                    "England",
                    "Congo DR",
                    fixture_id="a",
                    fair_ah=None,
                    blockers=["MISSING_AH_SETTLEMENT_DISTRIBUTION"],
                    recommendation={
                        "tier": "FORMAL",
                        "market": "ASIAN_HANDICAP",
                        "selection": "HOME_AH",
                        "line": "-1.5",
                    },
                ),
                _match("Belgium", "Senegal", fixture_id="b", blockers=[]),
                _match("USA", "Bosnia & Herzegovina", fixture_id="c", blockers=[]),
            ],
        ),
    )

    assert audit["records"][0]["root_cause_category"]["code"] == "E"


def test_markdown_summary_contains_required_chain_fields() -> None:
    row = build_audit(
        _payload(
            [
                _match("England", "Congo DR", fixture_id="1567307"),
                _match("Belgium", "Senegal", fixture_id="1567308"),
                _match("USA", "Bosnia & Herzegovina", fixture_id="1562586"),
            ],
        ),
    )["records"][0]
    markdown = render_markdown_summary([row])

    assert "# W2 Formal Eligibility Root Cause Audit" in markdown
    assert "fixture_id: 1567307" in markdown
    assert "formal_result:" in markdown
    assert "direction_top3:" in markdown
    assert "market_timeline.status:" in markdown


def test_cli_reads_input_and_emits_json(tmp_path: Path) -> None:
    payload_path = tmp_path / "dashboard.json"
    payload_path.write_text(
        json.dumps(
            _payload(
                [
                    _match("England", "Congo DR", fixture_id="1567307"),
                    _match("Belgium", "Senegal", fixture_id="1567308"),
                    _match("USA", "Bosnia & Herzegovina", fixture_id="1562586"),
                ],
            ),
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/debug_w2_formal_eligibility.py",
            "--input",
            str(payload_path),
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    audit = json.loads(result.stdout)
    assert audit["summary"]["audited_count"] == 3
    assert audit["markdown_summary"].startswith("# W2 Formal Eligibility Root Cause Audit")
