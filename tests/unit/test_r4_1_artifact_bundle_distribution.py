from __future__ import annotations

import json
import subprocess
import tarfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import scripts.build_w2_r4_1_artifact_bundle as builder
import scripts.verify_w2_r4_1_artifact_bundle as verifier

from w2.models.r4_1_artifacts import build_r4_1_artifact_payload


def test_build_bundle_manifest_and_verify_pass(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(builder, "publish_artifacts", _fake_publish_artifacts)

    report = builder.build_artifact_bundle(
        tmp_path,
        git_sha="abc123",
        created_at=datetime(2026, 7, 8, 0, 0, tzinfo=UTC),
    )

    assert report["status"] == "PASS"
    assert report["provider_calls"] == 0
    manifest = report["manifest"]
    assert manifest["git_sha"] == "abc123"
    assert manifest["canonical_pricing_shadow_key"] == "pricing_shadow.r4_1_calibrated"
    assert manifest["competition_ids"] == [
        "bundesliga",
        "chinese_super_league",
        "allsvenskan",
    ]
    assert "brasileirao_serie_a" not in manifest["competition_ids"]
    assert manifest["disabled_competitions"] == ["brasileirao_serie_a"]
    assert set(manifest["artifact_hashes"]) == set(manifest["competition_ids"])
    assert set(manifest["train_cutoff"]) == set(manifest["competition_ids"])
    assert set(manifest["protocol_identity_status"]) == set(manifest["competition_ids"])

    verify = verifier.verify_artifact_bundle(Path(report["bundle_path"]))

    assert verify["status"] == "PASS"
    assert verify["provider_calls"] == 0
    assert verify["artifact_count"] == 3
    assert verify["blockers"] == []


def test_verify_bundle_fails_on_corrupted_hash(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(builder, "publish_artifacts", _fake_publish_artifacts)
    report = builder.build_artifact_bundle(tmp_path, git_sha="abc123")
    corrupted = tmp_path / "corrupted.tar.gz"

    _rewrite_bundle(
        source=Path(report["bundle_path"]),
        target=corrupted,
        transform_artifact=lambda payload: {**payload, "temperature": 9.9},
    )

    verify = verifier.verify_artifact_bundle(corrupted)

    assert verify["status"] == "FAIL"
    assert "ARTIFACT_HASH_MISMATCH:bundesliga" in verify["blockers"]
    assert "ARTIFACT_PAYLOAD_HASH_MISMATCH:bundesliga" in verify["blockers"]


def test_verify_bundle_fails_on_missing_artifact(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(builder, "publish_artifacts", _fake_publish_artifacts)
    report = builder.build_artifact_bundle(tmp_path, git_sha="abc123")
    missing = tmp_path / "missing.tar.gz"

    _rewrite_bundle(
        source=Path(report["bundle_path"]),
        target=missing,
        drop_name="artifacts/allsvenskan.v1.json",
    )

    verify = verifier.verify_artifact_bundle(missing)

    assert verify["status"] == "FAIL"
    assert "MISSING_ARTIFACT:allsvenskan" in verify["blockers"]


def test_bundle_builder_does_not_track_runtime_artifacts() -> None:
    output = subprocess.check_output(
        ["git", "ls-files", "runtime/model_artifacts"],
        text=True,
    )
    assert output.strip() == ""


def _fake_publish_artifacts(out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for competition_id in ("bundesliga", "chinese_super_league", "allsvenskan"):
        payload = build_r4_1_artifact_payload(
            competition_id=competition_id,
            coefficients=(0.1, 0.2, -0.03),
            feature_names=("intercept", "home_field", "dixon_coles_rho"),
            temperature=0.96,
            rho=-0.03,
            train_cutoff_utc=datetime(2025, 12, 8, 20, 0, tzinfo=UTC),
            fit_sample_count=300,
            protocol_identity_check="PASS",
        )
        path = out_dir / f"{competition_id}.v1.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifacts.append(
            {
                "competition_id": competition_id,
                "artifact_path": path.as_posix(),
                "artifact_hash": payload["artifact_hash"],
                "fit_sample_count": payload["fit_sample_count"],
                "train_cutoff_utc": payload["train_cutoff_utc"],
                "protocol_identity_check": payload["protocol_identity_check"],
            }
        )
    return {
        "status": "PASS",
        "provider_calls": 0,
        "target_competitions": ["bundesliga", "chinese_super_league", "allsvenskan"],
        "disabled_competitions": ["brasileirao_serie_a"],
        "protocol_identity": [{"name": "test", "status": "PASS"}],
        "artifacts": artifacts,
    }


def _rewrite_bundle(
    *,
    source: Path,
    target: Path,
    transform_artifact: Any | None = None,
    drop_name: str | None = None,
) -> None:
    with tarfile.open(source, "r:gz") as src, tarfile.open(target, "w:gz") as dst:
        for member in src.getmembers():
            if member.name == drop_name:
                continue
            extracted = src.extractfile(member)
            if extracted is None:
                continue
            data = extracted.read()
            if member.name == "artifacts/bundesliga.v1.json" and transform_artifact:
                payload = json.loads(data.decode("utf-8"))
                data = (
                    json.dumps(
                        transform_artifact(payload),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
            info = tarfile.TarInfo(member.name)
            info.size = len(data)
            info.mode = member.mode
            dst.addfile(info, fileobj=BytesIO(data))
