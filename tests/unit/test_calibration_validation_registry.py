from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any

import pytest

from w2.domain.calibration_validation_registry import (
    CalibrationValidationRegistryError,
    calibration_identity,
    lookup_calibration_verdict,
    register_calibration_validation,
    validate_calibration_ledger,
)
from w2.strategy.calibration import (
    CALIBRATION_VERSION,
    LambdaCalibrationParams,
    calibrate_lambdas,
)

SHA256_A = "a" * 64
SHA256_B = "b" * 64
CODE_REVISION = "c" * 40


def _registration(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    document = tmp_path / "docs/calibration-preregistration.md"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("frozen calibration protocol\n", encoding="utf-8")
    values: dict[str, Any] = {
        "calibration_version": CALIBRATION_VERSION,
        "params": LambdaCalibrationParams(),
        "preregistration_document_path": "docs/calibration-preregistration.md",
        "preregistration_document_sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
        "cohort_sha256": SHA256_A,
        "sample_size": 8659,
        "evaluation_window_start": "2023-08-01",
        "evaluation_window_end": "2026-07-31",
        "evaluated_at": "2026-08-29T12:00:00Z",
        "out_of_fold_metrics": {"log_loss": 0.91, "brier_score": 0.22},
        "code_revision": CODE_REVISION,
        "config_sha256": SHA256_B,
        "verdict": "PRODUCTION_VALIDATED",
        "granted_at": "2026-08-30T01:00:00Z",
        "granter": "owner@example.invalid",
        "ledger_path": tmp_path / "calibration_validation_ledger.jsonl",
        "repository_root": tmp_path,
    }
    values.update(overrides)
    return values


def _calibration_output() -> dict[str, Any]:
    return asdict(
        calibrate_lambdas(
            home_xg_for=1.7,
            home_xg_against=1.1,
            away_xg_for=1.3,
            away_xg_against=1.5,
            home_elo=1610.0,
            away_elo=1540.0,
            home_squad_value_eur=250_000_000.0,
            away_squad_value_eur=175_000_000.0,
            lineup_strength_adjustment=0.25,
            lineup_ah_adjustment=0.1,
            lineup_totals_adjustment=-0.2,
            lineup_ah_evidence_enabled=True,
            lineup_totals_evidence_enabled=True,
        )
    )


def test_empty_ledger_uses_totals_axis_candidate_without_grant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import w2.domain.calibration_validation_registry as registry

    monkeypatch.setattr(registry, "DEFAULT_LEDGER_PATH", tmp_path / "empty.jsonl")
    assert _calibration_output() == {
        "calibration_status": "BASELINE_PRIOR",
        "calibration_version": "w2.formal.lambda_totals_axis.v2",
        "input_weights": {
            "elo": 0.28,
            "lineup_ah_enabled": 1.0,
            "lineup_totals_enabled": 1.0,
            "lineups": 0.08,
            "squad_value": 0.18,
            "xg": 1.0,
        },
        "lambda_away": 0.858046,
        "lambda_home": 1.791247,
        "params": {
            "applied_home_advantage_goals": 0.3,
            "dixon_coles_rho": 0.0,
            "elo_gap_weight": 0.28,
            "home_advantage_goals": 0.3,
            "lineup_adjustment_weight": 0.08,
            "lineup_ah_delta_cap": 0.25,
            "lineup_totals_delta_cap": 0.3,
            "maximum_lambda": 4.25,
            "maximum_total_goals": 4.4,
            "minimum_lambda": 0.15,
            "minimum_total_goals": 1.35,
            "squad_value_log_weight": 0.18,
            "total_goals_intercept": 0.885958,
            "total_goals_scale": 0.701191,
        },
    }


def test_totals_axis_changes_total_but_preserves_unclamped_home_away_delta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import w2.domain.calibration_validation_registry as registry

    monkeypatch.setattr(registry, "DEFAULT_LEDGER_PATH", tmp_path / "empty.jsonl")
    output = calibrate_lambdas(
        home_xg_for=1.7,
        home_xg_against=1.1,
        away_xg_for=1.3,
        away_xg_against=1.5,
        home_elo=None,
        away_elo=None,
        home_squad_value_eur=None,
        away_squad_value_eur=None,
    )
    expected_total = 0.885958 + 0.701191 * 2.8
    assert output.lambda_home + output.lambda_away == pytest.approx(expected_total, abs=1e-6)
    expected_delta = ((1.7 + 1.5) / 2.0) - ((1.3 + 1.1) / 2.0) + 0.30
    assert output.lambda_home - output.lambda_away == pytest.approx(expected_delta, abs=1e-6)


def test_shipped_home_advantage_grant_does_not_authorize_totals_axis_identity() -> None:
    previous_params = {
        "home_advantage_goals": 0.30,
        "elo_gap_weight": 0.28,
        "squad_value_log_weight": 0.18,
        "lineup_adjustment_weight": 0.08,
        "dixon_coles_rho": 0.0,
        "minimum_lambda": 0.15,
        "maximum_lambda": 4.25,
        "minimum_total_goals": 1.35,
        "maximum_total_goals": 4.40,
    }
    assert (
        calibration_identity(
            calibration_version="w2.formal.lambda_baseline_prior.v1", params=previous_params
        )
        == "21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71"
    )
    assert (
        calibration_identity(
            calibration_version=CALIBRATION_VERSION, params=LambdaCalibrationParams()
        )
        == "f98d4ef0c2b158a80eeba60ca979250736831583612ad126b6ae9010262dbc91"
    )
    assert (
        lookup_calibration_verdict(
            calibration_version=CALIBRATION_VERSION, params=LambdaCalibrationParams()
        )
        is None
    )


def test_registered_identity_matches_and_every_parameter_change_misses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import w2.domain.calibration_validation_registry as registry

    values = _registration(tmp_path)
    record = register_calibration_validation(**values)
    ledger_path = values["ledger_path"]
    params = values["params"]
    assert record["params"] == asdict(params)
    assert record["calibration_identity"] == calibration_identity(
        calibration_version=CALIBRATION_VERSION, params=params
    )
    assert (
        lookup_calibration_verdict(
            calibration_version=CALIBRATION_VERSION,
            params=params,
            ledger_path=ledger_path,
        )
        == "PRODUCTION_VALIDATED"
    )
    assert validate_calibration_ledger(ledger_path=ledger_path, repository_root=tmp_path) == 1
    previous_params = replace(params, home_advantage_goals=0.12)
    assert (
        lookup_calibration_verdict(
            calibration_version=CALIBRATION_VERSION,
            params=previous_params,
            ledger_path=ledger_path,
        )
        is None
    )
    for field in fields(LambdaCalibrationParams):
        changed = replace(params, **{field.name: getattr(params, field.name) + 0.1})
        assert (
            lookup_calibration_verdict(
                calibration_version=CALIBRATION_VERSION,
                params=changed,
                ledger_path=ledger_path,
            )
            is None
        ), field.name
    assert (
        lookup_calibration_verdict(
            calibration_version=f"{CALIBRATION_VERSION}.changed",
            params=params,
            ledger_path=ledger_path,
        )
        is None
    )
    expanded_snapshot = {**asdict(params), "future_numeric_field": 0.1}
    assert (
        calibration_identity(calibration_version=CALIBRATION_VERSION, params=expanded_snapshot)
        != record["calibration_identity"]
    )
    monkeypatch.setattr(registry, "DEFAULT_LEDGER_PATH", ledger_path)
    assert _calibration_output()["calibration_status"] == "PRODUCTION_VALIDATED"


@pytest.mark.parametrize("verdict", ["READY", "BASELINE_PRIOR", ""])
def test_non_validation_verdict_is_rejected_without_writing(tmp_path: Path, verdict: str) -> None:
    values = _registration(tmp_path, verdict=verdict)
    with pytest.raises(CalibrationValidationRegistryError, match="verdict"):
        register_calibration_validation(**values)
    assert not values["ledger_path"].exists()


@pytest.mark.parametrize("verdict", ["REVOKED", "WITHDRAWN", "INVALIDATED", "PRODUCTION_REVOKED"])
def test_revocation_verdict_is_rejected_without_writing(tmp_path: Path, verdict: str) -> None:
    values = _registration(tmp_path, verdict=verdict)
    with pytest.raises(CalibrationValidationRegistryError, match="verdict"):
        register_calibration_validation(**values)
    assert not values["ledger_path"].exists()


def test_each_required_evidence_field_is_rejected_without_writing(tmp_path: Path) -> None:
    required = {
        "calibration_version",
        "params",
        "preregistration_document_path",
        "preregistration_document_sha256",
        "cohort_sha256",
        "sample_size",
        "evaluation_window_start",
        "evaluation_window_end",
        "evaluated_at",
        "out_of_fold_metrics",
        "code_revision",
        "config_sha256",
        "verdict",
        "granted_at",
        "granter",
    }
    for missing in required:
        case = tmp_path / missing
        values = _registration(case)
        ledger_path = values["ledger_path"]
        del values[missing]
        with pytest.raises(TypeError):
            register_calibration_validation(**values)
        assert not ledger_path.exists(), missing


def test_preregistration_content_digest_mismatch_is_rejected_without_writing(
    tmp_path: Path,
) -> None:
    values = _registration(tmp_path, preregistration_document_sha256=SHA256_A)
    with pytest.raises(CalibrationValidationRegistryError, match="digest mismatch"):
        register_calibration_validation(**values)
    assert not values["ledger_path"].exists()


def test_registration_only_appends_and_preserves_existing_record(tmp_path: Path) -> None:
    first_values = _registration(tmp_path)
    first = register_calibration_validation(**first_values)
    ledger_path = first_values["ledger_path"]
    first_bytes = ledger_path.read_bytes()
    register_calibration_validation(
        **_registration(
            tmp_path,
            verdict="APPROVED_VALIDATED",
            granted_at="2026-08-30T02:00:00Z",
            granter="second-owner@example.invalid",
        )
    )
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert ledger_path.read_bytes().startswith(first_bytes)
    assert rows[0] == first
    assert len(rows) == 2


def test_repository_ledger_record_count_and_evidence_are_valid() -> None:
    import w2.domain.calibration_validation_registry as registry

    ledger_lines = [
        line
        for line in registry.DEFAULT_LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert validate_calibration_ledger() == len(ledger_lines)


def test_default_ledger_validation_requires_source_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import w2.domain.calibration_validation_registry as registry

    monkeypatch.setattr(registry, "DEFAULT_REPOSITORY_ROOT", tmp_path)
    with pytest.raises(CalibrationValidationRegistryError, match="source checkout or CI"):
        validate_calibration_ledger()


def test_params_and_verdict_have_no_environment_or_config_injection_surface() -> None:
    parameter_names = {field.name for field in fields(LambdaCalibrationParams)}
    forbidden_config_values = parameter_names | {
        "CALIBRATION_STATUS",
        "APPROVED_VALIDATED",
        "PRODUCTION_VALIDATED",
    }
    config_files = [
        path
        for root in (Path("config"), Path("infra"))
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".env", ".json", ".toml", ".yaml", ".yml"}
    ]
    hits = sorted(
        f"{path}:{token}"
        for path in config_files
        for token in forbidden_config_values
        if token in path.read_text(encoding="utf-8", errors="ignore")
    )
    assert hits == []

    source_paths = (
        Path("src/w2/strategy/calibration.py"),
        Path("src/w2/domain/calibration_validation_registry.py"),
    )
    environment_reads = []
    forbidden_imports = []
    for path in source_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
                environment_reads.append(f"{path}:{node.attr}")
            if isinstance(node, ast.ImportFrom) and node.module in {
                "w2.config",
                "pydantic_settings",
            }:
                forbidden_imports.append(f"{path}:{node.module}")
    assert environment_reads == []
    assert forbidden_imports == []
