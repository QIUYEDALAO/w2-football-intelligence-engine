from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_handicap_walkforward_dry_run_outputs_wave1_json() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_w2_handicap_walkforward.py", "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["samples"] == 0
    assert payload["n_min"] == 200
    assert payload["beats_market"] is False
    assert payload["reason"] == "INSUFFICIENT_VALIDATED_SAMPLES"
    assert payload["report_type"] == "S2_VALIDATION_READINESS_DRY_RUN"
    assert payload["gate"]["beats_market"] is False
    assert payload["gate"]["gate_checks"] == {
        "sample_minimum": False,
        "devig_market_advantage": False,
        "time_split": False,
        "holdout_replication": False,
        "forward_shadow": False,
    }
    assert payload["settlement_policy"] == {
        "market_snapshot": "AS_OF_LOCKED_MARKET_SNAPSHOT_REQUIRED",
        "devig_method": "REQUIRED_FOR_MARKET_BASELINE",
        "asian_handicap_outcomes": [
            "WIN",
            "HALF_WIN",
            "PUSH",
            "HALF_LOSS",
            "LOSS",
            "VOID",
        ],
        "push_counts_as_win": False,
        "void_included_in_sample": False,
    }


def test_handicap_walkforward_demo_artifacts_are_non_authoritative(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_handicap_walkforward.py",
            "--features-jsonl",
            "fixtures/stage5_demo/international/v1/features.jsonl",
            "--labels-jsonl",
            "fixtures/stage5_demo/international/v1/labels.jsonl",
            "--authoritative",
            "--output-report",
            str(report_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload == written
    assert payload["data_source"].endswith("fixtures/stage5_demo/international/v1/labels.jsonl")
    assert payload["authoritative"] is False
    assert payload["samples"] == 0
    assert payload["feature_row_count"] == 4
    assert payload["label_row_count"] == 4
    assert "DEMO_DATA_NOT_AUTHORITATIVE" in payload["blockers"]
    assert "SYNTHETIC_DATA_NOT_AUTHORITATIVE" in payload["blockers"]
    assert payload["beats_market"] is False
    assert payload["dashboard_publishable"] is False
    assert payload["card_publishable"] is False

    check = subprocess.run(
        [sys.executable, "scripts/check_w2_s2_readiness.py", str(report_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "s2 readiness report PASS" in check.stdout


def test_handicap_walkforward_authoritative_artifact_can_emit_evidence(tmp_path: Path) -> None:
    features = tmp_path / "features.jsonl"
    labels = tmp_path / "labels.jsonl"
    features.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "fixture_id": "real-1",
                        "season": "2025",
                        "odds_snapshot": {"markets": ["ASIAN_HANDICAP"]},
                        "provenance": {"synthetic": False},
                    },
                ),
                json.dumps(
                    {
                        "fixture_id": "real-2",
                        "season": "2025",
                        "odds_snapshot": {"markets": ["TOTALS"]},
                        "provenance": {"synthetic": False},
                    },
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    labels.write_text(
        json.dumps({"fixture_id": "real-1", "result_status": "FINAL"})
        + "\n"
        + json.dumps({"fixture_id": "real-2", "result_status": "FINAL"})
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_handicap_walkforward.py",
            "--features-jsonl",
            str(features),
            "--labels-jsonl",
            str(labels),
            "--data-source",
            "real-season-asof-test",
            "--authoritative",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["data_source"] == "real-season-asof-test"
    assert payload["authoritative"] is True
    assert payload["samples"] == 1
    assert payload["gate"]["covered_settled_sample"] == 1
    assert payload["gate"]["beats_market"] is False
    assert payload["beats_market"] is False
