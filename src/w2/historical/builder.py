from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.historical.adapters import JsonAdapter
from w2.historical.dataset import (
    AsOfSample,
    DatasetArtifact,
    DatasetVersion,
    sha256_text,
    stable_json,
)


@dataclass(frozen=True, kw_only=True)
class BuildResult:
    version: DatasetVersion
    artifacts: tuple[DatasetArtifact, ...]
    manifest: dict[str, Any]
    duplicate_keys: tuple[tuple[str, str, str], ...]


class DatasetManifestBuilder:
    def build(
        self,
        *,
        dataset_id: str,
        version: str,
        artifacts: list[DatasetArtifact],
        samples: list[AsOfSample],
    ) -> dict[str, Any]:
        return {
            "dataset_id": dataset_id,
            "version": version,
            "sample_count": len(samples),
            "fixture_count": len({sample.fixture_id for sample in samples}),
            "created_at": datetime.now(UTC).isoformat(),
            "artifacts": [artifact.__dict__ for artifact in artifacts],
            "sample_order": [sample.identity_key() for sample in samples],
        }


class AsOfDatasetBuilder:
    def __init__(
        self, output_root: Path, provider_mapping_hook: dict[str, str] | None = None
    ) -> None:
        self.output_root = output_root
        self.provider_mapping_hook = provider_mapping_hook or {}
        self.json = JsonAdapter()

    def detect_duplicates(self, samples: list[AsOfSample]) -> tuple[tuple[str, str, str], ...]:
        seen: set[tuple[str, str, str]] = set()
        duplicates: list[tuple[str, str, str]] = []
        for sample in samples:
            key = sample.identity_key()
            if key in seen:
                duplicates.append(key)
            seen.add(key)
        return tuple(duplicates)

    def build(
        self, *, dataset_id: str, version: str, samples: list[AsOfSample], incremental: bool = True
    ) -> BuildResult:
        ordered = sorted(
            samples, key=lambda sample: (sample.kickoff_utc, sample.fixture_id, sample.as_of_time)
        )
        duplicates = self.detect_duplicates(ordered)
        if duplicates:
            raise ValueError(f"duplicate as-of samples: {duplicates}")
        dataset_dir = self.output_root / dataset_id / version
        feature_rows = [sample.feature_payload() for sample in ordered]
        label_rows = [sample.label_payload() for sample in ordered]
        feature_path = dataset_dir / "features.jsonl"
        label_path = dataset_dir / "labels.jsonl"
        manifest_path = dataset_dir / "manifest.json"
        if not incremental or not manifest_path.exists():
            self.json.write(feature_path, feature_rows)
            self.json.write(label_path, label_rows)
        artifacts = [
            DatasetArtifact(
                artifact_id="features",
                dataset_id=dataset_id,
                version=version,
                path=str(feature_path),
                media_type="application/x-jsonlines",
                sha256=sha256_text(feature_path.read_text(encoding="utf-8")),
                row_count=len(feature_rows),
            ),
            DatasetArtifact(
                artifact_id="labels",
                dataset_id=dataset_id,
                version=version,
                path=str(label_path),
                media_type="application/x-jsonlines",
                sha256=sha256_text(label_path.read_text(encoding="utf-8")),
                row_count=len(label_rows),
            ),
        ]
        manifest = DatasetManifestBuilder().build(
            dataset_id=dataset_id, version=version, artifacts=artifacts, samples=ordered
        )
        manifest_sha = sha256_text(stable_json(manifest))
        dataset_version = DatasetVersion(
            dataset_id=dataset_id,
            version=version,
            created_at=datetime.now(UTC),
            source_ids=tuple(
                sorted({str(sample.provenance.get("source_id", "unknown")) for sample in ordered})
            ),
            manifest_sha256=manifest_sha,
        )
        manifest["manifest_sha256"] = manifest_sha
        manifest_path.write_text(stable_json(manifest) + "\n", encoding="utf-8")
        return BuildResult(
            version=dataset_version,
            artifacts=tuple(artifacts),
            manifest=manifest,
            duplicate_keys=(),
        )
