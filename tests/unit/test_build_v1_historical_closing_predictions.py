from __future__ import annotations

import json
from pathlib import Path

from scripts.build_v1_historical_closing_predictions import _lambdas, build
from scripts.fit_v1_ah_component_share_calibration import _lambdas as development_lambdas

HEADER = "Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,AHCh,PCAHH,PCAHA,PC>2.5,PC<2.5\n"


def test_fixed_blindtest_arms_match_frozen_development_formulas() -> None:
    values = {"home_for": 1.7, "home_against": 1.1, "away_for": 1.2, "away_against": 1.5}
    parameters = (0.208545, 0.663475, -0.112027)

    for arm, reference_arm, reference_parameters in (
        ("production", "production_current", None),
        ("totals_candidate", "totals_only", None),
        ("ah_candidate", "candidate", parameters),
    ):
        reference = development_lambdas(values, reference_arm, reference_parameters)
        assert _lambdas(values, arm) == (round(reference[0], 6), round(reference[1], 6))


def test_build_uses_only_strictly_earlier_xg_and_ignores_result_columns(tmp_path: Path) -> None:
    fixtures = []
    xg_rows = []
    market_rows = []
    for index in range(6):
        day = 1 + index * 4
        fixture_id = str(100 + index)
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "competition": "premier_league",
                "season": "2023",
                "status": "FT",
                "kickoff_at": f"2023-09-{day:02d}T14:00:00+00:00",
                "home_team_id": "1",
                "away_team_id": "2",
                "home_team_name": "Home FC",
                "away_team_name": "Away FC",
            }
        )
        xg_rows.append(
            {
                **fixtures[-1],
                "home_xg": 99.0 if index == 5 else float(index + 1),
                "away_xg": 1.0,
                "status": "COMPLETE",
            }
        )
        market_rows.append(
            f"{day:02d}/09/2023,15:00,Home FC,Away FC,99,98,-0.25,1.95,1.95,1.90,2.00"
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"competitions": {"premier_league": {"fixtures": fixtures}}}),
        encoding="utf-8",
    )
    xg = tmp_path / "xg.jsonl"
    xg.write_text("\n".join(json.dumps(row) for row in xg_rows) + "\n", encoding="utf-8")
    root = tmp_path / "football-data"
    folder = root / "extracted" / "2324"
    folder.mkdir(parents=True)
    for file_name in ("E0", "SP1", "D1", "I1", "F1"):
        content = HEADER + ("\n".join(market_rows) + "\n" if file_name == "E0" else "")
        (folder / f"{file_name}.csv").write_text(content, encoding="latin1")

    payload = build(manifest, xg, root)

    assert payload["fixture_count"] == 1
    assert payload["result_columns_read"] == []
    assert payload["predictions"][0]["fixture_id"] == "105"
    assert payload["predictions"][0]["pit_xg"]["home_for"] == 3.0
    assert "99" not in json.dumps(payload["predictions"][0]["pit_xg"])
