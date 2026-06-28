from __future__ import annotations

from datetime import UTC, datetime

from w2.calibration.handicap import HandicapCalibrationInput, build_handicap_calibration

NOW = datetime(2026, 6, 28, tzinfo=UTC)


def rows(count: int) -> list[dict[str, float]]:
    return [
        {
            "score_delta": float(index % 5) / 5,
            "fair_ah": -0.5,
            "market_ah": -0.25,
        }
        for index in range(count)
    ]


def test_samples_zero_and_199_remain_unvalidated() -> None:
    zero = build_handicap_calibration(
        HandicapCalibrationInput(
            sample_size=0,
            all_validation_checks_passed=False,
            included_rows=[],
            generated_at=NOW,
        )
    )
    one_ninety_nine = build_handicap_calibration(
        HandicapCalibrationInput(
            sample_size=199,
            all_validation_checks_passed=True,
            included_rows=rows(199),
            generated_at=NOW,
        )
    )

    assert zero["calibration_version"] == "UNVALIDATED"
    assert zero["status"] == "INSUFFICIENT_SAMPLE"
    assert one_ninety_nine["calibration_version"] == "UNVALIDATED"
    assert one_ninety_nine["status"] == "INSUFFICIENT_SAMPLE"


def test_samples_200_but_holdout_failed_remains_unvalidated() -> None:
    payload = build_handicap_calibration(
        HandicapCalibrationInput(
            sample_size=200,
            all_validation_checks_passed=False,
            included_rows=rows(200),
            generated_at=NOW,
        )
    )

    assert payload["calibration_version"] == "UNVALIDATED"
    assert payload["status"] == "VALIDATION_GATE_FAILED"


def test_samples_200_all_checks_pass_generate_candidate_not_runtime_enabled() -> None:
    payload = build_handicap_calibration(
        HandicapCalibrationInput(
            sample_size=200,
            all_validation_checks_passed=True,
            included_rows=rows(200),
            generated_at=NOW,
        )
    )

    assert str(payload["calibration_version"]).startswith("AH_CALIBRATION_CANDIDATE_")
    assert payload["status"] == "CANDIDATE_NOT_RUNTIME_ENABLED"
    assert payload["runtime_enabled"] is False
    assert payload["formal_enabled"] is False
    assert payload["candidate_enabled"] is False
    assert payload["beats_market"] is False
