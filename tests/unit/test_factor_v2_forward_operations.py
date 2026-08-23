from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_forward_preregistration_is_frozen_before_collection() -> None:
    path = ROOT / "docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_20260822.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "cad4b549bc8a00d56ad29f1913bc8ebd582a21ee8524b86a4fb7e24480f936c1"
    )
    assert payload["owner_decision"] == "COLLECTION_APPROVED_INFLUENCE_FORBIDDEN"
    assert payload["historical_replay_cutoff"] == "2026-08-21T19:18:10.674088Z"
    assert payload["first_evaluation"]["evaluation_date_utc"] == ("2028-02-01T00:05:00Z")
    assert payload["first_evaluation"]["minimum_distinct_completed_paired_fixtures"] == 5500
    assert payload["first_evaluation"]["evaluate_exactly_once"] is True
    assert payload["first_evaluation"]["interim_metric_evaluations_allowed"] is False
    assert payload["first_evaluation"]["early_evaluation_allowed"] is False
    assert payload["first_evaluation"]["metrics"] == [
        "LOG_LOSS",
        "RPS",
        "MULTICLASS_BRIER",
        "TOP_LABEL_ECE_10_EQUAL_WIDTH_BINS",
    ]
    assert payload["first_evaluation"]["ece_bootstrap"] == {
        "required": True,
        "resamples": 5000,
        "confidence_level": 0.95,
        "interval": "PERCENTILE",
        "resampling_unit": "PAIRED_FIXTURE",
        "seed": 20280201,
        "report_for": [
            "B0_SAME_ENGINE_XG",
            "B2_FACTOR_V2",
            "PAIRED_DELTA_B2_MINUS_B0",
        ],
    }


def test_forward_collector_uses_independent_oneshot_container_and_timer() -> None:
    compose = (ROOT / "infra/compose/compose.staging.yml").read_text(encoding="utf-8")
    service = (ROOT / "infra/systemd/w2-factor-v2-forward-collector.service").read_text(
        encoding="utf-8"
    )
    timer = (ROOT / "infra/systemd/w2-factor-v2-forward-collector.timer").read_text(
        encoding="utf-8"
    )

    collector = compose.split("  factor-v2-forward-collector:", 1)[1].split("\n  api:", 1)[0]
    assert 'profiles: ["factor-v2"]' in collector
    assert "run_factor_v2_forward_collection.py" in collector
    assert "W2_API_FOOTBALL_API_KEY" not in collector
    assert "CELERY" not in collector
    assert "REDIS" not in collector
    assert "W2_GIT_SHA" in collector
    assert "W2_BUILD_TIME" in collector
    assert "W2_RELEASE_ID" in collector
    assert "factor-v2-forward-collector" in service
    assert " worker" not in service
    assert "OnCalendar=*-*-* *:05:00 UTC" in timer
    assert "Persistent=false" in timer


def test_writer_role_is_noninheriting_and_v2_only() -> None:
    migration = (ROOT / "migrations/versions/0070_factor_shadow_v2_gate0.py").read_text(
        encoding="utf-8"
    )

    assert "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE" in migration
    assert "GRANT SELECT ON ALL TABLES" not in migration
    assert "REVOKE SELECT, INSERT, UPDATE, DELETE, TRUNCATE" in migration
    assert "GRANT INSERT, SELECT ON {', '.join(V2_TABLES)}" in migration
