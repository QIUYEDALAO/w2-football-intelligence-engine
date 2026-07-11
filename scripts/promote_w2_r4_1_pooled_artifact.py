#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from w2.models.r4_1_artifacts import (  # noqa: E402
    build_r4_1_artifact_payload,
    parse_r4_1_artifact,
)


def promote_pooled_artifact(
    *,
    source_path: Path,
    target_competition: str,
    output_dir: Path,
) -> dict[str, object]:
    source_payload = json.loads(source_path.read_text(encoding="utf-8"))
    source = parse_r4_1_artifact(source_payload)
    target_home_key = f"home_field__{target_competition}"
    if source.protocol_identity_check != "PASS":
        raise ValueError("source artifact protocol identity is not approved")
    if target_home_key not in source.feature_names:
        raise ValueError(f"source artifact does not model {target_competition}")
    payload = build_r4_1_artifact_payload(
        competition_id=target_competition,
        coefficients=source.coefficients,
        feature_names=source.feature_names,
        temperature=source.temperature,
        rho=source.rho,
        train_cutoff_utc=source.train_cutoff_utc,
        fit_sample_count=source.fit_sample_count,
        protocol_identity_check=source.protocol_identity_check,
        artifact_version=source.artifact_version,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{target_competition}.{source.artifact_version}.json"
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if existing != payload:
            raise ValueError("refusing to overwrite a different existing artifact")
    else:
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    promoted = parse_r4_1_artifact(payload)
    return {
        "status": "PASS",
        "provider_calls": 0,
        "source_competition": source.competition_id,
        "target_competition": promoted.competition_id,
        "artifact_path": output_path.as_posix(),
        "artifact_hash": promoted.artifact_hash,
        "artifact_version": promoted.artifact_version,
        "train_cutoff_utc": promoted.train_cutoff_utc.isoformat(),
        "fit_sample_count": promoted.fit_sample_count,
        "protocol_identity_check": promoted.protocol_identity_check,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote an approved pooled R4.1 artifact to another modeled league."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target-competition", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = promote_pooled_artifact(
        source_path=args.source,
        target_competition=args.target_competition,
        output_dir=args.output_dir,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(report["artifact_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
