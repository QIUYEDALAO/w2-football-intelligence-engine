"""AH/OU v3 cohort 预注册单测（S4/R3）。"""
from __future__ import annotations

from datetime import UTC, datetime

from w2.strategy.ah_ou_cohort import build_cohort_identity, preregister_cohort

DECISION_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


def _kwargs(**overrides) -> dict:
    base = dict(
        fixture_id="FIX1",
        decision_at=DECISION_AT,
        home_team_id="H",
        away_team_id="A",
        model_version="m1",
        ah_capture_id="cap-ah",
        ou_capture_id="cap-ou",
    )
    base.update(overrides)
    return base


def test_cohort_identity_is_deterministic() -> None:
    kwargs = _kwargs()
    assert build_cohort_identity(**kwargs) == build_cohort_identity(**kwargs)


def test_cohort_identity_covers_real_team_ids_and_both_captures() -> None:
    base = _kwargs()
    changed_home = build_cohort_identity(**_kwargs(home_team_id="H2"))
    changed_ah_capture = build_cohort_identity(**_kwargs(ah_capture_id="cap-ah2"))
    changed_ou_capture = build_cohort_identity(**_kwargs(ou_capture_id="cap-ou2"))
    changed_model = build_cohort_identity(**_kwargs(model_version="m2"))
    assert len(
        {
            build_cohort_identity(**base),
            changed_home,
            changed_ah_capture,
            changed_ou_capture,
            changed_model,
        }
    ) == 5


def test_preregister_payload_is_idempotent_and_complete() -> None:
    payload = preregister_cohort(
        fixture_id="FIX1",
        decision_at=DECISION_AT,
        home_team_id="H",
        away_team_id="A",
        model_version="m1",
        calibration_version="w2.ah_ou.softmax.calibrated.v3",
        ah_capture_id="cap-ah",
        ah_source_capture_sha256="s1" * 32,
        ou_capture_id="cap-ou",
        ou_source_capture_sha256="s2" * 32,
        frozen_identity="f" * 64,
    )
    assert payload["home_team_id"] == "H"
    assert payload["away_team_id"] == "A"
    assert payload["ah_capture_id"] == "cap-ah"
    assert payload["ou_capture_id"] == "cap-ou"
    assert payload["model_version"] == "m1"
    assert payload["frozen_identity"] == "f" * 64
    again = preregister_cohort(
        fixture_id="FIX1",
        decision_at=DECISION_AT,
        home_team_id="H",
        away_team_id="A",
        model_version="m1",
        calibration_version="w2.ah_ou.softmax.calibrated.v3",
        ah_capture_id="cap-ah",
        ah_source_capture_sha256="s1" * 32,
        ou_capture_id="cap-ou",
        ou_source_capture_sha256="s2" * 32,
        frozen_identity="f" * 64,
    )
    assert again["cohort_id"] == payload["cohort_id"]
