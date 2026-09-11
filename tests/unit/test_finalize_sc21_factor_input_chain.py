from __future__ import annotations

from scripts.finalize_sc21_factor_input_chain import build_acceptance


def test_acceptance_keeps_markets_independent() -> None:
    market = {
        "observation": {"reason": "READY"},
        "freshness": {"reason": "READY"},
        "bookmaker_depth": {"reason": "READY"},
        "exact_executable_quote": {"current_ready": True},
        "immutable_forward_record": {"selected": False},
    }
    blocked = {**market, "freshness": {"reason": "STALE"}}
    payload = {
        "evidence_as_of": "2026-08-14T00:00:00Z",
        "traces": [
            {
                "fixture_id": "f-1",
                "competition_id": "allsvenskan",
                "factors": {
                    "xg_four_fields": {"ready": True},
                    "simulation": {"ready": True},
                    "calibration": {"status": "BASELINE_PRIOR"},
                    "capability": {"status": "ANALYSIS_ONLY"},
                },
                "decision_v4": {"outcome": "ANALYSIS_PICK", "blockers": []},
                "markets": {"ASIAN_HANDICAP": market, "TOTALS": blocked},
            }
        ],
    }

    result = build_acceptance(payload)

    assert [row["current_status"] for row in result["market_rows"]] == [
        "READY",
        "NOT_READY",
    ]
    assert result["fixture_aggregate"] == [{"fixture_id": "f-1", "status": "PARTIAL"}]
