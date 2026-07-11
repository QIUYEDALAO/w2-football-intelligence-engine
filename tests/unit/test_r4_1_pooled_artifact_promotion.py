from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.promote_w2_r4_1_pooled_artifact import promote_pooled_artifact

from w2.models.r4_1_artifacts import build_r4_1_artifact_payload, parse_r4_1_artifact


def _source(path: Path, *, protocol_status: str = "PASS") -> Path:
    payload = build_r4_1_artifact_payload(
        competition_id="allsvenskan",
        coefficients=(0.1, 0.2, 0.03),
        feature_names=("intercept", "home_field", "home_field__eliteserien"),
        temperature=0.92,
        rho=-0.03,
        train_cutoff_utc=datetime(2025, 12, 8, 20, 0, tzinfo=UTC),
        fit_sample_count=3264,
        protocol_identity_check=protocol_status,
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_promotes_approved_pooled_artifact_without_changing_model_provenance(
    tmp_path: Path,
) -> None:
    source_path = _source(tmp_path / "allsvenskan.v1.json")

    report = promote_pooled_artifact(
        source_path=source_path,
        target_competition="eliteserien",
        output_dir=tmp_path / "out",
    )

    promoted = parse_r4_1_artifact(
        json.loads(Path(str(report["artifact_path"])).read_text(encoding="utf-8"))
    )
    source = parse_r4_1_artifact(json.loads(source_path.read_text(encoding="utf-8")))
    assert report["provider_calls"] == 0
    assert promoted.competition_id == "eliteserien"
    assert promoted.coefficients == source.coefficients
    assert promoted.temperature == source.temperature
    assert promoted.train_cutoff_utc == source.train_cutoff_utc
    assert promoted.fit_sample_count == source.fit_sample_count
    assert promoted.artifact_hash != source.artifact_hash


def test_rejects_unapproved_or_unmodeled_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="protocol identity"):
        promote_pooled_artifact(
            source_path=_source(tmp_path / "unapproved.json", protocol_status="FAIL"),
            target_competition="eliteserien",
            output_dir=tmp_path / "out",
        )

    with pytest.raises(ValueError, match="does not model"):
        promote_pooled_artifact(
            source_path=_source(tmp_path / "approved.json"),
            target_competition="eredivisie",
            output_dir=tmp_path / "out",
        )
