from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_export_w2_audit_tables_cli_writes_four_tables(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-07-01T01:00:00Z",
        "selected_football_day": "2026-07-01",
        "all": [
            {
                "fixture_id": "fixture-1",
                "home_team_name": "Home",
                "away_team_name": "Away",
                "recommendation": {"tier": "WATCH"},
                "pricing_shadow": {"market_ah": 0},
                "market_timeline": {"status": "INSUFFICIENT"},
            }
        ],
    }
    input_path = tmp_path / "dashboard.json"
    output_dir = tmp_path / "audit"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_w2_audit_tables.py",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--format",
            "csv",
            "--no-db",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    summary = json.loads(result.stderr)
    assert summary["status"] == "PASS"
    assert summary["provider_calls"] == 0
    assert summary["db_writes"] == 0
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "prematch_recommendations.csv").exists()
    assert (output_dir / "market_timeline_snapshots.csv").exists()
    assert (output_dir / "locked_recommendation_snapshots.csv").exists()
    assert (output_dir / "settlement_history.csv").exists()
