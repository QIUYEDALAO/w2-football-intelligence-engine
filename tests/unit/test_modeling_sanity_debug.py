from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.debug_w2_modeling_sanity import build_modeling_sanity_audit


def _payload() -> dict[str, object]:
    return {
        "selected_football_day": "2026-07-02",
        "generated_at": "2026-07-02T03:00:00Z",
        "all": [
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": "2026-07-02T20:00:00Z",
                "home_team_name": "France",
                "away_team_name": "Sweden",
                "formal_recommendation": False,
                "pricing_shadow": {
                    "fair_ah": -0.25,
                    "simulation": {
                        "status": "READY",
                        "lambda_home": 1.2,
                        "lambda_away": 1.2,
                        "calibration": {
                            "params": {"applied_home_advantage_goals": 0.0}
                        },
                        "input_readiness": {
                            "neutral_site": True,
                            "home_advantage_applied": False,
                            "proxy_elo_excluded": True,
                            "elo_ready": False,
                            "raw_ratings_ready": True,
                            "xg_ready": True,
                            "xg_status": "READY",
                        },
                    },
                },
            }
        ],
    }


def test_modeling_sanity_audit_exposes_neutral_and_proxy_elo_fields() -> None:
    audit = build_modeling_sanity_audit(_payload())

    assert audit["status"] == "PASS"
    assert audit["provider_calls"] == 0
    assert audit["db_writes"] == 0
    assert audit["summary"]["neutral_site_count"] == 1
    assert audit["summary"]["proxy_elo_excluded_count"] == 1
    row = audit["rows"][0]
    assert row["neutral_site"] is True
    assert row["home_advantage_applied"] is False
    assert row["applied_home_advantage_goals"] == 0.0
    assert row["proxy_elo_excluded"] is True


def test_debug_w2_modeling_sanity_cli_reads_input_file(tmp_path: Path) -> None:
    payload_path = tmp_path / "dashboard.json"
    payload_path.write_text(json.dumps(_payload()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/debug_w2_modeling_sanity.py",
            "--input",
            str(payload_path),
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(result.stdout)

    assert output["status"] == "PASS"
    assert output["summary"]["rows"] == 1
    assert output["rows"][0]["proxy_elo_excluded"] is True
