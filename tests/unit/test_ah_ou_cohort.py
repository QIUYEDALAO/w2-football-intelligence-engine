"""AH/OU v3 cohort 预注册单测（S4）。"""
from __future__ import annotations

from datetime import UTC, datetime

from w2.strategy.ah_ou_cohort import build_cohort_identity, preregister_cohort

DECISION_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


def test_cohort_identity_is_deterministic() -> None:
    kwargs = dict(
        fixture_id="FIX1",
        decision_at=DECISION_AT,
        home_team_id="H",
        away_team_id="A",
        model_version="m1",
        source_id="src-1",
        capture_id="cap-1",
    )
    assert build_cohort_identity(**kwargs) == build_cohort_identity(**kwargs)


def test_cohort_identity_covers_real_team_ids_and_capture() -> None:
    base = dict(
        fixture_id="FIX1",
        decision_at=DECISION_AT,
        home_team_id="H",
        away_team_id="A",
        model_version="m1",
        source_id="src-1",
        capture_id="cap-1",
    )
    changed_home = build_cohort_identity(**{**base, "home_team_id": "H2"})
    changed_capture = build_cohort_identity(**{**base, "capture_id": "cap-2"})
    changed_model = build_cohort_identity(**{**base, "model_version": "m2"})
    assert len({build_cohort_identity(**base), changed_home, changed_capture, changed_model}) == 4


def test_preregister_payload_is_idempotent_and_complete() -> None:
    payload = preregister_cohort(
        fixture_id="FIX1",
        decision_at=DECISION_AT,
        home_team_id="H",
        away_team_id="A",
        model_version="m1",
        source_id="src-1",
        capture_id="cap-1",
        quote_identity_hash="q1",
        source_capture_sha256="s1" * 32,
    )
    assert payload["home_team_id"] == "H"
    assert payload["away_team_id"] == "A"
    assert payload["capture_id"] == "cap-1"
    assert payload["model_version"] == "m1"
    assert payload["source_id"] == "src-1"
    again = preregister_cohort(
        fixture_id="FIX1",
        decision_at=DECISION_AT,
        home_team_id="H",
        away_team_id="A",
        model_version="m1",
        source_id="src-1",
        capture_id="cap-1",
        quote_identity_hash="q1",
        source_capture_sha256="s1" * 32,
    )
    assert again["cohort_id"] == payload["cohort_id"]
