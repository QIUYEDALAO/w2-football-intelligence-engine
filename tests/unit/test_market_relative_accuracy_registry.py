from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from w2.domain.market_relative_accuracy_registry import (
    MarketRelativeAccuracyRegistryError,
    admission_identity,
    lookup_market_relative_accuracy_verdict,
    register_market_relative_accuracy,
    validate_market_relative_accuracy_ledger,
)


def _values(tmp_path: Path, **overrides: object) -> dict[str, object]:
    doc = tmp_path / "docs/prereg.json"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("{}\n", encoding="utf-8")
    values: dict[str, object] = {
        "model_identity": "model-v1",
        "calibration_identity": "a" * 64,
        "market": "ASIAN_HANDICAP",
        "evaluation_policy_version": "candidate-eval.v2",
        "economic_admission_contract_version": "w2.economic_admission.cashflow.v1",
        "scoring_contract_version": "w2.market_relative_accuracy.scalar_settlement_brier.v1",
        "preregistration_document_path": "docs/prereg.json",
        "preregistration_document_sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
        "cohort_sha256": "b" * 64,
        "sample_size": 1500,
        "fixture_count": 1500,
        "evaluation_window_start": "2026-09-01T00:00:00Z",
        "evaluation_window_end": "2029-06-01T00:00:00Z",
        "metrics": {
            "model_minus_market_brier": -0.02,
            "one_sided_95pct_upper_bound": -0.001,
            "all_market_one_sided_95pct_upper_bounds": {
                "ASIAN_HANDICAP": -0.001,
                "TOTALS": -0.002,
            },
            "all_market_fixture_counts": {"ASIAN_HANDICAP": 1500, "TOTALS": 1500},
        },
        "code_revision": "c" * 40,
        "config_sha256": "d" * 64,
        "verdict": "MARKET_RELATIVE_ACCURACY_VALIDATED",
        "evaluated_at": "2027-06-01T00:00:00Z",
        "granted_at": "2027-06-02T00:00:00Z",
        "granter": "owner@example.invalid",
        "ledger_path": tmp_path / "market.jsonl",
        "repository_root": tmp_path,
    }
    values.update(overrides)
    return values


def test_empty_shipped_ledger_is_valid_and_has_no_grants() -> None:
    from w2.domain.market_relative_accuracy_registry import DEFAULT_LEDGER_PATH

    assert validate_market_relative_accuracy_ledger() == len(
        [line for line in DEFAULT_LEDGER_PATH.read_text(encoding="utf-8").splitlines() if line]
    ) == 0


def test_registration_is_exact_identity_bound_and_append_only(tmp_path: Path) -> None:
    values = _values(tmp_path)
    record = register_market_relative_accuracy(**values)  # type: ignore[arg-type]
    assert (
        lookup_market_relative_accuracy_verdict(
            **{
                k: values[k]
                for k in (
                    "model_identity",
                    "calibration_identity",
                    "market",
                    "evaluation_policy_version",
                    "economic_admission_contract_version",
                    "scoring_contract_version",
                )
            },
            ledger_path=values["ledger_path"],
        )
        == "MARKET_RELATIVE_ACCURACY_VALIDATED"
    )
    assert record["admission_identity"] == admission_identity(
        model_identity="model-v1",
        calibration_identity="a" * 64,
        market="ASIAN_HANDICAP",
        evaluation_policy_version="candidate-eval.v2",
        economic_admission_contract_version="w2.economic_admission.cashflow.v1",
        scoring_contract_version="w2.market_relative_accuracy.scalar_settlement_brier.v1",
    )
    assert (
        lookup_market_relative_accuracy_verdict(
            model_identity="model-v1",
            calibration_identity="e" * 64,
            market="ASIAN_HANDICAP",
            evaluation_policy_version="candidate-eval.v2",
            economic_admission_contract_version="w2.economic_admission.cashflow.v1",
            scoring_contract_version="w2.market_relative_accuracy.scalar_settlement_brier.v1",
            ledger_path=values["ledger_path"],  # type: ignore[arg-type]
        )
        is None
    )
    before = values["ledger_path"].read_bytes()  # type: ignore[union-attr]
    register_market_relative_accuracy(
        **_values(tmp_path, market="TOTALS", granted_at="2027-06-03T00:00:00Z")  # type: ignore[arg-type]
    )
    assert values["ledger_path"].read_bytes().startswith(before)  # type: ignore[union-attr]
    assert (
        validate_market_relative_accuracy_ledger(
            ledger_path=values["ledger_path"],
            repository_root=tmp_path,  # type: ignore[arg-type]
        )
        == 2
    )


def test_same_admission_identity_cannot_be_registered_twice(tmp_path: Path) -> None:
    values = _values(tmp_path)
    register_market_relative_accuracy(**values)  # type: ignore[arg-type]
    before = values["ledger_path"].read_bytes()  # type: ignore[union-attr]

    with pytest.raises(MarketRelativeAccuracyRegistryError, match="immutable grant"):
        register_market_relative_accuracy(**values)  # type: ignore[arg-type]
    assert values["ledger_path"].read_bytes() == before  # type: ignore[union-attr]


def test_committed_ledger_validation_rejects_duplicate_identity(tmp_path: Path) -> None:
    values = _values(tmp_path)
    register_market_relative_accuracy(**values)  # type: ignore[arg-type]
    ledger_path = values["ledger_path"]
    ledger_path.write_bytes(ledger_path.read_bytes() * 2)  # type: ignore[union-attr]

    with pytest.raises(MarketRelativeAccuracyRegistryError, match="duplicate"):
        validate_market_relative_accuracy_ledger(
            ledger_path=ledger_path,  # type: ignore[arg-type]
            repository_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evaluation_policy_version", "candidate-eval.v1"),
        ("economic_admission_contract_version", "w2.economic_admission.delta.v1"),
        ("scoring_contract_version", "w2.market_relative_accuracy.unknown.v1"),
    ],
)
def test_only_preregistered_contract_identities_are_accepted(
    tmp_path: Path, field: str, value: str
) -> None:
    with pytest.raises(MarketRelativeAccuracyRegistryError, match="not preregistered"):
        register_market_relative_accuracy(
            **_values(tmp_path, **{field: value})  # type: ignore[arg-type]
        )
    assert not (tmp_path / "market.jsonl").exists()


@pytest.mark.parametrize(
    "metrics",
    [
        {"model_minus_market_brier": 0.01, "one_sided_95pct_upper_bound": 0.01},
        {"model_minus_market_brier": -0.01, "one_sided_95pct_upper_bound": -0.01},
    ],
)
def test_grant_requires_both_market_results_and_passing_upper_bounds(
    tmp_path: Path, metrics: dict[str, float]
) -> None:
    with pytest.raises(MarketRelativeAccuracyRegistryError):
        register_market_relative_accuracy(
            **_values(tmp_path, metrics=metrics)  # type: ignore[arg-type]
        )
    assert not (tmp_path / "market.jsonl").exists()


@pytest.mark.parametrize("verdict", ["", "REVOKED", "APPROVED_VALIDATED"])
def test_only_forward_validation_verdict_is_accepted(tmp_path: Path, verdict: str) -> None:
    with pytest.raises(MarketRelativeAccuracyRegistryError, match="verdict"):
        register_market_relative_accuracy(
            **_values(tmp_path, verdict=verdict)  # type: ignore[arg-type]
        )
    assert not (tmp_path / "market.jsonl").exists()
