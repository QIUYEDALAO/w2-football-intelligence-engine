from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_w2_r1_1_checkpoint_dry_run import build_checkpoint_report


def test_r1_1_checkpoint_no_samples_accumulates_without_numeric_conclusion(
    tmp_path: Path,
) -> None:
    payload = build_checkpoint_report(tmp_path)

    assert payload["readiness_status"] == "NO_EVIDENCE_SOURCE"
    assert payload["evidence_source"] == "NONE"
    assert payload["double_snapshot_card_count"] == 0
    assert payload["shadow_nonempty_rate"] == "ACCUMULATING"
    assert payload["clv_shadow_sample_count"] == 0
    assert payload["clv_shadow_median"] == "ACCUMULATING"
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["direction_allowed_changed"] is False
    assert "STAGING_EVIDENCE_SNAPSHOT_NOT_PROVIDED" in payload["blockers"]


def test_r1_1_checkpoint_below_threshold_is_not_enough_sample(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _capture("fixture-1", "2026-07-07T00:00:00Z", "R4_1_CALIBRATED"),
            _capture("fixture-1", "2026-07-07T23:00:00Z", "R4_1_CALIBRATED"),
            _outcome("fixture-1", "WIN", "FT"),
        ],
    )

    payload = build_checkpoint_report(tmp_path, min_double_snapshot_cards=2)

    assert payload["readiness_status"] == "NOT_ENOUGH_SAMPLE"
    assert payload["double_snapshot_card_count"] == 1
    assert payload["clv_shadow_sample_count"] == 1
    assert payload["clv_shadow_median"] == -0.1
    assert "DOUBLE_SNAPSHOT_CARD_COUNT_BELOW_THRESHOLD" in payload["blockers"]
    assert "CLV_SHADOW_SAMPLE_COUNT_BELOW_THRESHOLD" in payload["blockers"]


def test_r1_1_checkpoint_splits_ft_aet_pen_outcomes(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _outcome("fixture-ft", "WIN", "FT"),
            _outcome("fixture-aet", "PUSH", "AET"),
            _outcome("fixture-pen", "LOSS", "PEN"),
        ],
    )

    payload = build_checkpoint_report(tmp_path)

    assert payload["outcome_count_ft"] == 1
    assert payload["outcome_count_aet"] == 1
    assert payload["outcome_count_pen"] == 1


def test_r1_1_checkpoint_reports_model_family_and_artifact_provenance(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _capture("fixture-csl", "2026-07-07T00:00:00Z", "R4_1_CALIBRATED"),
            _capture("fixture-pl", "2026-07-07T00:00:00Z", "FITTED_CALIBRATED"),
        ],
    )

    payload = build_checkpoint_report(tmp_path)

    assert payload["model_family_distribution"] == {
        "FITTED_CALIBRATED": 1,
        "R4_1_CALIBRATED": 1,
    }
    assert payload["r4_1_artifact_provenance_distribution"] == {
        "v1|artifact-fixture-csl|2025-12-08T20:00:00Z": 1
    }
    assert payload["direction_allowed_candidate_leagues"][0]["competition_id"] == "eliteserien"
    assert all(
        item["direction_allowed_changed"] is False
        for item in payload["direction_allowed_candidate_leagues"]
    )


def test_r1_1_checkpoint_uses_sanitized_staging_provider_usage(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [_capture("fixture-1", "2026-07-07T00:00:00Z", "FITTED_CALIBRATED")],
    )
    (tmp_path / "evidence_snapshot.json").write_text(
        json.dumps(
            {
                "source_sha": "staging-sha",
                "provider_daily_calls": {"2026-07-07": 117},
            }
        ),
        encoding="utf-8",
    )

    payload = build_checkpoint_report(tmp_path)

    assert payload["evidence_source_sha"] == "staging-sha"
    assert payload["evidence_source"] == "STAGING_SANITIZED_SNAPSHOT"
    assert payload["provider_usage_curve_summary"] == {
        "source": "STAGING_EVIDENCE_SNAPSHOT",
        "status": "SANITIZED_SNAPSHOT",
        "provider_calls": 0,
        "daily_provider_calls": {"2026-07-07": 117},
        "hard_cap_per_day": 120,
    }


def test_r1_1_checkpoint_cli_outputs_json_and_zero_side_effect_flags(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_r1_1_checkpoint_dry_run.py",
            "--runtime-root",
            str(tmp_path),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["lock_writes"] == 0
    assert payload["settlement_writes"] == 0


def test_r1_1_checkpoint_cli_accepts_sanitized_evidence_snapshot_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [_capture("fixture-1", "2026-07-07T00:00:00Z", "FITTED_CALIBRATED")],
    )
    (tmp_path / "evidence_snapshot.json").write_text(
        json.dumps({"source_sha": "staging-source"}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_r1_1_checkpoint_dry_run.py",
            "--evidence-snapshot-root",
            str(tmp_path),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["evidence_source"] == "STAGING_SANITIZED_SNAPSHOT"
    assert payload["evidence_source_sha"] == "staging-source"


def test_r1_1_checkpoint_has_no_stage16_surface(tmp_path: Path) -> None:
    payload = build_checkpoint_report(tmp_path)

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "Stage 16" not in serialized
    assert "stage16" not in serialized.lower()


def _capture(
    fixture_id: str,
    captured_at: str,
    model_family: str,
) -> dict[str, object]:
    divergence: dict[str, object] = {
        "model_family": model_family,
        "model_fair_line": "-1.25",
        "market_line": "-1",
    }
    if model_family == "R4_1_CALIBRATED":
        divergence.update(
            {
                "artifact_hash": f"artifact-{fixture_id}",
                "artifact_version": "v1",
                "train_cutoff": "2025-12-08T20:00:00Z",
            }
        )
    return {
        "schema_version": "w2.forward_outcome_ledger.v2",
        "record_type": "capture",
        "captured_at": captured_at,
        "football_day": "2026-07-07",
        "environment": "staging",
        "fixture_id": fixture_id,
        "kickoff_utc": "2026-07-08T02:00:00Z",
        "competition_id": "chinese_super_league"
        if model_family == "R4_1_CALIBRATED"
        else "premier_league",
        "card_hash": fixture_id,
        "model_market_divergence": divergence,
        "shadow_pick": {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "market_line_at_capture": "-1",
            "not_a_recommendation": True,
            "not_displayed": True,
        },
        "current_odds": {
            "ah": {
                "home_line": "-1",
                "home_price": "1.90" if captured_at == "2026-07-07T00:00:00Z" else "2.00",
                "away_line": "+1",
                "away_price": "1.88",
            }
        },
    }


def _outcome(fixture_id: str, settlement_outcome: str, status: str) -> dict[str, object]:
    return {
        "schema_version": "w2.forward_outcome_ledger.v2",
        "record_type": "outcome",
        "football_day": "2026-07-07",
        "environment": "staging",
        "fixture_id": fixture_id,
        "settled_side": "shadow_pick",
        "settlement_outcome": settlement_outcome,
        "final_score": {"home": 1, "away": 0, "status": status},
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows),
        encoding="utf-8",
    )
